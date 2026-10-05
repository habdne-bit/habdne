#!/usr/bin/env python3
"""The git evidence for `registry_history.HISTORY[0]` (G4-19).

    .venv/bin/python db/dev/registry_history_evidence.py > /outside/the/tree.txt

It shows, from git alone:
1. the pins file at 7a223d7, its sha256, and the digest its 20 pins give;
2. that this digest is the one `registry_history` records, and the live
   registry's;
3. every commit since 7a223d7 that touched the registry's files: only
   7a223d7 itself, so every match written with explanation format 1 (from
   7a223d7 until format 2) was evaluated under that one registry.
"""
from __future__ import annotations

import ast
import hashlib
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from turab.matching import registry, registry_history  # noqa: E402

FILES = ("src/turab/matching/rule_pins.py", "src/turab/matching/gates.py",
         "src/turab/matching/rules.py", "src/turab/matching/registry.py")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout


def main() -> int:
    entry = registry_history.HISTORY[0]
    since = entry["since"]
    pins_text = git("show", f"{since}:src/turab/matching/rule_pins.py")
    pins = next(ast.literal_eval(n.value) for n in ast.parse(pins_text).body
                if isinstance(n, (ast.Assign, ast.AnnAssign)) and isinstance(n.value, ast.Dict))
    from_git = registry_history.digest_of(
        (k.split("@")[0], k.split("@")[1], v) for k, v in pins.items())
    print("TURAB — the registry history's first entry, from git (G4-19)")
    print("=" * 60)
    print(f"HEAD                          : {git('rev-parse', 'HEAD').strip()}")
    print(f"entry 'since'                 : {since} ({git('rev-parse', since).strip()})")
    print(f"rule_pins.py at {since} sha256: "
          f"{hashlib.sha256(pins_text.encode('utf-8')).hexdigest()}")
    print(f"pins at {since}              : {len(pins)}")
    print(f"digest of those pins          : {from_git}")
    print(f"digest recorded in HISTORY[0] : {entry['digest']}")
    print(f"digest of the live registry   : {registry.REGISTRY.digest()}")
    pairs_match = {f"{i}@{v}": s for i, v, s in entry["pairs"]} == pins
    print(f"HISTORY[0] pairs == pins at {since}: {pairs_match}")
    print()
    print(f"--- commits touching the registry's files, {since}~1..HEAD ---")
    print(git("log", "--format=%h %s", f"{since}~1..HEAD", "--", *FILES).rstrip())
    ok = from_git == entry["digest"] and pairs_match
    print()
    print("RESULT:", "the entry is the registry of " + since if ok else "MISMATCH")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
