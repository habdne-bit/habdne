"""Slice 4 step 1, migration 0005: which guard refuses which write.

Z1 and Z4 first turned the guard into an AFTER INSERT trigger. That made the
fixture's own insert raise, so the tests ERRORED instead of testing an
unguarded table, and the runner (rightly) did not count an error as a kill.
They now remove the CREATE TRIGGER statement, which is what "unguarded"
means. The first run is kept in the evidence.

    .venv/bin/python db/dev/mutate_0005.py [Z1 Z2 ...] > /outside/the/tree.txt

The suite's database is rebuilt by `alembic upgrade head` at session start,
so a mutated migration is what the tests run against. See `mutation_runner.py`.
"""
import sys

from mutation_runner import run

MIG = "db/migrations/versions/0005_match_history_immutability.py"

MUTATIONS = [
 ("Z1 criterion results unguarded (trigger not created)", MIG,
  '"""CREATE TRIGGER prevent_match_criterion_result_update\n'
  '             BEFORE UPDATE OR DELETE ON turab.match_criterion_results\n'
  '             FOR EACH ROW EXECUTE FUNCTION turab.prevent_immutable_history_change()"""',
  '"SELECT 1"'),
 ("Z2 criterion results guarded against DELETE only", MIG,
  "BEFORE UPDATE OR DELETE ON turab.match_criterion_results",
  "BEFORE DELETE ON turab.match_criterion_results"),
 ("Z3 criterion results guarded against UPDATE only", MIG,
  "BEFORE UPDATE OR DELETE ON turab.match_criterion_results",
  "BEFORE UPDATE ON turab.match_criterion_results"),
 ("Z4 diagnostic runs unguarded (trigger not created)", MIG,
  '"""CREATE TRIGGER prevent_match_diagnostic_run_update\n'
  '             BEFORE UPDATE OR DELETE ON turab.match_diagnostic_runs\n'
  '             FOR EACH ROW EXECUTE FUNCTION turab.prevent_immutable_history_change()"""',
  '"SELECT 1"'),
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
