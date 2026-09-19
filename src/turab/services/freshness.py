"""Request freshness — read from the active policy, never hard-coded.

Ref: Developer Reference Spec §15.1; `IMPLEMENTATION_SLICES_v0.2.md` Slice 2
("reconfirmation/freshness"); §5.2 REQUEST state machine.

The specification is explicit on one point, and it decides this module's
shape:

    «سياسة المدة نفسها يجب أن تكون Configurable وليست hard-coded داخل الكود.
     قد تختلف حسب نوع العقار وحالة Public/Private/Potential وتجربة الـPilot.»

    The duration policy itself must be CONFIGURABLE and not hard-coded inside
    the code. It may differ by property type, by Public/Private/Potential
    status, and by the pilot's experience.

So no threshold appears in this file. The active row of `matching_policies`
carries it, seeded by the frozen master data:

    "freshness_threshold_days": {"request": 30, "property": 30, "offer_terms": 14}

and `ux_matching_policy_one_active` guarantees there is at most one active
policy, so "the threshold" is well defined at any moment. Changing it is a
data change to an immutable, versioned policy row — which is what
configurable was asked to mean.

**A missing policy is an error, not a default.** If no active policy carries a
request threshold, this raises rather than falling back to a number, because
inventing 30 days here would silently become the policy nobody approved.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session


class FreshnessState(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    NEVER_CONFIRMED = "NEVER_CONFIRMED"


class NoActiveFreshnessPolicy(RuntimeError):
    """There is no active policy carrying a request freshness threshold.

    Deliberately fatal. The alternative is a hard-coded fallback, and a
    fallback that runs is a policy — one that was never approved and that
    nobody can find by reading `matching_policies`.
    """


@dataclass(frozen=True, slots=True)
class RequestFreshness:
    state: FreshnessState
    threshold_days: int
    last_confirmed_at: datetime | None
    policy_version: str

    @property
    def is_stale(self) -> bool:
        # NEVER_CONFIRMED is not stale: a request that has never been
        # confirmed has not gone out of date, it has not yet been put in
        # date. The two need different operational handling, so they are not
        # collapsed here.
        return self.state is FreshnessState.STALE


def active_policy(session: Session) -> Mapping[str, Any]:
    row = session.execute(
        text(
            """SELECT matching_policy_id, version, rules
                 FROM turab.matching_policies WHERE active"""
        )
    ).mappings().first()
    if row is None:
        raise NoActiveFreshnessPolicy("no active matching policy")
    return row


def request_threshold_days(session: Session) -> tuple[int, str]:
    """The configured request freshness window, and the policy it came from."""
    policy = active_policy(session)
    rules = policy["rules"] or {}
    thresholds = rules.get("freshness_threshold_days") or {}
    days = thresholds.get("request")
    if not isinstance(days, int) or days <= 0:
        raise NoActiveFreshnessPolicy(
            f"policy {policy['version']} carries no usable "
            "rules.freshness_threshold_days.request; refusing to assume one"
        )
    return days, policy["version"]


def evaluate(
    session: Session, *, last_confirmed_at: datetime | None, now: datetime | None = None
) -> RequestFreshness:
    days, version = request_threshold_days(session)
    if last_confirmed_at is None:
        return RequestFreshness(
            FreshnessState.NEVER_CONFIRMED, days, None, version
        )
    reference = now or _now(session)
    state = (
        FreshnessState.STALE
        if reference - last_confirmed_at > timedelta(days=days)
        else FreshnessState.FRESH
    )
    return RequestFreshness(state, days, last_confirmed_at, version)


def evaluate_request(
    session: Session, request_id: uuid.UUID, *, now: datetime | None = None
) -> RequestFreshness:
    last = session.execute(
        text("SELECT last_confirmed_at FROM turab.requests WHERE request_id = :r"),
        {"r": request_id},
    ).scalar_one()
    return evaluate(session, last_confirmed_at=last, now=now)


def _now(session: Session) -> datetime:
    """`clock_timestamp()`, not `now()`.

    `now()` is the transaction start, so a long-running maintenance pass would
    measure every request against the moment it began rather than the moment
    it looked.
    """
    return session.execute(text("SELECT clock_timestamp()")).scalar_one()
