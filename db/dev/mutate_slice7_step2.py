"""Slice 7 step 2, the staff thread and the staff message: which test refuses which
weakening.

    .venv/bin/python db/dev/mutate_slice7_step2.py [T1 M1 ...] > /outside/the/tree.txt

Each mutation weakens ONE rule (plan revision 8; G7-3, G7-4, G7-6, G7-9,
G7-11, G7-16, CORRECTION-006), in `services/communication.py`, the route,
`CommandService`, `audit_rows` or the contract loader:
- T: the thread: G7-3's reference, G7-6's rules 0-4, what it writes;
- M: the message: G7-16 (i)-(v), G7-4's identity, G7-9's consent and its
  lock, G7-16 (iv)'s thread lock and `last_message_at`, what it writes;
- R: the route (R5.3b's recorded denial, CORRECTION-006's body);
- K: the loader's `anyOf` extension, against `tests/test_correction_006.py`.

Not mutated, each with its reason:
- the pre-checks `_refuse_taken_thread_ref` and `_refuse_taken_message_ref`:
  the INSERT's own refusal (the backstop) answers the same typed 409 and
  rolls the transaction back, the claim with it, so no test can tell a
  missing pre-check apart. The pre-check keeps the refusal before the claim,
  as every other refusal is. Each backstop is mutated (T13, M9) and killed by
  the test that blinds the pre-check. Removing both at once is not a single
  site. (The first trial run listed two such mutations, T14 and M10; each
  removed the pre-check only, and survived as the equivalent it is. They
  are withdrawn.);
- the consent's `b.purpose` alone, or `g.scope` alone: the frozen binding
  trigger requires the purpose to be the grant's scope (B01), so each
  implies the other; both together are mutated (M13, the two conditions on
  adjacent lines);
- the consent's `g.party_id`: the frozen binding trigger refuses a thread
  binding for another party (M5), so no row can differ;
- the opportunity's `FOR SHARE`: no command today changes an opportunity's
  `current_offer_id`, so no test can make the seller change under it; it
  is kept as the plan's lock discipline, and claimed by no test;
- `authorize_staff_only` on both routes: the contract's roles are ADMIN and
  OPERATOR, so the role gate refuses every other caller first.

Run in two parts, one per test file; each part prints its own header. See
`mutation_runner.py`.
"""
import sys

from mutation_runner import ROOT, run

SVC = "src/turab/services/communication.py"
ROUTE = "src/turab/api/routes/communication.py"
AUDIT = "src/turab/services/audit_rows.py"
CONTRACT = "src/turab/auth/contract.py"
TESTS = "tests/test_slice7_step2.py"
CONTRACT_TESTS = "tests/test_correction_006.py"

