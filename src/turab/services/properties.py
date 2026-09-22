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
    for name in ("canonical_location_id", "local_location_detail",
                 "land_area_m2", "built_area_m2", "current_availability"):
        if optional.get(name) is not None:
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
