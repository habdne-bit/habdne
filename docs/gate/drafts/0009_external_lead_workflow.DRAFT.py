"""DRAFT — NOT A MIGRATION. External-lead workflow: attempts, transitions, reason codes.

Revision ID: 0009_external_lead_workflow
Revises: 0008_communication_records

**Status: a draft for review, Slice 8 plan revision 4, §5A.3.** It is kept
under `docs/gate/drafts/`, which Alembic does not read by its configuration
(`alembic.ini`: `script_location = db/migrations`), and is NOT applied. The
reviews of `b39ad10` and `0a78e91` did not approve its text.

**Measured:** its statements on a scratch database
(`evidence/SLICE8-PLAN-MEASUREMENTS-R3.txt`, M7 to M11), and **this file as
an Alembic revision in the real chain after `0008`**, upgraded and
downgraded by Alembic on a scratch database, the downgrade refused with data
(`evidence/SLICE8-PLAN-MEASUREMENTS-R4.txt`, M12). Alembic was pointed at it
through an extra `version_locations` entry, on a temporary copy; nothing was
written under `db/migrations/`.

## What it would add

**A. Eight reason codes** (§5A.2): four `LEAD_CONTACT`, four `LEAD_CLOSURE`,
after a pre-check that no `LEAD_*` code exists yet (M5).

**B. `external_lead_contact_attempts`**, append-only (G8-2 (a)):
- **the clock rule:** `recorded_at` is ASSIGNED by the server at insert, by
  the BEFORE INSERT trigger (`NEW.recorded_at := clock_timestamp()`), so an
  explicit value in an INSERT is overwritten; then `CHECK (occurred_at <=
  recorded_at)`, no margin. The constraint compares two columns; the trigger
  is what makes one of them the server's clock (review of `0a78e91`;
  measured, M13). Not K06: a superuser can disable a trigger (EN-02);
- the outcome must be a `LEAD_CONTACT` code (the same BEFORE INSERT trigger);
- UPDATE and DELETE refused (trigger), as `0005`/`0006`;
- audited on INSERT by the frozen `audit_row_change('attempt_id')` (Q-A4):
  the function records the whole row, which is why the table holds **no free
  text and no content of a contact**.

**C. `trg_external_lead_transition`**, BEFORE UPDATE on `external_leads`:
- **the whole transition table of §5A.1**; a terminal status is never left;
- `CONVERTED` only with its target (the frozen check) and from `CONSENTED` or
  `PENDING_INFO`;
- `CONSENTED` only with a `party_id`;
- `DECLINED` and `CLOSED` only with a `close_reason_code` of category
  `LEAD_CLOSURE` (Q-A3); a reason code on a lead that is not `DECLINED` or
  `CLOSED` is refused;
- **a terminal lead's workflow columns are frozen**, with one exception
  (Q-B1 (a), decided in the review of `0a78e91`): **`party_id` may become
  NULL**, never another value, so the frozen key's `ON DELETE SET NULL` keeps
  working (M9). **A NULL written by hand passes the guard too**; the service
  never writes one (to be pinned by a test). The reason code never changes.
- **a `CONVERTED` lead's target never becomes NULL:** the guard lets the
  `converted_*` columns become NULL only as the frozen keys would, but the
  frozen check `ck_external_lead_converted_target` keeps a `CONVERTED` lead's
  target, `prevent_core_delete` refuses deleting a request or a property, and
  the target request's own `party_id` (`ON DELETE RESTRICT`) refuses deleting
  its party (M14). So for a `CONVERTED` lead, none of its links becomes NULL.
- **Deleting a party erases nothing captured:** the lead's `raw_payload` and
  its source's `raw_text` stay (M14). It is not an erasure of personal data.

**Not K06.** Under the superuser application role (EN-02) these are
trigger-level guards against careless writes, not a privilege boundary.

## Downgrade

Refused while data depends on it: if any attempt exists, or any lead's
`close_reason_code` is a `LEAD_*` code, it raises, naming the counts; nothing
is lost by a downgrade that runs. Otherwise it drops the triggers, their
functions and the table, then deletes the eight codes.
"""
from __future__ import annotations

from alembic import op

revision = "0009_external_lead_workflow"
down_revision = "0008_communication_records"
branch_labels = None
depends_on = None

