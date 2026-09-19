"""REQUEST: creation, typed updates with provenance, criteria, state — Slice 2.

Ref: IMPLEMENTATION_SLICES_v0.2.md Slice 2; Developer Reference Spec §5.2
(state machine), §15.1 (freshness); API_CONTRACTS `RequestCreate`,
`RequestPatch`, `RequestCriterion`, `RequestStateCommand`, `StateReconfirm`.

Three separations this module exists to keep, because collapsing any of them
is how a request stops being a real operational entity and becomes a saved
filter:

  * **data update** (`patch`) changes what the buyer wants;
  * **state transition** (`transition`) changes where the request is in its
    workflow;
  * **reconfirmation** (`reconfirm`) changes only when the information was
    last confirmed.

They are three commands, they take three different bodies in the contract,
and none of them silently performs another's job.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import freshness

# --- the documented state machine -----------------------------------------
#
# Reference Spec §5.2, transcribed edge for edge:
#
#     RAW -> CONTACTED -> QUALIFIED -> ACTIVE
#     ACTIVE -> NEEDS_CONFIRMATION -> ACTIVE | PAUSED | CLOSED
#     PAUSED/CLOSED -> ACTIVE only by explicit reactivation or materially new
#                      request logic
#
# The contract's `RequestStateCommand` accepts any of six target states, so it
# permits transitions the state machine does not define. Those are REFUSED
# here and reported as an undefined transition rather than guessed at — see
# `UndefinedTransition`.

TRANSITIONS: dict[str, frozenset[str]] = {
    "RAW": frozenset({"CONTACTED"}),
    "CONTACTED": frozenset({"QUALIFIED"}),
    "QUALIFIED": frozenset({"ACTIVE"}),
    "ACTIVE": frozenset({"NEEDS_CONFIRMATION"}),
    "NEEDS_CONFIRMATION": frozenset({"ACTIVE", "PAUSED", "CLOSED"}),
    "PAUSED": frozenset({"ACTIVE"}),
    "CLOSED": frozenset({"ACTIVE"}),
}

#: §5.2: "PAUSED/CLOSED -> ACTIVE only by explicit reactivation". Marked so the
#: caller must say it meant it, rather than reactivating by ordinary command.
REACTIVATION_FROM = frozenset({"PAUSED", "CLOSED"})

#: The columns `RequestPatch` may touch. Anything else is not patchable, and
#: `status`, `claim_status`, `management_mode`, `version` and
#: `last_confirmed_at` are absent on purpose: each has its own command.
PATCHABLE = (
    "intent", "payment", "desired_property_type", "primary_location_id",
    "local_location_detail", "budget_target_dzd", "budget_max_dzd",
    "budget_flexibility",
)

#: Criterion importance values a non-human actor may never set or change.
#: Reference Spec: Required/Preferred/Flexible are the buyer's own words about
#: what is negotiable, and an inference engine rewriting them silently rewrites
#: the buyer's intent.
IMPORTANCE_VALUES = ("REQUIRED", "PREFERRED", "FLEXIBLE")


class RequestError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class RequestNotFound(RequestError):
    def __init__(self) -> None:
        super().__init__("NOT_FOUND", "no such request")


class InvalidManagementCombination(RequestError):
    """The schema's own CHECK, surfaced as a typed error.

    ASSISTED must be UNCLAIMED; SELF_MANAGED and SHARED_MANAGEMENT must be
    CLAIMED. An assisted request inserted as CLAIMED would assert that a
    customer is managing a record they have never claimed.
    """

    def __init__(self, management_mode: str, claim_status: str) -> None:
        super().__init__(
            "VALIDATION_FAILED",
            f"{management_mode} cannot be {claim_status}: an assisted record is "
            "UNCLAIMED until it is claimed, and a self-managed one is CLAIMED",
        )


class UnknownCriterionCode(RequestError):
    """The code is not in the master criteria registry.

    `request_criteria.criterion_code` is FK-constrained to
    `criterion_definitions`, which is what makes criteria STRUCTURED rather
    than free text: a criterion nothing can interpret is not a criterion, it
    is a note. Surfaced as a typed error so the caller learns which codes
    exist instead of receiving a constraint violation.
    """

    def __init__(self, code: str, known: list[str]) -> None:
        super().__init__(
            "VALIDATION_FAILED",
            f"{code!r} is not a criterion in the master registry; "
            f"GET /master/criterion-definitions lists them ({len(known)} active)",
        )


class UnknownReasonCode(RequestError):
    """`close_reason_code` is FK-constrained to `reason_codes`."""

    def __init__(self, code: str) -> None:
        super().__init__(
            "VALIDATION_FAILED",
            f"{code!r} is not a code in the master reason registry",
        )


class UndefinedTransition(RequestError):
    """The contract permits the target; the documented state machine does not.

    Reported rather than guessed. Inventing an edge here would add a workflow
    rule to TURAB by implementation accident.
    """

    def __init__(self, current: str, target: str) -> None:
        self.current, self.target = current, target
        allowed = sorted(TRANSITIONS.get(current, frozenset()))
        super().__init__(
            "VALIDATION_FAILED",
            f"{current} -> {target} is not a transition defined by the request "
            f"state machine; from {current} the defined targets are {allowed}",
        )


class ReactivationNotRequested(RequestError):
    """§5.2: leaving PAUSED or CLOSED needs explicit reactivation."""

    def __init__(self, current: str) -> None:
        super().__init__(
            "VALIDATION_FAILED",
            f"a {current} request returns to ACTIVE only by explicit "
            "reactivation; set reactivate=true and give a reason",
        )


def _row(session: Session, request_id: uuid.UUID) -> Mapping[str, Any]:
    row = session.execute(
        text(
            """SELECT request_id, party_id, status::text AS status,
                      transaction_intent::text AS transaction_intent,
                      intent::text AS intent, payment::text AS payment,
                      desired_property_type::text AS desired_property_type,
                      property_type_importance::text AS property_type_importance,
                      primary_location_id, location_importance::text AS location_importance,
                      local_location_detail, budget_target_dzd, budget_max_dzd,
                      budget_importance::text AS budget_importance,
                      budget_flexibility::text AS budget_flexibility,
                      last_confirmed_at,
                      management_mode::text AS management_mode,
                      claim_status::text AS claim_status,
                      version, created_by_account_id, created_at, updated_at
                 FROM turab.requests WHERE request_id = :r"""
        ),
        {"r": request_id},
    ).mappings().first()
    if row is None:
        raise RequestNotFound()
    return row


# --- creation --------------------------------------------------------------

def create_request(
    session: Session,
    *,
    party_id: uuid.UUID,
    transaction_intent: str,
    intent: str,
    management_mode: str,
    claim_status: str,
    created_by_account_id: uuid.UUID | None,
    **optional: Any,
) -> Mapping[str, Any]:
    """Create a REQUEST, self-managed or assisted.

    The management pair is validated here as well as by the schema's CHECK, so
    the caller gets a typed error naming the rule rather than a constraint
    violation. Both are kept: the CHECK is what makes the rule true of data
    written by anything, including a future importer.
    """
    if management_mode == "ASSISTED" and claim_status != "UNCLAIMED":
        raise InvalidManagementCombination(management_mode, claim_status)
    if management_mode in ("SELF_MANAGED", "SHARED_MANAGEMENT") and claim_status != "CLAIMED":
        raise InvalidManagementCombination(management_mode, claim_status)

    columns = {
        "party_id": party_id,
        "transaction_intent": transaction_intent,
        "intent": intent,
        "management_mode": management_mode,
        "claim_status": claim_status,
        "created_by_account_id": created_by_account_id,
    }
    for name in (
        "payment", "desired_property_type", "property_type_importance",
        "primary_location_id", "location_importance", "local_location_detail",
        "budget_target_dzd", "budget_max_dzd", "budget_importance",
        "budget_flexibility",
    ):
        if optional.get(name) is not None:
            columns[name] = optional[name]

    casts = {
        "transaction_intent": "turab.request_transaction_intent",
        "intent": "turab.intent_stage",
        "payment": "turab.payment_method",
        "desired_property_type": "turab.property_type",
        "property_type_importance": "turab.criterion_importance",
        "location_importance": "turab.criterion_importance",
        "budget_importance": "turab.criterion_importance",
        "budget_flexibility": "turab.budget_flexibility",
        "management_mode": "turab.management_mode",
        "claim_status": "turab.account_claim_status",
    }
    names = ", ".join(columns)
    values = ", ".join(
        f"CAST(:{c} AS {casts[c]})" if c in casts else f":{c}" for c in columns
    )
    request_id = session.execute(
        text(f"INSERT INTO turab.requests ({names}) VALUES ({values}) "
             "RETURNING request_id"),
        columns,
    ).scalar_one()
    return _row(session, request_id)


def read_request(session: Session, request_id: uuid.UUID) -> Mapping[str, Any]:
    return _row(session, request_id)


# --- provenance ------------------------------------------------------------

def record_provenance(
    session: Session,
    *,
    request_id: uuid.UUID,
    party_id: uuid.UUID,
    changes: Mapping[str, Any],
    recorded_by_account_id: uuid.UUID | None,
    note: str | None = None,
    observation_kind: str = "FORM_SUBMISSION",
) -> uuid.UUID:
    """Record WHO said WHAT about a request, and WHEN — one claim per field.

    The frozen schema already models this and it is used as modelled rather
    than reinvented: an `observations` row is the utterance (who reported it,
    when, in what form), and a `claims` row per changed attribute is the
    assertion about this request (`idx_claims_request_attr` exists for exactly
    this lookup).

    **Contractual gap, surfaced not filled.** `RequestPatch` carries no
    provenance field: a client cannot say where a value came from, or attach
    an observation it already recorded. So the provenance captured here is
    what the server itself can witness — the acting account, the moment, and
    the submitted values — and `extracted_by` records that a human submitted
    it through the API. Richer provenance (a call note, a forwarded message, a
    document) needs a contract change to accept an `observation_id`, and that
    is recorded in the Slice 2 report rather than invented as an undeclared
    field.
    """
    observation_id = session.execute(
        text(
            """INSERT INTO turab.observations
                      (kind, party_id, observed_at, raw_text, payload,
                       recorded_by_account_id)
               VALUES (CAST(:kind AS turab.observation_kind), :party_id,
                       clock_timestamp(), :note, CAST(:payload AS jsonb), :account)
            RETURNING observation_id"""
        ),
        {
            "kind": observation_kind,
            "party_id": party_id,
            "note": note,
            "payload": json.dumps(changes, default=str),
            "account": recorded_by_account_id,
        },
    ).scalar_one()

    for attribute_code, value in changes.items():
        session.execute(
            text(
                """INSERT INTO turab.claims
                          (request_id, attribute_code, claimed_value,
                           asserted_by_party_id, observation_id, extracted_by,
                           observed_at, recorded_by_account_id)
                   VALUES (:request_id, :code, CAST(:value AS jsonb),
                           :party_id, :observation_id, 'HUMAN_API',
                           clock_timestamp(), :account)"""
            ),
            {
                "request_id": request_id,
                "code": attribute_code,
                "value": json.dumps(value, default=str),
                "party_id": party_id,
                "observation_id": observation_id,
                "account": recorded_by_account_id,
            },
        )
    return observation_id


def provenance_for(session: Session, request_id: uuid.UUID) -> list[Mapping[str, Any]]:
    return session.execute(
        text(
            """SELECT attribute_code, claimed_value, observation_id,
                      extracted_by, recorded_at, recorded_by_account_id,
                      status::text AS status
                 FROM turab.claims
                WHERE request_id = :r
                ORDER BY recorded_at, attribute_code"""
        ),
        {"r": request_id},
    ).mappings().all()


# --- typed update ----------------------------------------------------------

def patch_request(
    session: Session,
    *,
    request_id: uuid.UUID,
    changes: Mapping[str, Any],
    recorded_by_account_id: uuid.UUID | None,
    note: str | None = None,
) -> Mapping[str, Any]:
    """Change what the buyer wants. Never the status, never the confirmation.

    The version bump comes from `trg_requests_version`, so it happens for any
    update including one issued by something that forgets to ask.
    """
    unknown = set(changes) - set(PATCHABLE)
    if unknown:
        raise RequestError(
            "VALIDATION_FAILED",
            f"not updatable through this command: {sorted(unknown)}",
        )
    if not changes:
        raise RequestError("VALIDATION_FAILED", "no fields to update")

    before = _row(session, request_id)
    casts = {
        "intent": "turab.intent_stage",
        "payment": "turab.payment_method",
        "desired_property_type": "turab.property_type",
        "budget_flexibility": "turab.budget_flexibility",
    }
    assignments = ", ".join(
        f"{c} = CAST(:{c} AS {casts[c]})" if c in casts else f"{c} = :{c}"
        for c in changes
    )
    session.execute(
        text(f"UPDATE turab.requests SET {assignments} WHERE request_id = :request_id"),
        {**changes, "request_id": request_id},
    )
    record_provenance(
        session, request_id=request_id, party_id=before["party_id"],
        changes=changes, recorded_by_account_id=recorded_by_account_id, note=note,
    )
    return _row(session, request_id)


# --- criteria --------------------------------------------------------------

def add_criterion(
    session: Session,
    *,
    request_id: uuid.UUID,
    criterion_code: str,
    importance: str,
    operator: str,
    value: Any,
    unit: str | None = None,
    blocking_if_unknown: bool = False,
    sort_order: int = 100,
    recorded_by_account_id: uuid.UUID | None = None,
) -> Mapping[str, Any]:
    """Add a structured criterion, and bump the request's version.

    The bump is explicit. `request_criteria` has its own `set_updated_at`
    trigger and does NOT touch `requests.version`, so without this a criterion
    change would leave the request's version unmoved — and every consumer that
    uses the version to detect change, optimistic concurrency included, would
    miss it. Slice 2's mandatory test says criteria mutation bumps the
    request's version; this is where that happens.
    """
    if importance not in IMPORTANCE_VALUES:
        raise RequestError("VALIDATION_FAILED", f"importance must be one of {IMPORTANCE_VALUES}")
    known = session.execute(
        text("SELECT code FROM turab.criterion_definitions WHERE active ORDER BY code")
    ).scalars().all()
    if criterion_code not in known:
        raise UnknownCriterionCode(criterion_code, list(known))
    before = _row(session, request_id)

    row = session.execute(
        text(
            """INSERT INTO turab.request_criteria
                      (request_id, criterion_code, importance, operator, value,
                       unit, blocking_if_unknown, sort_order)
               VALUES (:request_id, :code,
                       CAST(:importance AS turab.criterion_importance),
                       CAST(:operator AS turab.criterion_operator),
                       CAST(:value AS jsonb), :unit, :blocking, :sort_order)
            RETURNING request_criterion_id, criterion_code,
                      importance::text AS importance, operator::text AS operator,
                      value, unit, blocking_if_unknown, sort_order, created_at"""
        ),
        {
            "request_id": request_id, "code": criterion_code,
            "importance": importance, "operator": operator,
            "value": json.dumps(value, default=str), "unit": unit,
            "blocking": blocking_if_unknown, "sort_order": sort_order,
        },
    ).mappings().one()

    _touch_request(session, request_id)
    record_provenance(
        session, request_id=request_id, party_id=before["party_id"],
        changes={f"criterion.{criterion_code}": {
            "importance": importance, "operator": operator, "value": value,
        }},
        recorded_by_account_id=recorded_by_account_id,
    )
    return row


def criteria_for(session: Session, request_id: uuid.UUID) -> list[Mapping[str, Any]]:
    return session.execute(
        text(
            """SELECT request_criterion_id, criterion_code,
                      importance::text AS importance, operator::text AS operator,
                      value, unit, blocking_if_unknown, sort_order
                 FROM turab.request_criteria
                WHERE request_id = :r ORDER BY sort_order, criterion_code"""
        ),
        {"r": request_id},
    ).mappings().all()


def _touch_request(session: Session, request_id: uuid.UUID) -> None:
    """Force `trg_requests_version` to fire without changing a field's meaning."""
    session.execute(
        text("UPDATE turab.requests SET updated_at = updated_at WHERE request_id = :r"),
        {"r": request_id},
    )


