"""OFFER: the commercial offer on a physical property — Slice 3, step 2.

Ref: IMPLEMENTATION_SLICES_v0.2.md Slice 3; the effective contract's
`OfferCreate`, `OfferPatch`, `OfferStateCommand`, `PropertyOffer` and the
`postOffersOfferIdSources` body; RFC-001 §4.6 (R4.12, R4.13);
`docs/gate/SLICE_3_PLAN.md` §3.5 (G3-1, ratified), §3.6, §6.3.

An offer is NOT the property. Several may exist for one physical property at
once — an owner's sale, a broker's sale and a rent — each with its own party,
terms, visibility and state. Nothing here reads or writes `properties` beyond
checking that the parent exists.

Three separations, kept for the same reason as on a REQUEST:

  * **terms** (`patch_offer`) change what is offered;
  * **state** (`transition`) changes where the offer is in its lifecycle;
  * **sources** (`link_source`) record where the offer was found.

None of them performs another's job.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import provenance
from .provenance import UpdateChannel

# --- the ratified state machine (G3-1, plan §3.5) --------------------------

TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"PENDING_INFO", "ACTIVE", "WITHDRAWN", "CLOSED"}),
    "PENDING_INFO": frozenset({"ACTIVE", "WITHDRAWN", "CLOSED"}),
    "ACTIVE": frozenset({"PENDING_INFO", "PAUSED", "WITHDRAWN", "CLOSED"}),
    "PAUSED": frozenset({"PENDING_INFO", "ACTIVE", "WITHDRAWN", "CLOSED"}),
    "WITHDRAWN": frozenset(),
    "CLOSED": frozenset(),
}

#: The CUSTOMER narrowing — a SECOND gate applied after the edge check, not a
#: separate table. A customer never sets `PENDING_INFO` or `CLOSED`.
CUSTOMER_TARGETS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"ACTIVE", "WITHDRAWN"}),
    "PENDING_INFO": frozenset({"ACTIVE", "WITHDRAWN"}),
    "ACTIVE": frozenset({"PAUSED", "WITHDRAWN"}),
    "PAUSED": frozenset({"ACTIVE", "WITHDRAWN"}),
}

#: Staff-only targets, each with what it MEANS. `CLOSED` is an operational
#: closure; `WITHDRAWN` is the offer holder withdrawing. A customer refused
#: `CLOSED` is told which of the two they want.
STAFF_ONLY_TARGETS: dict[str, str] = {
    "CLOSED": ("CLOSED is an operational closure recorded by staff; to take "
               "your own offer off the market, set WITHDRAWN"),
    "PENDING_INFO": ("PENDING_INFO is set by staff when they need more "
                     "information about an offer"),
}

#: `OfferPatch`, field for field. `transaction_type`, `party_id` and
#: `permission_scope` are absent on purpose: the contract's patch body does not
#: declare them, and the last is consent-bearing (red-team §166).
PATCHABLE = frozenset({
    "asking_price_dzd", "raw_price_text", "price_negotiable",
    "seller_expectation_dzd", "price_visibility",
})

#: The fields `OfferCreate` declares besides the two it requires.
CREATE_OPTIONAL = (
    "asking_price_dzd", "raw_price_text", "price_negotiable",
    "seller_expectation_dzd", "price_visibility", "permission_scope",
)

_CASTS = {
    "transaction_type": "turab.transaction_type",
    "price_negotiable": "turab.price_negotiability",
    "price_visibility": "turab.price_visibility",
    "permission_scope": "turab.sharing_scope",
    "status": "turab.offer_status",
}

#: The named constraints an API caller can reach with a well-formed body.
#: Everything else propagates: turning every database error into a 4xx would
#: hide real faults.
PROPERTY_FK = "property_offers_property_id_fkey"
PARTY_FK = "property_offers_party_id_fkey"
SOURCE_FK = "property_offer_sources_source_id_fkey"
PRIMARY_SOURCE_INDEX = "ux_offer_primary_source"


class OfferError(Exception):
    """A refusal with a stable code, mapped to a typed problem by the route."""

    def __init__(self, code: str, detail: str) -> None:
        self.code, self.detail = code, detail
        super().__init__(detail)


class OfferNotFound(OfferError):
    def __init__(self) -> None:
        super().__init__("NOT_FOUND", "no such offer")


class ParentPropertyNotFound(OfferError):
    def __init__(self) -> None:
        super().__init__("NOT_FOUND", "no such property")


class UnknownParty(OfferError):
    def __init__(self, party_id) -> None:
        super().__init__("VALIDATION_FAILED",
                         f"party_id {party_id} is not a known party")


class UnknownSource(OfferError):
    def __init__(self, source_id) -> None:
        super().__init__("VALIDATION_FAILED",
                         f"source_id {source_id} is not a known source")


class SellerExpectationOnRent(OfferError):
    """The frozen schema's `CHECK (seller_expectation_dzd IS NULL OR
    transaction_type = 'SALE')`, named for the caller.

    The `CHECK` is unnamed in the schema, so a violation would carry only a
    generated name and surface as a 500. It is checked here first, and the
    `CHECK` stays as what makes it true of data written by anything else.
    """

    def __init__(self) -> None:
        super().__init__(
            "VALIDATION_FAILED",
            "seller_expectation_dzd applies only to a SALE offer; a RENT offer "
            "cannot carry one",
        )


class NotPatchable(OfferError):
    def __init__(self, fields: list[str]) -> None:
        super().__init__(
            "VALIDATION_FAILED",
            f"not updatable through this command: {sorted(fields)}",
        )


class AlreadyInState(OfferError):
    def __init__(self, status: str) -> None:
        super().__init__("VALIDATION_FAILED", f"the offer is already {status}")


class UndefinedTransition(OfferError):
    """The contract accepts the target; the ratified machine does not."""

    def __init__(self, current: str, target: str) -> None:
        self.current, self.target = current, target
        allowed = sorted(TRANSITIONS.get(current, frozenset()))
        detail = (f"{current} is terminal; no transition leaves it"
                  if not allowed else
                  f"{current} -> {target} is not a transition of the offer "
                  f"state machine; from {current} the defined targets are "
                  f"{allowed}")
        super().__init__("VALIDATION_FAILED", detail)


class TargetNotPermittedForCustomer(OfferError):
    """The edge exists, but not for a CUSTOMER (plan §3.5)."""

    def __init__(self, current: str, target: str) -> None:
        why = STAFF_ONLY_TARGETS.get(target)
        allowed = sorted(CUSTOMER_TARGETS.get(current, frozenset()))
        detail = why or (f"a customer cannot move an offer from {current} to "
                         f"{target}")
        detail += f"; from {current} you may set {allowed}"
        super().__init__("ACTION_NOT_PERMITTED", detail)


class UnknownReasonCode(OfferError):
    def __init__(self, code: str) -> None:
        super().__init__(
            "VALIDATION_FAILED",
            f"{code!r} is not an active reason code",
        )


class AliasParent(OfferError):
    """Decided F-2: an offer is not created on an identity alias. See
    `properties.AliasNotCanonical`, whose rule and ordering this shares."""

    def __init__(self, detail: str) -> None:
        super().__init__("IDENTITY_ALIAS_NOT_CANONICAL", detail)


def _refuse_alias_parent(session: Session, property_id: uuid.UUID) -> None:
    from .properties import AliasNotCanonical, refuse_alias

    try:
        refuse_alias(session, property_id)
    except AliasNotCanonical as exc:
        raise AliasParent(exc.detail) from exc


class OfferStateChanged(OfferError):
    """The compare-and-set lost: the offer left the state this transition was
    decided from before the transition could be applied (plan §6.3)."""

    def __init__(self, expected: str) -> None:
        super().__init__(
            "OFFER_STATE_CHANGED",
            f"the offer is no longer {expected}; it was changed concurrently. "
            "Re-read it and decide again.",
        )


def _guarded(session: Session, run, **context):
    """Run one write inside a SAVEPOINT and map the named constraints only.

    Same shape as `properties._guarded`: the SAVEPOINT is what makes catching
    the error safe, and only the constraints listed here are mapped.
    """
    from sqlalchemy.exc import IntegrityError

    savepoint = session.begin_nested()
    try:
        result = run()
        savepoint.commit()
        return result
    except IntegrityError as exc:
        savepoint.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", "")
        if constraint == PROPERTY_FK:
            raise ParentPropertyNotFound() from exc
        if constraint == PARTY_FK:
            raise UnknownParty(context.get("party_id")) from exc
        if constraint == SOURCE_FK:
            raise UnknownSource(context.get("source_id")) from exc
        raise


def _row(session: Session, offer_id: uuid.UUID) -> Mapping[str, Any]:
    row = session.execute(
        text(
            """SELECT offer_id, property_id, party_id,
                      transaction_type::text AS transaction_type,
                      status::text AS status, asking_price_dzd, raw_price_text,
                      price_negotiable::text AS price_negotiable,
                      seller_expectation_dzd,
                      price_visibility::text AS price_visibility,
                      last_confirmed_at, commercial_terms_last_confirmed_at,
                      permission_scope::text AS permission_scope,
                      version, created_by_account_id, created_at, updated_at
                 FROM turab.property_offers WHERE offer_id = :o"""
        ),
        {"o": offer_id},
    ).mappings().first()
    if row is None:
        raise OfferNotFound()
    return row


def read_offer(session: Session, offer_id: uuid.UUID) -> Mapping[str, Any]:
    return _row(session, offer_id)


def create_offer(
    session: Session,
    *,
    property_id: uuid.UUID,
    party_id: uuid.UUID,
    transaction_type: str,
    created_by_account_id: uuid.UUID | None,
    recorded_by_account_id: uuid.UUID | None = None,
    channel: UpdateChannel = UpdateChannel.STAFF_RECORDED,
    **optional: Any,
) -> Mapping[str, Any]:
    """Create an offer in `DRAFT`, the schema default.

    `created_by_account_id` is condition 1 of RFC-001 §4.6, so it is passed
    explicitly and never defaulted. No `party_property_relations` row is
    written: naming a party on an offer is not a statement about who is
    related to the property (G3-6, R4.5).

    Neither confirmation column is set. A newly entered offer has not been
    reconfirmed; it is `NEVER_CONFIRMED` until `/reconfirm` says otherwise,
    the same as a new request.
    """
    unknown = set(optional) - set(CREATE_OPTIONAL)
    if unknown:
        raise NotPatchable(sorted(unknown))
    _refuse_alias_parent(session, property_id)
    if (transaction_type != "SALE"
            and optional.get("seller_expectation_dzd") is not None):
        raise SellerExpectationOnRent()

    columns: dict[str, Any] = {
        "property_id": property_id,
        "party_id": party_id,
        "transaction_type": transaction_type,
        "created_by_account_id": created_by_account_id,
    }
    # Presence, not truthiness: a supplied 0 or "" is a value (R-S2-05a).
    for name in CREATE_OPTIONAL:
        if name in optional:
            columns[name] = optional[name]

    names = ", ".join(columns)
    values = ", ".join(
        f"CAST(:{c} AS {_CASTS[c]})" if c in _CASTS else f":{c}" for c in columns
    )
    offer_id = _guarded(
        session,
        lambda: session.execute(
            text(f"INSERT INTO turab.property_offers ({names}) VALUES ({values}) "
                 "RETURNING offer_id"),
            columns,
        ).scalar_one(),
        party_id=party_id,
    )
    provenance.record(
        session,
        subject=provenance.Subject.OFFER,
        subject_id=offer_id,
        party_id=party_id,
        changes={k: v for k, v in columns.items() if k != "created_by_account_id"},
        previous=None,
        recorded_by_account_id=recorded_by_account_id or created_by_account_id,
        channel=channel,
    )
    return _row(session, offer_id)


def patch_offer(
    session: Session,
    *,
    offer_id: uuid.UUID,
    changes: Mapping[str, Any],
    recorded_by_account_id: uuid.UUID | None,
    channel: UpdateChannel,
) -> Mapping[str, Any]:
    """Change the terms. Never the state, the party, the transaction type or
    the sharing scope.

    Run under the version guard, which has already locked the row; the
    `transaction_type` read below cannot change underneath it in any case,
    because nothing updates it.
    """
    unknown = set(changes) - PATCHABLE
    if unknown:
        raise NotPatchable(sorted(unknown))
    if not changes:
        raise OfferError("VALIDATION_FAILED", "no fields to update")

    before = _row(session, offer_id)
    if (before["transaction_type"] != "SALE"
            and changes.get("seller_expectation_dzd") is not None):
        raise SellerExpectationOnRent()

    assignments = ", ".join(
        f"{c} = CAST(:{c} AS {_CASTS[c]})" if c in _CASTS else f"{c} = :{c}"
        for c in changes
    )
    session.execute(
        text(f"UPDATE turab.property_offers SET {assignments} "
             "WHERE offer_id = :offer_id"),
        {**changes, "offer_id": offer_id},
    )
    provenance.record(
        session,
        subject=provenance.Subject.OFFER,
        subject_id=offer_id,
        party_id=before["party_id"],
        changes=dict(changes),
        previous=before,
        recorded_by_account_id=recorded_by_account_id,
        channel=channel,
    )
    return _row(session, offer_id)


def _validate_reason_code(session: Session, reason_code: str) -> None:
    """Against `reason_codes`, as ratified — existence and `active`.

    No category is required, because none is defined for offer states and the
    plan forbids creating one (§2, §3.5). This is stated rather than implied:
    any active code is accepted, which is exactly what "validated against
    reason_codes" says and no more.
    """
    known = session.execute(
        text("SELECT 1 FROM turab.reason_codes WHERE code = :c AND active"),
        {"c": reason_code},
    ).first()
    if known is None:
        raise UnknownReasonCode(reason_code)


def _add_to_audit_context(session: Session, extra: Mapping[str, Any]) -> None:
    """Merge keys into `app.audit_context` for the rest of this transaction.

    `audit_row_change()` copies that setting into `audit_log.context`, so the
    audit row written by the UPDATE that follows carries these keys. Merged,
    never replaced: the operation and trace id set by the command stay.
    """
    session.execute(
        text(
            """SELECT set_config(
                   'app.audit_context',
                   (COALESCE(NULLIF(current_setting('app.audit_context', true), ''),
                             '{}')::jsonb || CAST(:extra AS jsonb))::text,
                   true)"""
        ),
        {"extra": json.dumps(dict(extra))},
    )


def transition(
    session: Session,
    *,
    offer_id: uuid.UUID,
    target_status: str,
    reason_code: str | None = None,
    customer: bool,
    recorded_by_account_id: uuid.UUID | None,
    channel: UpdateChannel,
) -> Mapping[str, Any]:
    """Move an offer along the ratified machine, by compare-and-set.

    **Why this is NOT the REQUEST pattern.** `requests.transition` locks the
    row and then decides from what it reads. Under Read Committed, a second
    transition waiting on that lock then reads the NEW state and decides from
    it — so on the request machine it is refused only when its edge happens
    not to exist from the new state. On the offer machine most edges exist
    from most states: `ACTIVE -> PAUSED` racing `ACTIVE -> WITHDRAWN` would
    apply both, the second from a `PAUSED` its caller never saw.

    Plan §6.3 declares the opposite outcome — a genuine winner and loser — and
    names the mechanism: `AND status = :expected` in the `UPDATE`. So the
    decision is taken from an unlocked read, and the `UPDATE` applies only if
    the row is still in that state. A concurrent `UPDATE` holding the row lock
    makes this one wait; PostgreSQL then re-evaluates the `WHERE` clause
    against the committed new version and skips the row if it no longer
    matches (PostgreSQL 16 documentation, §13.2.1 "Read Committed Isolation
    Level"). Zero rows is the losing outcome, reported as `OfferStateChanged`.
    """
    before = _row(session, offer_id)
    current = before["status"]

    if target_status == current:
        raise AlreadyInState(current)
    if target_status not in TRANSITIONS.get(current, frozenset()):
        raise UndefinedTransition(current, target_status)
    if customer and target_status not in CUSTOMER_TARGETS.get(current, frozenset()):
        raise TargetNotPermittedForCustomer(current, target_status)
    if reason_code is not None:
        _validate_reason_code(session, reason_code)
        _add_to_audit_context(session, {"reason_code": reason_code})

    applied = session.execute(
        text(
            """UPDATE turab.property_offers
                  SET status = CAST(:target AS turab.offer_status)
                WHERE offer_id = :o
                  AND status = CAST(:expected AS turab.offer_status)
            RETURNING offer_id"""
        ),
        {"target": target_status, "o": offer_id, "expected": current},
    ).first()
    if applied is None:
        raise OfferStateChanged(current)

    # The durable, readable trail for `reason_code` (plan §3.5): the offer has
    # no reason column and no migration is permitted, so it lives in the
    # provenance claim — alongside the audit row's context, set above.
    provenance.record(
        session,
        subject=provenance.Subject.OFFER,
        subject_id=offer_id,
        party_id=before["party_id"],
        changes={"status": {"from": current, "to": target_status,
                            "reason_code": reason_code}},
        previous=None,
        recorded_by_account_id=recorded_by_account_id,
        channel=channel,
        observation_kind="SYSTEM_IMPORT",
    )
    return _row(session, offer_id)


def state_history(session: Session, offer_id: uuid.UUID) -> list[Mapping[str, Any]]:
    """Every recorded transition, oldest first, with its `reason_code`."""
    return [
        r["claimed_value"]
        for r in provenance.read(session, subject=provenance.Subject.OFFER,
                                 subject_id=offer_id)
        if r["attribute_code"] == "status" and isinstance(r["claimed_value"], dict)
    ]


def link_source(
    session: Session,
    *,
    offer_id: uuid.UUID,
    source_id: uuid.UUID,
    is_primary: bool,
) -> None:
    """Link a source; when primary, TRANSFER the flag (plan §3.6).

    Under a lock on the parent offer: clear the existing primary, THEN set the
    new one — in that order, because `ux_offer_primary_source` would reject
    the intermediate state the other way round. No link is ever deleted.

    Two concurrent primary links serialise on the offer lock and BOTH succeed;
    the last committer's source is primary. That is the declared outcome: no
    compare-and-set is declared for this operation, so no loser is invented.
    """
    locked = session.execute(
        text("SELECT offer_id FROM turab.property_offers "
             "WHERE offer_id = :o FOR UPDATE"),
        {"o": offer_id},
    ).first()
    if locked is None:
        raise OfferNotFound()

    def write():
        if is_primary:
            session.execute(
                text("""UPDATE turab.property_offer_sources SET is_primary = false
                         WHERE offer_id = :o AND is_primary AND source_id <> :s"""),
                {"o": offer_id, "s": source_id},
            )
        session.execute(
            text("""INSERT INTO turab.property_offer_sources
                           (offer_id, source_id, is_primary)
                    VALUES (:o, :s, :p)
                    ON CONFLICT (offer_id, source_id)
                    DO UPDATE SET is_primary = EXCLUDED.is_primary"""),
            {"o": offer_id, "s": source_id, "p": is_primary},
        )

    from sqlalchemy.exc import IntegrityError

    try:
        _guarded(session, write, source_id=source_id)
    except IntegrityError as exc:
        # Reachable only if something bypasses the offer lock; mapped so it is
        # a typed 409 rather than a 500 (plan §3.6, point 3).
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", "")
        if constraint == PRIMARY_SOURCE_INDEX:
            raise OfferError("PRIMARY_SOURCE_CONFLICT",
                             "another primary source was set concurrently") from exc
        raise


def sources_of(session: Session, offer_id: uuid.UUID) -> list[Mapping[str, Any]]:
    return session.execute(
        text("""SELECT source_id, is_primary, linked_at
                  FROM turab.property_offer_sources
                 WHERE offer_id = :o ORDER BY linked_at, source_id"""),
        {"o": offer_id},
    ).mappings().all()


class ConfirmationInTheFuture(OfferError):
    def __init__(self) -> None:
        super().__init__(
            "VALIDATION_FAILED",
            "confirmed_at cannot be in the future; a confirmation records "
            "something that has already happened",
        )


def reconfirm(
    session: Session,
    *,
    offer_id: uuid.UUID,
    confirmed_at=None,
    notes: str | None = None,
    recorded_by_account_id: uuid.UUID | None,
    channel: UpdateChannel,
) -> Mapping[str, Any]:
    """Record that the offer's terms were confirmed (plan §3.4, ratified).

    Writes `last_confirmed_at` AND `commercial_terms_last_confirmed_at`, to
    the SAME instant, in one statement: v0.1 confirms them together. The
    freshness policy (`offer_terms`) reads only the second.

    It changes nothing else — not the terms, not the state. The offer state
    machine (§3.5) has no edge that a confirmation takes; that is what
    distinguishes this from the REQUEST reconfirm, whose §5.2 defines one.
    """
    if confirmed_at is not None:
        now = session.execute(text("SELECT clock_timestamp()")).scalar_one()
        if confirmed_at > now:
            raise ConfirmationInTheFuture()

    locked = session.execute(
        text("SELECT offer_id FROM turab.property_offers "
             "WHERE offer_id = :o FOR UPDATE"),
        {"o": offer_id},
    ).first()
    if locked is None:
        raise OfferNotFound()
    before = _row(session, offer_id)
    session.execute(
        text(
            """UPDATE turab.property_offers
                  SET last_confirmed_at = s.at,
                      commercial_terms_last_confirmed_at = s.at
                 FROM (SELECT COALESCE(CAST(:at AS timestamptz), clock_timestamp()) AS at) s
                WHERE offer_id = :o"""
        ),
        {"at": confirmed_at, "o": offer_id},
    )
    after = _row(session, offer_id)
    stamp = after["commercial_terms_last_confirmed_at"].isoformat()
    provenance.record(
        session,
        subject=provenance.Subject.OFFER,
        subject_id=offer_id,
        party_id=before["party_id"],
        changes={"last_confirmed_at": stamp,
                 "commercial_terms_last_confirmed_at": stamp},
        previous=before,
        recorded_by_account_id=recorded_by_account_id,
        channel=channel,
        note=notes,
    )
    return after
