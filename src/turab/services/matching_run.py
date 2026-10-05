"""The matching run: `POST /requests/{id}/matching/run` (Slice 4 step 7).

Ref: `docs/gate/SLICE_4_PLAN.md` §3.3 (one Repeatable Read transaction,
measured), §3.6 (audit), G4-13 (input hash; an identical re-run returns the
existing match), G4-15 (decided in the review of b3246b0, D1–D6), and the
seven conditions recorded under G4-15; CORRECTION-004 (the policy version);
`schema_v0.2.3.sql` `match_candidates`, `match_criterion_results`,
`match_diagnostic_runs`, `trg_match_commercial_context`.

## Two phases

`prepare` decides every refusal, and only reads. `CommandService.run` calls
it after the idempotency lookup and BEFORE the key is claimed, so a refused
run writes nothing at all (D6): no match, criterion, diagnostic or audit row,
and no idempotency record. The refusals:

| refusal | rule | status |
|---|---|---|
| no active policy | plan §3.1 | 500 `MATCHING_POLICY_NOT_ACTIVE` |
| an active policy this engine does not implement | plan §3.1 | 500 `MATCHING_POLICY_NOT_SUPPORTED` |
| the version is not the ACTIVE policy's | CORRECTION-004 | 422 `MATCHING_POLICY_VERSION_REFUSED` |
| no such request | — | 404 |
| a request status a run does not accept | G4-8 | 409 `REQUEST_NOT_MATCHABLE` |
| a criterion that contradicts the request, or cannot be evaluated; a RENT request | G4-3 (b), G4-7, G4-5R | 422 `MATCHING_INPUT_REFUSED` |

The two 500s (review of bf052f4, completed in the review of 48588a0) carry
a FIXED detail (`POLICY_FAULTS`), never the exception's text or the
policy's data: a policy version is free text, and once carried a word the
detail guard refuses. The cause is logged by the route, under the
response's trace id.

`execute` evaluates and writes. It refuses nothing a caller can cause.

## One Repeatable Read transaction (condition 1)

The route asks `CommandService.run` for REPEATABLE READ, set by the
transaction's first statement. `prepare` refuses to run under anything else
(`NotRepeatableRead`), so the run never reads two states of the world. The
run's instant, `as_of`, is the transaction's own timestamp: it is the
`evaluated_at` of every match written and the `run_at` of the diagnostic.

Each match is inserted with its criterion rows and their audit rows under
its own SAVEPOINT. A unique violation (23505) on
`(request_id, property_id, matching_policy_id, input_hash)` means that an
identical input is already stored (G4-13, condition 2). The savepoint is
rolled back and that match is returned instead:
- read in the run's snapshot, when it was committed before the run began;
- otherwise read on a NEW connection, because the row a concurrent run
  committed is invisible in this snapshot (measured D5). The row is
  immutable (`prevent_match_candidate_update`, migration 0005 for its
  criterion rows), so reading it outside the snapshot reads what was
  written.

No `ON CONFLICT`: under Repeatable Read it fails 40001 (measured D2, D4).

## What is stored

- the five snapshots, in canonical form, and the input hash, with the
  evaluated offer named (condition 2);
- every version used (condition 3): each criterion's `rule_id` and
  `rule_version`, and in `explanation.engine` the derivations, the gates,
  the precedence, `score.soft@2` and `action.next@1`;
- `generated_by = 'RULE_ENGINE'`, `ai_trace_ref` null (condition 6);
- the audit row of every row written, in the same transaction (§3.6,
  condition 6).

Nothing else is written (D1): no review, no opportunity, no task. No
request, property, offer, consent or criterion is changed.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from turab.matching import (candidates, canonical, criteria, eligibility, explain, hard_gate,
                            policy, snapshots, soft)
from turab.matching.registry import REGISTRY
from turab import exact_json
from turab.services import audit_rows, freshness

DIAGNOSTIC_FORMAT = "turab.diagnostic-input/1"
#: The frozen UNIQUE(request_id, property_id, matching_policy_id, input_hash),
#: by the name PostgreSQL 16 gives it (schema_v0.2.3.sql:684).
IDENTICAL_INPUT = "match_candidates_request_id_property_id_matching_policy_id__key"
#: The policy faults of plan §3.1: two codes, both 500, each with a FIXED
#: detail (review of 48588a0, R-S4-7-04).
POLICY_FAULTS = {
    "MATCHING_POLICY_NOT_ACTIVE": "no matching policy is active; no run can be evaluated",
    "MATCHING_POLICY_NOT_SUPPORTED": "the active matching policy is not one this engine "
                                     "implements; no run can be evaluated",
}


class RunRefused(ValueError):
    """A typed refusal decided by `prepare`. `code` names the problem code;
    the message names the rule and never echoes a submitted value.
    `internal`, when set, is the technical cause: it is logged with the trace
    id and never sent to the client."""

    def __init__(self, code: str, rule: str, message: str,
                 internal: str | None = None) -> None:
        super().__init__(f"{rule}: {message}")
        self.code = code
        self.rule = rule
        self.internal = internal


class RequestMissing(LookupError):
    code = "NOT_FOUND"


class NotRepeatableRead(RuntimeError):
    """The run was given a transaction that is not Repeatable Read."""


@dataclass(frozen=True, slots=True)
class Prepared:
    policy: policy.ActivePolicy
    request_id: uuid.UUID
    request_snapshot: dict
    plan: criteria.CriteriaPlan
    candidate_set: candidates.CandidateSet
    as_of: datetime


@dataclass(frozen=True, slots=True)
class Evaluation:
    candidate: candidates.Candidate
    property_snapshot: dict
    commercial_context_snapshot: dict
    permission_snapshot: dict
    freshness_snapshot: dict
    hard: hard_gate.HardGate
    verdict: eligibility.Eligibility
    score: soft.SoftScore
    next_action: dict | None
    explanation: dict
    input_hash: str


def _a_policy_is_active(session: Session) -> bool:
    return session.execute(text(
        "SELECT EXISTS (SELECT 1 FROM turab.matching_policies WHERE active)")).scalar_one()


def prepare(session: Session, request_id: uuid.UUID, *, matching_policy_version: Any,
            property_ids: Iterable[uuid.UUID] | None) -> Prepared:
    """Every refusal of the run, decided by reads alone (D6)."""
    isolation = session.execute(
        text("SELECT current_setting('transaction_isolation')")).scalar_one()
    if isolation != "repeatable read":
        raise NotRepeatableRead(f"the matching run needs REPEATABLE READ, not {isolation}")
    try:
        active = policy.load_active_policy(session)
    except (freshness.NoActiveFreshnessPolicy, policy.PolicyNotImplemented) as exc:
        # A configuration fault, not the caller's input: a TYPED 500, decided
        # like every refusal before any write. No active policy at all, or an
        # active one this engine cannot run (its promises, or a missing
        # threshold), each with its own code and a fixed detail.
        code = ("MATCHING_POLICY_NOT_SUPPORTED" if _a_policy_is_active(session)
                else "MATCHING_POLICY_NOT_ACTIVE")
        raise RunRefused(code, "plan §3.1", POLICY_FAULTS[code], internal=str(exc)) from None
    try:
        policy.require_active_version(active, matching_policy_version)
    except policy.PolicyVersionRefused as exc:
        raise RunRefused("MATCHING_POLICY_VERSION_REFUSED", "CORRECTION-004", str(exc)) from None
    try:
        candidate_set = candidates.candidate_set(session, request_id, property_ids)
    except candidates.RequestNotFound:
        raise RequestMissing("request") from None
    except candidates.RequestNotMatchable as exc:
        raise RunRefused("REQUEST_NOT_MATCHABLE", "G4-8", str(exc)) from None
    request = snapshots.request_snapshot(session, request_id)
    try:
        plan = criteria.criteria_of(request, criteria.read_vocabulary(session, request))
    except criteria.CriterionRefused as exc:
        raise RunRefused("MATCHING_INPUT_REFUSED", exc.decision,
                         str(exc).removeprefix(f"{exc.decision}: ")) from None
    as_of = session.execute(text("SELECT transaction_timestamp()")).scalar_one()
    return Prepared(active, request_id, request, plan, candidate_set, as_of)


def evaluate(session: Session, prepared: Prepared,
             candidate: candidates.Candidate) -> Evaluation:
    """One candidate, every step of plan §2, in the run's snapshot."""
    active, request = prepared.policy, prepared.request_snapshot
    prop = snapshots.property_snapshot(session, candidate.property_id)
    offer = snapshots.commercial_context_snapshot(session, candidate.offer_id)
    hard = hard_gate.evaluate(prepared.plan, request, prop, offer)
    freshness = snapshots.freshness_snapshot(
        request, prop, offer, policy_version=active.version,
        threshold_days=active.freshness_threshold_days, as_of=prepared.as_of)
    permission = snapshots.permission_snapshot(session, candidate.offer_id, as_of=prepared.as_of)
    verdict = eligibility.eligibility_of(hard, freshness, permission)
    score = soft.soft_score(prepared.plan, hard, offer)
    action = explain.next_action(hard, verdict, {
        "REQUEST": prepared.request_id, "PROPERTY": candidate.property_id,
        "PROPERTY_OFFER": candidate.offer_id})
    return Evaluation(
        candidate, prop, offer, permission, freshness, hard, verdict, score, action,
        explain.explanation(prepared.plan, hard, verdict, score, freshness, permission),
        canonical.input_hash(
            matching_policy_id=active.matching_policy_id,
            matching_policy_version=active.version,
            rule_registry_digest=REGISTRY.digest(),
            evaluated_offer_id=candidate.offer_id,
            request_snapshot=request, property_snapshot=prop,
            commercial_context_snapshot=offer, permission_snapshot=permission,
            freshness_snapshot=freshness))


