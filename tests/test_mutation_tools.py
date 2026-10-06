"""The mutation scripts in db/dev/ run only when executed, never on import.

Ref: the review of f5a9d88 (Slice 5 step 1, decision 3); Slice 5 step 1
delivery §4.3. Importing `mutate_input_hardening.py`, which had no
`__main__` guard, started its mutation run against the production code.
`evidence/MUTATE-INPUT-HARDENING-IMPORT-BEFORE-FIX.txt` records that, measured
in an isolated worktree: the import ran the baseline suite and then mutated
`src/turab/services/truth.py`.

**Safety of these tests themselves.** Each import runs in a temporary COPY of
`src`, `tests` and `db`, with no `.venv`. If a script did run on import, it
could neither start pytest nor touch the real tree: it would fail, and the
test would report it.
"""
from __future__ import annotations

import ast
import hashlib
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = sorted(p.name for p in (ROOT / "db" / "dev").glob("mutate_*.py"))


def _snapshot(tree: pathlib.Path) -> dict[str, str]:
    return {str(p.relative_to(tree)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in tree.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


@pytest.fixture(scope="module")
def copy(tmp_path_factory) -> pathlib.Path:
    tree = tmp_path_factory.mktemp("tree")
    ignore = shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.orig")
    for d in ("src", "tests", "db"):
        shutil.copytree(ROOT / d, tree / d, ignore=ignore)
    return tree


def test_there_are_mutation_scripts_to_check():
    assert "mutate_input_hardening.py" in SCRIPTS and len(SCRIPTS) >= 14, SCRIPTS


@pytest.mark.parametrize("script", SCRIPTS)
def test_importing_a_mutation_script_runs_nothing_and_changes_nothing(copy, script):
    """The import succeeds, prints nothing (the run header is the first thing
    a run prints), starts nothing, and leaves every file of the copy as it
    was, with no `.orig` backup."""
    before = _snapshot(copy)
    module = script[:-3]
    result = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, 'db/dev'); import {module}; "
         f"print('IMPORTED', len(getattr({module}, 'MUTATIONS', getattr({module}, 'M', []))))"],
        cwd=copy, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().startswith("IMPORTED"), (
        f"{script} printed on import, so it ran:\n{result.stdout[:500]}")
    assert int(result.stdout.split()[-1]) > 0, "the mutation list is still defined"
    after = _snapshot(copy)
    assert after == before, sorted(k for k in set(after) | set(before)
                                   if after.get(k) != before.get(k))


@pytest.mark.parametrize("script", SCRIPTS)
def test_a_mutation_script_runs_only_under_its_main_guard(script):
    """Structural: at module level, no call is made as a statement, and no
    loop, `with` or `try` runs. The run sits behind `if __name__ ==
    "__main__"`. The import test above is the behavioural proof; this one
    names the shape that would make an import run."""
    tree = ast.parse((ROOT / "db" / "dev" / script).read_text())
    guard = [n for n in tree.body if isinstance(n, ast.If)
             and ast.unparse(n.test) in ('__name__ == "__main__"', "__name__ == '__main__'")]
    assert len(guard) == 1, f"{script}: no single __main__ guard"
    for i, node in enumerate(tree.body):
        if i == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue  # the docstring
        assert not isinstance(node, (ast.Expr, ast.For, ast.While, ast.With, ast.Try)), (
            f"{script}, line {node.lineno}: `{ast.unparse(node)[:60]}` runs on import")


def test_input_hardening_runs_its_main_with_the_command_line_selection():
    """Direct invocation is unchanged: the guard passes `sys.argv[1:]` to
    `main`, which is what the former module-level `only = sys.argv[1:]`
    held. The rerun of the script, recorded on a clean tree, is the proof
    that its results are unchanged."""
    tree = ast.parse((ROOT / "db" / "dev" / "mutate_input_hardening.py").read_text())
    [guard] = [n for n in tree.body if isinstance(n, ast.If)]
    assert [ast.unparse(s) for s in guard.body] == ["main(sys.argv[1:])"]
    [main] = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"]
    assert [a.arg for a in main.args.args] == ["only"]
