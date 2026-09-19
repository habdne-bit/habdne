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
from enum import StrEnum
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
    # ACTIVE -> PAUSED and ACTIVE -> CLOSED are ADOPTED additions: a request
    # is not required to pass through NEEDS_CONFIRMATION in order to be
    # paused or closed. Recorded in docs/gate/REQUEST_STATE_TRANSITIONS.md.
    "ACTIVE": frozenset({"NEEDS_CONFIRMATION", "PAUSED", "CLOSED"}),
    "NEEDS_CONFIRMATION": frozenset({"ACTIVE", "PAUSED", "CLOSED"}),
    "PAUSED": frozenset({"ACTIVE"}),
    "CLOSED": frozenset({"ACTIVE"}),
}

#: §5.2: "PAUSED/CLOSED -> ACTIVE only by explicit reactivation".
#:
#: The explicit act IS the command: a caller sending `target_status=ACTIVE` to
#: `/requests/{id}/state` from PAUSED or CLOSED has said so. An earlier draft
#: added a `reactivate` flag for the same meaning — an undeclared field, and a
#: second way of saying something the contract already expresses.
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


#: Adopted closure reasons (migration 0002). A request is closed with one of
#: these and no other: an OPPORTUNITY code describes a different entity, and
#: the historical GENERAL/OTHER keeps its own meaning untouched.
CLOSURE_CATEGORY = "REQUEST_CLOSURE"

#: Requires a note, by its own definition ("another reason, explained in a
#: mandatory note"). A free-text escape hatch with nothing written in it is
#: the same as no reason at all.
CLOSURE_REASON_NEEDING_NOTE = "REQUEST_CLOSED_OTHER"


class UnknownReasonCode(RequestError):
    """`close_reason_code` is FK-constrained to `reason_codes`."""

    def __init__(self, code: str, known: list[str]) -> None:
        super().__init__(
            "VALIDATION_FAILED",
            f"{code!r} is not a REQUEST_CLOSURE reason; the adopted codes are "
            f"{known}",
        )


class ClosureReasonRequired(RequestError):
    def __init__(self) -> None:
        super().__init__(
            "VALIDATION_FAILED",
            "closing a request requires a reason_code from the REQUEST_CLOSURE "
            "category",
        )


