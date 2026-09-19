"""REQUEST_CLOSURE reason codes.

Revision ID: 0002_request_closure_reasons
Revises: 0001_frozen_baseline_v0_2_3

A migration in TURAB is a proposed change to a FROZEN baseline, not routine
output (RFC-001 R14.6). This one adds DATA, not structure: three rows in
`reason_codes`, under a new category `REQUEST_CLOSURE`.

## Why it is needed

`requests.close_reason_code` is FK-constrained to `reason_codes`, and the
frozen master data carries no category describing why a REQUEST closed — only
FRESHNESS, GENERAL, IDENTITY, MATCH, OPPORTUNITY and PERMISSION. An operator
closing a request could record only `OTHER`, or misuse an OPPORTUNITY code
that means something about a different entity.

## What it does not do

- It does **not** edit the published baseline. `seed_master_data_v0.2.3.sql`
  keeps its digest; this is additive data applied on top.
- It does **not** change the meaning of the historical `OTHER` row. That row
  stays exactly as seeded, in category GENERAL, and nothing is re-pointed at
  the new codes.

## Re-runnable by design

`INSERT ... WHERE NOT EXISTS`, not `ON CONFLICT DO NOTHING`: the frozen schema
carries BEFORE INSERT triggers on core tables, and `ON CONFLICT` does not stop
those from firing. The same lesson cost a seed re-run earlier in this project.
"""
from __future__ import annotations

from alembic import op

revision = "0002_request_closure_reasons"
down_revision = "0001_frozen_baseline_v0_2_3"
branch_labels = None
depends_on = None

CATEGORY = "REQUEST_CLOSURE"

#: (code, label_ar, label_en)
CODES = (
    (
        "REQUEST_FULFILLED",
        "أفاد صاحب الطلب بأن حاجته تحققت، داخل تُراب أو خارجها",
        "The requester reported their need was met, inside or outside TURAB",
    ),
    (
        "REQUEST_WITHDRAWN",
        "أفاد صاحب الطلب بأنه أنهى البحث أو سحب الطلب",
        "The requester reported they ended the search or withdrew the request",
    ),
    (
        "REQUEST_CLOSED_OTHER",
        "سبب آخر موضح بملاحظة إلزامية",
        "Another reason, explained in a mandatory note",
    ),
)


def upgrade() -> None:
    for code, label_ar, label_en in CODES:
        op.execute(
            f"""
            INSERT INTO turab.reason_codes (code, category, label_ar, label_en, active)
            SELECT '{code}', '{CATEGORY}', '{label_ar}', '{label_en}', true
             WHERE NOT EXISTS (
                   SELECT 1 FROM turab.reason_codes WHERE code = '{code}')
            """
        )


def downgrade() -> None:
    """Deliberately refuses.

    A closed request may already reference one of these codes, and removing
    the row would either break the foreign key or silently strip the reason a
    request was closed for. Reversing this is a data decision, not a schema
    one.
    """
    raise NotImplementedError(
        "reason codes may be deactivated (active = false) but not removed: "
        "closed requests reference them"
    )
