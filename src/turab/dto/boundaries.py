"""Public / Customer / Internal DTO boundaries.

Ref: ADR-06; API_CONTRACTS v0.2 §3, §8; RFC-001 R9.1-R9.5, R8.2, R8.2a;
red-team K03 and D02.

R9.1 is the load-bearing rule: these are SEPARATE TYPES, not one entity with
fields deleted. A delete-keys approach fails open the moment a column is added
to the table — the new column is serialized until someone remembers to remove
it. Building the target type explicitly fails closed instead: a new column is
simply not in the model, and nothing happens.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict

#: R9.2 / R8.2a. Never rendered to a public or customer audience at ANY sharing
#: scope. Scope raises the ceiling; it never opens this floor.
NEVER_SERIALIZED: frozenset[str] = frozenset(
    {
        # internal pricing expectations
        "seller_expectation_dzd",
        # consent internals
        "consent_id", "consent_binding_id", "current_permission_binding_id",
        "permission_snapshot",
        # management metadata
        "management_mode", "claim_status", "created_by_account_id",
        "recorded_by_account_id", "resolved_by_account_id", "reviewer_account_id",
        # staff notes and free internal text
        "notes", "staff_notes", "review_reason_text", "source_note",
        # provenance internals
        "observation_id", "claim_id", "resolved_claim_id", "source_id",
        "raw_text", "payload", "external_url", "external_ref", "metadata",
        "evidence_observation_id",
        # matching internals
        "approved_match_id", "request_snapshot", "property_snapshot",
        "commercial_context_snapshot", "freshness_snapshot", "input_hash",
        "soft_score", "matching_policy_id",
        # AI internals
        "ai_trace_ref", "extraction_model_version", "extraction_confidence",
        "generated_by",
    }
)


class Audience(StrEnum):
    PUBLIC = "PUBLIC"
    CUSTOMER = "CUSTOMER"
    INTERNAL = "INTERNAL"


class SharingScope(StrEnum):
    SUMMARY_ONLY = "SUMMARY_ONLY"
    PROPERTY_DETAILS_ALLOWED = "PROPERTY_DETAILS_ALLOWED"
    CONTACT_AFTER_CONFIRMATION = "CONTACT_AFTER_CONFIRMATION"


class PriceVisibility(StrEnum):
    PUBLIC = "PUBLIC"
    ON_REQUEST = "ON_REQUEST"
    PRIVATE = "PRIVATE"


class FieldLeak(AssertionError):
    """A forbidden field reached an outward-facing payload."""


@dataclass(frozen=True, slots=True)
class FloorException:
    """A NUMBERED, bounded exception to the R9.2 floor.

    ADR-06 forbids management metadata in customer DTOs "unless explicitly
    approved by the relevant sharing contract". An exception names the
    fields, the operations whose declared response carries them, and the
    decision that approved it. It applies ONLY to the top-level keys of those
    operations' responses — never to a nested object, never to another
    operation, never to a `/me` read or the public list. The fields stay in
    `NEVER_SERIALIZED`: the floor is not lowered, a hole is cut in it with an
    edge a test can find.
    """

    number: str
    fields: frozenset[str]
    operations: frozenset[str]
    basis: str


#: The register. Adding to it is a decision, not an implementation choice.
FLOOR_EXCEPTIONS: tuple[FloorException, ...] = (
    FloorException(
        number="R9.2-EX-01",
        fields=frozenset({"management_mode", "claim_status"}),
        # Every operation whose `x-roles` admits CUSTOMER and whose 2xx
        # response is `Property` or `Request` — both `allOf` a create body that
        # REQUIRES the two fields. Derived from the contract and asserted equal
        # to this set by a test, so neither can drift from the other.
        operations=frozenset({
            "postProperties", "patchPropertiesPropertyId",
            "postPropertiesPropertyIdReconfirm",
            "postRequests", "patchRequestsRequestId",
            "postRequestsRequestIdState", "postRequestsRequestIdReconfirm",
        }),
        basis=(
            "Decision F-1: the declared response schema of these commands is "
            "the explicit sharing approval ADR-06 permits. The basis is the "
            "schema, NOT that the customer supplied the values at creation: "
            "the response may carry state changed since."
        ),
    ),
)


def exempted_fields(operation_id: str | None) -> frozenset[str]:
    """The floor fields an operation's TOP-LEVEL response may carry."""
    if operation_id is None:
        return frozenset()
    allowed: set[str] = set()
    for exception in FLOOR_EXCEPTIONS:
        if operation_id in exception.operations:
            allowed |= exception.fields
    return frozenset(allowed)


