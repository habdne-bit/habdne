#!/usr/bin/env python3
"""The one-time backfill of the messages' interactions (G7-17 (i), G7-18 (v)).

    TURAB_DATABASE_URL=... .venv/bin/python db/ops/backfill_message_interactions.py

An operator's script, not an HTTP operation, run once when step 4 is
deployed. It writes one `interactions` row for every message that has none,
in one transaction, actor-less (audit context `backfillMessageInteractions`),
under a transaction-level advisory lock: a second run waits for the first,
then finds nothing left to write. A re-run writes nothing.

**Stated, as the review of bf1fe3d asks:** for the messages that existed
before step 4, the atomicity of a message with its interaction does not hold
retroactively. Their interaction is written later, by this script: its
`created_at` is this run's time, its `occurred_at` the message's.

It prints the count written and nothing else: no id, no content.
"""
from __future__ import annotations

import pathlib
import sys
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from turab.db.session import create_app_engine, session_factory  # noqa: E402
from turab.services import message_interactions  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    if argv:
        print("usage: backfill_message_interactions.py (no arguments)", file=sys.stderr)
        return 2
    engine = create_app_engine()
    trace_id = f"backfill-{uuid.uuid4().hex}"
    session = session_factory(engine)()
    try:
        written = message_interactions.backfill(session, trace_id)
    finally:
        session.close()
        engine.dispose()
    print(f"trace_id {trace_id}")
    print(f"written {written}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
