"""The active matching policy, loaded so that it fails closed.

Ref: `docs/gate/SLICE_4_PLAN.md` §3.1 (a policy this code does not implement
refuses the run), G4-1 / CORRECTION-004 (the version rule);
`seed_master_data_v0.2.3.sql:164–185` (policy 0.2.0).

**Why a loader that refuses.** The policy's `rules` are data. Some of them
promise behaviour this engine has:
- `automatic_request_relaxation: false`: matching never edits a request;
- `human_review_required_for_opportunity: true`: no opportunity without a
  human (Slice 5);
- the hard-gate mapping: a required unknown gives NEED_MORE_INFORMATION;
  a confirmed failure gives REJECTED.

A policy that says otherwise describes an engine that does not exist, and
running under it would make the stored `matching_policy_version` a false
statement about what was applied. So the loader refuses, as
`NoActiveFreshnessPolicy` already refuses a missing threshold rather than
assuming one.

**The version rule of CORRECTION-004.** `require_active_version` holds it:
- the requested version must equal the ACTIVE policy's version;
- an omitted, unknown or inactive version is refused;
- the refusal never echoes the value.

The route that applies it (and answers 422) is step 7.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy.orm import Session

from turab.services import freshness

#: The hard-gate mapping this engine implements (policy 0.2.0, verbatim).
IMPLEMENTED_HARD_GATE = {"unknown_required": "NEED_MORE_INFORMATION",
                         "confirmed_fail_required": "REJECTED"}


class PolicyNotImplemented(RuntimeError):
    """The active policy asks for behaviour this engine does not have."""


class PolicyVersionRefused(ValueError):
    """CORRECTION-004: the requested version is not the active policy's."""


@dataclass(frozen=True, slots=True)
class ActivePolicy:
    matching_policy_id: uuid.UUID
    version: str
    rules: Mapping[str, Any]
    freshness_threshold_days: Mapping[str, int]


def load_active_policy(session: Session) -> ActivePolicy:
    """The one active policy (`ux_matching_policy_one_active`), checked.

    Raises `freshness.NoActiveFreshnessPolicy` when there is no active policy,
    or a threshold is missing, and `PolicyNotImplemented` when its promises
    are not this engine's.
    """
    row = freshness.active_policy(session)
    rules = row["rules"] or {}
    version = row["version"]
    if rules.get("automatic_request_relaxation") is not False:
        raise PolicyNotImplemented(
            f"policy {version}: automatic_request_relaxation must be false; this engine "
            "never changes a request (Spec §14, Master §7)")
    if rules.get("human_review_required_for_opportunity") is not True:
        raise PolicyNotImplemented(
            f"policy {version}: human_review_required_for_opportunity must be true "
            "(Master §5.2, ADR-08)")
    if rules.get("hard_gate") != IMPLEMENTED_HARD_GATE:
        raise PolicyNotImplemented(
            f"policy {version}: hard_gate must be {IMPLEMENTED_HARD_GATE}; this engine "
            "implements no other mapping")
    thresholds = {key: freshness.threshold_days(session, key)[0]
                  for key in freshness.THRESHOLD_KEYS}
    return ActivePolicy(row["matching_policy_id"], version, rules, thresholds)


def require_active_version(policy: ActivePolicy, requested: object) -> None:
    """CORRECTION-004's runtime rule. The value is never echoed."""
    if not isinstance(requested, str) or requested != policy.version:
        raise PolicyVersionRefused(
            "matching_policy_version must be the version of the active matching policy")