def assert_no_forbidden_fields(
    payload: Any, audience: Audience, *, operation_id: str | None = None
) -> None:
    """Belt-and-braces check on a rendered payload.

    The types already make a leak hard; this makes it loud. Internal payloads
    are exempt by definition — they are the audience the fields exist for.

    `operation_id` admits the numbered `FLOOR_EXCEPTIONS` for that operation,
    at the top level of the payload only.
    """
    if audience is Audience.INTERNAL:
        return
    exempt = exempted_fields(operation_id)
    found: list[str] = []

    def walk(node: Any, path: str = "") -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if key in NEVER_SERIALIZED and not (path == "" and key in exempt):
                    found.append(f"{path}{key}")
                walk(value, f"{path}{key}.")
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item, path)

    walk(payload)
    if found:
        raise FieldLeak(
            f"{audience.value} payload contains {sorted(found)}: these are "
            "internal fields (ADR-06, API_CONTRACTS §3)"
        )


class _Strict(BaseModel):
    """Extra fields are an error, not silently dropped.

    Dropping them would let a caller build a view from a row containing
    internal columns and never know the boundary had been tested.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


# --- Public ----------------------------------------------------------------

class PublicOfferSummary(_Strict):
    offer_id: uuid.UUID
    transaction_type: str
    asking_price_dzd: int | None = None
    price_visibility: str
    price_negotiable: str

    @classmethod
    def render(cls, row: Mapping[str, Any]) -> "PublicOfferSummary":
        """R9.4. `price_visibility` redacts the price regardless of scope."""
        visibility = str(row["price_visibility"])
        price = row.get("asking_price_dzd")
        if visibility != PriceVisibility.PUBLIC:
            price = None
        return cls(
            offer_id=row["offer_id"],
            transaction_type=str(row["transaction_type"]),
            asking_price_dzd=int(price) if price is not None else None,
            price_visibility=visibility,
            price_negotiable=str(row["price_negotiable"]),
        )


class PublicPropertySummary(_Strict):
    property_id: uuid.UUID
    property_type: str
    canonical_location_id: uuid.UUID | None = None
    local_location_detail: str | None = None
    land_area_m2: Decimal | None = None
    built_area_m2: Decimal | None = None
    supply_mode: str
    availability: str
    offers: tuple[PublicOfferSummary, ...] = ()

    @classmethod
    def render(
        cls, row: Mapping[str, Any], offers: list[Mapping[str, Any]] | None = None
    ) -> "PublicPropertySummary":
        return cls(
            property_id=row["property_id"],
            property_type=str(row["property_type"]),
            canonical_location_id=row.get("canonical_location_id"),
            local_location_detail=row.get("local_location_detail"),
            land_area_m2=row.get("land_area_m2"),
            built_area_m2=row.get("built_area_m2"),
            supply_mode=str(row["supply_mode"]),
            availability=str(row.get("current_availability", "UNKNOWN")),
            offers=tuple(PublicOfferSummary.render(o) for o in (offers or [])),
        )


# --- Customer --------------------------------------------------------------

class CustomerPartyView(_Strict):
    """v0.2.2 (D2) adds `version`, so a CUSTOMER can obtain the value that
    PATCH /parties/{party_id} requires in If-Match-Version. Without it the
    contract demanded a version the customer had no way to read."""

    party_id: uuid.UUID
    display_name: str | None = None
    contact_points: tuple[str, ...] = ()
    version: int

    @classmethod
    def render(cls, row: Mapping[str, Any],
               contact_points: list[str] | None = None) -> "CustomerPartyView":
        return cls(
            party_id=row["party_id"],
            display_name=row.get("display_name"),
            contact_points=tuple(contact_points or ()),
            version=int(row["version"]),
        )


class CustomerPropertyView(_Strict):
    property_id: uuid.UUID
    property_type: str
    canonical_location_id: uuid.UUID | None = None
    local_location_detail: str | None = None
    land_area_m2: Decimal | None = None
    built_area_m2: Decimal | None = None
    current_availability: str
    availability_last_confirmed_at: datetime | None = None
    supply_mode: str
    version: int

    @classmethod
    def render(cls, row: Mapping[str, Any]) -> "CustomerPropertyView":
        return cls(
            property_id=row["property_id"],
            property_type=str(row["property_type"]),
            canonical_location_id=row.get("canonical_location_id"),
            local_location_detail=row.get("local_location_detail"),
            land_area_m2=row.get("land_area_m2"),
            built_area_m2=row.get("built_area_m2"),
            current_availability=str(row.get("current_availability", "UNKNOWN")),
            availability_last_confirmed_at=row.get("availability_last_confirmed_at"),
            supply_mode=str(row["supply_mode"]),
            version=int(row["version"]),
        )


class CustomerRequestView(_Strict):
    request_id: uuid.UUID
    status: str
    transaction_intent: str
    intent: str | None = None
    payment: str | None = None
    desired_property_type: str | None = None
    primary_location_id: uuid.UUID | None = None
    budget_target_dzd: int | None = None
    budget_max_dzd: int | None = None
    budget_flexibility: str | None = None
    last_confirmed_at: datetime | None = None
    criteria: tuple[dict[str, Any], ...] = ()

    @classmethod
    def render(cls, row: Mapping[str, Any],
               criteria: list[dict[str, Any]] | None = None) -> "CustomerRequestView":
        return cls(
            request_id=row["request_id"],
            status=str(row["status"]),
            transaction_intent=str(row["transaction_intent"]),
            intent=str(row["intent"]) if row.get("intent") else None,
            payment=str(row["payment"]) if row.get("payment") else None,
            desired_property_type=(
                str(row["desired_property_type"])
                if row.get("desired_property_type") else None
            ),
            primary_location_id=row.get("primary_location_id"),
            budget_target_dzd=row.get("budget_target_dzd"),
            budget_max_dzd=row.get("budget_max_dzd"),
            budget_flexibility=(
                str(row["budget_flexibility"]) if row.get("budget_flexibility") else None
            ),
            last_confirmed_at=row.get("last_confirmed_at"),
            criteria=tuple(criteria or ()),
        )


class CustomerOpportunityView(_Strict):
    opportunity_id: uuid.UUID
    status: str
    validity_status: str
    sharing_scope: str
    why_real: Any
    known_differences: Any = None
    property: CustomerPropertyView | PublicPropertySummary | None = None
    contact: dict[str, Any] | None = None
    created_at: datetime | None = None
    shared_at: datetime | None = None


def render_opportunity_for_scope(
    row: Mapping[str, Any],
    *,
    property_row: Mapping[str, Any] | None = None,
    offer_rows: list[Mapping[str, Any]] | None = None,
    contact: dict[str, Any] | None = None,
    confirmation_recorded: bool = False,
) -> CustomerOpportunityView:
    """R8.2 / R8.2a. The scope ladder, applied server-side.

    Each rung adds; none of them reaches the NEVER_SERIALIZED floor.
    """
    scope = SharingScope(str(row["sharing_scope"]))

    property_view: CustomerPropertyView | PublicPropertySummary | None = None
    if property_row is not None:
        if scope is SharingScope.SUMMARY_ONLY:
            # Type, location and area bands only — rendered through the PUBLIC
            # type, so the customer detail simply does not exist to leak.
            property_view = PublicPropertySummary.render(property_row, offers=[])
        else:
            property_view = CustomerPropertyView.render(property_row)

    released_contact: dict[str, Any] | None = None
    if scope is SharingScope.CONTACT_AFTER_CONFIRMATION and confirmation_recorded:
        # R8.3. The scope names a precondition; it is not its satisfaction.
        released_contact = contact

    return CustomerOpportunityView(
        opportunity_id=row["opportunity_id"],
        status=str(row["status"]),
        validity_status=str(row["validity_status"]),
        sharing_scope=scope.value,
        why_real=row.get("why_real"),
        known_differences=row.get("known_differences"),
        property=property_view,
        contact=released_contact,
        created_at=row.get("created_at"),
        shared_at=row.get("shared_at"),
    )
