"""The registry history that attributes a digest to every stored match (G4-19,
decided (a) in the review of c657bd9). Pure: no database.

Ref: `src/turab/matching/registry_history.py`;
`docs/gate/evidence/REGISTRY-HISTORY.txt` (the git evidence, produced by
`db/dev/registry_history_evidence.py`).
"""
from __future__ import annotations

from turab.matching import registry, registry_history


def test_each_recorded_digest_is_the_sha256_of_its_recorded_pairs():
    for entry in registry_history.HISTORY:
        assert registry_history.digest_of(entry["pairs"]) == entry["digest"]


def test_every_recorded_pair_is_still_pinned_with_the_same_source():
    """Pins only grow (G4-2): a recorded registry stays reproducible from the
    pins of today."""
    pins = registry.load_pins()
    for entry in registry_history.HISTORY:
        for rule_id, version, source in entry["pairs"]:
            assert pins[f"{rule_id}@{version}"] == source


def test_the_current_registry_is_recorded_in_the_history():
    """Registering a version without recording the new registry here fails,
    so every digest a new match records is attributable."""
    assert registry_history.known(registry.REGISTRY.digest())
    [entry] = [e for e in registry_history.HISTORY
               if e["digest"] == registry.REGISTRY.digest()]
    assert {(r.rule_id, r.rule_version, r.source_sha256())
            for r in registry.REGISTRY.rules()} == set(entry["pairs"])


def test_format_1_is_attributed_to_the_registry_of_7a223d7_alone():
    """Format 1 has exactly one digest: the first recorded registry, from
    7a223d7, the commit that introduced the run."""
    assert registry_history.FORMAT_DIGESTS == {
        "turab.match-explanation/1": registry_history.HISTORY[0]["digest"]}
    assert registry_history.HISTORY[0]["since"] == "7a223d7"
    assert len(registry_history.HISTORY[0]["pairs"]) == 20
