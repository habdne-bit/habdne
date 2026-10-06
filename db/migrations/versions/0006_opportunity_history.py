"""An opportunity's history cannot be rewritten.

Revision ID: 0006_opportunity_history
Revises: 0005_match_history_immutability

Decision G5-12, Slice 5 plan revision 4 (`docs/gate/SLICE_5_PLAN.md`),
approved for step 1 in the review of 6ba73ce. This revision implements that
text exactly. It is structural only: no table, no column, no reason code,
and no data.

## What the frozen schema left open

Measured before this revision (`docs/gate/evidence/SLICE5-PLAN-MEASUREMENTS.txt`
§B; again by the shipped tests, `SLICE5-STEP1-0006-BEFORE-FIX.txt`).

**Accepted on an opportunity, though it rewrites history:**
- an UPDATE of any of these columns (B4–B9):
  - `commercial_context_snapshot`;
  - `permission_snapshot`;
  - `why_real`;
  - `sharing_scope`;
  - `created_by_account_id`;
  - `created_at`.
- every status move tried (B11–B16), including CLOSED -> NEW;
- clearing `shared_at` (B17).

**What the frozen schema already refused:** only `request_id`, `property_id`
and `approved_match_id`, and that by `trg_opportunity_gate`'s re-check (B1–B3).

## What this revision adds

Two functions and two triggers on `turab.opportunities`. The plan's
sentence "one function and two triggers" contradicts its own list, which
names two functions, each with its rules. The two named functions are what
is implemented, and the delivery note states the discrepancy.

1. **`enforce_opportunity_history()`, with `trg_opportunity_history`
   BEFORE UPDATE.** Its rules, in this order:
   1. A CLOSED row is final.
   2. These columns are written once: `request_id`, `property_id`,
      `approved_match_id`, `commercial_context_snapshot`,
      `permission_snapshot`, `why_real`, `known_differences`,
      `sharing_scope`, `created_by_account_id` and `created_at`.
   3. A status change must be one of the five edges:
      - NEW -> SHARED;
      - NEW -> CLOSED;
      - SHARED -> ENGAGED;
      - SHARED -> CLOSED;
      - ENGAGED -> CLOSED.
   4. `closed_at` and `close_reason_code` are each set exactly when the
      status is CLOSED.
   5. `shared_at` is fixed once set, is set on NEW -> SHARED, and is null
      otherwise.
   6. `engaged_at` is fixed once set, is set on SHARED -> ENGAGED, and is
      null otherwise.
2. **`enforce_opportunity_birth()`, with `trg_opportunity_birth` BEFORE
   INSERT.** A new row is NEW and VALID, with no shared, engaged or closing
   time and no close reason.

Rules 5 and 6 bind a stamp to the EDGE of its event (R4-1). So:
- NEW -> CLOSED leaves both stamps null;
- SHARED -> CLOSED leaves `engaged_at` null;
- no UPDATE can write the stamp of an event that did not happen.

**Every refusal is P0001, with a fixed text that names no id.** No service
maps these texts; typed answers come from pre-checks (plan §2, item 7).

## Left writable

These columns stay writable on an open row, on purpose:
- `validity_status`, `last_confirmed_at`, `last_activity_at`;
- `current_permission_binding_id`;
- **`current_offer_id` (B10).** The contract lets revalidate "update current
  offer context" (`API_CONTRACTS` §4.11). Slice 5's guard for it is the
  service's, not this revision's (G5-12).

## Trigger order

PostgreSQL fires BEFORE triggers of one event in name order.
- `trg_opportunity_birth` fires before `trg_opportunity_gate`. A refused
  birth therefore reports the birth rule.
- `trg_opportunity_gate` fires before `trg_opportunity_history`. B1–B3
  therefore still report the frozen gate's refusal, and rule 2 is a second
  guard behind it.

## Downgrade

Refused, like 0003's and 0005's. Reverting it would re-open opportunity
history to silent rewriting.
"""
from __future__ import annotations

from alembic import op

