#!/usr/bin/env python3
"""Which files the execution gate READS — derived, never asserted.

`record_gate_run.sh` marks each uncommitted path in its header according to
whether a change there could alter the gate's result. That is a claim about
OTHER scripts, and a hand-maintained list of prefixes drifts from them silently.

It did. The list named `docs/handoff`, `docs/api` and `db/gate`, taken from the
paths written literally in `run_gate.sh`. But step 7 invokes
`generate_effective_contract.py --check`, and THAT script reads
`docs/contract/CONTRACT_CORRECTIONS.yaml` — so a corrections file was labelled
"[other] cannot affect this run" while a comment-only edit to it flipped the
contract check from PASS to FAIL. A reviewer demonstrated exactly that.

The lesson is not "add one more prefix". A list of literal paths in the entry
script cannot see what the scripts it INVOKES read, so this module follows the
call chain instead:

    run_gate.sh
      -> every db/gate script it invokes
        -> every script THOSE invoke
          -> the repository paths any of them mention

Anything reachable that way is a gate input. The walk is textual and therefore
over-inclusive rather than under-inclusive, which is the safe direction for
this question: naming a file an input when it is not costs a cautious label,
while missing one produces a false assurance.

Usage:
  python db/gate/gate_inputs.py           # one path prefix per line
  python db/gate/gate_inputs.py --classify PATH   # gate-input | source | other
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: Repository-relative paths mentioned in a script. Deliberately loose.
_PATH = re.compile(r"(?<![\w./-])(?:docs|db|src|tests)/[A-Za-z0-9_./-]+")

#: A script the gate hands off to. Both `python x.py` and "$GATE_DIR/x.py".
_INVOKED = re.compile(r"[A-Za-z0-9_./$\{\}-]*?([A-Za-z0-9_-]+\.(?:py|sh))")

#: Covered by the source fingerprint (db/dev/source_fingerprint.py).
_SOURCE_PREFIXES = ("src/", "tests/", "db/", "alembic.ini")

ENTRY = "db/gate/run_gate.sh"


def _read(rel: str) -> str:
    path = ROOT / rel
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _script_candidates(text: str) -> set[str]:
    """Script FILENAMES a text invokes, resolved against the gate directory.

    Names are matched rather than full paths because the scripts are invoked
    through shell variables (`"$GATE_DIR/x.py"`), which no textual scan can
    expand reliably.
    """
    found: set[str] = set()
    for name in _INVOKED.findall(text):
        for candidate in (f"db/gate/{name}", f"db/dev/{name}"):
            if (ROOT / candidate).is_file():
                found.add(candidate)
    return found


def reachable_paths() -> set[str]:
    """Every repository path reachable from the gate's entry script."""
    seen_scripts: set[str] = set()
    pending = [ENTRY]
    paths: set[str] = set()

    while pending:
        script = pending.pop()
        if script in seen_scripts:
            continue
        seen_scripts.add(script)
        text = _read(script)
        paths.update(_PATH.findall(text))
        paths.add(script)
        pending.extend(_script_candidates(text) - seen_scripts)

    return paths


def input_prefixes() -> set[str]:
    """The reachable paths, reduced to `<top>/<second>` prefixes.

    A prefix rather than an exact path, because the gate reads whole
    directories (`docs/handoff/...`) and because a file added beside one it
    reads is far more likely to be an input than not.
    """
    prefixes = set()
    for p in reachable_paths():
        parts = p.split("/")
        prefixes.add("/".join(parts[:2]) if len(parts) > 1 else parts[0])
    return prefixes


def classify(path: str) -> str:
    """`gate-input`, `source`, or `other` — in that order of precedence.

    Gate-input wins: `db/gate/*` is both, and what matters for the header is
    that changing it can change the result below.
    """
    prefixes = input_prefixes()
    parts = path.split("/")
    prefix = "/".join(parts[:2]) if len(parts) > 1 else parts[0]
    if prefix in prefixes:
        return "gate-input"
    if path.startswith(_SOURCE_PREFIXES):
        return "source"
    return "other"


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "--classify":
        print(classify(argv[1]))
        return 0
    for prefix in sorted(input_prefixes()):
        print(prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
