"""Slice 4 step 1, CORRECTION-004: which check refuses which narrowing.

    .venv/bin/python db/dev/mutate_correction_004.py [C1 C2 ...] > /outside/the/tree.txt

See `mutation_runner.py`.
"""
import sys

from mutation_runner import run

SRC = "src/turab/auth/contract.py"

MUTATIONS = [
 ("C1 unknown keys accepted", SRC, "        if unknown:\n", "        if False:\n"),
 ("C2 ids may repeat another correction's", SRC,
  "if not cid or cid in seen or cid in taken:", "if not cid or cid in seen:"),
 ("C3 no decision needed", SRC,
  "        if not entry.get(\"decision\"):\n            raise ContractError(f\"{cid}: names no decision\")",
  "        pass"),
 ("C4 a role-corrected operation may also be narrowed", SRC,
  "        if operation_id in role_corrected:", "        if False:"),
 ("C5 requiring nothing accepted", SRC,
  "        if not require:\n            raise ContractError(f\"{cid}: requires nothing\")",
  "        pass"),
 ("C6 an already-required field accepted", SRC,
  "            if field in already:", "            if False:"),
 ("C7 frozen defaults not compared", SRC,
  "        if dict(entry.get(\"frozen_defaults\") or {}) != declared:",
  "        if False:"),
 ("C8 not validated at startup", SRC,
  "    load_request_body_narrowings(contract=doc)\n", ""),
]

if __name__ == "__main__":
    run("TURAB — Slice 4 step 1: which check of CORRECTION-004 refuses which narrowing",
        "tests/test_correction_004.py", MUTATIONS, sys.argv[1:])
