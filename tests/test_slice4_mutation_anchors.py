"""The step-4 mutation evidence reaches the rule versions a new evaluation uses.

Found in the review of f789a59's fix: mutation R22's anchor matched only
`attribute_option@1`, which no evaluation selects, and it "survived" for that
reason alone. Anchors shared by versions 1 and 2 mutate both; an anchor that
reaches only an unused version proves nothing.

This test lives outside `tests/test_slice4_step4.py`, which is the file the
mutation runner executes. Inside it, a mutated `rules.py` would fail this
test and kill every mutation for the wrong reason.
"""
from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _functions(path: pathlib.Path) -> dict[str, str]:
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    out = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef):
            start = node.decorator_list[0].lineno if node.decorator_list else node.lineno
            out[node.name] = "".join(lines[start - 1:node.end_lineno])
    return out


def test_every_rule_mutation_reaches_the_version_in_use():
    sys.path.insert(0, str(ROOT / "db" / "dev"))
    try:
        import mutate_slice4_step4 as mutations
    finally:
        sys.path.pop(0)
    from turab.matching import criteria, registry

    in_use = {(rule_id, version) for rule_id, version, _ in criteria.RULES.values()}
    in_use.add(criteria.NO_RULE)
    function_of = {(r.rule_id, r.rule_version): r.evaluate.__name__
                   for r in registry.REGISTRY.rules()}
    used_functions = {function_of[key] for key in in_use}
    bodies = _functions(ROOT / "src" / "turab" / "matching" / "rules.py")
    problems = []
    for name, rel, anchor, _ in mutations.MUTATIONS:
        if not rel.endswith("rules.py"):
            continue
        reached = {f for f, body in bodies.items() if anchor in body}
        if not reached & used_functions:
            problems.append((name, sorted(reached)))
    assert problems == []


def test_every_gate_mutation_reaches_the_version_in_use():
    """The same guard for `gates.py` (steps 5 and 6): since the review of
    0cf6a7a, `score.soft@1` and `@2` share most of their text, and a mutation
    reaching only version 1 would prove nothing."""
    sys.path.insert(0, str(ROOT / "db" / "dev"))
    try:
        import mutate_slice4_step5 as step5
        import mutate_slice4_step6 as step6
    finally:
        sys.path.pop(0)
    from turab.matching import eligibility, registry, snapshots, soft

    in_use = set(eligibility.ENGINE.values()) | {soft.SOFT_SCORE, snapshots.FRESHNESS_STATE,
                                                 snapshots.BINDING_STATE}
    function_of = {(r.rule_id, r.rule_version): r.evaluate.__name__
                   for r in registry.REGISTRY.rules()}
    used_functions = {function_of[key] for key in in_use}
    bodies = _functions(ROOT / "src" / "turab" / "matching" / "gates.py")
    problems = []
    for name, rel, anchor, _ in step5.MUTATIONS + step6.MUTATIONS:
        if not rel.endswith("gates.py"):
            continue
        reached = {f for f, body in bodies.items() if anchor in body}
        if not reached & used_functions:
            problems.append((name, sorted(reached)))
    assert problems == []
