#!/usr/bin/env python3
"""TURAB — generate the API inventory from the frozen OpenAPI contract.

Ref: IMPLEMENTATION_SLICES_v0.2.md, Slice -1 ("generated API inventory or SDK
stubs using stable operationId values").

Emits a Markdown inventory keyed by operationId, carrying the role and
object-authorization metadata the contract declares. This is the table the
Slice 0 policy layer is checked against (RFC-001 R10.2): every operation with
x-roles must have a policy entry whose roles match exactly.

Usage:
  db/gate/generate_api_inventory.py <openapi.yaml> [-o docs/api/API_INVENTORY_GENERATED.md]
  db/gate/generate_api_inventory.py <openapi.yaml> --check   # fail if stale
"""
import argparse
import hashlib
import pathlib
import sys

import yaml

METHODS = ("get", "put", "post", "delete", "patch", "options", "head", "trace")


def operations(doc):
    for route, item in sorted(doc.get("paths", {}).items()):
        for method in METHODS:
            if method in item:
                yield route, method, item[method]


def render(doc, source_path, digest):
    rows, public, no_roles = [], [], []
    for route, method, op in operations(doc):
        op_id = op.get("operationId", "")
        roles = op.get("x-roles") or []
        auth = (op.get("x-authorization") or "").strip()
        if op.get("security") == []:
            public.append((op_id, method.upper(), route))
        elif not roles:
            no_roles.append((op_id, method.upper(), route))
        rows.append((op_id, method.upper(), route, roles, auth))

    out = [
        "# TURAB — API Inventory (generated)",
        "",
        "**Do not edit.** Regenerate with `db/gate/generate_api_inventory.py`.",
        "",
        f"- Source: `{source_path}`",
        f"- Source SHA-256: `{digest}`",
        f"- Operations: {len(rows)} · role-annotated: {sum(1 for r in rows if r[3])}"
        f" · unauthenticated: {len(public)}",
        "",
        "## Unauthenticated operations",
        "",
        "This is a closed list. Any addition is a security change, not a routine one",
        "(RFC-001 R10.4).",
        "",
        "| operationId | Method | Path |",
        "|---|---|---|",
    ]
    for op_id, m, route in sorted(public):
        out.append(f"| `{op_id}` | {m} | `{route}` |")

    if no_roles:
        out += [
            "",
            "## Authenticated operations without declared roles",
            "",
            "Each needs an explicit policy decision before implementation.",
            "",
            "| operationId | Method | Path |",
            "|---|---|---|",
        ]
        for op_id, m, route in sorted(no_roles):
            out.append(f"| `{op_id}` | {m} | `{route}` |")

    out += [
        "",
        "## All operations",
        "",
        "| operationId | Method | Path | Roles | Object authorization |",
        "|---|---|---|---|---|",
    ]
    for op_id, m, route, roles, auth in sorted(rows):
        role_txt = ", ".join(f"`{r}`" for r in roles) if roles else "—"
        auth_txt = auth.replace("|", "\\|") if auth else "—"
        out.append(f"| `{op_id}` | {m} | `{route}` | {role_txt} | {auth_txt} |")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("openapi")
    ap.add_argument("-o", "--out", default="docs/api/API_INVENTORY_GENERATED.md")
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if the committed inventory is stale")
    args = ap.parse_args()

    src = pathlib.Path(args.openapi)
    raw = src.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    doc = yaml.safe_load(raw)
    content = render(doc, args.openapi, digest)

    out = pathlib.Path(args.out)
    if args.check:
        if not out.exists():
            print(f"FAIL: {out} does not exist; run without --check", file=sys.stderr)
            return 1
        if out.read_text(encoding="utf-8") != content:
            print(f"FAIL: {out} is stale relative to {src}; regenerate it", file=sys.stderr)
            return 1
        print(f"PASS: {out} matches {src}")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