LEAD_CODES = (
    ("LEAD_NO_ANSWER", "LEAD_CONTACT", "لم يُجب", "No answer"),
    ("LEAD_REACHED", "LEAD_CONTACT", "تم التواصل", "Reached"),
    ("LEAD_WRONG_NUMBER", "LEAD_CONTACT", "رقم خاطئ", "Wrong number"),
    ("LEAD_NUMBER_NOT_IN_SERVICE", "LEAD_CONTACT", "رقم خارج الخدمة", "Number not in service"),
    ("LEAD_DECLINED_BY_PERSON", "LEAD_CLOSURE", "رفض الشخص", "Declined by the person"),
    ("LEAD_DUPLICATE", "LEAD_CLOSURE", "مكرّر", "Duplicate"),
    ("LEAD_NOT_RELEVANT", "LEAD_CLOSURE", "خارج النطاق", "Not relevant"),
    ("LEAD_STALE", "LEAD_CLOSURE", "قديم", "Stale"),
)

#: §5A.1's transitions, as the trigger enforces them. A status not listed as
#: a key is terminal.
TRANSITIONS = {
    "DISCOVERED": ("CONTACT_ATTEMPTED", "UNREACHABLE", "CONTACTED", "DECLINED", "CLOSED"),
    "CONTACT_ATTEMPTED": ("UNREACHABLE", "CONTACTED", "DECLINED", "CLOSED"),
    "UNREACHABLE": ("CONTACT_ATTEMPTED", "CONTACTED", "DECLINED", "CLOSED"),
    "CONTACTED": ("CONSENT_PENDING", "CONSENTED", "DECLINED", "CLOSED"),
    "CONSENT_PENDING": ("CONSENTED", "DECLINED", "CLOSED"),
    "CONSENTED": ("PENDING_INFO", "CONVERTED", "DECLINED", "CLOSED"),
    "PENDING_INFO": ("CONVERTED", "DECLINED", "CLOSED"),
}


def _allowed_sql() -> str:
    return ",\n      ".join(f"('{a}','{b}')" for a, targets in TRANSITIONS.items()
                           for b in targets)


