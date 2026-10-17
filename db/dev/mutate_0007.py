"""Slice 6 step 1, migration 0007: which guard refuses which write.

    .venv/bin/python db/dev/mutate_0007.py [A1 C2 ...] > /outside/the/tree.txt

Each mutation weakens ONE part of `0007_task_work_and_evidence.py`, as plan
§5.1 writes it:
- A1-A3: part A, the append-only events;
- B1-B4: part B, the four outcome codes;
- C1-C12: part C, the index: absent, its two predicates, each key component,
  each coalesce;
- D1-D4: part D, the guard on cited observations.

The suite's database is rebuilt by `alembic upgrade head` at session start,
so a mutated migration is what the tests run against. See
`mutation_runner.py`.
"""
import sys

from mutation_runner import run

MIG = "db/migrations/versions/0007_task_work_and_evidence.py"
TESTS = "tests/test_migration_0007_task_work_and_evidence.py"

KEY = {
    "request_id": "               request_id,\n",
    "entity": "               (payload -> 'subject' ->> 'entity'),\n",
    "id": "               (payload -> 'subject' ->> 'id'),\n",
    "gate": "               (payload -> 'subject' ->> 'gate'),\n",
    "criterion": "               (coalesce(payload -> 'subject' ->> 'criterion', '')),\n",
    "ordinal": "               (coalesce(payload -> 'subject' ->> 'ordinal', '')),\n",
}

MUTATIONS = [
 # --- A ---------------------------------------------------------------------------
 ("A1 part A trigger not created", MIG,
  '''"""CREATE TRIGGER prevent_task_completion_event_change
             BEFORE UPDATE OR DELETE ON turab.task_completion_events
             FOR EACH ROW EXECUTE FUNCTION turab.prevent_immutable_history_change()"""''',
  '"SELECT 1"'),
 ("A2 part A on UPDATE only: an event may be deleted", MIG,
  "BEFORE UPDATE OR DELETE ON turab.task_completion_events",
  "BEFORE UPDATE ON turab.task_completion_events"),
 ("A3 part A on DELETE only: an event may be rewritten", MIG,
  "BEFORE UPDATE OR DELETE ON turab.task_completion_events",
  "BEFORE DELETE ON turab.task_completion_events"),
 # --- B ---------------------------------------------------------------------------
 ("B1 one outcome code not inserted", MIG,
  ",\n               ('TASK_NO_LONGER_NEEDED',        'لم تعد المهمة لازمة', 'The task is no longer needed')",
  ""),
 ("B2 the codes under another category", MIG,
  "SELECT v.code, 'TASK_OUTCOME', v.label_ar", "SELECT v.code, 'GENERAL', v.label_ar"),
 ("B3 the codes inserted inactive", MIG,
  "v.label_ar, v.label_en, true", "v.label_ar, v.label_en, false"),
 ("B4 a label other than the approved one", MIG,
  "'The information asked for was obtained'", "'The information was verified'"),
 # --- C ---------------------------------------------------------------------------
 ("C1 the index not created", MIG,
  '''"""CREATE UNIQUE INDEX ux_one_open_task_per_subject''',
  '''"""CREATE INDEX ux_one_open_task_per_subject'''),
 ("C2 the index covers OPEN only (T4: IN_PROGRESS lets a second in)", MIG,
  "WHERE status IN ('OPEN', 'IN_PROGRESS')", "WHERE status IN ('OPEN')"),
 ("C3 the index covers every writer (no source predicate)", MIG,
  "\n               AND payload ->> 'source' = 'DIAGNOSTIC'", ""),
] + [
 (f"C{4 + i} the key without {name}", MIG, line, "")
 for i, (name, line) in enumerate(KEY.items())
] + [
 ("C10 the key without basis", MIG,
  ",\n               (payload -> 'subject' ->> 'basis'))", ")"),
 ("C11 criterion not coalesced: two criterion-less subjects never conflict", MIG,
  "(coalesce(payload -> 'subject' ->> 'criterion', ''))",
  "(payload -> 'subject' ->> 'criterion')"),
 ("C12 ordinal not coalesced", MIG,
  "(coalesce(payload -> 'subject' ->> 'ordinal', ''))",
  "(payload -> 'subject' ->> 'ordinal')"),
 # --- D ---------------------------------------------------------------------------
 ("D1 part D trigger not created", MIG,
  '''"""CREATE TRIGGER trg_cited_observation_unchanged
             BEFORE UPDATE OR DELETE ON turab.observations
             FOR EACH ROW EXECUTE FUNCTION turab.prevent_cited_observation_change()"""''',
  '"SELECT 1"'),
 ("D2 part D on UPDATE only", MIG,
  "BEFORE UPDATE OR DELETE ON turab.observations", "BEFORE UPDATE ON turab.observations"),
 ("D3 part D on DELETE only", MIG,
  "BEFORE UPDATE OR DELETE ON turab.observations", "BEFORE DELETE ON turab.observations"),
 ("D4 part D refuses nothing", MIG,
  "IF EXISTS (SELECT 1 FROM turab.task_completion_events",
  "IF FALSE AND EXISTS (SELECT 1 FROM turab.task_completion_events"),
]

if __name__ == "__main__":
    run("TURAB — Slice 6 step 1: which guard of migration 0007 refuses which write",
        TESTS, MUTATIONS, sys.argv[1:])
