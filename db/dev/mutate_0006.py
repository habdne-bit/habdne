"""Slice 5 step 1, migration 0006: which guard refuses which write.

    .venv/bin/python db/dev/mutate_0006.py [H1 H2a ...] > /outside/the/tree.txt

Each mutation weakens ONE rule of `0006_opportunity_history.py`, as G5-12
(plan revision 4) lists them:
- H1–H4: rules 1–4;
- H5a–H5c: the three cases of rule 5;
- H6a–H6c: the three cases of rule 6;
- B1–B4: the birth rule.

H2a–H2j remove one column at a time from rule 2's written-once row, so
each column is shown to be guarded by a test that fails without it. H3b
and H3c add one forbidden edge each (B16, B11). H4b makes rule 4 one-way.

The suite's database is rebuilt by `alembic upgrade head` at session start,
so a mutated migration is what the tests run against. See
`mutation_runner.py`.
"""
import re
import sys

from mutation_runner import run

MIG = "db/migrations/versions/0006_opportunity_history.py"
TESTS = "tests/test_migration_0006_opportunity_history.py"

RULE_1 = ("""             IF OLD.status = 'CLOSED' THEN
               RAISE EXCEPTION 'Opportunity history: a CLOSED opportunity is final';
             END IF;
""")

ROW_NEW = ("(NEW.request_id, NEW.property_id, NEW.approved_match_id,\n"
           "                 NEW.commercial_context_snapshot, NEW.permission_snapshot, NEW.why_real,\n"
           "                 NEW.known_differences, NEW.sharing_scope, NEW.created_by_account_id,\n"
           "                 NEW.created_at)")
ROW_OLD = ROW_NEW.replace("NEW.", "OLD.")
COLUMNS = ["request_id", "property_id", "approved_match_id", "commercial_context_snapshot",
           "permission_snapshot", "why_real", "known_differences", "sharing_scope",
           "created_by_account_id", "created_at"]


def _without(column):
    """Rule 2's comparison with one column removed from both rows.

    The column may sit mid-line ("X, "), at a line end ("X,\n") or last
    ("\n   X)"). The first run's version matched only the first form, so
    four mutants (H2c, H2f, H2i, H2j) were identical to the original and
    were reported as survivors; `mutation_runner` now refuses a no-op."""
    block = f"{ROW_NEW}\n                IS DISTINCT FROM\n                {ROW_OLD}"

    def strip(row, side):
        out = re.sub(rf"{side}\.{column},\s*", "", row)
        if out == row:  # the last column: drop the separator before it
            out = re.sub(rf",\s*{side}\.{column}\)", ")", row)
        assert out != row, (column, "not removed")
        return out
    return block, f"{strip(ROW_NEW, 'NEW')}\n                IS DISTINCT FROM\n                " \
                  f"{strip(ROW_OLD, 'OLD')}"


MUTATIONS = [
 ("H1 rule 1 removed: a CLOSED row may change", MIG, RULE_1, ""),
 ("H2 rule 2 removed: nothing is written once", MIG,
  f"IF {ROW_NEW}\n                IS DISTINCT FROM", f"IF FALSE AND {ROW_NEW}\n                IS DISTINCT FROM"),
] + [
 (f"H2{chr(ord('a') + i)} rule 2 without {c}", MIG, *_without(c))
 for i, c in enumerate(COLUMNS)
] + [
 ("H3 rule 3 removed: any status change", MIG,
  "IF NEW.status IS DISTINCT FROM OLD.status\n                AND",
  "IF FALSE AND NEW.status IS DISTINCT FROM OLD.status\n                AND"),
 ("H3b rule 3 admits SHARED -> NEW (B16)", MIG,
  "('ENGAGED', 'CLOSED')) THEN", "('ENGAGED', 'CLOSED'), ('SHARED', 'NEW')) THEN"),
 ("H3c rule 3 admits NEW -> ENGAGED (B11)", MIG,
  "('ENGAGED', 'CLOSED')) THEN", "('ENGAGED', 'CLOSED'), ('NEW', 'ENGAGED')) THEN"),
 ("H4 rule 4 removed: closing fields free", MIG,
  "IF (NEW.closed_at IS NOT NULL) <> (NEW.status = 'CLOSED')\n"
  "                OR (NEW.close_reason_code IS NOT NULL) <> (NEW.status = 'CLOSED') THEN",
  "IF FALSE THEN"),
 ("H4b rule 4 one-way: closed_at may be set while not CLOSED (B13)", MIG,
  "IF (NEW.closed_at IS NOT NULL) <> (NEW.status = 'CLOSED')\n"
  "                OR (NEW.close_reason_code IS NOT NULL) <> (NEW.status = 'CLOSED') THEN",
  "IF (NEW.status = 'CLOSED') AND (NEW.closed_at IS NULL OR NEW.close_reason_code IS NULL) THEN"),
 ("H4c rule 4 checks closed_at only, not the reason", MIG,
  "\n                OR (NEW.close_reason_code IS NOT NULL) <> (NEW.status = 'CLOSED') THEN",
  " THEN"),
 ("H5a rule 5, case 1: shared_at may move once set (B17)", MIG,
  "IF NEW.shared_at IS DISTINCT FROM OLD.shared_at THEN", "IF FALSE THEN"),
 ("H5b rule 5, case 2: NEW -> SHARED without shared_at", MIG,
  "IF NEW.shared_at IS NULL THEN", "IF FALSE THEN"),
 ("H5c rule 5, case 3: shared_at for an event that did not happen", MIG,
  "ELSIF NEW.shared_at IS NOT NULL THEN", "ELSIF FALSE THEN"),
 ("H6a rule 6, case 1: engaged_at may move once set", MIG,
  "IF NEW.engaged_at IS DISTINCT FROM OLD.engaged_at THEN", "IF FALSE THEN"),
 ("H6b rule 6, case 2: SHARED -> ENGAGED without engaged_at", MIG,
  "IF NEW.engaged_at IS NULL THEN", "IF FALSE THEN"),
 ("H6c rule 6, case 3: engaged_at for an event that did not happen", MIG,
  "ELSIF NEW.engaged_at IS NOT NULL THEN", "ELSIF FALSE THEN"),
 ("B1 birth trigger not created", MIG,
  '"""CREATE TRIGGER trg_opportunity_birth\n'
  '             BEFORE INSERT ON turab.opportunities\n'
  '             FOR EACH ROW EXECUTE FUNCTION turab.enforce_opportunity_birth()"""',
  '"SELECT 1"'),
 ("B2 birth admits any status", MIG,
  "IF NEW.status <> 'NEW' OR NEW.validity_status", "IF NEW.validity_status"),
 ("B3 birth admits any validity", MIG,
  "OR NEW.validity_status <> 'VALID'\n", "\n"),
 ("B4 birth admits event times", MIG,
  "                OR NEW.shared_at IS NOT NULL OR NEW.engaged_at IS NOT NULL\n"
  "                OR NEW.closed_at IS NOT NULL OR NEW.close_reason_code IS NOT NULL THEN",
  " THEN"),
 ("T1 history trigger not created", MIG,
  '"""CREATE TRIGGER trg_opportunity_history\n'
  '             BEFORE UPDATE ON turab.opportunities\n'
  '             FOR EACH ROW EXECUTE FUNCTION turab.enforce_opportunity_history()"""',
  '"SELECT 1"'),
]

if __name__ == "__main__":
    run("TURAB — Slice 5 step 1: which guard of migration 0006 refuses which write",
        TESTS, MUTATIONS, sys.argv[1:])
