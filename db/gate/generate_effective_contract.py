#!/usr/bin/env python3
"""Generate the EFFECTIVE API contract: frozen package + approved corrections
+ approved additions.

Ref: RFC-001 R14.1-R14.3; `docs/contract/CONTRACT_CORRECTIONS.yaml`;
`docs/contract/addenda/*.yaml`, each bound to its Contract Delta
`docs/gate/CONTRACT_DELTA_*.md` by sha256.

## Additions (review of 0a66f8e)

This file used to read the frozen package and the corrections only, so the
three G3-6 operations — enforced by the runtime policy table since `7ef416b`
— were absent from the effective contract and from the inventory generated
from it: 64 operations documented, 67 served. The effective contract now also
merges every approved addendum, validated by the SAME function the runtime
uses (`src/turab/auth/contract.py`, `load_addenda`: bound to its Delta by
sha256, additions only, x-roles required), and marks each added operation:

    x-turab-addendum:
      id: ADD-G3-6
      kind: ADDITION
      decision: ...
      delta_document: docs/gate/CONTRACT_DELTA_G3-6_party_property_relations.md
      delta_sha256: ...

`verify_policy_parity.py` then checks, in the gate, that the effective
contract, the generated inventory and the runtime policy table hold the SAME
set of operations in both directions.

## Why this exists

Keeping the published package byte-for-byte is right, but applying a
correction only to the runtime policy table leaves everyone who READS a
contract — developers, documentation, client generators — looking at roles
that are not the ones enforced. There has to be one artifact that says what is
actually in force, and it has to be derived, never hand-written.

So: this reads the frozen contract and the approved corrections and writes
`docs/api/openapi_effective_v0.2.3.yaml`. The frozen file is never touched;
the effective file is generated and carries, on every corrected operation, the
identity of the correction that changed it:

    x-turab-correction:
      id: CORRECTION-001
      decision: D7
      frozen-x-roles: [ADMIN, OPERATOR, CUSTOMER]

so a reader can always recover what the published package said and why it is
not what is enforced.

## Which contract to use for what

| Use | Contract |
|---|---|
| The authority, and what is frozen | `docs/handoff/05_API/openapi_v0.2.3.yaml` |
| Documentation, client generation, API inventory | the effective contract |
| Building the policy table | frozen + corrections + addenda, in `auth/contract.py` |
| Proving the two agree | `--check` here, `verify_policy_parity.py` in the gate, and `test_the_effective_contract_matches_the_policy_table` |

Usage:
  db/gate/generate_effective_contract.py            # write
  db/gate/generate_effective_contract.py --check    # fail if stale
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    # The addendum rules have ONE implementation, in the runtime.
    sys.path.insert(0, str(ROOT / "src"))
FROZEN = ROOT / "docs" / "handoff" / "05_API" / "openapi_v0.2.3.yaml"
CORRECTIONS = ROOT / "docs" / "contract" / "CONTRACT_CORRECTIONS.yaml"
OUT = ROOT / "docs" / "api" / "openapi_effective_v0.2.3.yaml"

_METHODS = ("get", "put", "post", "delete", "patch", "options", "head", "trace")

HEADER = """\
# =============================================================================
# GENERATED — DO NOT EDIT.
#
# The EFFECTIVE TURAB API contract: the frozen package with every approved
# correction applied and every approved ADDITION merged. Regenerate with:
#
#     db/gate/generate_effective_contract.py
#
# The authority remains docs/handoff/05_API/openapi_v0.2.3.yaml, vendored
# byte-for-byte and never edited. This file exists so that documentation,
# generated clients and drift checks read the roles that are actually
# ENFORCED, instead of roles a correction has since narrowed.
#
# Every corrected operation carries `x-turab-correction`, naming the
# correction, the decision behind it, and what the frozen package declared, so
# the published text is always recoverable from this file. An operation whose
# WORKFLOW was adopted rather than whose roles were narrowed carries
# `x-turab-workflow` instead, pointing at where that workflow is written down.
#
# Every operation added by an approved addendum carries `x-turab-addendum`,
# naming the addendum, its decision, and the Contract Delta it is bound to by
# sha256. Such an operation does not exist in the frozen package.
#
# Source digests at generation time:
#   openapi_v0.2.3.yaml          {frozen_sha}
#   CONTRACT_CORRECTIONS.yaml    {corrections_sha}
{addenda_digests}
#
# Corrections applied: {applied}
# Additions merged: {added}
# =============================================================================
"""


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _merge_addenda(doc: dict) -> tuple[list[str], list[str]]:
    """Merge every approved addendum into `doc`; return (added, digest lines).

    Validation is `load_addenda`'s — the runtime's — so the effective contract
    and the policy table cannot accept different addenda. Components may only
    be ADDED too: a name the frozen package already defines is refused, since
    replacing it would silently change a frozen operation's schema.
    """
    from turab.auth.contract import ADDENDA_DIR, load_addenda

    added: list[str] = []
    digests: list[str] = []
    for path in sorted(ADDENDA_DIR.glob("*.yaml")):
        digests.append(f"#   addenda/{path.name:<40} {_sha(path)}")
    for addendum in load_addenda():
        meta = addendum["addendum"]
        identity = {
            "id": meta["id"],
            "kind": meta["kind"],
            "decision": " ".join(str(meta["decision"]).split()),
            "delta_document": meta["delta_document"],
            "delta_sha256": meta["delta_sha256"],
        }
        for route, item in addendum.get("paths", {}).items():
            target = doc.setdefault("paths", {}).setdefault(route, {})
            for method in _METHODS:
                op = item.get(method)
                if not isinstance(op, dict):
                    continue
                if method in target:
                    raise SystemExit(f"{meta['id']}: {method.upper()} {route} "
                                     "already exists; an addendum may only add")
                op = dict(op)
                op["x-turab-addendum"] = dict(identity)
                target[method] = op
                added.append(f"{meta['id']} ({op['operationId']})")
        for section, entries in (addendum.get("components") or {}).items():
            existing = doc.setdefault("components", {}).setdefault(section, {})
            for name, value in entries.items():
                if name in existing:
                    raise SystemExit(f"{meta['id']}: components.{section}.{name} "
                                     "already exists; an addendum may only add")
                existing[name] = value
    return added, digests


def build() -> tuple[str, list[str]]:
    doc = yaml.safe_load(FROZEN.read_text(encoding="utf-8"))
    corrections = yaml.safe_load(CORRECTIONS.read_text(encoding="utf-8"))
    by_operation = {
        entry["operation_id"]: entry
        for entry in (corrections.get("corrections") or [])
    }

    # Workflow adoptions change no roles, so they are annotated rather than
    # applied: a reader of the effective contract must still be able to learn
    # that ACTIVE -> PAUSED was adopted, and where it is written down.
    adoptions = {
        entry["operation_id"]: entry
        for entry in (corrections.get("workflow_adoptions") or [])
    }
    adopted: list[str] = []
    for item in doc.get("paths", {}).values():
        for method in _METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            entry = adoptions.get(op.get("operationId"))
            if entry is None:
                continue
            op["x-turab-workflow"] = {
                "id": entry["id"],
                "decision": entry["decision"],
                "approved": str(entry.get("approved", "")),
                "summary": " ".join(entry["summary"].split()),
                "reference": entry.get("reference"),
            }
            adopted.append(f"{entry['id']} ({op['operationId']})")

    applied: list[str] = []
    for item in doc.get("paths", {}).values():
        for method in _METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            entry = by_operation.get(op.get("operationId"))
            if entry is None:
                continue
            frozen_roles = list(op.get("x-roles") or [])
            if sorted(frozen_roles) != sorted(entry["frozen"]):
                raise SystemExit(
                    f"{entry['id']}: declares frozen roles {sorted(entry['frozen'])} "
                    f"but the package says {sorted(frozen_roles)}. The correction "
                    "is stale and must be re-approved against the current package."
                )
            if not set(entry["corrected"]) <= set(frozen_roles):
                raise SystemExit(
                    f"{entry['id']}: a correction may only NARROW; "
                    f"{sorted(set(entry['corrected']) - set(frozen_roles))} is not "
                    "in the frozen contract."
                )
            op["x-roles"] = list(entry["corrected"])
            op["x-turab-correction"] = {
                "id": entry["id"],
                "decision": entry["decision"],
                "approved": str(entry.get("approved", "")),
                "frozen-x-roles": frozen_roles,
            }
            applied.append(f"{entry['id']} ({op['operationId']})")

    unmatched = set(by_operation) - {
        a.split("(")[1].rstrip(")") for a in applied
    }
    if unmatched:
        raise SystemExit(
            f"corrections name operations the contract does not have: {sorted(unmatched)}"
        )

    added, digests = _merge_addenda(doc)

    header = HEADER.format(
        frozen_sha=_sha(FROZEN),
        corrections_sha=_sha(CORRECTIONS),
        addenda_digests="\n".join(digests) if digests else "#   (no addenda)",
        applied=", ".join(applied + adopted) if (applied or adopted) else "none",
        added=", ".join(added) if added else "none",
    )
    body = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100)
    return header + body, applied + adopted + added


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="regenerate and fail if the committed file is stale")
    args = ap.parse_args()

    rendered, applied = build()

    if args.check:
        if not OUT.exists():
            print(f"{OUT} does not exist; run without --check", file=sys.stderr)
            return 1
        if OUT.read_text(encoding="utf-8") != rendered:
            print(f"{OUT} is stale; regenerate it", file=sys.stderr)
            return 1
        print(f"PASS: {OUT.relative_to(ROOT)} is current "
              f"({len(applied)} correction(s), adoption(s) and addition(s))")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUT} ({len(applied)} correction(s), adoption(s) and addition(s))")
    for line in applied:
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
