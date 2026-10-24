"""Communication records: identity, append-only rows, frozen threads.

Revision ID: 0008_communication_records
Revises: 0007_task_work_and_evidence

Slice 7 plan revision 4 (`docs/gate/SLICE_7_PLAN.md`), §5.1, parts E, A, B,
C and D2, approved in the review of 38281ab with the decisions they rest on:
G7-3 (part E), G7-4 (part A), G7-5 (part B), G7-2 (v) (part C), G7-12 (D),
decided D2 in the review of 4aed49b. This revision implements that text
exactly: `UPGRADE` below is the approved block, statement by statement, and
`tests/test_migration_0008_communication_records.py` compares the two.

## What the frozen schema left open

Measured before this revision (`docs/gate/evidence/SLICE7-PLAN-MEASUREMENTS.txt`):
- M1: with `provider` NULL, one `external_message_ref` is stored twice, in
  two threads: `UNIQUE(provider, external_message_ref)` does not apply;
- M3: as the application role, every UPDATE and DELETE of a message, of a
  webhook event and of a thread's links is accepted; the four communication
  tables carry no user trigger;
- M8: a guard freezing a thread's links also refuses the foreign keys'
  `ON DELETE SET NULL`, which is why part D (D2) makes six keys RESTRICT;
- and, read in the plan: nothing makes a WHATSAPP thread's reference unique,
  so an inbound message could resolve to two threads (review of 4aed49b).

## What this revision adds

**E.** A pre-check that refuses the migration if an existing WHATSAPP thread
reference is unscoped or shared, naming the counts; then
`ck_whatsapp_thread_ref_scoped` and the partial unique index
`ux_whatsapp_thread_ref`.

**A.** Three CHECKs on `communication_messages` (a reference has a provider;
the provider is `whatsapp`; an INTERNAL message has no reference) and the
BEFORE INSERT trigger `trg_message_provider_channel` (a message with a
provider belongs to a WHATSAPP thread).

**B.** `trg_guard_communication_message`: a message never changes, except its
`delivery_status`, by the accepted transitions only (UNKNOWN -> QUEUED, SENT,
DELIVERED or READ; forward within QUEUED < SENT < DELIVERED < READ; QUEUED or
SENT -> FAILED). DELETE is refused.

**C.** `trg_guard_webhook_event`: an event never changes, except its
processing fields, from RECEIVED or FAILED only, to PROCESSED, IGNORED or
FAILED. DELETE is refused.

**D (D2).** Six foreign keys, which the frozen schema declares
`ON DELETE SET NULL`, become `ON DELETE RESTRICT`: a thread's `party_id`,
`request_id`, `property_id`, `opportunity_id` and `created_by_account_id`, and
a message's `sent_by_account_id`. `trg_guard_communication_thread`: a thread
never changes after INSERT, except `last_message_at` moving forward. DELETE is
refused.

**A frozen object changes.** Part D alters six constraints of the frozen
schema. As `0003` did for a function body, this is a structural evolution ON
TOP of the baseline: `schema_v0.2.3.sql` keeps its digest, revision `0001`
still applies it verbatim, and each changed key is a declared delta in
`db/gate/migration_deltas.py`, digested before and after. The change was put
to the reviewer as such ("six frozen constraints change", plan G7-12 (D2)) and
approved with this text (review of 38281ab).

No table, no column. Proven at trigger level only, under the superuser role
(EN-02): K06 stays UNPROVEN.

## Downgrade

Allowed, unlike `0003`-`0007`: it removes guards and constraints and writes
no row, so nothing recorded is lost by it. It drops the four triggers and
their functions, part A's three CHECKs, part E's CHECK and index, and restores
the six keys to `ON DELETE SET NULL`, as the frozen schema declares them.
"""
from __future__ import annotations

from alembic import op

revision = "0008_communication_records"
down_revision = "0007_task_work_and_evidence"
branch_labels = None
depends_on = None

