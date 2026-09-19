#!/usr/bin/env python3
"""TURAB — OpenAPI contract lint for the PostgreSQL Execution Gate.

Parses the spec, resolves every internal $ref, and rejects duplicate or
missing operationIds. Exits non-zero on any finding (release blocker).
Ref: docs/handoff/04_DATABASE/POSTGRES_EXECUTION_GATE.md
"""
import json
import sys

import yaml

METHODS = ("get", "put", "post", "delete", "patch", "options", "head", "trace")


def collect_refs(node, out):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                out.append(value)
            else:
                collect_refs(value, out)
    elif isinstance(node, list):
        for item in node:
            collect_refs(item, out)


def resolve(doc, ref):
    cursor = doc
    for part in ref[2:].split("/"):
        cursor = cursor[part.replace("~1", "/").replace("~0", "~")]
    return cursor


def main(path):
    doc = yaml.safe_load(open(path, encoding="utf-8"))
    errors = []

    if not str(doc.get("openapi", "")).startswith("3.1"):
        errors.append(f"expected OpenAPI 3.1.x, found {doc.get('openapi')!r}")

    paths = doc.get("paths", {})
    operations = [
        (route, method, item[method])
        for route, item in paths.items()
        for method in item
        if method in METHODS
    ]

    refs = []
    collect_refs(doc, refs)
    for ref in refs:
        if not ref.startswith("#/"):
            errors.append(f"non-internal $ref: {ref}")
            continue
        try:
            resolve(doc, ref)
        except (KeyError, TypeError):
            errors.append(f"unresolved $ref: {ref}")

    seen = {}
    for route, method, op in operations:
        op_id = op.get("operationId")
        if not op_id:
            errors.append(f"missing operationId: {method.upper()} {route}")
            continue
        if op_id in seen:
            errors.append(f"duplicate operationId {op_id!r}: {seen[op_id]} and {method.upper()} {route}")
        seen[op_id] = f"{method.upper()} {route}"

    print(json.dumps({
        "status": "FAIL" if errors else "PASS",
        "openapi": doc.get("openapi"),
        "paths": len(paths),
        "operations": len(operations),
        "component_schemas": len(doc.get("components", {}).get("schemas", {})),
        "internal_refs": len(refs),
        "errors": errors,
    }, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "openapi_v0.2.3.yaml"))