# --- state transitions -----------------------------------------------------

def transition(
    session: Session,
    *,
    request_id: uuid.UUID,
    target_status: str,
    reason_code: str | None = None,
    note: str | None = None,
    reactivate: bool = False,
    recorded_by_account_id: uuid.UUID | None = None,
) -> Mapping[str, Any]:
    """Move a request through the documented state machine, and nowhere else."""
    before = _row(session, request_id)
    current = before["status"]

    if target_status == current:
        raise RequestError("VALIDATION_FAILED", f"the request is already {current}")
    if target_status not in TRANSITIONS.get(current, frozenset()):
        raise UndefinedTransition(current, target_status)
    if current in REACTIVATION_FROM and not reactivate:
        raise ReactivationNotRequested(current)

    closing = target_status == "CLOSED"
    if closing and reason_code is not None:
        exists = session.execute(
            text("SELECT 1 FROM turab.reason_codes WHERE code = :c"),
            {"c": reason_code},
        ).first()
        if exists is None:
            raise UnknownReasonCode(reason_code)
    session.execute(
        text(
            """UPDATE turab.requests
                  SET status = CAST(:status AS turab.request_status),
                      closed_at = CASE WHEN :closing THEN clock_timestamp() ELSE NULL END,
                      close_reason_code = CASE WHEN :closing THEN :reason ELSE NULL END
                WHERE request_id = :r"""
        ),
        {"status": target_status, "closing": closing,
         "reason": reason_code if closing else None, "r": request_id},
    )
    record_provenance(
        session, request_id=request_id, party_id=before["party_id"],
        changes={"status": {"from": current, "to": target_status,
                            "reason_code": reason_code}},
        recorded_by_account_id=recorded_by_account_id, note=note,
        observation_kind="SYSTEM_IMPORT" if not note else "CALL_NOTE",
    )
    return _row(session, request_id)


