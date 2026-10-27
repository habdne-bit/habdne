"""Slice 7 step 4, interactions, the backfill, the timeline's `message`, the
confirmation link: which test refuses which weakening.

    .venv/bin/python db/dev/mutate_slice7_step4.py [I1 B1 ...] > /outside/the/tree.txt

Each mutation weakens ONE rule (G7-8 (a), G7-10 (a), G7-17 (i), G7-18
(i)-(viii), decided in the review of e18271a):
- I: the interaction a message writes (its type, summary, columns, audit,
  its two writers);
- B: the backfill (its lock, its selection);
- T: the timeline's `message` (its presence, its content, its join);
- L: the confirmation link (its metadata, its type and channel, its
  decision, its observation, its lock).

Not mutated, each with its reason:
- the link's metadata checked in the body (`_link_ids` in
  `check_message_body`): `_check_link` checks the same metadata again after
  the thread's lock, with the same refusal, before the claim; removing the
  first is equivalent;
- the decision's `FOR SHARE`: a message's thread, type and direction are
  frozen by `0008` part B, and its delivery is not checked, so no change in
  flight can alter the decision's verdict; kept as the plan's lock
  discipline, and claimed by no test;
- the message's `FOR UPDATE` of the thread, and the webhook's savepoint: step
  2's and step 3's, mutated there.

Run in one part. See `mutation_runner.py`.
"""
import sys

from mutation_runner import ROOT, run

INTER = "src/turab/services/message_interactions.py"
SVC = "src/turab/services/communication.py"
HOOK = "src/turab/services/webhooks.py"
TL = "src/turab/services/timeline.py"
PROBLEMS = "src/turab/api/problems.py"
TESTS = "tests/test_slice7_step4.py"

