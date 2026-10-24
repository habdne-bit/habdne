"""Slice 7 step 1, migration 0008: which test refuses which weakened guard.

    .venv/bin/python db/dev/mutate_0008.py [E1 B5 ...] > /outside/the/tree.txt

Each mutation weakens ONE part of `0008_communication_records.py`, as plan
§5.1 writes it:
- E1-E7: part E, the pre-check on old rows, the scoped CHECK, the index;
- A1-A7: part A, the three CHECKs and the provider/channel trigger;
- B1-B23: part B, the message guard: its trigger, each frozen column, each
  transition rule;
- C1-C12: part C, the event guard: its trigger, each immutable field, each
  status rule;
- D1-D23: part D (D2), each of the six keys left SET NULL, the thread guard:
  its trigger, each frozen column, a depth bypass, `last_message_at`;
- G1-G5: the downgrade.

A frozen column is weakened by comparing NEW with NEW instead of NEW with OLD,
one column at a time.

`test_the_migration_executes_the_approved_text` is DESELECTED: it compares the
file's text with the plan's, so it fails under every mutation of UPGRADE and
would hide which behaviour test refuses the weakened write. It runs in the
suite (`record_test_run.py`).

Not mutated: the index predicate's `external_thread_ref IS NOT NULL`. A unique
index treats NULLs as distinct (PostgreSQL 16 §11.6, §5.4.3), so without it no
write differs; no test can kill that mutant, and none is claimed.

The suite's database and the scratch database are both built by
`alembic upgrade head` at session start, so a mutated migration is what the
tests run against. See `mutation_runner.py`.
"""
import sys

from mutation_runner import ROOT, run

MIG = "db/migrations/versions/0008_communication_records.py"
TESTS = "tests/test_migration_0008_communication_records.py"
DESELECT = ("test_the_migration_executes_the_approved_text",)

NOTHING = '"SELECT 1"'


def _statement(start: str) -> str:
    """The whole UPGRADE or DOWNGRADE string literal that starts with `start`."""
    source = (ROOT / MIG).read_text()
    begin = source.index('"""' + start)
    return source[begin:source.index('"""', begin + 3) + 3]


MESSAGE_COLUMNS = ("message_id", "thread_id", "provider", "external_message_ref",
                   "direction", "message_type", "body_text", "media_ref", "occurred_at",
                   "sent_by_account_id", "metadata", "created_at")
EVENT_COLUMNS = ("webhook_event_id", "provider", "provider_event_id", "event_type",
                 "payload", "received_at")
THREAD_COLUMNS = ("thread_id", "channel", "party_id", "request_id", "property_id",
                  "opportunity_id", "external_thread_ref", "opened_at", "archived_at",
                  "created_by_account_id")

MESSAGE_OLD = """     (OLD.message_id, OLD.thread_id, OLD.provider, OLD.external_message_ref,
      OLD.direction, OLD.message_type, OLD.body_text, OLD.media_ref,
      OLD.occurred_at, OLD.sent_by_account_id, OLD.metadata, OLD.created_at)"""
EVENT_OLD = """     (OLD.webhook_event_id, OLD.provider, OLD.provider_event_id, OLD.event_type,
      OLD.payload, OLD.received_at)"""
THREAD_OLD = """     (OLD.thread_id, OLD.channel, OLD.party_id, OLD.request_id, OLD.property_id,
      OLD.opportunity_id, OLD.external_thread_ref, OLD.opened_at, OLD.archived_at,
      OLD.created_by_account_id)"""


def _frozen(prefix, first, tuple_text, columns, what):
    return [(f"{prefix}{first + i} {what}: {c} compared NEW with NEW", MIG, tuple_text,
             tuple_text.replace(f"OLD.{c},", f"NEW.{c},").replace(f"OLD.{c})", f"NEW.{c})"))
            for i, c in enumerate(columns)]


KEYS = [
    ("party_id", "REFERENCES turab.parties(party_id)"),
    ("request_id", "REFERENCES turab.requests(request_id)"),
    ("property_id", "REFERENCES turab.properties(property_id)"),
    ("opportunity_id", "REFERENCES turab.opportunities(opportunity_id)"),
    ("created_by_account_id", "FOREIGN KEY (created_by_account_id)\n"
                              "      REFERENCES turab.user_accounts(account_id)"),
    ("sent_by_account_id", "FOREIGN KEY (sent_by_account_id)\n"
                           "      REFERENCES turab.user_accounts(account_id)"),
]