revision = "0006_opportunity_history"
down_revision = "0005_match_history_immutability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL search_path TO turab, public")
    op.execute(
        """CREATE FUNCTION turab.enforce_opportunity_history()
           RETURNS trigger LANGUAGE plpgsql AS $$
           BEGIN
             -- 1. A CLOSED row is final.
             IF OLD.status = 'CLOSED' THEN
               RAISE EXCEPTION 'Opportunity history: a CLOSED opportunity is final';
             END IF;
             -- 2. Written once.
             IF (NEW.request_id, NEW.property_id, NEW.approved_match_id,
                 NEW.commercial_context_snapshot, NEW.permission_snapshot, NEW.why_real,
                 NEW.known_differences, NEW.sharing_scope, NEW.created_by_account_id,
                 NEW.created_at)
                IS DISTINCT FROM
                (OLD.request_id, OLD.property_id, OLD.approved_match_id,
                 OLD.commercial_context_snapshot, OLD.permission_snapshot, OLD.why_real,
                 OLD.known_differences, OLD.sharing_scope, OLD.created_by_account_id,
                 OLD.created_at) THEN
               RAISE EXCEPTION 'Opportunity history: the request, property, approved match, snapshots, why_real, known_differences, sharing_scope, creator and creation time are written once';
             END IF;
             -- 3. Only the five edges.
             IF NEW.status IS DISTINCT FROM OLD.status
                AND (OLD.status::text, NEW.status::text) NOT IN (
                      ('NEW', 'SHARED'), ('NEW', 'CLOSED'), ('SHARED', 'ENGAGED'),
                      ('SHARED', 'CLOSED'), ('ENGAGED', 'CLOSED')) THEN
               RAISE EXCEPTION 'Opportunity history: this status change is not a permitted edge';
             END IF;
             -- 4. The closing fields go with the CLOSED status, both ways.
             IF (NEW.closed_at IS NOT NULL) <> (NEW.status = 'CLOSED')
                OR (NEW.close_reason_code IS NOT NULL) <> (NEW.status = 'CLOSED') THEN
               RAISE EXCEPTION 'Opportunity history: closed_at and close_reason_code are set exactly when the status is CLOSED';
             END IF;
             -- 5. shared_at records an event that happened.
             IF OLD.shared_at IS NOT NULL THEN
               IF NEW.shared_at IS DISTINCT FROM OLD.shared_at THEN
                 RAISE EXCEPTION 'Opportunity history: shared_at is set only on NEW -> SHARED, and never changed';
               END IF;
             ELSIF OLD.status = 'NEW' AND NEW.status = 'SHARED' THEN
               IF NEW.shared_at IS NULL THEN
                 RAISE EXCEPTION 'Opportunity history: shared_at is set only on NEW -> SHARED, and never changed';
               END IF;
             ELSIF NEW.shared_at IS NOT NULL THEN
               RAISE EXCEPTION 'Opportunity history: shared_at is set only on NEW -> SHARED, and never changed';
             END IF;
             -- 6. engaged_at records an event that happened.
             IF OLD.engaged_at IS NOT NULL THEN
               IF NEW.engaged_at IS DISTINCT FROM OLD.engaged_at THEN
                 RAISE EXCEPTION 'Opportunity history: engaged_at is set only on SHARED -> ENGAGED, and never changed';
               END IF;
             ELSIF OLD.status = 'SHARED' AND NEW.status = 'ENGAGED' THEN
               IF NEW.engaged_at IS NULL THEN
                 RAISE EXCEPTION 'Opportunity history: engaged_at is set only on SHARED -> ENGAGED, and never changed';
               END IF;
             ELSIF NEW.engaged_at IS NOT NULL THEN
               RAISE EXCEPTION 'Opportunity history: engaged_at is set only on SHARED -> ENGAGED, and never changed';
             END IF;
             RETURN NEW;
           END $$"""
    )
    op.execute(
        """CREATE TRIGGER trg_opportunity_history
             BEFORE UPDATE ON turab.opportunities
             FOR EACH ROW EXECUTE FUNCTION turab.enforce_opportunity_history()"""
    )
    op.execute(
        """CREATE FUNCTION turab.enforce_opportunity_birth()
           RETURNS trigger LANGUAGE plpgsql AS $$
           BEGIN
             IF NEW.status <> 'NEW' OR NEW.validity_status <> 'VALID'
                OR NEW.shared_at IS NOT NULL OR NEW.engaged_at IS NOT NULL
                OR NEW.closed_at IS NOT NULL OR NEW.close_reason_code IS NOT NULL THEN
               RAISE EXCEPTION 'Opportunity birth: a new opportunity is NEW and VALID, with no shared, engaged or closing time and no close reason';
             END IF;
             RETURN NEW;
           END $$"""
    )
    op.execute(
        """CREATE TRIGGER trg_opportunity_birth
             BEFORE INSERT ON turab.opportunities
             FOR EACH ROW EXECUTE FUNCTION turab.enforce_opportunity_birth()"""
    )


def downgrade() -> None:
    """Refused. See the module docstring."""
    raise RuntimeError(
        "0006 has no downgrade: reverting it lets an opportunity's history be "
        "rewritten (G5-12). If that is genuinely wanted, write a forward "
        "migration that says why."
    )
