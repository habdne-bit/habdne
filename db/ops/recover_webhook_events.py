#!/usr/bin/env python3
"""The operator recovery command for stuck webhook events (G7-2 (v)).

    TURAB_DATABASE_URL=... .venv/bin/python db/ops/recover_webhook_events.py

An operator's script, not an HTTP operation. It runs T2 again on every
`whatsapp` event RECEIVED for longer than 5 minutes, and on every FAILED one,
skipping the rows another processor holds (`FOR UPDATE SKIP LOCKED`).

**Its limit, accepted in the review of `58a0067`:** it recovers from the
content-free payload. A message whose content existed is stored WITHOUT it
(`content_withheld_reason: RECOVERED_WITHOUT_CONTENT`); only the relay's
redelivery brings content back. It is not a full recovery of the archive.

It prints the count of each outcome and nothing else: no reference, no
payload, no content (G7-9 (4)).
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from turab.db.session import create_app_engine, session_factory  # noqa: E402
from turab.services import webhooks  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--delay-seconds", type=int, default=webhooks.RECOVERY_DELAY_SECONDS,
                        help="a RECEIVED event older than this is stuck (default 300)")
    args = parser.parse_args(argv)
    if args.delay_seconds < 0:
        parser.error("--delay-seconds must not be negative")
    engine = create_app_engine()
    trace_id = f"recovery-{uuid.uuid4().hex}"
    session = session_factory(engine)()
    try:
        outcomes = webhooks.recover(session, trace_id, delay_seconds=args.delay_seconds)
    finally:
        session.close()
        engine.dispose()
    print(f"trace_id {trace_id}")
    for outcome in sorted(outcomes):
        print(f"{outcome} {outcomes[outcome]}")
    print(f"total {sum(outcomes.values())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
