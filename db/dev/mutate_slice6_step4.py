"""Slice 6 step 4, the run's format-2 diagnostic and its tasks: which test
refuses which weakening.

    .venv/bin/python db/dev/mutate_slice6_step4.py [W1 T1 ...] > /outside/the/tree.txt

Each mutation weakens ONE rule (plan revision 11; G6-4 (a), (i)-(iii), G6-11,
§5.3), in `services/matching_run.py`:
- W: what the run writes in the diagnostic row (G6-11);
- T: the tasks of the HIGH suggestions (G6-4 (a), (ii), (iii); OQ6-1's
  obligation).

The test file is `tests/test_slice6_step4.py`. See `mutation_runner.py`.
"""
import sys

from mutation_runner import run

RUN = "src/turab/services/matching_run.py"
TESTS = "tests/test_slice6_step4.py"

TASK_SAVEPOINT = ("            with session.begin_nested():\n"
                  "                task_id = session.execute(text(\"\"\"")
TASK_NO_SAVEPOINT = ("            if True:\n"
                     "                task_id = session.execute(text(\"\"\"")
SKIP_OPEN_WORK = ("        except IntegrityError as exc:\n"
                  "            if getattr(getattr(exc.orig, \"diag\", None), \"constraint_name\", "
                  "None) != OPEN_WORK:\n"
                  "                raise\n"
                  "            continue")

MUTATIONS = [
    # --- W: the diagnostic row (G6-11) ---------------------------------------------------
    ("W1 no suggestion written", RUN,
     '"actions": _json(computed["suggested_actions"]),', '"actions": "[]",'),
    ("W2 no scenario written", RUN,
     '"scenarios": _json(computed["relaxation_scenarios"])}', '"scenarios": "[]"}'),
    ("W3 the evaluated matches not recorded", RUN,
     '"near": tally["near_match_count"], "summary": _json(computed["blocker_summary"]),',
     '"near": tally["near_match_count"], "summary": _json({**computed["blocker_summary"], '
     '"evaluated": []}),'),
    ("W4 every match recorded NEW", RUN,
     '"stored": "NEW" if new else "EXISTING"}', '"stored": "NEW"}'),
    ("W5 the chains not in the input hash", RUN,
     '        "requested_location_chains": location_chains,\n    }', "    }"),
    ("W6 the chains not read", RUN,
     "    chains = diagnostic.read_location_chains(session, _requested_locations(prepared.plan))",
     "    chains = {}"),
    # --- T: the tasks (G6-4) --------------------------------------------------------------
    ("T1 no task raised", RUN,
     '    _raise_tasks(session, prepared, diagnostic_id, computed["suggested_actions"], evaluated)',
     "    pass"),
    ("T2 NORMAL suggestions raise tasks", RUN,
     '        if action["priority"] != "HIGH":\n            continue\n', ""),
    ("T3 every task error swallowed", RUN, SKIP_OPEN_WORK,
     "        except Exception:\n            continue"),
    ("T4 open work not skipped", RUN, SKIP_OPEN_WORK,
     "        except IntegrityError:\n            raise"),
    ("T5 no savepoint around the insert", RUN, TASK_SAVEPOINT, TASK_NO_SAVEPOINT),
    ("T6 the source not stated", RUN,
     '"source": "DIAGNOSTIC",\n', ""),
    ("T7 the basis left out of the subject", RUN,
     'SUBJECT_KEYS = ("entity", "id", "gate", "criterion", "ordinal", "basis")',
     'SUBJECT_KEYS = ("entity", "id", "gate", "criterion", "ordinal")'),
    ("T8 the diagnostic not named", RUN,
     'payload = {"diagnostic_run_id": str(diagnostic_id),',
     'payload = {"diagnostic_run_id": None,'),
    ("T9 the property not named", RUN,
     '"p": property_id, "m": match_id,', '"p": None, "m": match_id,'),
    ("T10 the match not named", RUN,
     '"p": property_id, "m": match_id,', '"p": property_id, "m": None,'),
    ("T11 the task stored NORMAL", RUN,
     "VALUES (CAST(:type AS turab.task_type), 'HIGH', :title,",
     "VALUES (CAST(:type AS turab.task_type), 'NORMAL', :title,"),
    ("T12 the task not audited", RUN,
     "                audit_rows.write(session, \"tasks\", task_id, \"INSERT\", None,\n"
     "                                 audit_rows.row_json(session, \"tasks\", task_id))",
     "                pass"),
    ("T13 the reason not kept", RUN,
     '"reason": subject.get("reason_code"),', '"reason": None,'),
]

if __name__ == "__main__":
    sys.exit(1 if run("TURAB — Slice 6 step 4: the run's format-2 diagnostic and its tasks",
                      TESTS, MUTATIONS, tuple(sys.argv[1:])) else 0)