#: The approved text of plan §5.1, statement by statement, in its order: E, A,
#: B, C, D2. Each is executed as written.
UPGRADE: tuple[str, ...] = (
    """DO $$
DECLARE
  malformed integer;
  duplicated integer;
BEGIN
  SELECT count(*) INTO malformed FROM turab.communication_threads
   WHERE channel = 'WHATSAPP' AND external_thread_ref IS NOT NULL
     AND external_thread_ref !~ '^[^:]+:[^:]+$';
  SELECT count(*) INTO duplicated FROM (
    SELECT external_thread_ref FROM turab.communication_threads
     WHERE channel = 'WHATSAPP' AND external_thread_ref IS NOT NULL
     GROUP BY external_thread_ref HAVING count(*) > 1) d;
  IF malformed > 0 OR duplicated > 0 THEN
    RAISE EXCEPTION '0008: % WHATSAPP thread reference(s) not scoped, % reference(s) shared; resolve them before this migration',
      malformed, duplicated;
  END IF;
END $$""",
    """ALTER TABLE turab.communication_threads
  ADD CONSTRAINT ck_whatsapp_thread_ref_scoped
      CHECK (channel <> 'WHATSAPP' OR external_thread_ref IS NULL
             OR external_thread_ref ~ '^[^:]+:[^:]+$')""",
    """CREATE UNIQUE INDEX ux_whatsapp_thread_ref
    ON turab.communication_threads (external_thread_ref)
 WHERE channel = 'WHATSAPP' AND external_thread_ref IS NOT NULL""",
    """ALTER TABLE turab.communication_messages
  ADD CONSTRAINT ck_message_ref_needs_provider
      CHECK (external_message_ref IS NULL OR provider IS NOT NULL),
  ADD CONSTRAINT ck_message_provider_known
      CHECK (provider IS NULL OR provider = 'whatsapp'),
  ADD CONSTRAINT ck_internal_message_has_no_ref
      CHECK (direction <> 'INTERNAL' OR external_message_ref IS NULL)""",
    """CREATE FUNCTION turab.enforce_message_provider_channel() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.provider IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM turab.communication_threads
        WHERE thread_id = NEW.thread_id AND channel = 'WHATSAPP') THEN
    RAISE EXCEPTION 'communication_messages: provider % outside a WHATSAPP thread',
      NEW.provider;
  END IF;
  RETURN NEW;
END $$""",
    """CREATE TRIGGER trg_message_provider_channel
  BEFORE INSERT ON turab.communication_messages
  FOR EACH ROW EXECUTE FUNCTION turab.enforce_message_provider_channel()""",
    """CREATE FUNCTION turab.guard_communication_message() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  rank_old integer;
  rank_new integer;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'communication_messages: DELETE refused (append-only)';
  END IF;
  IF (NEW.message_id, NEW.thread_id, NEW.provider, NEW.external_message_ref,
      NEW.direction, NEW.message_type, NEW.body_text, NEW.media_ref,
      NEW.occurred_at, NEW.sent_by_account_id, NEW.metadata, NEW.created_at)
     IS DISTINCT FROM
     (OLD.message_id, OLD.thread_id, OLD.provider, OLD.external_message_ref,
      OLD.direction, OLD.message_type, OLD.body_text, OLD.media_ref,
      OLD.occurred_at, OLD.sent_by_account_id, OLD.metadata, OLD.created_at) THEN
    RAISE EXCEPTION 'communication_messages: only delivery_status may change';
  END IF;
  IF NEW.delivery_status IS NOT DISTINCT FROM OLD.delivery_status THEN
    RETURN NEW;
  END IF;
  rank_old := array_position(ARRAY['QUEUED','SENT','DELIVERED','READ']::text[],
                             OLD.delivery_status::text);
  rank_new := array_position(ARRAY['QUEUED','SENT','DELIVERED','READ']::text[],
                             NEW.delivery_status::text);
  IF (OLD.delivery_status = 'UNKNOWN' AND rank_new IS NOT NULL)
     OR (rank_old IS NOT NULL AND rank_new IS NOT NULL AND rank_new > rank_old)
     OR (NEW.delivery_status = 'FAILED' AND OLD.delivery_status IN ('QUEUED', 'SENT')) THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'communication_messages: delivery_status % -> % refused',
    OLD.delivery_status, NEW.delivery_status;
END $$""",
    """CREATE TRIGGER trg_guard_communication_message
  BEFORE UPDATE OR DELETE ON turab.communication_messages
  FOR EACH ROW EXECUTE FUNCTION turab.guard_communication_message()""",
    """CREATE FUNCTION turab.guard_webhook_event() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'webhook_events: DELETE refused';
  END IF;
  IF (NEW.webhook_event_id, NEW.provider, NEW.provider_event_id, NEW.event_type,
      NEW.payload, NEW.received_at)
     IS DISTINCT FROM
     (OLD.webhook_event_id, OLD.provider, OLD.provider_event_id, OLD.event_type,
      OLD.payload, OLD.received_at) THEN
    RAISE EXCEPTION 'webhook_events: only the processing fields may change';
  END IF;
  IF OLD.processing_status NOT IN ('RECEIVED', 'FAILED') THEN
    RAISE EXCEPTION 'webhook_events: a % event is final', OLD.processing_status;
  END IF;
  IF NEW.processing_status NOT IN ('PROCESSED', 'IGNORED', 'FAILED') THEN
    RAISE EXCEPTION 'webhook_events: % -> % refused',
      OLD.processing_status, NEW.processing_status;
  END IF;
  RETURN NEW;
END $$""",
    """CREATE TRIGGER trg_guard_webhook_event
  BEFORE UPDATE OR DELETE ON turab.webhook_events
  FOR EACH ROW EXECUTE FUNCTION turab.guard_webhook_event()""",
    """ALTER TABLE turab.communication_threads
  DROP CONSTRAINT communication_threads_party_id_fkey,
  ADD CONSTRAINT communication_threads_party_id_fkey FOREIGN KEY (party_id)
      REFERENCES turab.parties(party_id) ON DELETE RESTRICT,
  DROP CONSTRAINT communication_threads_request_id_fkey,
  ADD CONSTRAINT communication_threads_request_id_fkey FOREIGN KEY (request_id)
      REFERENCES turab.requests(request_id) ON DELETE RESTRICT,
  DROP CONSTRAINT communication_threads_property_id_fkey,
  ADD CONSTRAINT communication_threads_property_id_fkey FOREIGN KEY (property_id)
      REFERENCES turab.properties(property_id) ON DELETE RESTRICT,
  DROP CONSTRAINT communication_threads_opportunity_id_fkey,
  ADD CONSTRAINT communication_threads_opportunity_id_fkey FOREIGN KEY (opportunity_id)
      REFERENCES turab.opportunities(opportunity_id) ON DELETE RESTRICT,
  DROP CONSTRAINT communication_threads_created_by_account_id_fkey,
  ADD CONSTRAINT communication_threads_created_by_account_id_fkey
      FOREIGN KEY (created_by_account_id)
      REFERENCES turab.user_accounts(account_id) ON DELETE RESTRICT""",
    """ALTER TABLE turab.communication_messages
  DROP CONSTRAINT communication_messages_sent_by_account_id_fkey,
  ADD CONSTRAINT communication_messages_sent_by_account_id_fkey
      FOREIGN KEY (sent_by_account_id)
      REFERENCES turab.user_accounts(account_id) ON DELETE RESTRICT""",
    """CREATE FUNCTION turab.guard_communication_thread() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'communication_threads: DELETE refused';
  END IF;
  IF (NEW.thread_id, NEW.channel, NEW.party_id, NEW.request_id, NEW.property_id,
      NEW.opportunity_id, NEW.external_thread_ref, NEW.opened_at, NEW.archived_at,
      NEW.created_by_account_id)
     IS DISTINCT FROM
     (OLD.thread_id, OLD.channel, OLD.party_id, OLD.request_id, OLD.property_id,
      OLD.opportunity_id, OLD.external_thread_ref, OLD.opened_at, OLD.archived_at,
      OLD.created_by_account_id) THEN
    RAISE EXCEPTION 'communication_threads: a thread''s links never change';
  END IF;
  IF OLD.last_message_at IS NOT NULL
     AND (NEW.last_message_at IS NULL OR NEW.last_message_at < OLD.last_message_at) THEN
    RAISE EXCEPTION 'communication_threads: last_message_at moves forward only';
  END IF;
  RETURN NEW;
END $$""",
    """CREATE TRIGGER trg_guard_communication_thread
  BEFORE UPDATE OR DELETE ON turab.communication_threads
  FOR EACH ROW EXECUTE FUNCTION turab.guard_communication_thread()""",
)