MUTATIONS = [
 # --- T: the thread --------------------------------------------------------------------
 ("T1 an unscoped WHATSAPP reference accepted", SVC,
  "            and not SCOPED.match(external_thread_ref)):",
  "            and False):"),
 ("T2 an id naming no row passes the check", SVC,
  "               and session.execute(text(_EXISTS[f]), {\"v\": v}).first() is None]",
  "               and False]"),
 ("T3 a named opportunity's type not checked", SVC,
  "        if not (opp[\"evaluated_type\"] == \"SALE\" and opp[\"intent\"] == \"BUY\"):",
  "        if False:"),
 ("T4 the SALE check reads the evaluated offer only", SVC,
  "        if not (opp[\"evaluated_type\"] == \"SALE\" and opp[\"intent\"] == \"BUY\"):",
  "        if not opp[\"evaluated_type\"] == \"SALE\":"),
 ("T5 the SALE check reads the request's intent only", SVC,
  "        if not (opp[\"evaluated_type\"] == \"SALE\" and opp[\"intent\"] == \"BUY\"):",
  "        if not opp[\"intent\"] == \"BUY\":"),
 ("T6 rule 1: the opportunity's request not compared", SVC,
  "        if request_id is not None and request_id != opp[\"request_id\"]:",
  "        if False:"),
 ("T7 rule 1: the opportunity's property not compared", SVC,
  "        if property_id is not None and property_id != opp[\"property_id\"]:",
  "        if False:"),
 ("T8 rule 1: the seller refused", SVC,
  "        if party_id not in {opp[\"buyer\"], opp[\"seller\"]} - {None}:",
  "        if party_id not in {opp[\"buyer\"]}:"),
 ("T9 rule 1: any party accepted", SVC,
  "        if party_id not in {opp[\"buyer\"], opp[\"seller\"]} - {None}:",
  "        if False:"),
 ("T10 rule 2: the request's party not compared", SVC,
  "            if party_id != buyer:", "            if False:"),
 ("T11 rule 3: the offer's party not compared", SVC,
  "                 WHERE property_id = :p AND party_id = :party LIMIT 1\"\"\"),",
  "                 WHERE property_id = :p LIMIT 1\"\"\"),"),
 ("T12 rule 3 not applied", SVC,
  "            if offered is None:", "            if False:"),
 ("T13 the thread reference's backstop raises (500)", SVC,
  "        if _constraint(exc) != THREAD_REF_INDEX:", "        if True:"),
 ("T15 the creator not recorded", SVC,
  "                 \"acct\": created_by_account_id}).mappings().one()",
  "                 \"acct\": None}).mappings().one()"),
 ("T16 the thread not audited", SVC,
  "    audit_rows.write(session, \"communication_threads\", row[\"thread_id\"], \"INSERT\", None,",
  "    if False: audit_rows.write(session, \"communication_threads\", row[\"thread_id\"], "
  "\"INSERT\", None,"),
 # --- M: the message -------------------------------------------------------------------
 ("M1 INBOUND accepted", SVC,
  "    if direction == \"INBOUND\":", "    if False:"),
 ("M2 metadata accepted", SVC,
  "    if metadata:", "    if False:"),
 ("M3 no message type reserved", SVC,
  "RESERVED_TYPES = (\"PHONE_DECISION\", \"CONFIRMATION_LINK\")",
  "RESERVED_TYPES = ()"),
 ("M4 an INTERNAL message may state a status", SVC,
  "    if direction == \"INTERNAL\" and delivery_status not in (None, \"UNKNOWN\"):",
  "    if False:"),
 ("M5 an INTERNAL message may carry a reference", SVC,
  "    if direction == \"INTERNAL\" and external_message_ref is not None:",
  "    if False:"),
 ("M6 a reference accepted in any channel", SVC,
  "        if thread[\"channel\"] != \"WHATSAPP\":", "        if False:"),
 ("M7 the provider not set", SVC,
  "        provider = PROVIDER\n", "        provider = None\n"),
 ("M8 an OUTBOUND message's status not kept", SVC,
  "        delivery_status=(delivery_status or \"UNKNOWN\") if direction == \"OUTBOUND\"",
  "        delivery_status=\"UNKNOWN\" if direction == \"OUTBOUND\""),
 ("M9 the message reference's backstop raises (500)", SVC,
  "        if _constraint(exc) != MESSAGE_REF_KEY:", "        if True:"),
 ("M11 content stored without the consent", SVC,
  "    if has_content and not _archive_consent_holds(session, thread_id=thread_id,",
  "    if False and not _archive_consent_holds(session, thread_id=thread_id,"),
 ("M12 a consent bound to any thread counts", SVC,
  "         WHERE b.thread_id = :t\n", "         WHERE (b.thread_id = :t OR true)\n"),
 ("M13 a consent of any purpose counts", SVC,
  "           AND b.purpose = 'COMMUNICATION_ARCHIVE'\n"
  "           AND g.scope = 'COMMUNICATION_ARCHIVE'\n", ""),
 ("M14 a revoked binding counts", SVC,
  "           AND b.revoked_at IS NULL\n", ""),
 ("M15 a revoked grant counts", SVC,
  "           AND g.status = 'GRANTED'\n", ""),
 ("M16 the consent read without a lock", SVC,
  "           FOR SHARE OF b, g\"\"\"), {\"t\": thread_id, \"party\": party_id}).first()",
  "           \"\"\"), {\"t\": thread_id, \"party\": party_id}).first()"),
 ("M17 the thread read without a lock (G7-16 (iv))", SVC,
  "          FROM turab.communication_threads WHERE thread_id = :t FOR UPDATE\"\"\"),",
  "          FROM turab.communication_threads WHERE thread_id = :t\"\"\"),"),
 ("M18 last_message_at not moved", SVC,
  "         WHERE thread_id = :t AND (last_message_at IS NULL OR last_message_at < :at)\n",
  "         WHERE false\n"),
 ("M19 last_message_at moved backwards too", SVC,
  "         WHERE thread_id = :t AND (last_message_at IS NULL OR last_message_at < :at)\n",
  "         WHERE thread_id = :t\n"),
 ("M20 the sender not recorded", SVC,
  "                 \"at\": prepared.occurred_at, \"acct\": sent_by_account_id,",
  "                 \"at\": prepared.occurred_at, \"acct\": None,"),
 ("M21 content_archived always false", SVC,
  "                 \"meta\": json.dumps({\"content_archived\": prepared.content_archived})},",
  "                 \"meta\": json.dumps({\"content_archived\": False})},"),
 ("M22 the message not audited", SVC,
  "    audit_rows.write(session, \"communication_messages\", row[\"message_id\"], \"INSERT\", "
  "None,",
  "    if False: audit_rows.write(session, \"communication_messages\", row[\"message_id\"], "
  "\"INSERT\", None,"),
 ("M23 the thread's move not audited", SVC,
  "        audit_rows.write(session, \"communication_threads\", prepared.thread_id, "
  "\"UPDATE\",",
  "        if False: audit_rows.write(session, \"communication_threads\", "
  "prepared.thread_id, \"UPDATE\","),
 ("M24 the content enters the audit log", AUDIT,
  "    \"communication_messages\": (\"body_text\", \"media_ref\"),\n", ""),
 # --- R: the route ---------------------------------------------------------------------
 ("R1 the unknown thread not refused at the route (no recorded denial)", ROUTE,
  "        command.authorize_staff_only(MESSAGE, \"recording a message is a staff action\"),\n"
  "        command.authorize_thread_exists(thread_id, MESSAGE)))",
  "        command.authorize_staff_only(MESSAGE, \"recording a message is a staff action\")))"),
 ("R2 CORRECTION-006 not applied by the route: party_id optional", ROUTE,
  "    party_id: uuid.UUID\n", "    party_id: uuid.UUID | None = None\n"),
]

