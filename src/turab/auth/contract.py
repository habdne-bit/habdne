"""Build the policy table from the frozen OpenAPI contract.

Ref: RFC-001 R10.2, R14.1-R14.3.

The contract is the authority; the policy table is derived from it rather than
transcribed beside it. Hand-maintaining a parallel table is exactly how a
policy silently drifts from the contract it is supposed to enforce.
"""
from __future__ import annotations

import copy
import functools
import json
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


#: The keys a request-body narrowing may carry. Anything else is refused, so
#: no other kind of change can travel under this heading.
_BODY_NARROWING_KEYS = frozenset({
    "id", "decision", "approved", "operation_id", "require", "non_null", "enum",
    "frozen_defaults", "rationale", "runtime_rule", "reference",
})

#: JSON Schema types a narrowing `enum` value may have, as Python types. A
#: bool is not an integer or a number here, as in JSON.
_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,), "integer": (int,), "number": (int, float), "boolean": (bool,),
}
_SCHEMA_REF = "#/components/schemas/"


def _refs(node: Any, out: dict[str, int]) -> dict[str, int]:
    """Every `$ref` value in a parsed document, with its count."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            out[ref] = out.get(ref, 0) + 1
        for value in node.values():
            _refs(value, out)
    elif isinstance(node, list):
        for value in node:
            _refs(value, out)
    return out


def _frozen_body(cid: str, op: dict[str, Any], contract: dict[str, Any]
                 ) -> tuple[dict[str, Any], str | None]:
    """The operation's JSON object body, and the `$ref` it was given by, if any.

    A body given by `$ref` (CORRECTION-005, F6-19) is accepted only when the
    component is referenced by this operation alone, counted in the frozen
    document: narrowing a shared component would narrow another operation
    too. The component itself is never changed; the effective contract gets
    an operation-local copy (`narrowed_body_schema`)."""
    try:
        schema = op["requestBody"]["content"]["application/json"]["schema"]
    except (KeyError, TypeError):
        raise ContractError(f"{cid}: {op.get('operationId')} has no JSON body") from None
    ref = None
    if isinstance(schema, dict) and "$ref" in schema:
        ref = schema["$ref"]
        if set(schema) != {"$ref"} or not str(ref).startswith(_SCHEMA_REF):
            raise ContractError(f"{cid}: the body is not a plain reference to a schema "
                                "component")
        uses = _refs(contract, {}).get(ref, 0)
        if uses != 1:
            raise ContractError(f"{cid}: {ref} is referenced {uses} times in the frozen "
                                "contract; a narrowing may only change a component this "
                                "operation alone uses")
        schema = (contract.get("components", {}).get("schemas", {})
                  .get(ref[len(_SCHEMA_REF):]))
    if not isinstance(schema, dict) or not isinstance(schema.get("properties"), dict):
        raise ContractError(f"{cid}: {op.get('operationId')} has no JSON object body")
    return schema, ref


def _non_null_types(field_schema: dict[str, Any]) -> list[str]:
    declared = field_schema.get("type")
    types = declared if isinstance(declared, list) else [declared]
    return [t for t in types if t != "null"]


_NULL_BRANCH = {"type": "null"}


def _admits_null(branch: Any) -> bool:
    """Whether one `anyOf` branch, other than the null branch itself, could
    accept null. Only a branch whose `type` is a string or a list without
    "null", and which has no combinator of its own, is known not to; any
    other shape counts as admitting null, so a narrowing is never assumed."""
    if not isinstance(branch, dict):
        return True
    if any(k in branch for k in ("anyOf", "oneOf", "allOf", "not", "$ref")):
        return True
    declared = branch.get("type")
    if isinstance(declared, str):
        return declared == "null"
    if isinstance(declared, list) and declared:
        return "null" in declared
    return True


def _null_branches(field_schema: dict[str, Any]) -> tuple[list[Any], list[Any]] | None:
    """For a field written `anyOf: [..., {type: 'null'}]` (CORRECTION-006,
    `CommunicationThreadCreate.party_id`): the null branches and the others,
    or None when the field has no `anyOf`."""
    branches = field_schema.get("anyOf")
    if not isinstance(branches, list):
        return None
    nulls = [b for b in branches if b == _NULL_BRANCH]
    return nulls, [b for b in branches if b != _NULL_BRANCH]


def narrowed_body_schema(entry: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    """The effective body schema of a VALIDATED narrowing, as a new object.

    The one implementation of the transformation: the generator writes it into
    the effective contract, and the runtime reads its enum (CORRECTION-005).
    - `require`: appended to `required`; each field's `default` removed;
    - `non_null`: `null` removed from the field's type list, or the
      `{type: 'null'}` branch removed from its `anyOf` (CORRECTION-006);
    - `enum`: the field's values.
    A body given by `$ref` is copied, so the frozen component is unchanged.

    Only the levels that change are new objects: the schema, its `required`,
    its `properties` and each narrowed field. Every other value is the frozen
    object itself, so a YAML dump keeps its anchors, and the effective text of
    CORRECTION-004 is unchanged byte for byte. A body given by `$ref` is
    copied whole instead: the copy then shares nothing with the component,
    which a YAML dump would otherwise write with aliases into the operation."""
    op = next(o for _, _, o in _operations(contract)
              if o.get("operationId") == entry["operation_id"])
    frozen, ref = _frozen_body(entry["id"], op, contract)
    if ref is not None:
        # A JSON round trip, not `deepcopy`: deepcopy keeps the objects the
        # component shares within itself shared in the copy, which a YAML dump
        # then writes as aliases, renumbering every later anchor of the file.
        # Measured on CORRECTION-006 (three `anyOf` branches of one object).
        frozen = json.loads(json.dumps(frozen))
    schema = dict(frozen)
    schema["required"] = list(frozen.get("required") or []) + list(entry["require"])
    properties = schema["properties"] = dict(frozen["properties"])
    for field in entry["require"]:
        properties[field] = {k: v for k, v in properties[field].items() if k != "default"}
    for field in entry.get("non_null") or ():
        split = _null_branches(properties[field])
        if split is not None:
            # CORRECTION-006: the null branch removed. One branch left
            # replaces the `anyOf`; the field's other keywords are kept.
            others = split[1]
            rest = {k: v for k, v in properties[field].items() if k != "anyOf"}
            properties[field] = ({**rest, **copy.deepcopy(others[0])} if len(others) == 1
                                 else {**rest, "anyOf": copy.deepcopy(others)})
            continue
        remaining = _non_null_types(properties[field])
        properties[field] = {**properties[field],
                             "type": remaining[0] if len(remaining) == 1 else remaining}
    for field, values in (entry.get("enum") or {}).items():
        properties[field] = {**properties[field], "enum": list(values)}
    return schema


def _check_non_null(cid: str, fields: Any, properties: dict[str, Any]) -> None:
    if not isinstance(fields, list) or not fields:
        raise ContractError(f"{cid}: non_null must be a non-empty list of fields")
    repeated = sorted({f for f in fields if fields.count(f) > 1})
    if repeated:
        raise ContractError(f"{cid}: {repeated} listed more than once in non_null")
    for field in fields:
        if field not in properties:
            raise ContractError(f"{cid}: {field!r} is not a property of the body")
        split = _null_branches(properties[field])
        if split is not None:
            # CORRECTION-006: `anyOf` with exactly one `{type: 'null'}` branch,
            # and other branches none of which admits null. Removing that
            # branch then refuses null and nothing else. The field may carry
            # no `type` beside its `anyOf`, which could admit null on its own.
            nulls, others = split
            if len(nulls) != 1:
                raise ContractError(f"{cid}: {field!r} has {len(nulls)} null branches in "
                                    "its anyOf; non_null needs exactly one")
            if not others:
                raise ContractError(f"{cid}: {field!r} admits null only; non_null would "
                                    "refuse every value")
            if any(_admits_null(b) for b in others):
                raise ContractError(f"{cid}: another anyOf branch of {field!r} may admit "
                                    "null; removing the null branch would not refuse it")
            if "type" in properties[field]:
                raise ContractError(f"{cid}: {field!r} declares a type beside its anyOf; "
                                    "nothing is narrowed with certainty")
            continue
        declared = properties[field].get("type")
        if not isinstance(declared, list) or "null" not in declared:
            raise ContractError(f"{cid}: {field!r} has no type list admitting null; "
                                "nothing to narrow by non_null")
        if not _non_null_types(properties[field]):
            raise ContractError(f"{cid}: {field!r} admits null only; non_null would "
                                "refuse every value")


def _check_enum(cid: str, enums: Any, properties: dict[str, Any]) -> None:
    if not isinstance(enums, dict) or not enums:
        raise ContractError(f"{cid}: enum must map fields to their values")
    for field, values in enums.items():
        if field not in properties:
            raise ContractError(f"{cid}: {field!r} is not a property of the body")
        if not isinstance(values, list) or not values:
            raise ContractError(f"{cid}: the enum of {field!r} is empty")
        if any(values.count(v) > 1 for v in values):
            raise ContractError(f"{cid}: the enum of {field!r} repeats a value")
        types = _non_null_types(properties[field])
        allowed = tuple(c for t in types for c in _JSON_TYPES.get(t, ()))
        for value in values:
            if (not allowed or not isinstance(value, allowed)
                    or (isinstance(value, bool) and bool not in allowed)):
                raise ContractError(f"{cid}: an enum value of {field!r} is not of its "
                                    f"type {types}")
        frozen = properties[field].get("enum")
        if frozen is not None and not set(values) <= set(frozen):
            raise ContractError(f"{cid}: the enum of {field!r} admits a value the frozen "
                                "enum does not; a narrowing may only remove values")


def load_request_body_narrowings(
    path: pathlib.Path | None = None, contract: dict[str, Any] | None = None,
) -> tuple[dict, ...]:
    """Read and validate the approved request-body narrowings (CORRECTION-004,
    CORRECTION-005).

    A narrowing makes fields of an operation's JSON request body REQUIRED.
    That accepts strictly fewer requests than the frozen contract, so it
    narrows. It also removes each such field's `default`. A default applies
    only when the field is omitted, and omission is now refused, so removing
    it changes no request that is still accepted. The removed defaults are
    recorded in `frozen_defaults`, and must equal what the frozen package
    declares today (the staleness invariant of the role corrections).

    Slice 6 step 2 (F6-19; plan §5.2) adds, each a narrowing check:
    - a body given by `$ref`, only when that component is referenced by this
      operation alone (`_frozen_body`); the frozen component is unchanged;
    - `non_null`: each field's frozen type must be a list that admits null;
      the effective type removes it;
    - `enum`: each field's frozen schema must have no enum, or a superset of
      the values, and every value must be of the field's type.

    Refused:
    - an unknown key;
    - a missing id or decision;
    - an id used twice;
    - a second narrowing of the same operation, which would replace the first
      (review of aad9f34);
    - a field listed twice in `require`;
    - an operation that is also role-corrected;
    - an operation absent from the frozen contract;
    - a field the body does not declare, or already requires;
    - `frozen_defaults` that differ from the package.

    The generator of the effective contract applies what this returns, so
    the two cannot accept different narrowings.
    """
    doc = yaml.safe_load((path or CORRECTIONS_PATH).read_text(encoding="utf-8"))
    entries = tuple(doc.get("request_body_narrowings") or ())
    frozen = contract if contract is not None else load_contract()
    by_operation = {op.get("operationId"): op for _, _, op in _operations(frozen)}
    role_corrected = {e.get("operation_id") for e in doc.get("corrections") or ()}
    taken = {e.get("id") for e in doc.get("corrections") or ()} | {
        e.get("id") for e in doc.get("workflow_adoptions") or ()}
    seen: set[str] = set()
    narrowed: dict[str, str] = {}
    for entry in entries:
        cid = entry.get("id")
        unknown = set(entry) - _BODY_NARROWING_KEYS
        if unknown:
            raise ContractError(f"{cid}: unknown key(s) {sorted(unknown)}; a request-body "
                                "narrowing may only require fields, remove null or "
                                "restrict values")
        if not cid or cid in seen or cid in taken:
            raise ContractError(f"narrowing {cid!r}: missing or duplicated id")
        seen.add(cid)
        if not entry.get("decision"):
            raise ContractError(f"{cid}: names no decision")
        operation_id = entry.get("operation_id")
        if operation_id in role_corrected:
            raise ContractError(f"{cid}: {operation_id} is already role-corrected; one "
                                "correction per operation")
        # One narrowing per operation (review of aad9f34). The generator and
        # any caller index narrowings by operation, so a second entry would
        # REPLACE the first. A later narrowing could then silently undo an
        # approved one: measured, a second entry requiring `property_ids` made
        # `matching_policy_version` optional again, with its default back.
        if operation_id in narrowed:
            raise ContractError(
                f"{cid}: {operation_id} is already narrowed by {narrowed[operation_id]}; "
                "one narrowing per operation. Amend that one instead.")
        narrowed[operation_id] = cid
        op = by_operation.get(operation_id)
        if op is None:
            raise ContractError(f"{cid}: {operation_id!r} is not in the frozen contract")
        schema, _ = _frozen_body(cid, op, frozen)
        properties = schema["properties"]
        require = list(entry.get("require") or ())
        if not require:
            raise ContractError(f"{cid}: requires nothing")
        repeated = sorted({f for f in require if require.count(f) > 1})
        if repeated:
            raise ContractError(f"{cid}: {repeated} listed more than once in require; "
                                "a required array must not repeat a field")
        already = set(schema.get("required") or ())
        for field in require:
            if field not in properties:
                raise ContractError(f"{cid}: {field!r} is not a property of the body")
            if field in already:
                raise ContractError(f"{cid}: {field!r} is already required; nothing "
                                    "to narrow")
        declared = {f: properties[f]["default"] for f in require
                    if "default" in properties[f]}
        if dict(entry.get("frozen_defaults") or {}) != declared:
            raise ContractError(
                f"{cid}: frozen_defaults {entry.get('frozen_defaults')!r} but the "
                f"package declares {declared!r}. The correction is stale and must "
                "be re-approved against the current package.")
        if "non_null" in entry:
            _check_non_null(cid, entry["non_null"], properties)
        if "enum" in entry:
            _check_enum(cid, entry["enum"], properties)
    return entries


@functools.cache
def effective_request_body(operation_id: str) -> dict[str, Any] | None:
    """The effective body schema of a narrowed operation, or None. The runtime
    reads its rules from here, so they are the effective contract's (one
    loader, as CORRECTION-004)."""
    frozen = load_contract()
    for entry in load_request_body_narrowings(contract=frozen):
        if entry["operation_id"] == operation_id:
            return narrowed_body_schema(entry, frozen)
    return None


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
    # Validated here too, so a stale or widening body narrowing stops the
    # application at startup, as a bad role correction does (CORRECTION-004).
    load_request_body_narrowings(contract=doc)
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