def _json(value: Any) -> str | None:
    return None if value is None else canonical.canonical_bytes(value).decode("utf-8")


def _insert(session: Session, prepared: Prepared, ev: Evaluation) -> uuid.UUID:
    """The match, its criterion rows and their audit rows. The caller holds
    the savepoint."""
    v = ev.verdict
    match_id = session.execute(text("""
        INSERT INTO turab.match_candidates (
            request_id, property_id, evaluated_offer_id, matching_policy_id,
            matching_policy_version, request_version, property_version, offer_version,
            evaluated_at, eligibility, hard_gate_status, information_gate_status,
            request_freshness, property_freshness, offer_freshness, freshness_gate_status,
            permission_gate_status, soft_score, request_snapshot, property_snapshot,
            commercial_context_snapshot, permission_snapshot, freshness_snapshot,
            input_hash, explanation, next_action, generated_by, ai_trace_ref)
        VALUES (
            :request_id, :property_id, :offer_id, :policy_id, :policy_version,
            :request_version, :property_version, :offer_version, :as_of,
            CAST(:eligibility AS turab.match_eligibility),
            CAST(:hard AS turab.gate_status), CAST(:information AS turab.gate_status),
            CAST(:request_freshness AS turab.freshness_state),
            CAST(:property_freshness AS turab.freshness_state),
            CAST(:offer_freshness AS turab.freshness_state),
            CAST(:freshness AS turab.gate_status), CAST(:permission AS turab.gate_status),
            :soft_score, CAST(:request_snapshot AS jsonb), CAST(:property_snapshot AS jsonb),
            CAST(:commercial AS jsonb), CAST(:permission_snapshot AS jsonb),
            CAST(:freshness_snapshot AS jsonb), :input_hash, CAST(:explanation AS jsonb),
            CAST(:next_action AS jsonb), 'RULE_ENGINE', NULL)
        RETURNING match_id"""), {
        "request_id": prepared.request_id, "property_id": ev.candidate.property_id,
        "offer_id": ev.candidate.offer_id,
        "policy_id": prepared.policy.matching_policy_id,
        "policy_version": prepared.policy.version,
        "request_version": prepared.request_snapshot["version"],
        "property_version": ev.property_snapshot["version"],
        "offer_version": ev.commercial_context_snapshot["version"],
        "as_of": prepared.as_of, "eligibility": v.eligibility,
        "hard": v.hard_gate_status, "information": v.information_gate_status,
        "request_freshness": v.request_freshness,
        "property_freshness": v.property_freshness, "offer_freshness": v.offer_freshness,
        "freshness": v.freshness_gate_status, "permission": v.permission_gate_status,
        "soft_score": ev.score.soft_score,
        "request_snapshot": _json(prepared.request_snapshot),
        "property_snapshot": _json(ev.property_snapshot),
        "commercial": _json(ev.commercial_context_snapshot),
        "permission_snapshot": _json(ev.permission_snapshot),
        "freshness_snapshot": _json(ev.freshness_snapshot),
        "input_hash": ev.input_hash, "explanation": _json(ev.explanation),
        "next_action": _json(ev.next_action)}).scalar_one()
    audit_rows.write(session, "match_candidates", match_id, "INSERT", None,
                     audit_rows.row_json(session, "match_candidates", match_id))
    for r in ev.hard.results:
        row_id = session.execute(text("""
            INSERT INTO turab.match_criterion_results (
                match_id, request_criterion_id, criterion_code, ordinal, importance,
                request_value, property_value, compatibility, blocking, delta,
                evidence_level, evidence_claim_id, reason_code, rule_id, rule_version)
            VALUES (:match_id, :request_criterion_id, :code, :ordinal,
                    CAST(:importance AS turab.criterion_importance),
                    CAST(:request_value AS jsonb), CAST(:property_value AS jsonb),
                    CAST(:compatibility AS turab.compatibility_status), :blocking,
                    CAST(:delta AS jsonb), CAST(:evidence_level AS turab.verification_level),
                    :evidence_claim_id, :reason_code, :rule_id, :rule_version)
            RETURNING match_criterion_result_id"""), {
            "match_id": match_id, "request_criterion_id": r.request_criterion_id,
            "code": r.criterion_code, "ordinal": r.ordinal, "importance": r.importance,
            "request_value": _json(r.request_value), "property_value": _json(r.property_value),
            "compatibility": r.compatibility, "blocking": r.blocking, "delta": _json(r.delta),
            "evidence_level": r.evidence_level, "evidence_claim_id": r.evidence_claim_id,
            "reason_code": r.reason_code, "rule_id": r.rule_id,
            "rule_version": r.rule_version}).scalar_one()
        audit_rows.write(session, "match_criterion_results", row_id, "INSERT", None,
                         audit_rows.row_json(session, "match_criterion_results", row_id))
    return match_id


