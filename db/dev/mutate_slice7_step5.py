"""Slice 7 step 5, the mandatory and red-team tests end to end: which test
refuses which weakening.

    .venv/bin/python db/dev/mutate_slice7_step5.py [W2 J2 ...] > /outside/the/tree.txt

Step 5 adds no product code. Each mutation weakens ONE rule that an
end-to-end test of `tests/test_slice7_step5.py` claims (plan §6.1, §6.2, and
the two gaps G7-19 names, decided in the review of d04d5c8). The rule may sit
in any module the HTTP path reaches; the anchors are those of steps 2-4:
- W: mandatory test 1 (J01, S42), the webhook's event, message and
  interaction;
- D: mandatory test 2 (J02), one provider reference in one thread;
- L: mandatory test 3, the thread's links;
- C: mandatory test 4, the decision, the confirmation and the link;
- J: J03, content under the consent only;
- K: K05, the key's other body;
- S: S41, the relay's signature.

Not mutated, each with its reason (W1, D1 and C4 were in the first trial run,
outside the tree, and survived; they are removed for these reasons, not
hidden):
- a replay of a final event taken as new (step 3's T2): the claim re-reads
  the status (`processing_status IN ('RECEIVED', 'FAILED')`) and takes no
  final event, so a sequential replay is still 200 writing nothing; each of
  the two guards alone is equivalent here, and step 3 mutates both against
  its own tests;
- the webhook's 23505 backstop (step 3's M5): the read before the insert
  (`taken`) answers IGNORED MESSAGE_REF_TAKEN first, so the backstop is not
  reached by a sequential test; the same holds for the staff command below;
- a `message` key on every timeline item (step 4's T2): every item of the
  parties these tests read is a message's; the rule is claimed by step 4's
  `test_vi_any_other_interaction_keeps_slice_1s_exact_keys`, not here;
- the staff command's two refusals of a recorded reference: the read before
  the insert (`_refuse_taken_message_ref`) and the 23505 backstop each answer
  409 MESSAGE_REF_TAKEN when the other is removed, so removing either alone
  is equivalent for a sequential test; both are mutated in step 2 against
  their own tests;
- the concurrent test of mandatory 1 is NOT deselected here, unlike step 3:
  under each mutation below its result does not depend on timing, since none
  of them touches the claim's lock or the thread's lock. A pair of runs that
  differ is reported as such, not hidden.

Only `tests/test_slice7_step5.py` is run, so a kill is this file's, not an
earlier step's.

Part 2, E (review of 8dd7921): the closure evidence's own refusals: the
sample bound to the database the run's record names, no skipped case, and
the recorder running the suite on the database it records. Killed by
`tests/test_slice7_evidence.py`, which runs the tools on a copy of the tree.

Run in two parts, one per test file; each part prints its own header. See
`mutation_runner.py`.
"""
import sys

from mutation_runner import ROOT, run

HOOK = "src/turab/services/webhooks.py"
ROUTE = "src/turab/api/routes/webhooks.py"
SVC = "src/turab/services/communication.py"
INTER = "src/turab/services/message_interactions.py"
IDEM = "src/turab/services/idempotency.py"
TESTS = "tests/test_slice7_step5.py"
GEN = "db/gate/slice7_evidence.py"
TOOL = "db/gate/slice7_event_store_counts.py"
RECORDER = "db/gate/record_test_run.py"
EVIDENCE_TESTS = "tests/test_slice7_evidence.py"