UPGRADE: tuple[str, ...] = (
    # A. pre-check, then the codes
    """DO $$
DECLARE n bigint;
BEGIN
  SELECT count(*) INTO n FROM turab.reason_codes WHERE code LIKE 'LEAD\\_%';
  IF n > 0 THEN
    RAISE EXCEPTION '0009: % reason code(s) named LEAD_* already exist', n;
  END IF;
END $$""",
    "INSERT INTO turab.reason_codes (code, category, label_ar, label_en) VALUES\n  "
    + ",\n  ".join(f"('{c}', '{k}', '{ar}', '{en}')" for c, k, ar, en in LEAD_CODES),
    # B. the attempts record
    """CREATE TABLE turab.external_lead_contact_attempts (
  attempt_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  external_lead_id    uuid NOT NULL REFERENCES turab.external_leads(external_lead_id)
                        ON DELETE RESTRICT,
  channel             turab.communication_channel NOT NULL,
  outcome_code        text NOT NULL REFERENCES turab.reason_codes(code),
  occurred_at         timestamptz NOT NULL,
  operator_account_id uuid NOT NULL REFERENCES turab.user_accounts(account_id)
                        ON DELETE RESTRICT,
  recorded_at         timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT ck_lead_attempt_not_future CHECK (occurred_at <= recorded_at)
)""",
    """CREATE INDEX idx_lead_attempts_lead ON turab.external_lead_contact_attempts
  (external_lead_id, occurred_at, attempt_id)""",
    """CREATE FUNCTION turab.enforce_lead_attempt_insert() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.recorded_at := clock_timestamp();
  IF NOT EXISTS (SELECT 1 FROM turab.reason_codes
                  WHERE code = NEW.outcome_code AND category = 'LEAD_CONTACT') THEN
    RAISE EXCEPTION 'outcome_code % is not a LEAD_CONTACT code', NEW.outcome_code;
  END IF;
  RETURN NEW;
END $$""",
    """CREATE TRIGGER trg_lead_attempt_insert BEFORE INSERT
  ON turab.external_lead_contact_attempts
  FOR EACH ROW EXECUTE FUNCTION turab.enforce_lead_attempt_insert()""",
    """CREATE FUNCTION turab.prevent_lead_attempt_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'external_lead_contact_attempts is append-only';
END $$""",
    """CREATE TRIGGER trg_lead_attempt_immutable BEFORE UPDATE OR DELETE
  ON turab.external_lead_contact_attempts
  FOR EACH ROW EXECUTE FUNCTION turab.prevent_lead_attempt_change()""",
    """CREATE TRIGGER audit_external_lead_contact_attempts AFTER INSERT
  ON turab.external_lead_contact_attempts
  FOR EACH ROW EXECUTE FUNCTION turab.audit_row_change('attempt_id')""",
    # C. the lead's transitions
    """CREATE FUNCTION turab.enforce_external_lead_transition() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status THEN
    IF (OLD.status::text, NEW.status::text) NOT IN (
      """ + _allowed_sql() + """
    ) THEN
      RAISE EXCEPTION 'external lead transition % -> % is not allowed', OLD.status, NEW.status;
    END IF;
    IF NEW.status = 'CONSENTED' AND NEW.party_id IS NULL THEN
      RAISE EXCEPTION 'CONSENTED requires party_id';
    END IF;
  END IF;
  IF NEW.status IN ('DECLINED', 'CLOSED') THEN
    IF NEW.close_reason_code IS NULL OR NOT EXISTS (
         SELECT 1 FROM turab.reason_codes
          WHERE code = NEW.close_reason_code AND category = 'LEAD_CLOSURE') THEN
      RAISE EXCEPTION '% requires a LEAD_CLOSURE reason code', NEW.status;
    END IF;
  ELSIF NEW.close_reason_code IS NOT NULL THEN
    RAISE EXCEPTION 'a reason code belongs to a DECLINED or CLOSED lead only';
  END IF;
  IF OLD.status IN ('CONVERTED', 'DECLINED', 'CLOSED') THEN
    IF NEW.close_reason_code IS DISTINCT FROM OLD.close_reason_code
       OR (NEW.party_id IS NOT NULL
           AND NEW.party_id IS DISTINCT FROM OLD.party_id)
       OR (NEW.converted_request_id IS NOT NULL
           AND NEW.converted_request_id IS DISTINCT FROM OLD.converted_request_id)
       OR (NEW.converted_property_id IS NOT NULL
           AND NEW.converted_property_id IS DISTINCT FROM OLD.converted_property_id) THEN
      RAISE EXCEPTION 'a terminal lead''s workflow columns are frozen (a link may only become NULL)';
    END IF;
  END IF;
  RETURN NEW;
END $$""",
    """CREATE TRIGGER trg_external_lead_transition BEFORE UPDATE ON turab.external_leads
  FOR EACH ROW EXECUTE FUNCTION turab.enforce_external_lead_transition()""",
)

DOWNGRADE: tuple[str, ...] = (
    """DO $$
DECLARE attempts bigint; coded bigint;
BEGIN
  SELECT count(*) INTO attempts FROM turab.external_lead_contact_attempts;
  SELECT count(*) INTO coded FROM turab.external_leads WHERE close_reason_code LIKE 'LEAD\\_%';
  IF attempts > 0 OR coded > 0 THEN
    RAISE EXCEPTION '0009 downgrade refused: % attempt(s), % lead(s) with a LEAD_* reason',
      attempts, coded;
  END IF;
END $$""",
    "DROP TRIGGER trg_external_lead_transition ON turab.external_leads",
    "DROP FUNCTION turab.enforce_external_lead_transition()",
    "DROP TRIGGER audit_external_lead_contact_attempts ON turab.external_lead_contact_attempts",
    "DROP TRIGGER trg_lead_attempt_immutable ON turab.external_lead_contact_attempts",
    "DROP FUNCTION turab.prevent_lead_attempt_change()",
    "DROP TRIGGER trg_lead_attempt_insert ON turab.external_lead_contact_attempts",
    "DROP FUNCTION turab.enforce_lead_attempt_insert()",
    "DROP TABLE turab.external_lead_contact_attempts",
    "DELETE FROM turab.reason_codes WHERE code IN ("
    + ", ".join(f"'{c}'" for c, *_ in LEAD_CODES) + ")",
)


def upgrade() -> None:
    op.execute("SET LOCAL search_path TO turab, public")
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    op.execute("SET LOCAL search_path TO turab, public")
    for statement in DOWNGRADE:
        op.execute(statement)
