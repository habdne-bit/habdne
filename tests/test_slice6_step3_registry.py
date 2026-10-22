"""Slice 6 step 3: the diagnostic's functions in the registry (G6-11, G4-2).

Kept apart from `test_slice6_step3.py` on purpose: a pin fails on ANY edit of
a pinned function, so the mutation record of step 3, which runs that file,
shows only what its behavioural tests catch (as Slice 4 step 4's record).
"""
from __future__ import annotations

from turab.matching import registry, registry_history
from turab.matching.registry import REGISTRY



def test_the_three_functions_are_registered_pinned_and_recorded():
    keys = {r.key for r in REGISTRY.rules()}
    assert {"diagnostic.value@1", "diagnostic.actions@1", "diagnostic.relaxation@1"} <= keys
    assert REGISTRY.verify_pins(registry.load_pins()) == []
    [entry] = [e for e in registry_history.HISTORY if e["digest"] == REGISTRY.digest()]
    assert len(entry["pairs"]) == 23
    first = {p for p in registry_history.HISTORY[0]["pairs"]}
    assert first < set(entry["pairs"]), "the twenty earlier pairs are unchanged"
