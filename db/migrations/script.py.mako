"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Created: ${create_date}

A migration in TURAB is a proposed change to a FROZEN baseline, not routine
output (RFC-001 R14.6). State what it changes and why the change was approved.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "raise NotImplementedError"}


def downgrade() -> None:
    ${downgrades if downgrades else "raise NotImplementedError"}
