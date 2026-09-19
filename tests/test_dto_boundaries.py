"""Public / Customer / Internal DTO boundaries.

Ref: ADR-06; API_CONTRACTS §3, §8; RFC-001 R9.1-R9.5, R8.2, R8.2a; K03, D02.

The allow-lists below are written out in full and deliberately not derived from
the models: a test that computes its expectation from the thing it is testing
passes whatever the thing does.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from turab.dto import (
    NEVER_SERIALIZED,
    Audience,
    CustomerPropertyView,
    CustomerRequestView,
    FieldLeak,
    PublicOfferSummary,
    PublicPropertySummary,
    assert_no_forbidden_fields,
    render_opportunity_for_scope,
)
from turab.dto.boundaries import CustomerPartyView

PUBLIC_PROPERTY_KEYS = {
    "property_id", "property_type", "canonical_location_id", "local_location_detail",
    "land_area_m2", "built_area_m2", "supply_mode", "availability", "offers",
}
PUBLIC_OFFER_KEYS = {
    "offer_id", "transaction_type", "asking_price_dzd", "price_visibility",
    "price_negotiable",
}
CUSTOMER_PROPERTY_KEYS = {
    "property_id", "property_type", "canonical_location_id", "local_location_detail",
    "land_area_m2", "built_area_m2", "current_availability",
    "availability_last_confirmed_at", "supply_mode", "version",
}
CUSTOMER_REQUEST_KEYS = {
    "request_id", "status", "transaction_intent", "intent", "payment",
    "desired_property_type", "primary_location_id", "budget_target_dzd",
    "budget_max_dzd", "budget_flexibility", "last_confirmed_at", "criteria",
}


def _row(session, sql, **params):
    return session.execute(text(sql), params).mappings().one()


# --- allow-lists -----------------------------------------------------------

@pytest.mark.parametrize(
    "model, expected",
    [
        (PublicPropertySummary, PUBLIC_PROPERTY_KEYS),
        (PublicOfferSummary, PUBLIC_OFFER_KEYS),
        (CustomerPropertyView, CUSTOMER_PROPERTY_KEYS),
        (CustomerRequestView, CUSTOMER_REQUEST_KEYS),
    ],
)
def test_dto_field_sets_are_exactly_the_allow_list(model, expected):
    """R9.5 / K03. A new column fails this before it can ship."""
    assert set(model.model_fields) == expected


def test_no_dto_declares_a_forbidden_field():
    for model in (
        PublicPropertySummary, PublicOfferSummary, CustomerPropertyView,
        CustomerRequestView, CustomerPartyView,
    ):
        leaks = set(model.model_fields) & NEVER_SERIALIZED
        assert not leaks, f"{model.__name__} declares {sorted(leaks)}"


def test_the_public_schema_matches_the_frozen_contract():
    """The allow-list is not ours to choose: the contract fixes it."""
    from turab.auth.contract import load_contract

    frozen = load_contract()["components"]["schemas"]
    assert set(frozen["PublicPropertySummary"]["properties"]) == PUBLIC_PROPERTY_KEYS
    assert set(frozen["PublicOfferSummary"]["properties"]) == PUBLIC_OFFER_KEYS
    assert set(frozen["CustomerPropertyView"]["properties"]) == CUSTOMER_PROPERTY_KEYS
    assert set(frozen["CustomerRequestView"]["properties"]) == CUSTOMER_REQUEST_KEYS


# --- rendering from real rows ---------------------------------------------

def test_public_render_from_a_real_property_row_leaks_nothing(session, ids):
    """K03. The source row carries management_mode, claim_status, creator."""
    row = _row(session, "SELECT * FROM turab.properties WHERE property_id=:p",
               p=ids.VILLA_SELF_MANAGED)
    assert "management_mode" in row and "created_by_account_id" in row
    dto = PublicPropertySummary.render(row).model_dump()
    assert set(dto) == PUBLIC_PROPERTY_KEYS
    assert_no_forbidden_fields(dto, Audience.PUBLIC)


def test_public_offer_never_carries_seller_expectation(session, ids):
    """D02. The source row has it; the rendered offer must not."""
    row = _row(session, "SELECT * FROM turab.property_offers WHERE offer_id=:o",
               o=ids.OFFER_OWNER_SALE)
    assert row["seller_expectation_dzd"] is not None
    dto = PublicOfferSummary.render(row).model_dump()
    assert "seller_expectation_dzd" not in dto
    assert_no_forbidden_fields(dto, Audience.PUBLIC)


def test_customer_request_render_leaks_nothing(session, ids):
    row = _row(session, "SELECT * FROM turab.requests WHERE request_id=:r",
               r=ids.REQ_AMINA)
    dto = CustomerRequestView.render(row).model_dump()
    assert set(dto) == CUSTOMER_REQUEST_KEYS
    assert_no_forbidden_fields(dto, Audience.CUSTOMER)


@pytest.mark.parametrize("visibility", ["ON_REQUEST", "PRIVATE"])
def test_price_is_redacted_when_visibility_is_not_public(session, ids, visibility):
    """R9.4 / S35. Redaction is independent of sharing scope."""
    session.execute(
        text("UPDATE turab.property_offers SET price_visibility=:v WHERE offer_id=:o"),
        {"v": visibility, "o": ids.OFFER_OWNER_SALE},
    )
    row = _row(session, "SELECT * FROM turab.property_offers WHERE offer_id=:o",
               o=ids.OFFER_OWNER_SALE)
    assert row["asking_price_dzd"] is not None
    assert PublicOfferSummary.render(row).asking_price_dzd is None


def test_public_price_is_shown_when_visibility_is_public(session, ids):
    """The redaction test above is only meaningful with this one beside it."""
    row = _row(session, "SELECT * FROM turab.property_offers WHERE offer_id=:o",
               o=ids.OFFER_OWNER_SALE)
    assert row["price_visibility"] == "PUBLIC"
    assert PublicOfferSummary.render(row).asking_price_dzd == row["asking_price_dzd"]


# --- extra fields are refused, not dropped --------------------------------

def test_constructing_a_dto_with_an_internal_field_is_an_error():
    """R9.1. Separate types, not filtered dictionaries."""
    with pytest.raises(Exception) as exc:
        PublicPropertySummary(
            property_id=uuid.uuid4(), property_type="LAND", supply_mode="PUBLIC",
            availability="UNKNOWN", seller_expectation_dzd=1,
        )
    assert "extra" in str(exc.value).lower() or "forbid" in str(exc.value).lower()


def test_a_new_column_does_not_silently_reach_the_public_dto(session, ids):
    """R9.5, the scenario the rule exists for (S37).

    Simulates a column being added to the table: the renderer must not pick it
    up, and the allow-list must still hold.
    """
    row = dict(_row(session, "SELECT * FROM turab.properties WHERE property_id=:p",
                    p=ids.VILLA_SELF_MANAGED))
    row["newly_added_internal_column"] = "secret"
    dto = PublicPropertySummary.render(row).model_dump()
    assert "newly_added_internal_column" not in dto
    assert set(dto) == PUBLIC_PROPERTY_KEYS


# --- the leak detector itself ---------------------------------------------

def test_the_leak_detector_catches_a_nested_leak():
    """A guard that never fires is not a guard."""
    payload = {"opportunity_id": "x", "property": {"seller_expectation_dzd": 1}}
    with pytest.raises(FieldLeak):
        assert_no_forbidden_fields(payload, Audience.CUSTOMER)


def test_the_leak_detector_catches_a_leak_inside_a_list():
    payload = {"offers": [{"offer_id": "x"}, {"consent_id": "leak"}]}
    with pytest.raises(FieldLeak):
        assert_no_forbidden_fields(payload, Audience.PUBLIC)


def test_internal_audience_is_exempt():
    payload = {"seller_expectation_dzd": 1, "permission_snapshot": {}}
    assert_no_forbidden_fields(payload, Audience.INTERNAL)


# --- sharing scope ladder (R8.2 / R8.2a) ----------------------------------

@pytest.fixture
def opportunity_rows(session, ids):
    prop = dict(_row(session, "SELECT * FROM turab.properties WHERE property_id=:p",
                     p=ids.CLAIMED_HOUSE))
    row = {
        "opportunity_id": uuid.uuid4(), "status": "SHARED",
        "validity_status": "VALID", "sharing_scope": "SUMMARY_ONLY",
        "why_real": {"reasons": ["budget", "location"]},
        "known_differences": [], "created_at": None, "shared_at": None,
    }
    return row, prop


def test_summary_only_withholds_property_detail(opportunity_rows):
    """S33."""
    row, prop = opportunity_rows
    view = render_opportunity_for_scope({**row, "sharing_scope": "SUMMARY_ONLY"},
                                        property_row=prop)
    assert set(view.property.model_dump()) == PUBLIC_PROPERTY_KEYS
    assert "version" not in view.property.model_dump()
    assert view.contact is None


def test_property_details_allowed_adds_the_customer_view(opportunity_rows):
    row, prop = opportunity_rows
    view = render_opportunity_for_scope(
        {**row, "sharing_scope": "PROPERTY_DETAILS_ALLOWED"}, property_row=prop
    )
    assert set(view.property.model_dump()) == CUSTOMER_PROPERTY_KEYS


def test_contact_is_withheld_without_a_recorded_confirmation(opportunity_rows):
    """S34 / R8.3. The scope names a precondition, not its satisfaction."""
    row, prop = opportunity_rows
    view = render_opportunity_for_scope(
        {**row, "sharing_scope": "CONTACT_AFTER_CONFIRMATION"},
        property_row=prop, contact={"phone": "+213661000002"},
        confirmation_recorded=False,
    )
    assert view.contact is None


def test_contact_is_released_after_a_recorded_confirmation(opportunity_rows):
    row, prop = opportunity_rows
    view = render_opportunity_for_scope(
        {**row, "sharing_scope": "CONTACT_AFTER_CONFIRMATION"},
        property_row=prop, contact={"phone": "+213661000002"},
        confirmation_recorded=True,
    )
    assert view.contact == {"phone": "+213661000002"}


@pytest.mark.parametrize(
    "scope",
    ["SUMMARY_ONLY", "PROPERTY_DETAILS_ALLOWED", "CONTACT_AFTER_CONFIRMATION"],
)
def test_no_scope_lifts_the_never_serialized_floor(opportunity_rows, scope):
    """S36a / R8.2a. The question a reviewer should be able to ask: does a
    higher scope add this field? For the floor the answer is always no."""
    row, prop = opportunity_rows
    view = render_opportunity_for_scope(
        {**row, "sharing_scope": scope}, property_row=prop,
        contact={"phone": "+213661000002"}, confirmation_recorded=True,
    )
    assert_no_forbidden_fields(view.model_dump(), Audience.CUSTOMER)