# --- reconfirmation --------------------------------------------------------

def reconfirm(
    session: Session,
    *,
    request_id: uuid.UUID,
    confirmed_at: datetime | None = None,
    notes: str | None = None,
    recorded_by_account_id: uuid.UUID | None = None,
) -> Mapping[str, Any]:
    """Record that the information is still current.

    This moves `last_confirmed_at` and nothing else about what the buyer
    wants. It DOES return a NEEDS_CONFIRMATION request to ACTIVE, because
    §5.2 defines that edge and reconfirming is precisely how it is taken —
    the transition is a consequence of the confirmation, not a separate
    caller-chosen state change.
    """
    before = _row(session, request_id)
    session.execute(
        text(
            """UPDATE turab.requests
                  SET last_confirmed_at = COALESCE(:at, clock_timestamp())
                WHERE request_id = :r"""
        ),
        {"at": confirmed_at, "r": request_id},
    )
    if before["status"] == "NEEDS_CONFIRMATION":
        session.execute(
            text("UPDATE turab.requests SET status = 'ACTIVE' WHERE request_id = :r"),
            {"r": request_id},
        )
    record_provenance(
        session, request_id=request_id, party_id=before["party_id"],
        changes={"last_confirmed_at": (confirmed_at.isoformat()
                                       if confirmed_at else "now")},
        recorded_by_account_id=recorded_by_account_id, note=notes,
    )
    return _row(session, request_id)