MUTATIONS = [
 # --- E ---------------------------------------------------------------------------
 ("E1 the pre-check not run", MIG, _statement("DO $$"), NOTHING),
 ("E2 the pre-check refuses unscoped references only", MIG,
  "IF malformed > 0 OR duplicated > 0 THEN", "IF malformed > 0 THEN"),
 ("E3 the pre-check counts shared references across every channel", MIG,
  """    SELECT external_thread_ref FROM turab.communication_threads
     WHERE channel = 'WHATSAPP' AND external_thread_ref IS NOT NULL
     GROUP BY""",
  """    SELECT external_thread_ref FROM turab.communication_threads
     WHERE external_thread_ref IS NOT NULL
     GROUP BY"""),
 ("E4 the scoped CHECK not created", MIG,
  _statement("ALTER TABLE turab.communication_threads\n  ADD CONSTRAINT ck_whatsapp"), NOTHING),
 ("E5 the scoped CHECK asks for one colon anywhere", MIG,
  "OR external_thread_ref ~ '^[^:]+:[^:]+$')", "OR external_thread_ref ~ ':')"),
 ("E6 the index not unique (the race makes two threads)", MIG,
  "CREATE UNIQUE INDEX ux_whatsapp_thread_ref", "CREATE INDEX ux_whatsapp_thread_ref"),
 ("E7 the index over every channel", MIG,
  " WHERE channel = 'WHATSAPP' AND external_thread_ref IS NOT NULL\"\"\"",
  " WHERE external_thread_ref IS NOT NULL\"\"\""),
 # --- A ---------------------------------------------------------------------------
 ("A1 a reference without a provider accepted", MIG,
  "CHECK (external_message_ref IS NULL OR provider IS NOT NULL)", "CHECK (true)"),
 ("A2 any provider accepted", MIG,
  "CHECK (provider IS NULL OR provider = 'whatsapp')", "CHECK (true)"),
 ("A3 the provider compared without case", MIG,
  "provider = 'whatsapp')", "lower(provider) = 'whatsapp')"),
 ("A4 an INTERNAL message may carry a reference", MIG,
  "CHECK (direction <> 'INTERNAL' OR external_message_ref IS NULL)", "CHECK (true)"),
 ("A5 the provider/channel trigger not created", MIG,
  _statement("CREATE TRIGGER trg_message_provider_channel"), NOTHING),
 ("A6 the provider/channel trigger on UPDATE instead of INSERT", MIG,
  "BEFORE INSERT ON turab.communication_messages",
  "BEFORE UPDATE ON turab.communication_messages"),
 ("A7 any thread's channel accepted", MIG,
  "WHERE thread_id = NEW.thread_id AND channel = 'WHATSAPP') THEN",
  "WHERE thread_id = NEW.thread_id) THEN"),
 # --- B ---------------------------------------------------------------------------
 ("B1 the message guard not created", MIG,
  _statement("CREATE TRIGGER trg_guard_communication_message"), NOTHING),
 ("B2 the message guard on UPDATE only: a message may be deleted", MIG,
  "BEFORE UPDATE OR DELETE ON turab.communication_messages",
  "BEFORE UPDATE ON turab.communication_messages"),
 ("B3 the message guard on DELETE only: a message may be rewritten", MIG,
  "BEFORE UPDATE OR DELETE ON turab.communication_messages",
  "BEFORE DELETE ON turab.communication_messages"),
] + _frozen("B", 4, MESSAGE_OLD, MESSAGE_COLUMNS, "a message column") + [
 ("B16 UNKNOWN -> FAILED accepted (G7-5's contradiction back)", MIG,
  "(OLD.delivery_status = 'UNKNOWN' AND rank_new IS NOT NULL)",
  "(OLD.delivery_status = 'UNKNOWN')"),
 ("B17 UNKNOWN moves nowhere", MIG,
  "(OLD.delivery_status = 'UNKNOWN' AND rank_new IS NOT NULL)", "(false)"),
 ("B18 backward moves accepted", MIG, "rank_new > rank_old", "rank_new <> rank_old"),
 ("B19 FAILED from DELIVERED accepted", MIG,
  "OLD.delivery_status IN ('QUEUED', 'SENT')",
  "OLD.delivery_status IN ('QUEUED', 'SENT', 'DELIVERED')"),
 ("B20 FAILED from SENT refused", MIG,
  "OLD.delivery_status IN ('QUEUED', 'SENT')", "OLD.delivery_status IN ('QUEUED')"),
 ("B21 the forward order loses DELIVERED", MIG,
  """  rank_new := array_position(ARRAY['QUEUED','SENT','DELIVERED','READ']::text[],""",
  """  rank_new := array_position(ARRAY['QUEUED','SENT','READ']::text[],"""),
 ("B22 an update that changes nothing refused", MIG,
  """  IF NEW.delivery_status IS NOT DISTINCT FROM OLD.delivery_status THEN
    RETURN NEW;
  END IF;
""", ""),
 ("B23 a refused transition returns instead of raising", MIG,
  """  RAISE EXCEPTION 'communication_messages: delivery_status % -> % refused',
    OLD.delivery_status, NEW.delivery_status;""", "  RETURN NEW;"),
 # --- C ---------------------------------------------------------------------------
 ("C1 the event guard not created", MIG,
  _statement("CREATE TRIGGER trg_guard_webhook_event"), NOTHING),
 ("C2 the event guard on UPDATE only: an event may be deleted", MIG,
  "BEFORE UPDATE OR DELETE ON turab.webhook_events", "BEFORE UPDATE ON turab.webhook_events"),
 ("C3 the event guard on DELETE only: an event may be rewritten", MIG,
  "BEFORE UPDATE OR DELETE ON turab.webhook_events", "BEFORE DELETE ON turab.webhook_events"),
] + _frozen("C", 4, EVENT_OLD, EVENT_COLUMNS, "an event field") + [
 ("C10 a PROCESSED event may be processed again", MIG,
  "IF OLD.processing_status NOT IN ('RECEIVED', 'FAILED') THEN",
  "IF OLD.processing_status NOT IN ('RECEIVED', 'FAILED', 'PROCESSED') THEN"),
 ("C11 a FAILED event is final", MIG,
  "IF OLD.processing_status NOT IN ('RECEIVED', 'FAILED') THEN",
  "IF OLD.processing_status NOT IN ('RECEIVED') THEN"),
 ("C12 an event may go back to RECEIVED", MIG,
  "IF NEW.processing_status NOT IN ('PROCESSED', 'IGNORED', 'FAILED') THEN",
  "IF NEW.processing_status NOT IN ('PROCESSED', 'IGNORED', 'FAILED', 'RECEIVED') THEN"),
 # --- D ---------------------------------------------------------------------------
] + [
 (f"D{1 + i} {column} left ON DELETE SET NULL", MIG, f"{anchor} ON DELETE RESTRICT",
  f"{anchor} ON DELETE SET NULL")
 for i, (column, anchor) in enumerate(KEYS)
] + [
 ("D7 the thread guard not created", MIG,
  _statement("CREATE TRIGGER trg_guard_communication_thread"), NOTHING),
 ("D8 the thread guard on UPDATE only: a thread may be deleted", MIG,
  "BEFORE UPDATE OR DELETE ON turab.communication_threads",
  "BEFORE UPDATE ON turab.communication_threads"),
 ("D9 the thread guard on DELETE only: a thread may be rewritten", MIG,
  "BEFORE UPDATE OR DELETE ON turab.communication_threads",
  "BEFORE DELETE ON turab.communication_threads"),
] + _frozen("D", 10, THREAD_OLD, THREAD_COLUMNS, "a thread column") + [
 ("D20 a nested update passes (D3's limit)", MIG,
  """    RAISE EXCEPTION 'communication_threads: DELETE refused';
  END IF;
""", """    RAISE EXCEPTION 'communication_threads: DELETE refused';
  END IF;
  IF pg_trigger_depth() > 1 THEN
    RETURN NEW;
  END IF;
"""),
 ("D21 last_message_at may move back", MIG,
  "NEW.last_message_at < OLD.last_message_at",
  "NEW.last_message_at < OLD.last_message_at - interval '1 year'"),
 ("D22 last_message_at may be cleared", MIG,
  "AND (NEW.last_message_at IS NULL OR NEW.last_message_at < OLD.last_message_at) THEN",
  "AND (NEW.last_message_at < OLD.last_message_at) THEN"),
 ("D23 the threads' ALTER not run: five keys stay SET NULL", MIG,
  _statement("ALTER TABLE turab.communication_threads\n  DROP CONSTRAINT"
             " communication_threads_party_id_fkey,\n  ADD CONSTRAINT"
             " communication_threads_party_id_fkey FOREIGN KEY (party_id)\n"
             "      REFERENCES turab.parties(party_id) ON DELETE RESTRICT"), NOTHING),
 # --- G: the downgrade ------------------------------------------------------------
 ("G1 the downgrade leaves the party key RESTRICT", MIG,
  "REFERENCES turab.parties(party_id) ON DELETE SET NULL",
  "REFERENCES turab.parties(party_id) ON DELETE RESTRICT"),
 ("G2 the downgrade leaves the sender key RESTRICT", MIG,
  "FOREIGN KEY (sent_by_account_id)\n      REFERENCES turab.user_accounts(account_id)"
  " ON DELETE SET NULL",
  "FOREIGN KEY (sent_by_account_id)\n      REFERENCES turab.user_accounts(account_id)"
  " ON DELETE RESTRICT"),
 ("G3 the downgrade leaves the index", MIG, '"DROP INDEX turab.ux_whatsapp_thread_ref"',
  NOTHING),
 ("G4 the downgrade leaves one CHECK of part A", MIG,
  "  DROP CONSTRAINT ck_internal_message_has_no_ref,\n", ""),
 ("G5 the downgrade leaves the scoped CHECK", MIG,
  '"ALTER TABLE turab.communication_threads DROP CONSTRAINT ck_whatsapp_thread_ref_scoped"',
  NOTHING),
]

def _check_anchors() -> None:
    """Each anchor must name ONE site: the runner replaces every occurrence,
    and a second site would weaken two guards under one name. Each mutation
    has its own label. Run before a run, never on import."""
    source = (ROOT / MIG).read_text()
    for name, _rel, old, _new in MUTATIONS:
        assert source.count(old) == 1, (name, source.count(old))
    assert len({m[0].split()[0] for m in MUTATIONS}) == len(MUTATIONS)


if __name__ == "__main__":
    _check_anchors()
    run("TURAB — Slice 7 step 1: which test refuses which weakened guard of migration 0008",
        TESTS, MUTATIONS, sys.argv[1:], deselect=DESELECT)
