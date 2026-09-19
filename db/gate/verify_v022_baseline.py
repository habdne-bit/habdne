#!/usr/bin/env python3
"""Acceptance check for a candidate Technical Patch v0.2.2 / Handoff v1.0.2.

Run this against an official package BEFORE adopting it. It asserts that the
package implements the D1 and D2 decisions exactly, and that nothing else moved.

A package is not adopted because it is labelled v1.0.2; it is adopted because it
does what was decided. This script is the difference between those two things.

Usage:
  db/gate/verify_v022_baseline.py /path/to/TURAB_Developer_Handoff_v1.0.2
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import re
import sys

import yaml

# Digests of the PREVIOUS baseline (v0.2.1 / v1.0.1), kept so the "nothing else
# moved" checks remain meaningful. v0.2.2 is now adopted; this script stays as
# the record of how that package was accepted and as the template for the next.
FROZEN_V021 = {
    "schema": "9fac9fa2552d2963a8fc8c0745eea4c71a12c193c161268a073b64c216b42688",
    "seed": "c8edb576500e6726487deab121b85fc1f6b99f6a07cc3f87e557b123807409da",
    "openapi": "8e4bd4fbf171adfb3724d6ebb1acdc5d72fac12503fdf67fa8aa2175bf294724",
}

# The adopted v0.2.2 baseline, verified against D1/D2 and re-gated.
FROZEN_V022 = {
    "schema": "eb1862b1984b7a62e29b1e58a490c2c6c4a1783cab01be66738cd1c97bb032ea",
    "seed": "132869b4b91a2c07925f352fdd71192cc26a90313a0a19a1844366141fedc553",
    "openapi": "7e6187ce700c504060a0f0dc724174c35369b39ba6c24b99a64a06cf41005d07",
}

#: D1. The canonical concurrency header for TURAB v0.1.
CANONICAL_HEADER = "If-Match-Version"

#: D2. The column the patch must add to `parties`.
PARTIES_VERSION_PATTERN = re.compile(
    r"version\s+integer\s+NOT\s+NULL\s+DEFAULT\s+1\s+CHECK\s*\(\s*version\s*>\s*0\s*\)",
    re.IGNORECASE,
)

#: The four operations that require optimistic concurrency.
IF_MATCH_OPERATIONS = {
    "patchOffersOfferId", "patchPartiesPartyId",
    "patchPropertiesPropertyId", "patchRequestsRequestId",
}


class Findings:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.notes: list[str] = []

    def check(self, ok: bool, message: str) -> bool:
        if not ok:
            self.errors.append(message)
        return ok

    def note(self, message: str) -> None:
        self.notes.append(message)


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _table_block(sql: str, table: str) -> str:
    match = re.search(
        rf"CREATE TABLE {table} \((.*?)\n\);", sql, re.DOTALL,
    )
    return match.group(1) if match else ""


def verify(root: pathlib.Path) -> Findings:
    f = Findings()
    db = root / "04_DATABASE"
    api = root / "05_API"

    schema = next(db.glob("schema_v0.2.*.sql"), None)
    seed = next(db.glob("seed_master_data_v0.2.*.sql"), None)
    openapi = next(api.glob("openapi_v0.2*.yaml"), None)

    if not (schema and seed and openapi):
        f.errors.append(f"package is missing schema/seed/openapi under {root}")
        return f

    f.note(f"schema:  {schema.name}  {_sha(schema)}")
    f.note(f"seed:    {seed.name}  {_sha(seed)}")
    f.note(f"openapi: {openapi.name}  {_sha(openapi)}")

    sql = schema.read_text(encoding="utf-8")
    doc = yaml.safe_load(openapi.read_text(encoding="utf-8"))

    # ---- D1: the concurrency header -------------------------------------
    params = doc.get("components", {}).get("parameters", {})
    if f.check("IfMatchVersion" in params,
               "D1: components.parameters.IfMatchVersion is missing"):
        declared = params["IfMatchVersion"].get("name")
        f.check(
            declared == CANONICAL_HEADER,
            f"D1: header is named {declared!r}, expected {CANONICAL_HEADER!r}",
        )
        f.check(
            params["IfMatchVersion"].get("required") is True,
            "D1: IfMatchVersion must remain required",
        )

    stale = [
        name for name, p in params.items() if p.get("name") == "If-Match"
    ]
    f.check(not stale, f"D1: parameters still declaring the old If-Match header: {stale}")

    using = set()
    for path, item in doc.get("paths", {}).items():
        for method, op in item.items():
            if method not in ("get", "post", "patch", "put", "delete"):
                continue
            refs = [p.get("$ref", "") for p in op.get("parameters", [])]
            if any("IfMatchVersion" in r for r in refs):
                using.add(op["operationId"])
    f.check(
        using == IF_MATCH_OPERATIONS,
        f"D1: operations requiring the header changed: "
        f"missing {sorted(IF_MATCH_OPERATIONS - using)}, "
        f"unexpected {sorted(using - IF_MATCH_OPERATIONS)}",
    )

    # ---- D2: parties.version + the version-bumping trigger ---------------
    parties = _table_block(sql, "parties")
    f.check(bool(parties), "D2: CREATE TABLE parties not found")
    f.check(
        bool(PARTIES_VERSION_PATTERN.search(parties)),
        "D2: parties must gain `version integer NOT NULL DEFAULT 1 CHECK (version > 0)`",
    )

    parties_triggers = re.findall(
        r"CREATE TRIGGER (\w+)[^;]*ON parties[^;]*EXECUTE FUNCTION (\w+)\(\)", sql
    )
    bumping = [t for t, fn in parties_triggers if fn == "bump_version_and_timestamp"]
    timestamp_only = [t for t, fn in parties_triggers if fn == "set_updated_at"]
    f.check(
        bool(bumping),
        "D2: parties must use bump_version_and_timestamp(), none found",
    )
    f.check(
        not timestamp_only,
        f"D2: the timestamp-only trigger must be replaced, still present: {timestamp_only}",
    )

    # ---- D2: version reaches both party schemas --------------------------
    schemas = doc.get("components", {}).get("schemas", {})
    customer_party = schemas.get("CustomerPartyView", {}).get("properties", {})
    f.check(
        "version" in customer_party,
        "D2: CustomerPartyView must expose `version` so a CUSTOMER can satisfy "
        "PATCH /parties/{party_id}",
    )
    internal = [
        name for name in schemas
        if "Party" in name and name not in ("CustomerPartyView",)
        and "properties" in schemas[name]
    ]
    with_version = [
        n for n in internal if "version" in schemas[n].get("properties", {})
    ]
    f.check(
        bool(with_version),
        f"D2: no internal Party response schema exposes `version` (looked at {internal})",
    )
    f.note(f"internal Party schemas carrying version: {with_version}")

    # ---- nothing else moved ---------------------------------------------
    f.check(
        _sha(schema) != FROZEN_V021["schema"],
        "the schema is byte-identical to v0.2.1: the patch changes nothing",
    )
    for fk in ("fk_consent_evidence_observation", "fk_property_attribute_resolved_claim"):
        f.check(
            sql.count(fk) == 1,
            f"regression: {fk} appears {sql.count(fk)} times; v0.2.1 fixed it to 1",
        )
    if _sha(seed) == FROZEN_V021["seed"]:
        f.note("seed unchanged from v0.2.1 (expected: D1/D2 do not touch master data)")
    else:
        f.note("seed CHANGED from v0.2.1 — confirm this is intended")

    return f


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("package_root", type=pathlib.Path)
    args = ap.parse_args()

    if not args.package_root.is_dir():
        print(f"not a directory: {args.package_root}", file=sys.stderr)
        return 2

    f = verify(args.package_root)
    for note in f.notes:
        print(f"  note: {note}")
    if f.errors:
        print("\nV0.2.2 ACCEPTANCE: FAIL", file=sys.stderr)
        for e in f.errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("\nV0.2.2 ACCEPTANCE: PASS — package implements D1 and D2 as decided")
    return 0


if __name__ == "__main__":
    sys.exit(main())