class ClosureNoteRequired(RequestError):
    def __init__(self) -> None:
        super().__init__(
            "VALIDATION_FAILED",
            f"{CLOSURE_REASON_NEEDING_NOTE} requires a note explaining it",
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

#: How a recorded change reached TURAB. Distinct from WHO recorded it.
class UpdateChannel(StrEnum):
    #: The party's own account submitted it.
    SELF_SERVICE = "SELF_SERVICE"
    #: A member of staff typed it in. This says who typed it — NOT that the
    #: party said it. See `source_reference`.
    STAFF_RECORDED = "STAFF_RECORDED"


def record_provenance(
    session: Session,
    *,
    request_id: uuid.UUID,
    party_id: uuid.UUID,
    changes: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    recorded_by_account_id: uuid.UUID | None,
    channel: UpdateChannel,
    source_reference: uuid.UUID | None = None,
    note: str | None = None,
    observation_kind: str = "FORM_SUBMISSION",
) -> uuid.UUID:
    """Record WHO acted, WHAT changed, WHEN, HOW it arrived — and whether any
    source backs it.

    The distinction this function exists to keep, and the reason it takes
    `channel` and `source_reference` separately:

        **A staff member typing a value is not evidence that the customer
        asked for it.**

    So an `observations` row carries:

      * `recorded_by_account_id` — the authenticated actor. Never inferred.
      * `channel` — SELF_SERVICE when the party's own account submitted it,
        STAFF_RECORDED when a member of staff did.
      * `source_reference` — an id for the call, message or document the staff
        member was working from, when there is one, and NULL when there is
        not. A NULL here is the honest statement that nobody recorded where
        this came from.
      * `payload.before` / `payload.after` — the previous and new values, so a
        reader can see what actually changed rather than only what it is now.

    And `claims.effective_verification_level` is left at its schema default of
    `DECLARED` for every row written here. **Nothing in this path raises a
    verification level.** Raising it is what `verification_events` is for, and
    a staff member retyping a value is not a verification of it.

    **Contractual gap, surfaced not filled.** `RequestPatch` carries no field
    for a source reference, so a client cannot attach the call or message it
    was working from. `source_reference` is therefore NULL on every update
    that arrives through the contract as frozen today — which the read
    surfaces as `source_recorded: false` rather than hiding. Accepting one
    needs a contract change.
    """
    channel = UpdateChannel(channel)
    payload = {
        "channel": channel.value,
        "source_recorded": source_reference is not None,
        "after": changes,
    }
    if previous is not None:
        payload["before"] = {k: previous.get(k) for k in changes}

    observation_id = session.execute(
        text(
            """INSERT INTO turab.observations
                      (kind, party_id, observed_at, raw_text, payload,
                       recorded_by_account_id, source_id)
               VALUES (CAST(:kind AS turab.observation_kind), :party_id,
                       clock_timestamp(), :note, CAST(:payload AS jsonb),
                       :account, :source)
            RETURNING observation_id"""
        ),
        {
            "kind": observation_kind,
            "party_id": party_id,
            "note": note,
            "payload": json.dumps(payload, default=str),
            "account": recorded_by_account_id,
            "source": source_reference,
        },
    ).scalar_one()

    for attribute_code, value in changes.items():
        session.execute(
            text(
                """INSERT INTO turab.claims
                          (request_id, attribute_code, claimed_value,
                           asserted_by_party_id, observation_id, source_id,
                           extracted_by, observed_at, recorded_by_account_id)
                   VALUES (:request_id, :code, CAST(:value AS jsonb),
                           :asserted_by, :observation_id, :source,
                           :extracted_by, clock_timestamp(), :account)"""
            ),
            {
                "request_id": request_id,
                "code": attribute_code,
                "value": json.dumps(value, default=str),
                # Attributed to the party ONLY when the party's own account
                # submitted it. A staff-recorded change asserts nothing about
                # what the party said, so it names no asserting party.
                "asserted_by": party_id if channel is UpdateChannel.SELF_SERVICE else None,
                "observation_id": observation_id,
                "source": source_reference,
                "extracted_by": channel.value,
                "account": recorded_by_account_id,
            },
        )
    return observation_id


def provenance_for(session: Session, request_id: uuid.UUID) -> list[Mapping[str, Any]]:
    return session.execute(
        text(
            """SELECT c.attribute_code, c.claimed_value, c.observation_id,
                      c.extracted_by AS channel, c.recorded_at,
                      c.recorded_by_account_id, c.asserted_by_party_id,
                      c.source_id,
                      (c.source_id IS NOT NULL) AS source_recorded,
                      c.effective_verification_level::text AS verification_level,
                      c.status::text AS status,
                      o.payload AS observation_payload
                 FROM turab.claims c
                 LEFT JOIN turab.observations o
                        ON o.observation_id = c.observation_id
                WHERE c.request_id = :r
                ORDER BY c.recorded_at, c.attribute_code"""
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
    channel: UpdateChannel,
    source_reference: uuid.UUID | None = None,
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
        changes=changes, previous=before,
        recorded_by_account_id=recorded_by_account_id,
        channel=channel, source_reference=source_reference, note=note,
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
    channel: UpdateChannel = UpdateChannel.STAFF_RECORDED,
    source_reference: uuid.UUID | None = None,
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
        previous=None, recorded_by_account_id=recorded_by_account_id,
        channel=channel, source_reference=source_reference,
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
    recorded_by_account_id: uuid.UUID | None = None,
    channel: UpdateChannel = UpdateChannel.STAFF_RECORDED,
) -> Mapping[str, Any]:
    """Move a request through the documented state machine, and nowhere else.

    Reactivation from PAUSED or CLOSED is this command with
    `target_status=ACTIVE`; that IS the explicit act §5.2 requires. It does
    **not** refresh `last_confirmed_at`: a request paused for six months is
    not made current by restarting it, and the freshness rules apply to it
    from the moment it is active again exactly as they do to any other.
    """
    before = _row(session, request_id)
    current = before["status"]

    if target_status == current:
        raise RequestError("VALIDATION_FAILED", f"the request is already {current}")
    if target_status not in TRANSITIONS.get(current, frozenset()):
        raise UndefinedTransition(current, target_status)
    closing = target_status == "CLOSED"
    if closing:
        known = session.execute(
            text("""SELECT code FROM turab.reason_codes
                     WHERE category = :cat AND active ORDER BY code"""),
            {"cat": CLOSURE_CATEGORY},
        ).scalars().all()
        if reason_code is None:
            raise ClosureReasonRequired()
        if reason_code not in known:
            raise UnknownReasonCode(reason_code, list(known))
        if reason_code == CLOSURE_REASON_NEEDING_NOTE and not (note or "").strip():
            raise ClosureNoteRequired()
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
        previous=None, recorded_by_account_id=recorded_by_account_id,
        channel=channel, note=note,
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
    channel: UpdateChannel = UpdateChannel.STAFF_RECORDED,
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
        # ONLY from NEEDS_CONFIRMATION. A PAUSED or CLOSED request is not
        # returned to ACTIVE by confirming that its details are still true —
        # it was stopped for a reason unrelated to freshness, and undoing that
        # implicitly would reverse a decision nobody revisited.
        session.execute(
            text("UPDATE turab.requests SET status = 'ACTIVE' WHERE request_id = :r"),
            {"r": request_id},
        )
    record_provenance(
        session, request_id=request_id, party_id=before["party_id"],
        changes={"last_confirmed_at": (confirmed_at.isoformat()
                                       if confirmed_at else "now")},
        previous=before, recorded_by_account_id=recorded_by_account_id,
        channel=channel, note=notes,
    )
    return _row(session, request_id)


def stale_active_requests(
    session: Session, *, now: datetime | None = None, limit: int = 500
) -> list[uuid.UUID]:
    """Which ACTIVE requests the current policy considers stale. Reads only."""
    days, _ = freshness.request_threshold_days(session)
    return list(session.execute(
        text(
            """SELECT request_id FROM turab.requests
                WHERE status = 'ACTIVE'
                  AND last_confirmed_at IS NOT NULL
                  AND last_confirmed_at
                      < COALESCE(:now, clock_timestamp()) - make_interval(days => :days)
                ORDER BY last_confirmed_at
                LIMIT :limit"""
        ),
        {"now": now, "days": days, "limit": limit},
    ).scalars().all())


def mark_stale_as_needing_confirmation(
    session: Session, *, now: datetime | None = None, limit: int = 500
) -> list[uuid.UUID]:
    """ACTIVE requests past the configured window become NEEDS_CONFIRMATION.

    Slice 2's mandatory test: "stale request becomes NEEDS_CONFIRMATION
    according to policy/workflow". Only ACTIVE requests are moved, because
    §5.2 defines the edge only from ACTIVE.

    **This does not run by itself.** There is no scheduler in this version:
    the contract declares no scheduled-job operation and the handoff names no
    schedule, so none was invented. The documented way to run it is
    `db/dev/run_freshness_pass.py`, and a request becomes NEEDS_CONFIRMATION
    when someone runs that — not before. What runs it, and how often, is
    still open.
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