#: The downgrade, in reverse order (plan §5.1, "The downgrade").
DOWNGRADE: tuple[str, ...] = (
    "DROP TRIGGER trg_guard_communication_thread ON turab.communication_threads",
    "DROP FUNCTION turab.guard_communication_thread()",
    """ALTER TABLE turab.communication_messages
  DROP CONSTRAINT communication_messages_sent_by_account_id_fkey,
  ADD CONSTRAINT communication_messages_sent_by_account_id_fkey
      FOREIGN KEY (sent_by_account_id)
      REFERENCES turab.user_accounts(account_id) ON DELETE SET NULL""",
    """ALTER TABLE turab.communication_threads
  DROP CONSTRAINT communication_threads_party_id_fkey,
  ADD CONSTRAINT communication_threads_party_id_fkey FOREIGN KEY (party_id)
      REFERENCES turab.parties(party_id) ON DELETE SET NULL,
  DROP CONSTRAINT communication_threads_request_id_fkey,
  ADD CONSTRAINT communication_threads_request_id_fkey FOREIGN KEY (request_id)
      REFERENCES turab.requests(request_id) ON DELETE SET NULL,
  DROP CONSTRAINT communication_threads_property_id_fkey,
  ADD CONSTRAINT communication_threads_property_id_fkey FOREIGN KEY (property_id)
      REFERENCES turab.properties(property_id) ON DELETE SET NULL,
  DROP CONSTRAINT communication_threads_opportunity_id_fkey,
  ADD CONSTRAINT communication_threads_opportunity_id_fkey FOREIGN KEY (opportunity_id)
      REFERENCES turab.opportunities(opportunity_id) ON DELETE SET NULL,
  DROP CONSTRAINT communication_threads_created_by_account_id_fkey,
  ADD CONSTRAINT communication_threads_created_by_account_id_fkey
      FOREIGN KEY (created_by_account_id)
      REFERENCES turab.user_accounts(account_id) ON DELETE SET NULL""",
    "DROP TRIGGER trg_guard_webhook_event ON turab.webhook_events",
    "DROP FUNCTION turab.guard_webhook_event()",
    "DROP TRIGGER trg_guard_communication_message ON turab.communication_messages",
    "DROP FUNCTION turab.guard_communication_message()",
    "DROP TRIGGER trg_message_provider_channel ON turab.communication_messages",
    "DROP FUNCTION turab.enforce_message_provider_channel()",
    """ALTER TABLE turab.communication_messages
  DROP CONSTRAINT ck_internal_message_has_no_ref,
  DROP CONSTRAINT ck_message_provider_known,
  DROP CONSTRAINT ck_message_ref_needs_provider""",
    "DROP INDEX turab.ux_whatsapp_thread_ref",
    "ALTER TABLE turab.communication_threads DROP CONSTRAINT ck_whatsapp_thread_ref_scoped",
)


def upgrade() -> None:
    op.execute("SET LOCAL search_path TO turab, public")
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    op.execute("SET LOCAL search_path TO turab, public")
    for statement in DOWNGRADE:
        op.execute(statement)
