"""Build the policy table from the frozen OpenAPI contract.

Ref: RFC-001 R10.2, R14.1-R14.3.

The contract is the authority; the policy table is derived from it rather than
transcribed beside it. Hand-maintaining a parallel table is exactly how a
policy silently drifts from the contract it is supposed to enforce.
"""
from __future__ import annotations

import functools
import pathlib
from typing import Any

import yaml

from .policy import (
    CONTRACT_ROLE_EXCEPTIONS,
    PUBLIC_OPERATIONS,
    PolicyTable,
    RoutePolicy,
)
from .roles import Role

_METHODS = ("get", "put", "post", "delete", "patch", "options", "head", "trace")

#: The frozen contract, vendored unmodified. Never written to (R14.1).
CONTRACT_PATH = (
    pathlib.Path(__file__).resolve().parents[3]
    / "docs"
    / "handoff"
    / "05_API"
    / "openapi_v0.2.yaml"
)


class ContractError(RuntimeError):
    """The contract and the policy layer disagree. Fails at startup."""


def _operations(doc: dict[str, Any]):
    for path, item in doc.get("paths", {}).items():
        for method in _METHODS:
            if method in item:
                yield path, method, item[method]


@functools.cache
def load_contract(path: pathlib.Path | None = None) -> dict[str, Any]:
    return yaml.safe_load((path or CONTRACT_PATH).read_text(encoding="utf-8"))


def build_policy_table(path: pathlib.Path | None = None) -> PolicyTable:
    """Derive the policy table, and verify the contract's own consistency.

    Raises ContractError when the contract carries an operation this module has
    no rule for, so a contract change cannot land silently unenforced.
    """
    doc = load_contract(path)
    policies: dict[str, RoutePolicy] = {}
    unannotated: list[str] = []

    for route, method, op in _operations(doc):
        operation_id = op.get("operationId")
        if not operation_id:
            raise ContractError(f"{method.upper()} {route} has no operationId")

        is_public = op.get("security") == []
        declared = op.get("x-roles") or []

        if is_public:
            if operation_id not in PUBLIC_OPERATIONS:
                raise ContractError(
                    f"{operation_id} is unauthenticated in the contract but is "
                    "not in the closed list PUBLIC_OPERATIONS (RFC-001 R10.4)"
                )
            roles: frozenset[Role] = frozenset()
        elif declared:
            roles = frozenset(Role(r) for r in declared)
        elif operation_id in CONTRACT_ROLE_EXCEPTIONS:
            # R10.3a. Authenticated, no x-roles, ruled on explicitly.
            roles = CONTRACT_ROLE_EXCEPTIONS[operation_id]
        else:
            unannotated.append(f"{operation_id} ({method.upper()} {route})")
            continue

        policies[operation_id] = RoutePolicy(
            operation_id=operation_id,
            method=method.upper(),
            path=route,
            roles=roles,
            public=is_public,
            customer_scoped=route.startswith("/me/"),
        )

    if unannotated:
        raise ContractError(
            "authenticated operations with no x-roles and no explicit ruling: "
            + ", ".join(sorted(unannotated))
            + " — each needs a decision before it can be reachable"
        )

    # PUBLIC_OPERATIONS must not claim anything the contract does not.
    declared_public = {p.operation_id for p in policies.values() if p.public}
    if declared_public != PUBLIC_OPERATIONS:
        raise ContractError(
            "PUBLIC_OPERATIONS disagrees with the contract: "
            f"only in code {sorted(PUBLIC_OPERATIONS - declared_public)}, "
            f"only in contract {sorted(declared_public - PUBLIC_OPERATIONS)}"
        )

    # The exception list must stay minimal: every entry must really be an
    # authenticated operation the contract left without roles.
    for operation_id in CONTRACT_ROLE_EXCEPTIONS:
        policy = policies.get(operation_id)
        if policy is None or policy.public:
            raise ContractError(
                f"{operation_id} is listed in CONTRACT_ROLE_EXCEPTIONS but is "
                "not an authenticated contract operation"
            )

    return PolicyTable(policies)


def verify_policy_matches_contract(table: PolicyTable, path: pathlib.Path | None = None) -> None:
    """R10.2. Assert the table equals what the contract declares, role for role.

    Run at startup and as a test, so code and contract cannot drift apart.
    """
    doc = load_contract(path)
    problems: list[str] = []

    for route, method, op in _operations(doc):
        operation_id = op["operationId"]
        policy = table.get(operation_id)
        if policy is None:
            problems.append(f"{operation_id}: in the contract, absent from the policy table")
            continue
        if op.get("security") == []:
            if not policy.public:
                problems.append(f"{operation_id}: unauthenticated in contract, not in policy")
            continue
        expected = frozenset(Role(r) for r in (op.get("x-roles") or [])) or (
            CONTRACT_ROLE_EXCEPTIONS.get(operation_id, frozenset())
        )
        if policy.roles != expected:
            problems.append(
                f"{operation_id}: contract {sorted(r.value for r in expected)} "
                f"!= policy {sorted(r.value for r in policy.roles)}"
            )

    contract_ops = {op["operationId"] for _, _, op in _operations(doc)}
    for extra in sorted(table.operations() - contract_ops):
        problems.append(f"{extra}: in the policy table, absent from the contract")

    if problems:
        raise ContractError("policy/contract drift:\n  " + "\n  ".join(problems))
