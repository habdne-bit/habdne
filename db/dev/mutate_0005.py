"""Slice 4 step 1, migration 0005: which guard refuses which write.

    .venv/bin/python db/dev/mutate_0005.py [Z1 Z2 ...] > /outside/the/tree.txt

The suite's database is rebuilt by `alembic upgrade head` at session start,
so a mutated migration is what the tests run against. See `mutation_runner.py`.
"""
import sys

from mutation_runner import run

MIG = "db/migrations/versions/0005_match_history_immutability.py"

MUTATIONS = [
 ("Z1 criterion results unguarded", MIG,
  "BEFORE UPDATE OR DELETE ON turab.match_criterion_results",
  "AFTER INSERT ON turab.match_criterion_results"),
 ("Z2 criterion results guarded against DELETE only", MIG,
  "BEFORE UPDATE OR DELETE ON turab.match_criterion_results",
  "BEFORE DELETE ON turab.match_criterion_results"),
 ("Z3 criterion results guarded against UPDATE only", MIG,
  "BEFORE UPDATE OR DELETE ON turab.match_criterion_results",
  "BEFORE UPDATE ON turab.match_criterion_results"),
 ("Z4 diagnostic runs unguarded", MIG,
  "BEFORE UPDATE OR DELETE ON turab.match_diagnostic_runs",
  "AFTER INSERT ON turab.match_diagnostic_runs"),
 ("Z5 diagnostic runs guarded against UPDATE only", MIG,
  "BEFORE UPDATE OR DELETE ON turab.match_diagnostic_runs",
  "BEFORE UPDATE ON turab.match_diagnostic_runs"),
 ("Z6 policy rules may change", MIG,
  "               OR NEW.rules     IS DISTINCT FROM OLD.rules\n", ""),
 ("Z7 policy version may change", MIG,
  "                  NEW.version   IS DISTINCT FROM OLD.version\n               OR ",
  "                  "),
 ("Z8 policy name may change", MIG,
  "               OR NEW.name      IS DISTINCT FROM OLD.name\n", ""),
 ("Z9 policy immutability may be lifted", MIG,
  "\n               OR NEW.immutable IS DISTINCT FROM OLD.immutable)", ")"),
 ("Z10 a mutable policy is guarded too", MIG,
  "IF OLD.immutable AND (", "IF (OLD.immutable OR NOT OLD.immutable) AND ("),
 ("Z11 activation is guarded too", MIG,
  "               OR NEW.immutable IS DISTINCT FROM OLD.immutable)",
  "               OR NEW.immutable IS DISTINCT FROM OLD.immutable\n"
  "               OR NEW.active    IS DISTINCT FROM OLD.active)"),
]

if __name__ == "__main__":
    run("TURAB — Slice 4 step 1: which guard of migration 0005 refuses which write",
        "tests/test_migration_0005_match_history.py", MUTATIONS, sys.argv[1:])
