#!/usr/bin/env python3
"""One number for "this exact source tree", so a review round can be pinned.

The previous rounds computed this with an ad-hoc shell pipeline that was
never committed, which means the recorded value could not be reproduced by a
reviewer. The recipe therefore lives here now, and the value recorded in
`docs/gate/evidence/TEST-RUN-PROVENANCE.txt` and `gate-run.txt`
carry this script's output, each bound to the run it describes.

Recipe, deliberately simple enough to re-implement in any language:

  1. Collect every file under src/, tests/ and db/ whose suffix is one of
     .py .sql .sh .ini .mako, plus alembic.ini at the repository root.
  2. Sort the POSIX-style paths, relative to the repository root, as byte
     strings (not locale-aware ordering).
  3. For each, emit "<sha256 of the file bytes>  <path>\n".
  4. The fingerprint is the sha256 of that concatenation.

Content AND layout are covered: moving a file to a new name changes the
value even when no byte of any file changes. This says nothing about the
database — `baseline_fingerprint.py` is the structural fingerprint of the
schema, and the two answer different questions.

Usage: python db/dev/source_fingerprint.py [--list] [repository root]
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

SUFFIXES = {".py", ".sql", ".sh", ".ini", ".mako"}
TREES = ("src", "tests", "db")
EXTRA = ("alembic.ini",)


def _files(root: Path) -> list[Path]:
    found: set[Path] = set()
    for tree in TREES:
        for path in (root / tree).rglob("*"):
            if path.is_file() and path.suffix in SUFFIXES:
                found.add(path)
    for name in EXTRA:
        candidate = root / name
        if candidate.is_file():
            found.add(candidate)
    return sorted(found, key=lambda p: p.relative_to(root).as_posix().encode())


def lines(root: Path) -> list[str]:
    out = []
    for path in _files(root):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        out.append(f"{digest}  {path.relative_to(root).as_posix()}\n")
    return out


def fingerprint(root: Path) -> str:
    return hashlib.sha256("".join(lines(root)).encode()).hexdigest()


def main(argv: list[str]) -> int:
    show = "--list" in argv
    rest = [a for a in argv if not a.startswith("--")]
    root = Path(rest[0] if rest else ".").resolve()
    if show:
        sys.stdout.write("".join(lines(root)))
    print(fingerprint(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