_EXISTING = """SELECT match_id FROM turab.match_candidates
                WHERE request_id = :r AND property_id = :p
                  AND matching_policy_id = :policy AND input_hash = :h"""


def _identical_input(exc: IntegrityError) -> bool:
    orig = exc.orig
    return (getattr(orig, "sqlstate", None) == "23505"
            and getattr(getattr(orig, "diag", None), "constraint_name", None) == IDENTICAL_INPUT)


def _store(session: Session, prepared: Prepared, ev: Evaluation) -> tuple[uuid.UUID, bool]:
    """(match_id, visible in this snapshot). The new match, or the identical
    one already stored (G4-13)."""
    try:
        with session.begin_nested():
            return _insert(session, prepared, ev), True
    except IntegrityError as exc:
        if not _identical_input(exc):
            raise
    key = {"r": prepared.request_id, "p": ev.candidate.property_id,
           "policy": prepared.policy.matching_policy_id, "h": ev.input_hash}
    existing = session.execute(text(_EXISTING), key).scalar_one_or_none()
    if existing is not None:
        return existing, True
    # Committed by a concurrent run after this snapshot was taken (D5).
    with session.get_bind().engine.connect() as fresh:
        return fresh.execute(text(_EXISTING), key).scalar_one(), False


def match_view(conn: Any, match_id: uuid.UUID) -> dict:
    """The stored match as the contract's `MatchCandidate` (staff only, R9.2),
    read from its rows: what was written, not what was computed. Every number
    is read exactly (`exact_json`), never through a float (review of bf052f4,
    R-S4-7-03). Each
    criterion also carries its `ordinal` and `request_criterion_id`, the key
    of `explanation.criteria`."""
    row = conn.execute(text("""
        SELECT (to_jsonb(m) - 'generated_by' - 'ai_trace_ref' - 'created_at')::text
          FROM turab.match_candidates m WHERE match_id = :m"""), {"m": match_id}).scalar_one()
    view = exact_json.loads(row)
    view["criteria"] = [exact_json.loads(c) for c in conn.execute(text("""
        SELECT (to_jsonb(c) - 'match_id' - 'match_criterion_result_id' - 'created_at')::text
          FROM turab.match_criterion_results c WHERE match_id = :m
         ORDER BY criterion_code, ordinal"""), {"m": match_id}).scalars()]
    return view


