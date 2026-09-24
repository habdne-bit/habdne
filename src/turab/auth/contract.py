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
    / "openapi_v0.2.3.yaml"
)

#: Approved decisions that correct the frozen contract's declared roles.
#: The frozen file is never edited; this is the audited difference.
CORRECTIONS_PATH = (
    pathlib.Path(__file__).resolve().parents[3]
    / "docs" / "contract" / "CONTRACT_CORRECTIONS.yaml"
)


#: Approved contract ADDITIONS — operations the frozen contract does not have.
#: Distinct from the corrections overlay, which may only narrow.
ADDENDA_DIR = (
    pathlib.Path(__file__).resolve().parents[3] / "docs" / "contract" / "addenda"
)
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


class ContractError(RuntimeError):
    """The contract and the policy layer disagree. Fails at startup."""


@functools.cache
def load_addenda(directory: pathlib.Path | None = None) -> tuple[dict, ...]:
    """Every approved addendum, validated. Refuses to return a partial set.

    An addendum can only ADD. Each rule below exists so that this directory
    cannot become a quieter way to change the frozen contract than the
    decision process allows:

      * it names its decision and the Delta text it implements, and the
        Delta's sha256 must match — an edit to the approved wording without
        re-binding the addendum stops the service rather than drifting;
      * none of its operations may exist in the frozen contract, by
        operationId or by METHOD+PATH;
      * every operation is authenticated and carries `x-roles`;
      * no two addenda declare the same operation.
    """
    import hashlib

    frozen = load_contract()
    frozen_ids = {op["operationId"] for _, _, op in _operations(frozen)}
    frozen_routes = {(m, r) for r, m, _ in _operations(frozen)}
    seen: set[str] = set()
    out: list[dict] = []
    for path in sorted((directory or ADDENDA_DIR).glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        meta = doc.get("addendum") or {}
        aid = meta.get("id") or path.name
        if meta.get("kind") != "ADDITION":
            raise ContractError(f"{aid}: an addendum must declare kind ADDITION")
        if not meta.get("decision"):
            raise ContractError(f"{aid}: names no decision")
        delta = _REPO_ROOT / str(meta.get("delta_document", ""))
        if not delta.is_file():
            raise ContractError(f"{aid}: its Delta document {delta} does not exist")
        actual = hashlib.sha256(delta.read_bytes()).hexdigest()
        if actual != meta.get("delta_sha256"):
            raise ContractError(
                f"{aid}: bound to Delta sha256 {meta.get('delta_sha256')}, but "
                f"the document is now {actual}. The approved text changed; the "
                "addendum must be re-bound to it deliberately."
            )
        for route, method, op in _operations(doc):
            oid = op.get("operationId")
            if not oid:
                raise ContractError(f"{aid}: {method.upper()} {route} has no operationId")
            if oid in frozen_ids or (method, route) in frozen_routes:
                raise ContractError(
                    f"{aid}: {oid} ({method.upper()} {route}) already exists in "
                    "the frozen contract; an addendum may only add"
                )
            if oid in seen:
                raise ContractError(f"{aid}: {oid} is declared twice")
            seen.add(oid)
            if op.get("security") == [] or not op.get("x-roles"):
                raise ContractError(
                    f"{aid}: {oid} must be authenticated and carry x-roles")
        out.append(doc)
    return tuple(out)


def _all_operations(frozen: dict[str, Any]):
    """The frozen contract's operations, then every approved addendum's."""
    yield from _operations(frozen)
    for addendum in load_addenda():
        yield from _operations(addendum)


@functools.cache
def _correction_entries(path: pathlib.Path | None = None) -> tuple[dict, ...]:
    doc = yaml.safe_load((path or CORRECTIONS_PATH).read_text(encoding="utf-8"))
    return tuple(doc.get("corrections") or ())


def load_corrections(
    path: pathlib.Path | None = None,
) -> dict[str, frozenset[Role]]:
    """Read the numbered corrections and return operation_id -> corrected roles.

    Every check here exists to stop this file being a quieter way to grant
    access than changing the contract.
    """
    out: dict[str, frozenset[Role]] = {}
    seen_ids: set[str] = set()

    for entry in _correction_entries(path):
        cid = entry.get("id")
        if not cid or cid in seen_ids:
            raise ContractError(f"correction {cid!r}: missing or duplicated id")
        seen_ids.add(cid)
        if not entry.get("decision"):
            raise ContractError(
                f"{cid}: names no decision. A correction without an approved "
                "decision behind it is an opinion, not a contract change."
            )
        operation_id = entry.get("operation_id")
        if operation_id in out:
            raise ContractError(f"{cid}: {operation_id} is corrected twice")

        frozen = frozenset(Role(r) for r in entry.get("frozen") or [])
        corrected = frozenset(Role(r) for r in entry.get("corrected") or [])
        if not corrected:
            raise ContractError(
                f"{cid}: an empty role set makes the operation unreachable; "
                "remove the operation from the contract instead"
            )
        if not corrected <= frozen:
            raise ContractError(
                f"{cid}: {sorted(r.value for r in corrected - frozen)} is not in "
                "the frozen contract. A correction may only NARROW — widening "
                "access needs a new official handoff package (R14.1)."
            )
        out[operation_id] = corrected

    return out


def _corrected_roles(
    operation_id: str, declared: frozenset[Role], corrections: dict[str, frozenset[Role]]
) -> frozenset[Role]:
    return corrections.get(operation_id, declared)


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
    corrections = load_corrections()
    policies: dict[str, RoutePolicy] = {}
    unannotated: list[str] = []
    corrected_frozen: dict[str, frozenset[Role]] = {}

    for route, method, op in _all_operations(doc):
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
            as_declared = frozenset(Role(r) for r in declared)
            corrected_frozen[operation_id] = as_declared
            roles = _corrected_roles(operation_id, as_declared, corrections)
        elif operation_id in CONTRACT_ROLE_EXCEPTIONS:
            # R10.3a. Authenticated, no x-roles, ruled on explicitly.
            roles = CONTRACT_ROLE_EXCEPTIONS[operation_id]
        else:
            unannotated.append(f"{operation_id} ({method.upper()} {route})")
            continue

        param_refs = " ".join(
            p.get("$ref", "") for p in op.get("parameters", [])
        )
        policies[operation_id] = RoutePolicy(
            operation_id=operation_id,
            method=method.upper(),
            path=route,
            roles=roles,
            public=is_public,
            customer_scoped=route.startswith("/me/"),
            requires_idempotency="IdempotencyKey" in param_refs,
            requires_if_match="IfMatchVersion" in param_refs,
        )

    if unannotated:
        raise ContractError(
            "authenticated operations with no x-roles and no explicit ruling: "
            + ", ".join(sorted(unannotated))
            + " — each needs a decision before it can be reachable"
        )

    # Every correction must name a real, role-annotated operation, and must
    # still describe the contract as it stands today (invariant 2).
    addendum_ids = {op["operationId"] for a in load_addenda()
                    for _, _, op in _operations(a)}
    for entry in _correction_entries():
        operation_id = entry["operation_id"]
        if operation_id in addendum_ids:
            raise ContractError(
                f"{entry['id']}: {operation_id} is an addendum operation; it is "
                "changed by amending its addendum under a decision, not by a "
                "correction"
            )
        if operation_id not in corrected_frozen:
            raise ContractError(
                f"{entry['id']}: {operation_id} is not an operation the frozen "
                "contract annotates with x-roles"
            )
        stated = frozenset(Role(r) for r in entry["frozen"])
        if stated != corrected_frozen[operation_id]:
            raise ContractError(
                f"{entry['id']}: declares the frozen roles as "
                f"{sorted(r.value for r in stated)}, but the contract now says "
                f"{sorted(r.value for r in corrected_frozen[operation_id])}. "
                "The correction is stale and must be re-approved against the "
                "current package."
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
    corrections = load_corrections()
    problems: list[str] = []

    for route, method, op in _all_operations(doc):
        operation_id = op["operationId"]
        policy = table.get(operation_id)
        if policy is None:
            problems.append(f"{operation_id}: in the contract, absent from the policy table")
            continue
        if op.get("security") == []:
            if not policy.public:
                problems.append(f"{operation_id}: unauthenticated in contract, not in policy")
            continue
        declared = frozenset(Role(r) for r in (op.get("x-roles") or []))
        expected = _corrected_roles(operation_id, declared, corrections) if declared else (
            CONTRACT_ROLE_EXCEPTIONS.get(operation_id, frozenset())
        )
        if policy.roles != expected:
            problems.append(
                f"{operation_id}: contract {sorted(r.value for r in expected)} "
                f"!= policy {sorted(r.value for r in policy.roles)}"
            )

    contract_ops = {op["operationId"] for _, _, op in _all_operations(doc)}
    for extra in sorted(table.operations() - contract_ops):
        problems.append(f"{extra}: in the policy table, absent from the contract")

    if problems:
        raise ContractError("policy/contract drift:\n  " + "\n  ".join(problems))
