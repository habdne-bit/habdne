"""Slice 6 step 2, the task list and the completion: which test refuses which
weakening.

    .venv/bin/python db/dev/mutate_slice6_step2.py [L1 K1 ...] > /outside/the/tree.txt

Each mutation weakens ONE rule (plan revision 6; G6-8, G6-9, §3.7,
CORRECTION-005), in `services/tasks.py`, the route, `CommandService`,
`AccessService`, `audit_rows` or the contract loader:
- L: the completion's locks and their order (G6-8 (i), (iv); F6-18). L2 and
  L3 are the review of b6a08e7's condition: without the FOR SHARE, R2a must
  become R1a;
- C: which tasks a completion accepts (G6-8 (i), (vii));
- E: the evidence observation (G6-8 (iii), (iv) R2d);
- W: what the completion writes (§3.6);
- A: the audit (§3.7);
- G: the list (G6-9);
- R: the route (CORRECTION-005's body, the recorded denial of an unknown id);
- K: the loader's extension (F6-19), against `tests/test_correction_005.py`.

Run in two parts, one per test file; each part prints its own header. See
`mutation_runner.py`.
"""
import sys

from mutation_runner import run

SVC = "src/turab/services/tasks.py"
ROUTE = "src/turab/api/routes/tasks.py"
CMD = "src/turab/services/command.py"
ACCESS = "src/turab/services/access.py"
AUDIT = "src/turab/services/audit_rows.py"
CONTRACT = "src/turab/auth/contract.py"
TESTS = "tests/test_slice6_step2.py"
CONTRACT_TESTS = "tests/test_correction_005.py"

PREPARE_ORDER = '''    task = _lock_task(session, task_id)
    if task is None:
        # The route checked existence first, and no path deletes a task;
        # the same answer, kept in case it is reached.
        raise TaskRefused("OBJECT_NOT_AUTHORIZED", "not an available task")
    if task["status"] not in COMPLETABLE:
        raise TaskRefused("TASK_NOT_OPEN",
                          f"the task is {task['status']}; only an OPEN or IN_PROGRESS "
                          "task is completed")
    if evidence_observation_id is not None and not _lock_observation(
            session, evidence_observation_id):
        raise TaskRefused("EVIDENCE_OBSERVATION_NOT_FOUND",
                          "the evidence observation does not exist")'''
OBSERVATION_FIRST = '''    if evidence_observation_id is not None and not _lock_observation(
            session, evidence_observation_id):
        raise TaskRefused("EVIDENCE_OBSERVATION_NOT_FOUND",
                          "the evidence observation does not exist")
    task = _lock_task(session, task_id)
    if task is None:
        raise TaskRefused("OBJECT_NOT_AUTHORIZED", "not an available task")
    if task["status"] not in COMPLETABLE:
        raise TaskRefused("TASK_NOT_OPEN",
                          f"the task is {task['status']}; only an OPEN or IN_PROGRESS "
                          "task is completed")'''
EVIDENCE_CHECK = '''    if evidence_observation_id is not None and not _lock_observation(
            session, evidence_observation_id):
        raise TaskRefused("EVIDENCE_OBSERVATION_NOT_FOUND",
                          "the evidence observation does not exist")'''
EVIDENCE_UNCHECKED = '''    if evidence_observation_id is not None:
        _lock_observation(session, evidence_observation_id)'''
EVENT_AUDIT = '''    audit_rows.write(session, "task_completion_events", event["task_completion_event_id"],
                     "INSERT", None, audit_rows.row_json(
                         session, "task_completion_events",
                         event["task_completion_event_id"]))'''
TASK_AUDIT = '''    audit_rows.write(session, "tasks", prepared.task_id, "UPDATE", before,
                     audit_rows.row_json(session, "tasks", prepared.task_id))'''
LIST_AUDIT = '''        self.record_list_access(
            operation_id=operation_id, resource_kind=TASK_KIND, result_count=len(items),'''
TASK_DENIAL = '''            self._auditor.denied(
                subject=self._subject, operation_id=operation_id,
                trace_id=self._trace_id,
                reason_code=DenyReason.OBJECT_NOT_AUTHORIZED.value,
                resource_kind=TASK_KIND, resource_id=task_id)
            return deny(DenyReason.OBJECT_NOT_AUTHORIZED, "not an available task")'''

