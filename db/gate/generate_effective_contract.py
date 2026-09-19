#!/usr/bin/env python3
"""Generate the EFFECTIVE API contract: frozen package + approved corrections.

Ref: RFC-001 R14.1-R14.3; `docs/contract/CONTRACT_CORRECTIONS.yaml`.

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
| Building the policy table | frozen + corrections, in `auth/contract.py` |
| Proving the two agree | `--check` here, plus `test_the_effective_contract_matches_the_policy_table` |

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
FROZEN = ROOT / "docs" / "handoff" / "05_API" / "openapi_v0.2.3.yaml"
CORRECTIONS = ROOT / "docs" / "contract" / "CONTRACT_CORRECTIONS.yaml"
OUT = ROOT / "docs" / "api" / "openapi_effective_v0.2.3.yaml"

_METHODS = ("get", "put", "post", "delete", "patch", "options", "head", "trace")

HEADER = """\
# =============================================================================
# GENERATED — DO NOT EDIT.
#
# The EFFECTIVE TURAB API contract: the frozen package with every approved
# correction applied. Regenerate with:
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
# the published text is always recoverable from this file.
#
# Source digests at generation time:
#   openapi_v0.2.3.yaml          {frozen_sha}
#   CONTRACT_CORRECTIONS.yaml    {corrections_sha}
#
# Corrections applied: {applied}
# =============================================================================
"""


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> tuple[str, list[str]]:
    doc = yaml.safe_load(FROZEN.read_text(encoding="utf-8"))
    corrections = yaml.safe_load(CORRECTIONS.read_text(encoding="utf-8"))
    by_operation = {
        entry["operation_id"]: entry
        for entry in (corrections.get("corrections") or [])
    }

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

    header = HEADER.format(
        frozen_sha=_sha(FROZEN),
        corrections_sha=_sha(CORRECTIONS),
        applied=", ".join(applied) if applied else "none",
    )
    body = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100)
    return header + body, applied


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
              f"({len(applied)} correction(s) applied)")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUT} ({len(applied)} correction(s) applied)")
    for line in applied:
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