def diagnostic_input_hash(prepared: Prepared, evaluations: list[Evaluation]) -> str:
    """The diagnostic row's `input_hash`: what this run evaluated, and what it
    excluded, under which policy and rules."""
    document = {
        "format": DIAGNOSTIC_FORMAT,
        "matching_policy_id": prepared.policy.matching_policy_id,
        "matching_policy_version": prepared.policy.version,
        "rule_registry_digest": REGISTRY.digest(),
        "request_snapshot": prepared.request_snapshot,
        "candidates": [[ev.candidate.property_id, ev.candidate.offer_id, ev.input_hash]
                       for ev in evaluations],
        "excluded": [[e.property_id, e.reason.value, e.detail]
                     for e in prepared.candidate_set.excluded],
    }
    return hashlib.sha256(canonical.canonical_bytes(document)).hexdigest()


def execute(session: Session, prepared: Prepared) -> tuple[int, dict]:
    """Evaluate every candidate, store each match (or find the identical one),
    then write the run's diagnostic row. Returns the 201 body."""
    evaluations = [evaluate(session, prepared, c) for c in prepared.candidate_set.candidates]
    stored = [_store(session, prepared, ev) for ev in evaluations]

    tally = explain.counts((ev.hard, ev.verdict) for ev in evaluations)
    summary = explain.blocker_summary((ev.verdict for ev in evaluations),
                                      prepared.candidate_set.excluded)
    diagnostic_id = session.execute(text("""
        INSERT INTO turab.match_diagnostic_runs (
            request_id, request_version, matching_policy_id, matching_policy_version,
            request_snapshot, input_hash, run_at, ready_opportunity_count,
            actionable_unknown_count, near_match_count, blocker_summary,
            suggested_actions, relaxation_scenarios)
        VALUES (:r, :rv, :policy, :version, CAST(:snapshot AS jsonb), :h, :at,
                :ready, :actionable, :near, CAST(:summary AS jsonb), '[]'::jsonb, '[]'::jsonb)
        RETURNING diagnostic_run_id"""), {
        "r": prepared.request_id, "rv": prepared.request_snapshot["version"],
        "policy": prepared.policy.matching_policy_id, "version": prepared.policy.version,
        "snapshot": _json(prepared.request_snapshot),
        "h": diagnostic_input_hash(prepared, evaluations), "at": prepared.as_of,
        "ready": tally["ready_opportunity_count"],
        "actionable": tally["actionable_unknown_count"],
        "near": tally["near_match_count"], "summary": _json(summary)}).scalar_one()
    audit_rows.write(session, "match_diagnostic_runs", diagnostic_id, "INSERT", None,
                     audit_rows.row_json(session, "match_diagnostic_runs", diagnostic_id))

    matches = []
    for match_id, visible in stored:
        if visible:
            matches.append(match_view(session, match_id))
        else:
            with session.get_bind().engine.connect() as fresh:
                matches.append(match_view(fresh, match_id))
    diagnostic = exact_json.loads(session.execute(text("""
        SELECT jsonb_build_object(
                   'diagnostic_run_id', diagnostic_run_id, 'request_id', request_id,
                   'run_at', run_at,
                   'ready_opportunity_count', ready_opportunity_count,
                   'actionable_unknown_count', actionable_unknown_count,
                   'near_match_count', near_match_count, 'blocker_summary', blocker_summary,
                   'suggested_actions', suggested_actions,
                   'relaxation_scenarios', relaxation_scenarios)::text
          FROM turab.match_diagnostic_runs WHERE diagnostic_run_id = :d"""),
        {"d": diagnostic_id}).scalar_one())
    return 201, {"matches": matches, "diagnostic": diagnostic}
