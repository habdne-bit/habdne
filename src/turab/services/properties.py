"""PROPERTY: the physical record — Slice 3, step 1.

Ref: IMPLEMENTATION_SLICES_v0.2.md Slice 3 (lines 127-166); the effective
contract's `PropertyCreate`, `PropertyPatch`; RFC-001 §4.4 (R4.1-R4.3),
§4.2 (R4.5); `docs/gate/SLICE_3_PLAN.md` §3.3.

A property is a **physical thing**, and this module keeps it separate from
three things it is repeatedly confused with:

  * **its commercial offers** — several may exist for one property, by
    different parties, at once. `property_offers` is a different table and a
    different slice step.
  * **who is related to it** — `party_property_relations`, which nothing may
    yet create (G3-6) and which is never an authorization source (R4.5).
  * **whether it is available** — an operational fact that changes, recorded
    through reconfirmation, NOT through `PATCH`. See `PATCHABLE` below.

What a property does NOT have is a `party_id` column. Authority over it is the
creator account or a recorded claim, and nothing else (R4.1). This module
therefore never asks "whose property is this?" — there is no such column to
answer from, and answering it from `party_property_relations` would contradict
a FINAL decision.
"""
from __future__ import annotations

import uuid
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import provenance
from .provenance import UpdateChannel

#: The frozen schema's `property_type`, transcribed once.
PROPERTY_TYPES = (
    "HOUSE_VILLA", "APARTMENT", "LAND", "SHOP_COMMERCIAL",
    "AGRICULTURAL_PROPERTY", "BUILDING", "OTHER",
)

#: `PropertyPatch` in the effective contract, field for field. Availability is
#: DELIBERATELY absent: the contract's patch body has `additionalProperties:
#: false` and does not declare it, so changing availability through this
#: command is not something we decline to support — it is something the
#: contract does not define. It changes through `reconfirm`, which requires an
#: explicit value and stamps when it was confirmed (plan §3.3, ratified G3-3).
PATCHABLE = frozenset({
    "property_type", "canonical_location_id", "local_location_detail",
    "land_area_m2", "built_area_m2",
})

#: Set at creation only. Listed so a reader can see the difference between
#: "not patchable because the contract says so" and "not a column".
CREATE_ONLY = frozenset({"current_availability", "supply_mode",
                         "management_mode", "claim_status"})

#: The one foreign key an API caller can violate with a well-formed body.
#: `created_by_account_id` is not in this map: it comes from the authenticated
#: subject, never from the request, so a violation there would be a real fault
#: and must keep surfacing as one rather than being reported as bad input.
LOCATION_FK = "properties_canonical_location_id_fkey"

_CASTS = {
    "property_type": "turab.property_type",
    "current_availability": "turab.availability_status",
    "supply_mode": "turab.supply_mode",
    "management_mode": "turab.management_mode",
    "claim_status": "turab.account_claim_status",
}


class PropertyError(Exception):
    """A refusal with a stable code, mapped to a typed problem by the route."""

    def __init__(self, code: str, detail: str) -> None:
        self.code, self.detail = code, detail
        super().__init__(detail)


class PropertyNotFound(PropertyError):
    def __init__(self) -> None:
        super().__init__("NOT_FOUND", "no such property")


class InvalidManagementCombination(PropertyError):
    """`ASSISTED` means unclaimed; anything else means claimed.

    The frozen schema enforces the same pair with a `CHECK`. Both are kept: the
    typed error names the rule for the caller, and the `CHECK` makes it true of
    data written by anything, including a future importer.
    """

    def __init__(self, management_mode: str, claim_status: str) -> None:
        super().__init__(
            "VALIDATION_FAILED",
            f"management_mode {management_mode!r} cannot be combined with "
            f"claim_status {claim_status!r}: ASSISTED records are UNCLAIMED, "
            "and SELF_MANAGED or SHARED_MANAGEMENT records are CLAIMED",
        )


class UnknownLocation(PropertyError):
    """`canonical_location_id` names a location that does not exist.

    A well-formed UUID that matches no row reached
    `properties_canonical_location_id_fkey` and surfaced as a 500. It is an
    input error and is reported as one — the same lesson as R-S2-03, applied
    to a foreign key rather than a unique index.
    """

    def __init__(self, location_id) -> None:
        super().__init__(
            "VALIDATION_FAILED",
            f"canonical_location_id {location_id} is not a known location",
        )


