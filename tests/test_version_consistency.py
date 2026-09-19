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


def _set_schema_metadata(root: pathlib.Path, value: str) -> None:
    schema = next((root / "04_DATABASE").glob("schema_v*.sql"))
    text = schema.read_text(encoding="utf-8")
    text = re.sub(r"\('schema_version','[^']+'\)", f"('schema_version','{value}')", text)
    schema.write_text(text, encoding="utf-8")


def test_the_adopted_package_still_carries_d6(package_copy):
    """Documents the open finding rather than asserting it away.

    When v0.2.3 lands this test is deleted, not adjusted: the finding will no
    longer exist.
    """
    ok, errors, claims = verify(package_copy)
    assert not ok
    assert len(errors) == 1, f"expected D6 alone, got {errors}"
    assert "schema_metadata.schema_version" in errors[0]
    assert "'0.2.1'" in errors[0]


def test_d6_is_the_only_version_drift_in_the_package(package_copy):
    """Ten of the eleven claims agree, which is why D6 was a single defect
    rather than a systemically mis-versioned package."""
    _ok, _errors, claims = verify(package_copy)
    stated = [c for c in claims if c.version]
    assert len(stated) == 11
    agreeing = [c for c in stated if c.version == "0.2.2"]
    assert len(agreeing) == 10


def test_a_consistent_package_passes(package_copy):
    """The positive direction: correct D6 in a copy and the invariant is clean."""
    _set_schema_metadata(package_copy, "0.2.2")
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
    _set_schema_metadata(package_copy, "0.2.2")  # start from a clean package
    db = package_copy / "04_DATABASE"
    schema = next(db.glob("schema_v*.sql"))

    if mutate == "schema_metadata":
        _set_schema_metadata(package_copy, "9.9.9")
    elif mutate == "schema_header":
        text = schema.read_text(encoding="utf-8").replace(
            "PostgreSQL schema v0.2.2", "PostgreSQL schema v9.9.9", 1
        )
        schema.write_text(text, encoding="utf-8")
    elif mutate == "seed_header":
        seed = next(db.glob("seed_master_data_v*.sql"))
        text = seed.read_text(encoding="utf-8").replace(
            "master data seed v0.2.2", "master data seed v9.9.9", 1
        )
        seed.write_text(text, encoding="utf-8")
    elif mutate == "openapi_info":
        api = next((package_copy / "05_API").glob("openapi_v*.yaml"))
        text = api.read_text(encoding="utf-8").replace(
            "  version: 0.2.2", "  version: 9.9.9", 1
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
