"""The version-consistency invariant.

Ref: deviation D6. A version stated in eleven places and wrong in one, which
every runtime test passed over because nothing executable reads it.

A check that only ever fails is as useless as one that only ever passes, so
both directions are tested.
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil

import pytest

from db_gate_version_consistency import verify  # type: ignore

PACKAGE = pathlib.Path(__file__).resolve().parents[1] / "docs" / "handoff"


@pytest.fixture
def package_copy(tmp_path):
    dest = tmp_path / "pkg"
    shutil.copytree(PACKAGE, dest)
    return dest


def _baseline_version(root: pathlib.Path) -> str:
    """Read the version from the schema filename.

    Derived, never hardcoded: these tests must survive the next version bump
    without edits, which is the whole point of a version-agnostic invariant.
    """
    schema = next((root / "04_DATABASE").glob("schema_v*.sql"))
    return re.search(r"schema_v(\d+\.\d+(?:\.\d+)?)\.sql", schema.name).group(1)


def _set_schema_metadata(root: pathlib.Path, value: str) -> None:
    schema = next((root / "04_DATABASE").glob("schema_v*.sql"))
    text = schema.read_text(encoding="utf-8")
    text = re.sub(r"\('schema_version','[^']+'\)", f"('schema_version','{value}')", text)
    schema.write_text(text, encoding="utf-8")


def test_the_adopted_package_is_version_consistent():
    """v0.2.3 resolved D6. The two tests that documented the finding were
    deleted rather than inverted, because the finding no longer exists."""
    ok, errors, claims = verify(PACKAGE)
    assert ok, errors
    stated = [c for c in claims if c.version]
    assert len(stated) == 11
    assert len({c.version for c in stated}) == 1


def test_a_consistent_package_passes(package_copy):
    """The positive direction, on the package exactly as shipped."""
    ok, errors, _claims = verify(package_copy)
    assert ok, errors


@pytest.mark.parametrize(
    "mutate,expected",
    [
        ("schema_metadata", "schema_metadata.schema_version"),
        ("schema_header", "schema header"),
        ("seed_header", "seed header"),
        ("openapi_info", "openapi info.version"),
        ("manifest_baseline", "HANDOFF_MANIFEST.technical_baseline"),
        ("schema_filename", "filename"),
    ],
)
def test_drift_in_any_single_place_is_caught(package_copy, mutate, expected):
    """Every claim is load-bearing: break one and the invariant fires."""
    version = _baseline_version(package_copy)
    db = package_copy / "04_DATABASE"
    schema = next(db.glob("schema_v*.sql"))

    if mutate == "schema_metadata":
        _set_schema_metadata(package_copy, "9.9.9")
    elif mutate == "schema_header":
        text = schema.read_text(encoding="utf-8").replace(
            f"PostgreSQL schema v{version}", "PostgreSQL schema v9.9.9", 1
        )
        schema.write_text(text, encoding="utf-8")
    elif mutate == "seed_header":
        seed = next(db.glob("seed_master_data_v*.sql"))
        text = seed.read_text(encoding="utf-8").replace(
            f"master data seed v{version}", "master data seed v9.9.9", 1
        )
        seed.write_text(text, encoding="utf-8")
    elif mutate == "openapi_info":
        api = next((package_copy / "05_API").glob("openapi_v*.yaml"))
        text = api.read_text(encoding="utf-8").replace(
            f"  version: {version}", "  version: 9.9.9", 1
        )
        api.write_text(text, encoding="utf-8")
    elif mutate == "manifest_baseline":
        mf = package_copy / "HANDOFF_MANIFEST.json"
        data = json.loads(mf.read_text(encoding="utf-8"))
        data["technical_baseline"] = "v9.9.9 something"
        mf.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    elif mutate == "schema_filename":
        schema.rename(db / "schema_v9.9.9.sql")

    ok, errors, _claims = verify(package_copy)
    assert not ok, f"drift in {mutate} was not caught"
    assert any(expected in e for e in errors), errors


def test_a_missing_artifact_is_an_error(package_copy):
    next((package_copy / "04_DATABASE").glob("seed_master_data_v*.sql")).unlink()
    ok, errors, _claims = verify(package_copy)
    assert not ok
    assert any("missing the seed artifact" in e for e in errors)