class AliasNotCanonical(PropertyError):
    """A write names an identity ALIAS rather than its canonical property.

    Decided F-2: refused with `409 IDENTITY_ALIAS_NOT_CANONICAL`. The refusal
    is raised INSIDE the command, i.e. after the route's object check, which
    already resolved the alias to the canonical (R4.9): an actor with no
    authority is refused with the ordinary 404 before this can be reached, so
    the 409 never tells an unauthorized caller that the id exists.

    Nothing already attached to the alias is moved or relinked (ADR-03:
    identity resolution is non-destructive). Only NEW writes are refused.
    """

    def __init__(self, property_id, canonical_id) -> None:
        self.canonical_id = canonical_id
        super().__init__(
            "IDENTITY_ALIAS_NOT_CANONICAL",
            f"property {property_id} is an identity alias of {canonical_id}; "
            "write to the canonical property",
        )


def refuse_alias(session: Session, property_id: uuid.UUID) -> None:
    """Raise `AliasNotCanonical` if `property_id` is an identity alias.

    Aliases are created only by identity review (plan step 7), which will have
    to take the property's row lock so this check and a concurrent aliasing
    cannot interleave; until then no path creates one.
    """
    canonical = session.execute(
        text("""SELECT canonical_property_id FROM turab.property_identity_aliases
                 WHERE alias_property_id = :p"""),
        {"p": property_id},
    ).scalar_one_or_none()
    if canonical is not None:
        raise AliasNotCanonical(property_id, canonical)


class NotPatchable(PropertyError):
    """Names the field AND why, because 'unknown field' would be misleading
    for `current_availability`, which is a real column reached another way."""

    def __init__(self, fields: list[str]) -> None:
        availability = [f for f in fields if f in CREATE_ONLY]
        detail = f"not updatable through this command: {sorted(fields)}"
        if "current_availability" in availability:
            detail += ("; availability is recorded through "
                       "POST /properties/{property_id}/reconfirm, which states "
                       "the confirmed value explicitly and stamps when it was "
                       "confirmed")
        super().__init__("VALIDATION_FAILED", detail)