MUTATIONS = [
 # --- W: mandatory test 1 (J01, S42) ------------------------------------------------------
 ("W2 the webhook message writes no interaction", HOOK,
  "    message_interactions.write(session, message)", "    pass"),
 ("W3 no rollback to the savepoint", HOOK,
  "                savepoint.rollback()\n", "                pass\n"),
 ("W4 the failure not recorded", HOOK,
  "                finish(s, event_id, \"FAILED\", PROCESSING_FAILED)\n", ""),
 # --- D: mandatory test 2 (J02) -----------------------------------------------------------
 ("D2 a reference accepted in any channel", SVC,
  "        if thread[\"channel\"] != \"WHATSAPP\":", "        if False:"),
 # --- L: mandatory test 3 -----------------------------------------------------------------
 ("L1 rule 1: the seller refused", SVC,
  "        if party_id not in {opp[\"buyer\"], opp[\"seller\"]} - {None}:",
  "        if party_id not in {opp[\"buyer\"]}:"),
 ("L2 rule 1: any party accepted", SVC,
  "        if party_id not in {opp[\"buyer\"], opp[\"seller\"]} - {None}:",
  "        if False:"),
 # --- C: mandatory test 4 -----------------------------------------------------------------
 ("C1 an INTERNAL message typed by its channel", INTER,
  "    return \"NOTE\" if direction == \"INTERNAL\" else TYPE_BY_CHANNEL[channel]",
  "    return TYPE_BY_CHANNEL[channel]"),
 ("C2 the observation required before the decision", SVC,
  "            or observation[\"observed_at\"] < decision[\"occurred_at\"]):",
  "            or observation[\"observed_at\"] > decision[\"occurred_at\"]):"),
 ("C3 the staff message writes no interaction", SVC,
  "    message_interactions.write(session, row[\"message_id\"])", "    pass"),
 # --- J: J03 ------------------------------------------------------------------------------
 ("J1 the content archived without the consent", HOOK,
  "        if _archive_consent_holds(session, thread_id=thread[\"thread_id\"],",
  "        if True or _archive_consent_holds(session, thread_id=thread[\"thread_id\"],"),
 ("J2 the content kept when the consent does not hold", HOOK,
  "            body = media = None\n", "            pass\n"),
 ("J3 the event keeps every key of the payload", HOOK,
  "    kept = {k: envelope.payload[k] for k in STORED_KEYS\n",
  "    kept = {k: envelope.payload[k] for k in envelope.payload\n"),
 # --- K: K05 ------------------------------------------------------------------------------
 ("K1 another body on the key replayed", IDEM,
  "    if existing[\"request_hash\"] != request_hash:\n        raise IdempotencyKeyConflict",
  "    if False:\n        raise IdempotencyKeyConflict"),
 # --- S: S41 ------------------------------------------------------------------------------
 ("S1 any well-formed signature accepted", HOOK,
  "    return hmac.compare_digest(expected, match.group(1))", "    return True"),
 ("S2 the signature not checked", ROUTE,
  "    if not webhook_service.verify(", "    if False and not webhook_service.verify("),
]


#: Part 2 (review of 8dd7921): the closure evidence's own refusals, killed by
#: `tests/test_slice7_evidence.py`.
EVIDENCE_MUTATIONS = [
 ("E1 the sample's database and host not compared", GEN,
  "                \"database\": database, \"host\": host}", "                }"),
 ("E2 a record naming no database accepted by the generator", GEN,
  "    if database is None:\n        problems.append(",
  "    if False:\n        problems.append("),
 ("E3 a skipped case accepted by the generator", GEN,
  "        if cases.skipped:", "        if False:"),
 ("E4 the tool samples the environment's database", TOOL,
  "    database, host = recorded[\"database\"]\n",
  "    database, host = run_binding.test_database()\n"),
 ("E5 the environment not compared by the tool", TOOL,
  "        if os.environ.get(var) not in (None, value):", "        if False:"),
 ("E6 a record naming no database accepted by the tool", TOOL,
  "    if \"database\" not in recorded:\n        return [",
  "    if False:\n        return ["),
 ("E7 a skipped case accepted by the tool", TOOL,
  "    return [f\"the run skipped {skipped} cases; Slice 7's evidence requires none\"] "
  "if skipped else []",
  "    return []"),
 ("E8 the suite not run on the recorded database", RECORDER,
  "cwd=ROOT, env=env).returncode", "cwd=ROOT).returncode"),
 ("E9 the record names no database", RECORDER,
  "report_name=REPORT.as_posix(), database=database))", "report_name=REPORT.as_posix()))"),
]


def _check_anchors() -> None:
    """Each anchor names ONE site: the runner replaces every occurrence. Run
    before a run, never on import."""
    for name, rel, old, _new in MUTATIONS + EVIDENCE_MUTATIONS:
        count = (ROOT / rel).read_text().count(old)
        assert count == 1, (name, count)
    labels = [m[0].split()[0] for m in MUTATIONS + EVIDENCE_MUTATIONS]
    assert len(set(labels)) == len(labels)


if __name__ == "__main__":
    _check_anchors()
    only = tuple(sys.argv[1:])
    survivors = run("TURAB — Slice 7 step 5: the mandatory and red-team tests end to end",
                    TESTS, MUTATIONS, only)
    print()
    survivors += run("TURAB — Slice 7 step 5: the closure evidence's refusals (review of "
                     "8dd7921)", EVIDENCE_TESTS, EVIDENCE_MUTATIONS, only)
    sys.exit(1 if survivors else 0)