def mark_stale_as_needing_confirmation(
    session: Session, *, now: datetime | None = None, limit: int = 500
) -> list[uuid.UUID]:
    """ACTIVE requests past the configured window become NEEDS_CONFIRMATION.

    Slice 2's mandatory test: "stale request becomes NEEDS_CONFIRMATION
    according to policy/workflow". Only ACTIVE requests are moved, because
    §5.2 defines the edge only from ACTIVE.

    **Contractual gap, surfaced not filled.** The contract declares no
    scheduled-job operation and the handoff names no schedule, so this is an
    invocable operational function rather than a timer invented here. What
    calls it, and how often, is a decision that has not been taken.
    """
    days, _ = freshness.request_threshold_days(session)
    moved = session.execute(
        text(
            """UPDATE turab.requests
                  SET status = 'NEEDS_CONFIRMATION'
                WHERE request_id IN (
                      SELECT request_id FROM turab.requests
                       WHERE status = 'ACTIVE'
                         AND last_confirmed_at IS NOT NULL
                         AND last_confirmed_at < COALESCE(:now, clock_timestamp())
                             - make_interval(days => :days)
                       ORDER BY last_confirmed_at
                       LIMIT :limit)
            RETURNING request_id"""
        ),
        {"now": now, "days": days, "limit": limit},
    ).scalars().all()
    return list(moved)
