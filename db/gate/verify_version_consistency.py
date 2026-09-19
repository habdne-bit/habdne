#!/usr/bin/env python3
"""Version-consistency invariant for a handoff package.

D6 was a version stated in four places and wrong in one: `schema_v0.2.2.sql`
seeded `schema_metadata.schema_version = '0.2.1'`. Every runtime test passed,
because nothing executable depends on that value — which is exactly why a
human had to notice it. This makes the class of defect mechanical.

The rule: a package declares ONE technical baseline version, and every place
that states it must agree. A filename is a claim; a header is a claim; a seeded
metadata row is a claim. They must be the same claim.

Files legitimately pinned to an older line are not in scope: the architecture
and API documents are at v0.2 and stay there, and 99_REFERENCE_HISTORY holds
superseded manifests on purpose. This checks the executable baseline set.

Usage:
  db/gate/verify_version_consistency.py <package-root>
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

import yaml

VERSION_IN_NAME = re.compile(r"_v(\d+\.\d+(?:\.\d+)?)\.[a-z]+$")
SCHEMA_HEADER = re.compile(r"^--\s*TURAB\s*—\s*PostgreSQL schema v(\d+\.\d+(?:\.\d+)?)")
SEED_HEADER = re.compile(r"^--\s*TURAB\s*—\s*minimum master data seed v(\d+\.\d+(?:\.\d+)?)")
SCHEMA_METADATA = re.compile(r"\(\s*'schema_version'\s*,\s*'([^']+)'\s*\)")


class Claim:
    """One place a version is stated, and what it says."""

    def __init__(self, where: str, version: str | None, how: str) -> None:
        self.where = where
        self.version = version
        self.how = how

    def __repr__(self) -> str:
        return f"{self.where} = {self.version!r} ({self.how})"


def _one(root: pathlib.Path, pattern: str) -> pathlib.Path | None:
    matches = sorted(root.glob(pattern))
    return matches[-1] if matches else None


def _name_version(path: pathlib.Path) -> str | None:
    m = VERSION_IN_NAME.search(path.name)
    return m.group(1) if m else None


def collect(root: pathlib.Path) -> tuple[list[Claim], list[str]]:
    claims: list[Claim] = []
    errors: list[str] = []

    schema = _one(root / "04_DATABASE", "schema_v*.sql")
    seed = _one(root / "04_DATABASE", "seed_master_data_v*.sql")
    openapi = _one(root / "05_API", "openapi_v*.yaml")
    audit = _one(root / "07_QA_ACCEPTANCE", "technical_pack_static_audit_v*.py")
    results = _one(root / "07_QA_ACCEPTANCE", "STATIC_AUDIT_RESULTS_v*.json")
    manifest = _one(root / "07_QA_ACCEPTANCE", "TECHNICAL_PACK_MANIFEST_SHA256_v*.txt")

    for label, path in (
        ("schema", schema), ("seed", seed), ("openapi", openapi),
        ("static audit script", audit), ("static audit results", results),
        ("technical pack manifest", manifest),
    ):
        if path is None:
            errors.append(f"package is missing the {label} artifact")
        else:
            claims.append(Claim(f"{label} filename", _name_version(path), path.name))

    if schema:
        text = schema.read_text(encoding="utf-8")
        head = next((l for l in text.splitlines() if l.startswith("--")), "")
        m = SCHEMA_HEADER.match(head)
        claims.append(Claim("schema header", m.group(1) if m else None, head.strip()))
        m = SCHEMA_METADATA.search(text)
        claims.append(
            Claim(
                "schema_metadata.schema_version",
                m.group(1) if m else None,
                "seeded row inside the schema",
            )
        )

    if seed:
        head = next((l for l in seed.read_text(encoding="utf-8").splitlines()
                     if l.startswith("--")), "")
        m = SEED_HEADER.match(head)
        claims.append(Claim("seed header", m.group(1) if m else None, head.strip()))

    if openapi:
        doc = yaml.safe_load(openapi.read_text(encoding="utf-8"))
        claims.append(
            Claim("openapi info.version", str(doc.get("info", {}).get("version")),
                  "info.version")
        )

    handoff = root / "HANDOFF_MANIFEST.json"
    if handoff.exists():
        baseline = str(json.loads(handoff.read_text(encoding="utf-8"))
                       .get("technical_baseline", ""))
        found = re.search(r"v(\d+\.\d+(?:\.\d+)?)", baseline)
        claims.append(
            Claim("HANDOFF_MANIFEST.technical_baseline",
                  found.group(1) if found else None, baseline[:60])
        )
    else:
        errors.append("package is missing HANDOFF_MANIFEST.json")

    return claims, errors


def verify(root: pathlib.Path) -> tuple[bool, list[str], list[Claim]]:
    claims, errors = collect(root)
    stated = [c for c in claims if c.version]

    for c in claims:
        if not c.version:
            errors.append(f"{c.where}: no version could be read ({c.how})")

    if stated:
        # The schema filename is the anchor: it names the executable baseline.
        anchor = next((c for c in stated if c.where == "schema filename"), stated[0])
        disagreeing = [c for c in stated if c.version != anchor.version]
        for c in disagreeing:
            errors.append(
                f"{c.where} says {c.version!r} but {anchor.where} says "
                f"{anchor.version!r} — {c.how}"
            )

    return not errors, errors, claims


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("package_root", type=pathlib.Path)
    args = ap.parse_args()

    ok, errors, claims = verify(args.package_root)

    width = max(len(c.where) for c in claims) if claims else 0
    for c in claims:
        mark = " " if c.version else "?"
        print(f"  {mark} {c.where.ljust(width)}  {c.version}")

    if ok:
        print("\nVERSION CONSISTENCY: PASS — every statement of the baseline "
              "version agrees")
        return 0
    print("\nVERSION CONSISTENCY: FAIL", file=sys.stderr)
    for e in errors:
        print(f"  - {e}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