MUTATIONS = [
 # --- I: the interaction -----------------------------------------------------------------
 ("I1 an INTERNAL message typed by its channel", INTER,
  "    return \"NOTE\" if direction == \"INTERNAL\" else TYPE_BY_CHANNEL[channel]",
  "    return TYPE_BY_CHANNEL[channel]"),
 ("I2 a PHONE message typed OTHER", INTER, "\"PHONE\": \"CALL\"", "\"PHONE\": \"OTHER\""),
 ("I3 a WEB message typed WHATSAPP", INTER, "\"WEB\": \"OTHER\"", "\"WEB\": \"WHATSAPP\""),
 ("I4 the summary of the wrong direction", INTER,
  "\"OUTBOUND\": \"Outbound message\"", "\"OUTBOUND\": \"Inbound message\""),
 ("I5 the opportunity not copied", INTER,
  "\"opportunity\": m[\"opportunity_id\"]", "\"opportunity\": None"),
 ("I6 no operator", INTER,
  "         \"operator\": m[\"sent_by_account_id\"],", "         \"operator\": None,"),
 ("I7 the metadata carries more than the id", INTER,
  "json.dumps({\"message_id\": str(message_id)})",
  "json.dumps({\"message_id\": str(message_id), \"direction\": m[\"direction\"]})"),
 ("I8 the interaction's time is now", INTER,
  "                :property, :opportunity, :thread, :summary, :at, :operator,",
  "                :property, :opportunity, :thread, :summary, now(), :operator,"),
 ("I9 the interaction not audited", INTER,
  "    audit_rows.write(session, \"interactions\", interaction, \"INSERT\", None,",
  "    (lambda *a: None)(session, \"interactions\", interaction, \"INSERT\", None,"),
 ("I10 the staff message writes no interaction", SVC,
  "    message_interactions.write(session, row[\"message_id\"])", "    pass"),
 ("I11 the webhook message writes no interaction", HOOK,
  "    message_interactions.write(session, message)", "    pass"),
 # --- B: the backfill --------------------------------------------------------------------
 ("B1 no advisory lock", INTER,
  "        s.execute(text(\"SELECT pg_advisory_xact_lock(:k)\"), {\"k\": BACKFILL_LOCK})",
  "        pass"),
 ("B2 every message backfilled again", INTER,
  "                    WHERE i.metadata->>'message_id' = m.message_id::text)",
  "                    WHERE false)"),
 ("B3 the backfill reports nothing written", INTER,
  "        return len(missing)", "        return 0"),
 # --- T: the timeline --------------------------------------------------------------------
 ("T1 unarchived content shown", TL,
  "        if message[\"content_archived\"]:", "        if True:"),
 ("T2 a message key on every item", TL,
  "    if row.get(\"m_message_id\") is not None:", "    if True:"),
 ("T3 the status not read live", TL,
  "m.delivery_status::text AS m_delivery_status", "'UNKNOWN' AS m_delivery_status"),
 ("T4 a message_id not a uuid cast", TL,
  "                ON m.message_id = CASE WHEN i.metadata->>'message_id' ~ '{_UUID}'\n"
  "                                       THEN (i.metadata->>'message_id')::uuid END",
  "                ON m.message_id = (i.metadata->>'message_id')::uuid"),
 # --- L: the confirmation link -----------------------------------------------------------
 ("L1 metadata accepted on any type", SVC,
  "        if message_type != LINK:", "        if False:"),
 ("L2 a PHONE thread not required", SVC,
  "    if message_type in LINK_TYPES and thread[\"channel\"] != \"PHONE\":", "    if False:"),
 ("L3 an extra metadata key accepted", SVC,
  "set(metadata) != set(LINK_KEYS)", "not set(LINK_KEYS) <= set(metadata)"),
 ("L4 a decision of another thread", SVC,
  "    if (decision is None or decision[\"thread_id\"] != thread_id",
  "    if (decision is None or False"),
 ("L5 a decision of another type", SVC,
  "            or decision[\"message_type\"] != DECISION or decision[\"direction\"] != "
  "\"INTERNAL\"):",
  "            or decision[\"direction\"] != \"INTERNAL\"):"),
 ("L6 a decision of another direction", SVC,
  "            or decision[\"message_type\"] != DECISION or decision[\"direction\"] != "
  "\"INTERNAL\"):",
  "            or decision[\"message_type\"] != DECISION):"),
 ("L7 an observation of another kind", SVC,
  "    if (observation is None or observation[\"kind\"] != \"MESSAGE\" or party_id is None",
  "    if (observation is None or party_id is None"),
 ("L8 an observation of another party", SVC,
  "            or observation[\"party_id\"] != party_id or observation[\"observed_at\"] is None",
  "            or observation[\"observed_at\"] is None"),
 ("L9 an observation before the decision", SVC,
  "            or observation[\"observed_at\"] < decision[\"occurred_at\"]):",
  "            or False):"),
 ("L10 an observation at the decision's time refused", SVC,
  "            or observation[\"observed_at\"] < decision[\"occurred_at\"]):",
  "            or observation[\"observed_at\"] <= decision[\"occurred_at\"]):"),
 ("L11 the observation not locked", SVC,
  "          FROM turab.observations WHERE observation_id = :o FOR SHARE\"\"\"),",
  "          FROM turab.observations WHERE observation_id = :o\"\"\"),"),
 ("L12 the link's ids not stored", SVC,
  "                                     **(prepared.link or {})})},",
  "                                     })},"),
 ("L13 a link refusal answered 409", PROBLEMS,
  "    ProblemCode.DECISION_NOT_LINKABLE: (422,", "    ProblemCode.DECISION_NOT_LINKABLE: (409,"),
]


def _check_anchors() -> None:
    """Each anchor names ONE site: the runner replaces every occurrence. Run
    before a run, never on import."""
    for name, rel, old, _new in MUTATIONS:
        count = (ROOT / rel).read_text().count(old)
        assert count == 1, (name, count)
    labels = [m[0].split()[0] for m in MUTATIONS]
    assert len(set(labels)) == len(labels)


if __name__ == "__main__":
    _check_anchors()
    survivors = run("TURAB — Slice 7 step 4: interactions, the backfill, the timeline, the "
                    "confirmation link", TESTS, MUTATIONS, tuple(sys.argv[1:]))
    sys.exit(1 if survivors else 0)
