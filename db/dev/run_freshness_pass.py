#!/usr/bin/env python3
"""Run a freshness pass, once, against the active policy.

`--kind request` (the default, unchanged) moves stale ACTIVE requests to
NEEDS_CONFIRMATION. `--kind property` (Slice 3 step 4, plan §3.3) moves stale
availability to NEEDS_CONFIRMATION for the four named values only.

Ref: IMPLEMENTATION_SLICES_v0.2.md Slice 2 ("reconfirmation/freshness");
Developer Reference Spec §5.2, §15.1.

## What this is, and what it is not

**It is an administrative command that must be RUN.** Nothing in TURAB calls
it. There is no scheduler, no timer and no background worker in this version:
the frozen contract declares no scheduled-job operation and the handoff names
no schedule, so none was invented. A request therefore becomes
`NEEDS_CONFIRMATION` when someone runs this, and not before.

**It is not a freshness mechanism that maintains itself.** Any report that
describes it as one is wrong. Deciding what runs it, and how often, is still
open.

## What it does

Moves every `ACTIVE` request whose `last_confirmed_at` is older than the
ACTIVE matching policy's `freshness_threshold_days.request` to
`NEEDS_CONFIRMATION` — the one edge §5.2 defines for this. It reads the
threshold from the policy row, never from code, and refuses to run if no
active policy carries one.

Requests that have been reconfirmed are, by construction, not stale, so a
second run immediately after the first moves nothing.

Usage:
  TURAB_DATABASE_URL=... db/dev/run_freshness_pass.py [--dry-run] [--limit N]

Exit codes: 0 ran (including "moved nothing"); 2 no usable active policy.
"""
from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2] / "src"))

from turab.db.session import audited_transaction  # noqa: E402
from turab.services import freshness, properties as property_service  # noqa: E402
from turab.services import requests as request_service  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would move, change nothing")
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--kind", choices=("request", "property"), default="request")
    args = ap.parse_args()

    url = os.environ.get("TURAB_DATABASE_URL")
    if not url:
        print("TURAB_DATABASE_URL is not set", file=sys.stderr)
        return 2

    engine = create_engine(url, future=True)
    try:
        # The inspection and the write get SEPARATE sessions on purpose. A
        # read opens a transaction, and `audited_transaction` must own the
        # one it commits — the same ordering that produced a 500 on every
        # guarded command earlier in this slice.
        if args.kind == "property":
            threshold = freshness.property_threshold_days
            preview = property_service.stale_available_properties
            apply = property_service.mark_stale_availability
            noun = "property availability value(s)"
        else:
            threshold = freshness.request_threshold_days
            preview = request_service.stale_active_requests
            apply = request_service.mark_stale_as_needing_confirmation
            noun = "request(s)"

        with Session(bind=engine, future=True) as reader:
            try:
                days, policy = threshold(reader)
            except freshness.NoActiveFreshnessPolicy as exc:
                print(f"refusing to run: {exc}", file=sys.stderr)
                return 2
            print(f"policy {policy}: {args.kind} freshness window is {days} days")

            if args.dry_run:
                candidates = preview(reader, limit=args.limit)
                print(f"would move {len(candidates)} {noun}")
                for resource_id in candidates:
                    print(f"  {resource_id}")
                return 0

        with Session(bind=engine, future=True) as writer:
            # A state change must be attributed (R6.2 / S23). This is a
            # system pass with no human actor, which is the one legitimate
            # use of an actor-less audited transaction.
            with audited_transaction(writer, None, {"operation": f"freshness-pass:{args.kind}"},
                                     require_actor=False):
                moved = apply(writer, limit=args.limit)
        print(f"moved {len(moved)} {noun} to NEEDS_CONFIRMATION")
        for resource_id in moved:
            print(f"  {resource_id}")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
