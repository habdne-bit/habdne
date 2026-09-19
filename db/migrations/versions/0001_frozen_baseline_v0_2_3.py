"""Frozen technical baseline v0.2.3 as the initial migration.

Revision ID: 0001_frozen_baseline_v0_2_3
Revises: (none — this is the root)

Ref: RFC-001 R14.4; `docs/gate/TECHNICAL_BASELINE_FROZEN_v0.2.3.md`.

R14.4 says the frozen schema **is** the initial migration and that Alembic
must not recreate it from models. This revision therefore applies
`docs/handoff/04_DATABASE/schema_v0.2.3.sql` **verbatim**, as bytes read from
the vendored handoff package. It contains no transcription of that file, so
there is no second copy of the baseline to drift.

Two consequences are deliberate.

**The digest is checked before the file is executed.** A migration that
silently applied whatever happened to be at that path would turn an edit to
the frozen package into an approved schema change. If the bytes are not the
frozen ones, this refuses to run and names the mismatch. That is the same
guarantee `verify_handoff.py` gives in CI, enforced at the one moment it
matters most.

**`downgrade()` refuses.** Dropping the baseline is not a migration; it is
`db/dev/reset_db.sh` against a development database, which says so in its own
name and refuses to run against anything that looks like production.
"""
from __future__ import annotations

import hashlib
import pathlib

from alembic import op

revision = "0001_frozen_baseline_v0_2_3"
down_revision = None
branch_labels = None
depends_on = None

#: The frozen artifact and its digest, as recorded at the v0.2.3 freeze.
SCHEMA = (
    pathlib.Path(__file__).resolve().parents[3]
    / "docs" / "handoff" / "04_DATABASE" / "schema_v0.2.3.sql"
)
SCHEMA_SHA256 = "789841a1a41d869ca78de256879e62950f0672c9719c40a94408c549e28d98a0"


def _frozen_sql() -> str:
    raw = SCHEMA.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SCHEMA_SHA256:
        raise SystemExit(
            f"refusing to migrate: {SCHEMA.name} is not the frozen baseline.\n"
            f"  expected {SCHEMA_SHA256}\n"
            f"  found    {digest}\n"
            "The frozen package is vendored byte-for-byte and corrected only by "
            "a new official handoff (RFC-001 R14.6). Applying an edited baseline "
            "as this revision would make a local edit the new truth."
        )
    return raw.decode("utf-8")


def upgrade() -> None:
    op.execute(_frozen_sql())


def downgrade() -> None:
    raise NotImplementedError(
        "There is no downgrade from the initial baseline. To rebuild a "
        "development database from zero, use db/dev/reset_db.sh."
    )
