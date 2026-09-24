#!/usr/bin/env python3
"""The effective contract, the inventory and the policy table: ONE set.

Ref: RFC-001 R10.2, R14.2; review of 0a66f8e.

The policy table enforced 67 operations while the effective contract and the
inventory generated from it documented 64: the three G3-6 additions were
served but not described. The existing check walked the EFFECTIVE contract
and looked each operation up in the policy table — one direction only — so
operations present in the table and missing from the document passed
unnoticed.

What this compares, precisely:

  * OPERATION SETS, in both directions, across all three —
    `docs/api/openapi_effective_v0.2.3.yaml` (what is documented),
    `docs/api/API_INVENTORY_GENERATED.md` (what is listed) and
    `build_policy_table()` in `src/turab/auth/contract.py` (what is enforced:
    frozen + corrections + approved addenda);
  * ROLES between the effective contract and the policy table only: an
    operation present everywhere but authorized differently is the same lie
    told more quietly.

What it does NOT compare: the inventory's text, including the roles it
prints. That is held to the effective contract by
`generate_api_inventory.py --check`, run just before this in the same gate
step, which fails on any difference from a fresh rendering.

Usage:
  db/gate/verify_policy_parity.py
"""
from __future__ import annotations

import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

EFFECTIVE = ROOT / "docs" / "api" / "openapi_effective_v0.2.3.yaml"
INVENTORY = ROOT / "docs" / "api" / "API_INVENTORY_GENERATED.md"
_METHODS = ("get", "put", "post", "delete", "patch", "options", "head", "trace")
_ROW = re.compile(r"^\| `([A-Za-z0-9]+)` \| [A-Z]+ \| `")


def effective_operations() -> dict[str, dict]:
    doc = yaml.safe_load(EFFECTIVE.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for item in doc.get("paths", {}).values():
        for method in _METHODS:
            op = item.get(method)
            if isinstance(op, dict):
                out[op["operationId"]] = op
    return out


def inventory_operations() -> set[str]:
    """Operation ids in the inventory's "All operations" table."""
    text = INVENTORY.read_text(encoding="utf-8")
    section = text.split("## All operations", 1)[1]
    return {m.group(1) for line in section.splitlines() if (m := _ROW.match(line))}


def problems() -> list[str]:
    from turab.auth.contract import build_policy_table
    from turab.auth.policy import CONTRACT_ROLE_EXCEPTIONS

    table = build_policy_table()
    enforced = set(table.operations())
    documented = effective_operations()
    listed = inventory_operations()

    found: list[str] = []
    for name, left, right in (
        ("policy table", enforced, set(documented)),
        ("inventory", listed, set(documented)),
    ):
        for op in sorted(left - right):
            found.append(f"{op}: in the {name}, absent from the effective contract")
        for op in sorted(right - left):
            found.append(f"{op}: in the effective contract, absent from the {name}")

    for op_id in sorted(enforced & set(documented)):
        op, policy = documented[op_id], table.get(op_id)
        if op.get("security") == []:
            if not policy.public:
                found.append(f"{op_id}: public in the document, not in the table")
            continue
        declared = op.get("x-roles")
        expected = (frozenset(declared) if declared is not None
                    else frozenset(r.value for r in CONTRACT_ROLE_EXCEPTIONS.get(op_id, ())))
        actual = frozenset(r.value for r in policy.roles)
        if expected != actual:
            found.append(f"{op_id}: documented {sorted(expected)} != enforced {sorted(actual)}")
    return found


def main() -> int:
    found = problems()
    if found:
        print("FAIL: documentation and enforcement disagree:", file=sys.stderr)
        for line in found:
            print(f"  {line}", file=sys.stderr)
        return 1
    count = len(effective_operations())
    print(f"PASS: effective contract, inventory and policy table hold the same "
          f"{count} operations; the effective contract's roles equal the "
          f"policy table's")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