MUTATIONS = [
    # --- L: the locks and their order (G6-8 (iv)) --------------------------------------
    ("L1 task not locked", SVC, 'WHERE task_id = :t FOR UPDATE"),', 'WHERE task_id = :t"),'),
    ("L2 observation not locked", SVC,
     '"SELECT 1 FROM turab.observations WHERE observation_id = :o FOR SHARE"',
     '"SELECT 1 FROM turab.observations WHERE observation_id = :o"'),
    ("L3 observation locked FOR KEY SHARE, the FK's mode", SVC,
     "WHERE observation_id = :o FOR SHARE", "WHERE observation_id = :o FOR KEY SHARE"),
    ("L4 observation locked before the task", SVC, PREPARE_ORDER, OBSERVATION_FIRST),
    # --- C: which tasks (G6-8 (i), (vii)) ------------------------------------------------
    ("C1 a DONE task is completed again", SVC,
     'COMPLETABLE = ("OPEN", "IN_PROGRESS")', 'COMPLETABLE = ("OPEN", "IN_PROGRESS", "DONE")'),
    ("C2 a CANCELLED task is completed", SVC,
     'COMPLETABLE = ("OPEN", "IN_PROGRESS")',
     'COMPLETABLE = ("OPEN", "IN_PROGRESS", "CANCELLED")'),
    ("C3 IN_PROGRESS is not completed", SVC,
     'COMPLETABLE = ("OPEN", "IN_PROGRESS")', 'COMPLETABLE = ("OPEN",)'),
    # --- E: the evidence (G6-8 (iii), R2d) -------------------------------------------------
    ("E1 a missing observation is not refused", SVC, EVIDENCE_CHECK, EVIDENCE_UNCHECKED),
    # --- W: what is written (§3.6) ------------------------------------------------------
    ("W1 the note is not kept", SVC, '"note": note,', '"note": None,'),
    ("W2 the evidence is not kept", SVC,
     '"obs": prepared.evidence_observation_id,', '"obs": None,'),
    ("W3 the task is not marked DONE", SVC,
     "UPDATE turab.tasks SET status = 'DONE', completed_at = :at",
     "UPDATE turab.tasks SET completed_at = :at"),
    ("W4 the task's completed_at is not the event's", SVC,
     "SET status = 'DONE', completed_at = :at", "SET status = 'DONE', completed_at = now()"),
    # --- A: the audit (§3.7) --------------------------------------------------------------
    ("A1 the event is not audited", SVC, EVENT_AUDIT, "    pass"),
    ("A2 the task change is not audited", SVC, TASK_AUDIT, "    pass"),
    ("A3 the note is not withheld", AUDIT,
     '    "task_completion_events": ("note",),\n', ""),
    # --- G: the list (G6-9) -----------------------------------------------------------------
    ("G1 status not filtered", SVC,
     "(CAST(:s AS text) IS NULL OR status::text = CAST(:s AS text))", "true"),
    ("G2 priority not filtered", SVC,
     "(CAST(:p AS text) IS NULL OR priority::text = CAST(:p AS text))", "true"),
    ("G3 assigned_to_me ignored", SVC,
     "(CAST(:a AS uuid) IS NULL OR assigned_account_id = CAST(:a AS uuid))",
     "(CAST(:a AS uuid) IS NULL OR true)"),
    ("G4 priority ordered as text", SVC,
     "ORDER BY array_position(CAST(:order AS text[]), priority::text), created_at, task_id",
     "ORDER BY priority::text, created_at, task_id"),
    ("G5 creation not ordered", SVC,
     "ORDER BY array_position(CAST(:order AS text[]), priority::text), created_at, task_id",
     "ORDER BY array_position(CAST(:order AS text[]), priority::text), task_id"),
    ("G6 the list is not audited", ACCESS, LIST_AUDIT,
     "        (lambda **_: None)(\n"
     "            operation_id=operation_id, resource_kind=TASK_KIND, result_count=len(items),"),
    # --- R: the route --------------------------------------------------------------------
    ("R1 any string is an outcome code", ROUTE,
     "if not isinstance(value, str) or value not in OUTCOME_CODES:",
     "if not isinstance(value, str):"),
    ("R2 null is an outcome code", ROUTE,
     "if not isinstance(value, str) or value not in OUTCOME_CODES:",
     "if value is not None and value not in OUTCOME_CODES:"),
    ("R3 the body is open", ROUTE, 'model_config = ConfigDict(extra="forbid")',
     'model_config = ConfigDict(extra="allow")'),
    ("R4 an unknown task's denial is not recorded", CMD, TASK_DENIAL,
     '            return deny(DenyReason.OBJECT_NOT_AUTHORIZED, "not an available task")'),
]

LOADER_MUTATIONS = [
    ("K1 a shared component is accepted", CONTRACT, "        if uses != 1:",
     "        if uses < 1:"),
    ("K2 non_null accepted on a type without null", CONTRACT,
     'if not isinstance(declared, list) or "null" not in declared:',
     "if not isinstance(declared, list):"),
    ("K3 an enum value of another type is accepted", CONTRACT,
     "            if (not allowed or not isinstance(value, allowed)\n"
     "                    or (isinstance(value, bool) and bool not in allowed)):",
     "            if False:"),
    ("K4 an enum wider than the frozen one is accepted", CONTRACT,
     "if frozen is not None and not set(values) <= set(frozen):", "if False:"),
    ("K5 non_null not checked", CONTRACT,
     '        if "non_null" in entry:\n            _check_non_null(cid, entry["non_null"], properties)\n',
     ""),
    ("K6 enum not checked", CONTRACT,
     '        if "enum" in entry:\n            _check_enum(cid, entry["enum"], properties)\n',
     ""),
    ("K7 a reference with siblings is accepted", CONTRACT,
     'if set(schema) != {"$ref"} or not str(ref).startswith(_SCHEMA_REF):',
     "if not str(ref).startswith(_SCHEMA_REF):"),
    ("K8 non_null keeps null in the effective type", CONTRACT,
     '"type": remaining[0] if len(remaining) == 1 else remaining}',
     '"type": properties[field]["type"]}'),
]

if __name__ == "__main__":
    only = tuple(sys.argv[1:])
    survivors = run("TURAB — Slice 6 step 2: the task list and the completion",
                    TESTS, MUTATIONS, only)
    print()
    survivors += run("TURAB — Slice 6 step 2: the loader's extension (CORRECTION-005)",
                     CONTRACT_TESTS, LOADER_MUTATIONS, only)
    sys.exit(1 if survivors else 0)