LOADER_MUTATIONS = [
 ("R3 the thread reference made nullable at the route", ROUTE,
  "    external_thread_ref: str = None  # type: ignore[assignment]\n",
  "    external_thread_ref: str | None = None\n"),
 ("K1 several null branches accepted", CONTRACT,
  "            if len(nulls) != 1:", "            if len(nulls) < 1:"),
 ("K2 no null branch accepted", CONTRACT,
  "            if len(nulls) != 1:", "            if len(nulls) > 1:"),
 ("K3 a null-only field accepted", CONTRACT,
  "            if not others:\n", "            if False:\n"),
 ("K4 a branch that may admit null accepted", CONTRACT,
  "            if any(_admits_null(b) for b in others):", "            if False:"),
 ("K5 a branch whose type list holds null counts as non-null", CONTRACT,
  "    if isinstance(declared, list) and declared:\n        return \"null\" in declared",
  "    if isinstance(declared, list) and declared:\n        return False"),
 ("K6 a branch by reference counts as non-null", CONTRACT,
  "    if any(k in branch for k in (\"anyOf\", \"oneOf\", \"allOf\", \"not\", \"$ref\")):",
  "    if any(k in branch for k in (\"anyOf\", \"oneOf\", \"allOf\", \"not\")):"),
 ("K10 a branch with its own combinator counts as non-null", CONTRACT,
  "    if any(k in branch for k in (\"anyOf\", \"oneOf\", \"allOf\", \"not\", \"$ref\")):",
  "    if any(k in branch for k in (\"oneOf\", \"allOf\", \"not\", \"$ref\")):"),
 ("K7 a type beside the anyOf accepted", CONTRACT,
  "            if \"type\" in properties[field]:", "            if False:"),
 ("K8 the transformation keeps the null branch", CONTRACT,
  "            others = split[1]\n", "            others = properties[field][\"anyOf\"]\n"),
 ("K9 the transformation drops the field's other keywords", CONTRACT,
  "            rest = {k: v for k, v in properties[field].items() if k != \"anyOf\"}",
  "            rest = {}"),
]


def _check_anchors() -> None:
    """Each anchor names ONE site: the runner replaces every occurrence. Run
    before a run, never on import."""
    for name, rel, old, _new in MUTATIONS + LOADER_MUTATIONS:
        count = (ROOT / rel).read_text().count(old)
        assert count == 1, (name, count)
    labels = [m[0].split()[0] for m in MUTATIONS + LOADER_MUTATIONS]
    assert len(set(labels)) == len(labels)


if __name__ == "__main__":
    _check_anchors()
    only = tuple(sys.argv[1:])
    survivors = run("TURAB — Slice 7 step 2: the staff thread and the staff message",
                    TESTS, MUTATIONS, only)
    print()
    survivors += run("TURAB — Slice 7 step 2: CORRECTION-006, the route's body and the "
                     "loader's anyOf extension", CONTRACT_TESTS, LOADER_MUTATIONS, only)
    sys.exit(1 if survivors else 0)