def _guarded(session: Session, run, *, location_id):
    """Run a write inside a SAVEPOINT and map exactly one named constraint.

    A SAVEPOINT is what makes catching it safe: without one the failed
    statement poisons the whole transaction, so the caller could not continue
    to a clean rollback of just this work. ONLY the location foreign key is
    mapped; every other database error propagates unchanged, because turning
    all of them into 4xx would hide real faults.
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
        if constraint == LOCATION_FK:
            raise UnknownLocation(location_id) from exc
        raise


def _row(
    session: Session, property_id: uuid.UUID, *, for_update: bool = False
) -> Mapping[str, Any]:
    """Read a property. With `for_update`, lock it first.

    Same rule as Slice 2's `requests._row`, and for the same reason (R-S2-02):
    a command that DECIDES from what it reads must lock it, because under Read
    Committed a plain read is a snapshot and the decision can be applied after
    another transaction changed the thing it was about. A read for rendering
    takes no lock.
    """
    row = session.execute(
        text(
            """SELECT property_id, property_type::text AS property_type,
                      canonical_location_id, local_location_detail,
                      land_area_m2, built_area_m2,
                      current_availability::text AS current_availability,
                      availability_last_confirmed_at,
                      supply_mode::text AS supply_mode,
                      management_mode::text AS management_mode,
                      claim_status::text AS claim_status,
                      version, created_by_account_id, created_at, updated_at
                 FROM turab.properties WHERE property_id = :p"""
            + (" FOR UPDATE" if for_update else "")
        ),
        {"p": property_id},
    ).mappings().first()
    if row is None:
        raise PropertyNotFound()
    return row


def create_property(
    session: Session,
    *,
    property_type: str,
    management_mode: str,
    claim_status: str,
    supply_mode: str,
    created_by_account_id: uuid.UUID | None,
    recorded_by_account_id: uuid.UUID | None = None,
    channel: UpdateChannel = UpdateChannel.STAFF_RECORDED,
    **optional: Any,
) -> Mapping[str, Any]:
    """Create the physical record.

    `created_by_account_id` is the only thing this writes that later grants
    anyone authority (R4.1), so it is passed explicitly and never defaulted
    from the session.
    """
    if management_mode == "ASSISTED" and claim_status != "UNCLAIMED":
        raise InvalidManagementCombination(management_mode, claim_status)
    if (management_mode in ("SELF_MANAGED", "SHARED_MANAGEMENT")
            and claim_status != "CLAIMED"):
        raise InvalidManagementCombination(management_mode, claim_status)

    columns: dict[str, Any] = {
        "property_type": property_type,
        "management_mode": management_mode,
        "claim_status": claim_status,
        "supply_mode": supply_mode,
        "created_by_account_id": created_by_account_id,
    }
    # Presence, not truthiness, and not `is not None` either: a caller that
    # PASSED a field gets that value written, including "" and 0. A field the
    # caller did not pass is left out so the column default decides. Testing
    # `if optional.get(name)` turned an empty `local_location_detail` into
    # NULL — the contract allows the empty string, so that was data loss.
    for name in ("canonical_location_id", "local_location_detail",
                 "land_area_m2", "built_area_m2", "current_availability"):
        if name in optional:
            columns[name] = optional[name]

    names = ", ".join(columns)
    values = ", ".join(
        f"CAST(:{c} AS {_CASTS[c]})" if c in _CASTS else f":{c}" for c in columns
    )
    property_id = _guarded(
        session,
        lambda: session.execute(
            text(f"INSERT INTO turab.properties ({names}) VALUES ({values}) "
                 "RETURNING property_id"),
            columns,
        ).scalar_one(),
        location_id=columns.get("canonical_location_id"),
    )

    # The creation itself is provenance: it records what was asserted about a
    # physical thing, by whom, and through which channel. `party_id` is NULL
    # because a property HAS no party — see the module docstring. Recording a
    # party here would be inventing the very relation G3-6 forbids inferring.
    recorded = {k: v for k, v in columns.items()
                if k != "created_by_account_id"}
    provenance.record(
        session,
        subject=provenance.Subject.PROPERTY,
        subject_id=property_id,
        party_id=None,
        changes=recorded,
        previous=None,
        recorded_by_account_id=recorded_by_account_id or created_by_account_id,
        channel=channel,
    )
    return _row(session, property_id)


def read_property(session: Session, property_id: uuid.UUID) -> Mapping[str, Any]:
    return _row(session, property_id)


def patch_property(
    session: Session,
    *,
    property_id: uuid.UUID,
    changes: Mapping[str, Any],
    recorded_by_account_id: uuid.UUID | None,
    channel: UpdateChannel,
    source_reference: uuid.UUID | None = None,
    note: str | None = None,
) -> Mapping[str, Any]:
    """Change the physical description. Never the availability, never the
    management pair, never the supply mode.

    The version bump comes from `trg_properties_version`, so it happens for any
    update including one issued by something that forgets to ask.
    """
    unknown = set(changes) - PATCHABLE
    if unknown:
        raise NotPatchable(sorted(unknown))
    if not changes:
        raise PropertyError("VALIDATION_FAILED", "no fields to update")

    before = _row(session, property_id)
    refuse_alias(session, property_id)
    assignments = ", ".join(
        f"{c} = CAST(:{c} AS {_CASTS[c]})" if c in _CASTS else f"{c} = :{c}"
        for c in changes
    )
    _guarded(
        session,
        lambda: session.execute(
            text(f"UPDATE turab.properties SET {assignments} "
                 "WHERE property_id = :property_id"),
            {**changes, "property_id": property_id},
        ),
        location_id=changes.get("canonical_location_id"),
    )
    provenance.record(
        session,
        subject=provenance.Subject.PROPERTY,
        subject_id=property_id,
        party_id=None,
        changes=dict(changes),
        previous=before,
        recorded_by_account_id=recorded_by_account_id,
        channel=channel,
        source_reference=source_reference,
        note=note,
    )
    return _row(session, property_id)


def provenance_for(session: Session, property_id: uuid.UUID) -> list[Mapping[str, Any]]:
    return provenance.read(
        session, subject=provenance.Subject.PROPERTY, subject_id=property_id
    )


# --- availability: reconfirmation and the staleness pass (plan §3.3, G3-3) --

#: The seven values of the frozen `availability_status` enum.
AVAILABILITY_VALUES = (
    "AVAILABLE", "POTENTIALLY_AVAILABLE", "UNDER_DISCUSSION",
    "TEMPORARILY_UNAVAILABLE", "UNAVAILABLE", "NEEDS_CONFIRMATION", "UNKNOWN",
)

#: Ratified rule 4: the ONLY values the staleness pass converts. `UNKNOWN`,
#: `NEEDS_CONFIRMATION` and `UNAVAILABLE` are never touched — each has its own
#: test, because a single "the others are untouched" assertion would pass on a
#: predicate that excluded only one of them.
STALE_CONVERTIBLE = ("AVAILABLE", "POTENTIALLY_AVAILABLE", "UNDER_DISCUSSION",
                     "TEMPORARILY_UNAVAILABLE")


class ConfirmationInTheFuture(PropertyError):
    """Same rule as a REQUEST confirmation: a confirmation records something
    that has already happened."""

    def __init__(self) -> None:
        super().__init__(
            "VALIDATION_FAILED",
            "confirmed_at cannot be in the future; a confirmation records "
            "something that has already happened",
        )


def reconfirm_availability(
    session: Session,
    *,
    property_id: uuid.UUID,
    availability: str,
    confirmed_at=None,
    notes: str | None = None,
    recorded_by_account_id: uuid.UUID | None,
    channel: UpdateChannel,
) -> Mapping[str, Any]:
    """Record the availability that was confirmed, and when (ratified G3-3).

    Rule 1: ANY value may follow ANY value — this records a fact, it does not
    traverse an edge, so there is no transition table to consult.
    Rule 2: the value is the one the caller STATES; nothing is restored from
    memory. Rule 3: time, actor and channel are stamped, and the provenance
    trail is written with the previous value.

    Locked: the provenance records `before`, so the row must not change
    between reading it and writing (R-S2-02). A write to an identity alias is
    refused (decision F-2).
    """
    if availability not in AVAILABILITY_VALUES:
        raise PropertyError("VALIDATION_FAILED",
                            f"availability must be one of {list(AVAILABILITY_VALUES)}")
    if confirmed_at is not None:
        now = session.execute(text("SELECT clock_timestamp()")).scalar_one()
        if confirmed_at > now:
            raise ConfirmationInTheFuture()

    before = _row(session, property_id, for_update=True)
    refuse_alias(session, property_id)
    session.execute(
        text(
            """UPDATE turab.properties
                  SET current_availability = CAST(:a AS turab.availability_status),
                      availability_last_confirmed_at = COALESCE(:at, clock_timestamp())
                WHERE property_id = :p"""
        ),
        {"a": availability, "at": confirmed_at, "p": property_id},
    )
    after = _row(session, property_id)
    provenance.record(
        session,
        subject=provenance.Subject.PROPERTY,
        subject_id=property_id,
        party_id=None,
        changes={
            "current_availability": availability,
            "availability_last_confirmed_at":
                after["availability_last_confirmed_at"].isoformat(),
        },
        previous=before,
        recorded_by_account_id=recorded_by_account_id,
        channel=channel,
        note=notes,
    )
    return after


def stale_available_properties(
    session: Session, *, now=None, limit: int = 500
) -> list[uuid.UUID]:
    """Which properties the staleness pass WOULD convert. Reads only."""
    from . import freshness

    days, _ = freshness.property_threshold_days(session)
    return list(session.execute(
        text(
            """SELECT property_id FROM turab.properties
                WHERE current_availability::text = ANY(:convertible)
                  AND availability_last_confirmed_at IS NOT NULL
                  AND availability_last_confirmed_at
                      < COALESCE(:now, clock_timestamp()) - make_interval(days => :days)
                ORDER BY availability_last_confirmed_at, property_id
                LIMIT :limit"""
        ),
        {"convertible": list(STALE_CONVERTIBLE), "now": now, "days": days,
         "limit": limit},
    ).scalars().all())


#: The staleness pass, as ONE statement. A module constant so the step-4
#: concurrency experiment can run controlled variants of exactly this text
#: (tests/test_slice3_step4.py) and check each variant really differs from it.
_STALE_AVAILABILITY_SQL = text(
    """UPDATE turab.properties p
                  SET current_availability = 'NEEDS_CONFIRMATION'
                 FROM (
                      SELECT property_id FROM turab.properties
                       WHERE current_availability::text = ANY(:convertible)
                         AND availability_last_confirmed_at IS NOT NULL
                         AND availability_last_confirmed_at
                             < COALESCE(:now, clock_timestamp())
                               - make_interval(days => :days)
                       ORDER BY availability_last_confirmed_at, property_id
                       LIMIT :limit
                       FOR UPDATE SKIP LOCKED) AS candidate
                WHERE p.property_id = candidate.property_id
                  AND p.current_availability::text = ANY(:convertible)
                  AND p.availability_last_confirmed_at IS NOT NULL
                  AND p.availability_last_confirmed_at
                      < COALESCE(:now, clock_timestamp()) - make_interval(days => :days)
            RETURNING p.property_id"""
)


def mark_stale_availability(
    session: Session, *, now=None, limit: int = 500
) -> list[uuid.UUID]:
    """Stale availability becomes `NEEDS_CONFIRMATION` — for the four named
    values only (ratified rule 4).

    Staleness is measured on `availability_last_confirmed_at` against the
    active policy's `freshness_threshold_days.property`, never a constant. A
    property whose availability was NEVER confirmed (`NULL`) is not stale: it
    has not gone out of date, it has not been put in date — the rule the
    REQUEST pass already applies.

    Same shape as the REQUEST pass, and for the same reason (R-S2-02): the
    subquery SELECTS candidates with `FOR UPDATE SKIP LOCKED`, and the outer
    `UPDATE` RE-ASSERTS every condition — the four-value set included — on
    the row as it stands at the moment of writing. A property reconfirmed or
    marked `UNAVAILABLE` between the sample and the write is therefore left
    alone.

    Not scheduled: like the request pass, this runs when someone runs
    `db/dev/run_freshness_pass.py`. Nothing in this version schedules it.
    """
    from . import freshness

    days, _ = freshness.property_threshold_days(session)
    return list(session.execute(
        _STALE_AVAILABILITY_SQL,
        {"convertible": list(STALE_CONVERTIBLE), "now": now, "days": days,
         "limit": limit},
    ).scalars().all())
