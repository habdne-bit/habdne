"""The public property list — Slice 3, step 6, over HTTP on PostgreSQL.

Ref: the contract's `getPublicProperties` and `PublicPropertySummary`;
API_CONTRACTS v0.2 §3 "Public"; red-team D04; `services/public_listing.py`;
`docs/gate/SLICE_3_STEP6_DELIVERY.md`.

**Isolation.** HTTP tests commit, and the database is shared across the run.
So every test builds its own rows under a location created for it, and reads
the list filtered to that location. The rows are built with SQL: the
listing's inputs are the rows, whatever path wrote them. The consent binding
still passes through `enforce_consent_binding()`, so no fixture here is a row
the schema would refuse.

**What each exclusion test proves.** Each one starts from a world that IS
listed, `_listed_world`, and changes exactly one fact. A test that only
showed an absence could pass on an empty list.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from turab.auth.audit import AccessAuditor, RecordingAuditSink

PUB = "/public/properties"


@pytest.fixture
def sink():
    return RecordingAuditSink()


@pytest.fixture
def client(engine, sink):
    from turab.app import create_app

    app = create_app(engine=engine, auditor=AccessAuditor(sink))
    # A 500 fails with its cause (see test_input_hardening.py).
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# --- rows -------------------------------------------------------------------

def _one(engine, sql, **params):
    with engine.begin() as conn:
        return conn.execute(text(sql), params).scalar_one()


def _run(engine, sql, **params):
    with engine.begin() as conn:
        conn.execute(text(sql), params)


def _location(engine, parent=None):
    return _one(engine, """INSERT INTO turab.locations (code, canonical_ar, location_type,
                                                        parent_id)
                           VALUES (:c, 'موقع اختبار', 'AREA', :parent)
                           RETURNING location_id""",
                c=f"TEST-PUB-{uuid.uuid4().hex[:16]}", parent=parent)


def _property(engine, loc, *, supply="PUBLIC", availability="AVAILABLE",
              ptype="LAND", detail="قرب البئر القديمة", land=250.5, built=None):
    return _one(engine, """
        INSERT INTO turab.properties (property_type, canonical_location_id,
               local_location_detail, land_area_m2, built_area_m2, current_availability,
               supply_mode, management_mode, claim_status, created_by_account_id)
        VALUES (CAST(:t AS turab.property_type), :loc, :detail, :land, :built,
                CAST(:a AS turab.availability_status), CAST(:s AS turab.supply_mode),
                'ASSISTED', 'UNCLAIMED', 'f3000000-0000-4000-8000-000000000002')
        RETURNING property_id""",
        t=ptype, loc=loc, detail=detail, land=land, built=built, a=availability, s=supply)


def _offer(engine, pid, party, *, status="ACTIVE", tx="SALE", price=1_500_000,
           visibility="PUBLIC", negotiable="YES", expectation=None):
    return _one(engine, """
        INSERT INTO turab.property_offers (property_id, party_id, transaction_type, status,
               asking_price_dzd, price_negotiable, seller_expectation_dzd, price_visibility,
               created_by_account_id)
        VALUES (:p, :party, CAST(:tx AS turab.transaction_type),
                CAST(:st AS turab.offer_status), :price,
                CAST(:neg AS turab.price_negotiability), :exp,
                CAST(:vis AS turab.price_visibility), 'f3000000-0000-4000-8000-000000000002')
        RETURNING offer_id""",
        p=pid, party=party, tx=tx, st=status, price=price, neg=negotiable,
        exp=expectation, vis=visibility)


def _grant(engine, party, *, scope="PUBLIC_LISTING_ALLOWED", granted_at=None):
    return _one(engine, """
        INSERT INTO turab.consent_grants (party_id, scope, channel, consent_version,
                                          granted_at)
        VALUES (:party, CAST(:scope AS turab.consent_scope), 'PHONE_CONFIRMED',
                'consent-v1', :at)
        RETURNING consent_id""",
        party=party, scope=scope,
        at=granted_at or datetime.now(timezone.utc) - timedelta(days=1))


def _bind(engine, consent, *, offer=None, property_id=None,
          purpose="PUBLIC_LISTING_ALLOWED", bound_at=None):
    return _one(engine, """
        INSERT INTO turab.resource_consent_bindings (consent_id, purpose, offer_id,
                                                     property_id, bound_at)
        VALUES (:c, CAST(:purpose AS turab.consent_scope), :o, :p, :at)
        RETURNING consent_binding_id""",
        c=consent, purpose=purpose, o=offer, p=property_id,
        at=bound_at or datetime.now(timezone.utc) - timedelta(hours=1))


def _consented_offer(engine, pid, party, **offer):
    offer_id = _offer(engine, pid, party, **offer)
    consent = _grant(engine, party)
    binding = _bind(engine, consent, offer=offer_id)
    return offer_id, consent, binding


def _listed_world(engine, ids, **prop):
    """One PUBLIC property with one ACTIVE offer bound to a valid
    PUBLIC_LISTING_ALLOWED consent: all three conditions hold."""
    loc = _location(engine)
    pid = _property(engine, loc, **prop)
    offer, consent, binding = _consented_offer(engine, pid, ids.BRAHIM)
    return loc, pid, offer, consent, binding


def _get(client, **params):
    r = client.get(PUB, params={k: str(v) for k, v in params.items()})
    assert r.status_code == 200, r.text
    return r.json()


def _ids(client, loc, **params):
    return [item["property_id"] for item in _get(client, location_id=loc, **params)]


# --- the three conditions: all hold -> listed ---------------------------------

def test_a_public_property_with_an_active_consented_offer_is_listed(client, engine, ids):
    loc, pid, offer, _, _ = _listed_world(engine, ids)
    body = _get(client, location_id=loc)
    assert [item["property_id"] for item in body] == [str(pid)]
    assert [o["offer_id"] for o in body[0]["offers"]] == [str(offer)]


def test_the_fixture_world_lists_the_villa_with_its_one_consented_offer(client, engine,
                                                                        ids):
    """The seeded world: the villa is PUBLIC and has three ACTIVE offers, but
    only OFFER_OWNER_SALE is bound to a PUBLIC_LISTING_ALLOWED consent
    (dev_fixtures.sql). The broker's offer and the rent offer are not listed."""
    loc = _one(engine, "SELECT canonical_location_id FROM turab.properties "
                       "WHERE property_id = :p", p=ids.VILLA_SELF_MANAGED)
    villa = [i for i in _get(client, location_id=loc, page_size=100)
             if i["property_id"] == str(ids.VILLA_SELF_MANAGED)]
    assert len(villa) == 1
    assert [o["offer_id"] for o in villa[0]["offers"]] == [str(ids.OFFER_OWNER_SALE)]


# --- condition 1: supply_mode -------------------------------------------------

@pytest.mark.parametrize("supply", ["PRIVATE", "POTENTIAL"])
def test_a_property_that_is_not_public_is_absent(client, engine, ids, supply):
    loc, pid, *_ = _listed_world(engine, ids)
    assert _ids(client, loc) == [str(pid)]
    _run(engine, "UPDATE turab.properties SET supply_mode = CAST(:s AS turab.supply_mode) "
                 "WHERE property_id = :p", s=supply, p=pid)
    assert _ids(client, loc) == []


# --- condition 2: an ACTIVE offer ---------------------------------------------

@pytest.mark.parametrize("status", ["DRAFT", "PENDING_INFO", "PAUSED", "WITHDRAWN", "CLOSED"])
def test_a_consented_offer_that_is_not_active_does_not_list_its_property(client, engine,
                                                                         ids, status):
    loc, pid, offer, *_ = _listed_world(engine, ids)
    assert _ids(client, loc) == [str(pid)]
    _run(engine, "UPDATE turab.property_offers SET status = CAST(:s AS turab.offer_status) "
                 "WHERE offer_id = :o", s=status, o=offer)
    assert _ids(client, loc) == []


def test_d04_a_public_property_whose_offers_are_all_withdrawn_is_absent(client, engine,
                                                                       ids):
    """Red-team D04: supply_mode=PUBLIC alone is insufficient."""
    loc, pid, first, *_ = _listed_world(engine, ids)
    second, *_ = _consented_offer(engine, pid, ids.BRAHIM, tx="RENT", price=40_000)
    assert len(_get(client, location_id=loc)[0]["offers"]) == 2
    for offer, status in ((first, "WITHDRAWN"), (second, "CLOSED")):
        _run(engine, "UPDATE turab.property_offers SET status = CAST(:s AS "
                     "turab.offer_status) WHERE offer_id = :o", s=status, o=offer)
    assert _ids(client, loc) == []


def test_a_property_is_listed_by_its_own_offer_not_by_a_neighbours(client, engine, ids):
    loc, listed, *_ = _listed_world(engine, ids)
    bare = _property(engine, loc)
    assert _ids(client, loc) == [str(listed)]
    assert str(bare) not in _ids(client, loc)


# --- condition 3: a CURRENTLY VALID PUBLIC_LISTING_ALLOWED binding ON that offer

def test_an_active_offer_with_no_binding_does_not_list_its_property(client, engine, ids):
    loc = _location(engine)
    pid = _property(engine, loc)
    _offer(engine, pid, ids.BRAHIM)
    _grant(engine, ids.BRAHIM)  # a grant, but bound to nothing (ADR-04)
    assert _ids(client, loc) == []


def test_a_revoked_binding_does_not_list(client, engine, ids):
    loc, pid, _, _, binding = _listed_world(engine, ids)
    assert _ids(client, loc) == [str(pid)]
    _run(engine, "UPDATE turab.resource_consent_bindings SET revoked_at = now() "
                 "WHERE consent_binding_id = :b", b=binding)
    assert _ids(client, loc) == []


def test_revoking_the_grant_delists_although_the_binding_row_survives(client, engine, ids):
    """ADR-04: revocation leaves the binding in place, inert. The READ must
    see that the grant is no longer GRANTED."""
    from turab.services.consent import revoke_consent

    loc, pid, _, consent, binding = _listed_world(engine, ids)
    assert _ids(client, loc) == [str(pid)]
    with Session(bind=engine, future=True) as s:
        revoke_consent(s, consent_id=consent)
        s.commit()
    assert _one(engine, "SELECT revoked_at IS NULL FROM turab.resource_consent_bindings "
                        "WHERE consent_binding_id = :b", b=binding) is True
    assert _ids(client, loc) == []


def test_a_revocation_date_alone_delists_although_the_status_says_granted(client,
                                                                          engine, ids):
    """ADR-04: the "current grant/revocation state". The frozen schema allows
    a GRANTED row with `revoked_at` filled. Here ONLY that column changes, on a
    grant whose offer was listed. `revoke_consent` changes status and date
    together, so it cannot isolate this."""
    loc, pid, _, consent, _ = _listed_world(engine, ids)
    assert _ids(client, loc) == [str(pid)]
    _run(engine, "UPDATE turab.consent_grants SET revoked_at = now() "
                 "WHERE consent_id = :c", c=consent)
    assert _one(engine, "SELECT status::text FROM turab.consent_grants "
                        "WHERE consent_id = :c", c=consent) == "GRANTED"
    assert _ids(client, loc) == []


def test_a_revoked_status_alone_delists_although_no_date_is_recorded(client, engine,
                                                                    ids):
    """The mirror case: status REVOKED, `revoked_at` still NULL. The schema
    allows it too; only `g.status` refuses it."""
    loc, pid, _, consent, _ = _listed_world(engine, ids)
    assert _ids(client, loc) == [str(pid)]
    _run(engine, "UPDATE turab.consent_grants SET status = 'REVOKED' "
                 "WHERE consent_id = :c", c=consent)
    assert _one(engine, "SELECT revoked_at IS NULL FROM turab.consent_grants "
                        "WHERE consent_id = :c", c=consent) is True
    assert _ids(client, loc) == []


def test_a_binding_for_another_purpose_does_not_list(client, engine, ids):
    loc = _location(engine)
    pid = _property(engine, loc)
    offer = _offer(engine, pid, ids.BRAHIM)
    consent = _grant(engine, ids.BRAHIM, scope="PRIVATE_MATCHING_ONLY")
    _bind(engine, consent, offer=offer, purpose="PRIVATE_MATCHING_ONLY")
    assert _ids(client, loc) == []
    # ...and the same offer lists once a PUBLIC_LISTING_ALLOWED binding exists.
    _bind(engine, _grant(engine, ids.BRAHIM), offer=offer)
    assert _ids(client, loc) == [str(pid)]


def test_a_grant_whose_scope_changed_after_binding_does_not_list(client, engine, ids):
    """The trigger compares scope and purpose when the binding is WRITTEN. A
    grant changed afterwards (direct SQL here; no API path does it) is caught
    by the read's own `g.scope` clause."""
    loc, pid, _, consent, _ = _listed_world(engine, ids)
    assert _ids(client, loc) == [str(pid)]
    _run(engine, "UPDATE turab.consent_grants SET scope = 'PRIVATE_MATCHING_ONLY' "
                 "WHERE consent_id = :c", c=consent)
    assert _ids(client, loc) == []


def test_a_binding_whose_purpose_is_not_public_listing_does_not_list(client, engine, ids):
    """The mirror case: a PRIVATE_MATCHING_ONLY binding whose grant was later
    re-scoped to PUBLIC_LISTING_ALLOWED. `b.purpose` is what refuses it."""
    loc = _location(engine)
    pid = _property(engine, loc)
    offer = _offer(engine, pid, ids.BRAHIM)
    consent = _grant(engine, ids.BRAHIM, scope="PRIVATE_MATCHING_ONLY")
    _bind(engine, consent, offer=offer, purpose="PRIVATE_MATCHING_ONLY")
    _run(engine, "UPDATE turab.consent_grants SET scope = 'PUBLIC_LISTING_ALLOWED' "
                 "WHERE consent_id = :c", c=consent)
    assert _ids(client, loc) == []


def test_a_consent_bound_to_the_property_rather_than_the_offer_does_not_list(client,
                                                                            engine, ids):
    """Plan §4.4: the public list's consent binds to the OFFER. A
    property-scoped PUBLIC_LISTING_ALLOWED binding is not that consent. The
    trigger requires an active relation for a property binding, so one is
    inserted as fixture; it grants nothing (R4.5)."""
    loc = _location(engine)
    pid = _property(engine, loc)
    _offer(engine, pid, ids.BRAHIM)
    _run(engine, """INSERT INTO turab.party_property_relations
                          (party_id, property_id, relation_code, verification_level,
                           valid_from)
                    VALUES (:party, :p, 'OWNER_DECLARED', 'DECLARED',
                            now() - interval '1 day')""", party=ids.BRAHIM, p=pid)
    _bind(engine, _grant(engine, ids.BRAHIM), property_id=pid)
    assert _ids(client, loc) == []


def test_a_consent_from_a_party_other_than_the_offers_does_not_list(client, engine, ids):
    """The trigger checks the party when the binding is WRITTEN; the list
    checks it again when it READS. The offer's party is changed directly
    here, since no API path changes it."""
    loc, pid, offer, *_ = _listed_world(engine, ids)
    assert _ids(client, loc) == [str(pid)]
    _run(engine, "UPDATE turab.property_offers SET party_id = :party WHERE offer_id = :o",
         party=ids.AMINA, o=offer)
    assert _ids(client, loc) == []


def test_a_grant_that_starts_in_the_future_does_not_list_yet(client, engine, ids):
    loc = _location(engine)
    pid = _property(engine, loc)
    offer = _offer(engine, pid, ids.BRAHIM)
    later = datetime.now(timezone.utc) + timedelta(days=2)
    _bind(engine, _grant(engine, ids.BRAHIM, granted_at=later), offer=offer)
    assert _ids(client, loc) == []


def test_a_binding_that_starts_in_the_future_does_not_list_yet(client, engine, ids):
    loc = _location(engine)
    pid = _property(engine, loc)
    offer = _offer(engine, pid, ids.BRAHIM)
    later = datetime.now(timezone.utc) + timedelta(days=2)
    _bind(engine, _grant(engine, ids.BRAHIM), offer=offer, bound_at=later)
    assert _ids(client, loc) == []


# --- which offers are projected ------------------------------------------------

def test_only_active_consented_offers_are_projected(client, engine, ids):
    """A party that did not consent is not listed, even on a listed property."""
    from turab.services.consent import revoke_consent

    loc, pid, listed, *_ = _listed_world(engine, ids)
    _offer(engine, pid, ids.AGENCY, price=2_000_000)                     # no consent
    _consented_offer(engine, pid, ids.BRAHIM, status="PAUSED")           # not active
    _, revoked, _ = _consented_offer(engine, pid, ids.BRAHIM, tx="RENT")  # revoked below
    with Session(bind=engine, future=True) as s:
        revoke_consent(s, consent_id=revoked)
        s.commit()
    body = _get(client, location_id=loc)
    assert [o["offer_id"] for o in body[0]["offers"]] == [str(listed)]


def test_projected_offers_are_in_creation_order(client, engine, ids):
    loc, pid, first, *_ = _listed_world(engine, ids)
    second, *_ = _consented_offer(engine, pid, ids.BRAHIM, tx="RENT", price=50_000)
    body = _get(client, location_id=loc)
    assert [o["offer_id"] for o in body[0]["offers"]] == [str(first), str(second)]


# --- publication rule R6-P1, and the alias exclusion ---------------------------

@pytest.mark.parametrize("availability", ["TEMPORARILY_UNAVAILABLE", "UNAVAILABLE"])
def test_rule_r6_p1_a_temporarily_or_wholly_unavailable_property_is_not_published(
        client, engine, ids, availability):
    """Our precautionary rule R6-P1, accepted for now. It is NOT forced by the
    response schema: `availability` is optional there, so the property could
    have been listed without the field."""
    loc, pid, *_ = _listed_world(engine, ids, availability=availability)
    assert _ids(client, loc) == []


@pytest.mark.parametrize("availability", ["AVAILABLE", "POTENTIALLY_AVAILABLE",
                                          "UNDER_DISCUSSION", "NEEDS_CONFIRMATION",
                                          "UNKNOWN"])
def test_each_availability_the_public_schema_declares_is_listed_as_is(client, engine,
                                                                      ids, availability):
    loc, pid, *_ = _listed_world(engine, ids, availability=availability)
    assert _get(client, location_id=loc)[0]["availability"] == availability


def test_an_alias_is_not_listed_and_its_offers_are_not_folded_in(client, engine, ids):
    """G3-13, stated not decided: a record known to duplicate another is not a
    second public property, and its offers are not moved to the canonical."""
    loc = _location(engine)
    canonical = _property(engine, loc)
    alias = _property(engine, loc)
    own, *_ = _consented_offer(engine, canonical, ids.BRAHIM)
    _consented_offer(engine, alias, ids.BRAHIM, tx="RENT")
    assert sorted(_ids(client, loc)) == sorted([str(canonical), str(alias)])
    candidate = _one(engine, """INSERT INTO turab.property_identity_candidates
                                       (property_a_id, property_b_id, review_status)
                                VALUES (:a, :b, 'PENDING_REVIEW')
                                RETURNING identity_candidate_id""", a=alias, b=canonical)
    _run(engine, """INSERT INTO turab.property_identity_aliases
                          (alias_property_id, canonical_property_id,
                           source_identity_candidate_id, resolved_by_account_id)
                    VALUES (:alias, :canon, :c, 'f3000000-0000-4000-8000-000000000002')""",
         alias=alias, canon=canonical, c=candidate)
    body = _get(client, location_id=loc)
    assert [i["property_id"] for i in body] == [str(canonical)]
    assert [o["offer_id"] for o in body[0]["offers"]] == [str(own)]


# --- the projection -------------------------------------------------------------

def _contract_schemas():
    from turab.auth.contract import load_contract

    return load_contract()["components"]["schemas"]


def _conforms(value, schema, schemas, path="$"):
    """The JSON Schema constructs these two schemas use, and no more:
    `$ref`, `anyOf`, `type` (one or a list), `format: uuid`, `enum`,
    `properties`, `required`, `additionalProperties: false`, `items`."""
    if "$ref" in schema:
        return _conforms(value, schemas[schema["$ref"].rsplit("/", 1)[1]], schemas, path)
    if "anyOf" in schema:
        errors = [_conforms(value, s, schemas, path) for s in schema["anyOf"]]
        return [] if any(not e for e in errors) else [f"{path}: matches no anyOf branch"]
    types = schema.get("type")
    types = [types] if isinstance(types, str) else (types or [])
    checks = {"string": lambda v: isinstance(v, str),
              "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
              "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
              "array": lambda v: isinstance(v, list),
              "object": lambda v: isinstance(v, dict),
              "null": lambda v: v is None}
    if types and not any(checks[t](value) for t in types):
        return [f"{path}: {type(value).__name__} is not {types}"]
    out = []
    if "enum" in schema and value not in schema["enum"]:
        out.append(f"{path}: not in the declared enum")
    if schema.get("format") == "uuid" and isinstance(value, str):
        uuid.UUID(value)
    if isinstance(value, dict):
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            out += [f"{path}.{k}: not declared" for k in value if k not in props]
        out += [f"{path}.{k}: required, missing" for k in schema.get("required", [])
                if k not in value]
        for k, v in value.items():
            if k in props:
                out += _conforms(v, props[k], schemas, f"{path}.{k}")
    if isinstance(value, list) and "items" in schema:
        for i, v in enumerate(value):
            out += _conforms(v, schema["items"], schemas, f"{path}[{i}]")
    return out


def test_every_item_conforms_to_the_contracts_public_property_summary(client, engine, ids):
    loc, pid, *_ = _listed_world(engine, ids, built=120.25)
    _consented_offer(engine, pid, ids.BRAHIM, tx="RENT", visibility="ON_REQUEST",
                     negotiable="UNKNOWN")
    _listed_world(engine, ids, availability="NEEDS_CONFIRMATION", land=None)
    schemas = _contract_schemas()
    body = _get(client, page_size=100)
    assert body, "nothing listed; the check would be vacuous"
    problems = [p for item in body
                for p in _conforms(item, schemas["PublicPropertySummary"], schemas)]
    assert problems == []


def test_the_conformance_check_is_not_vacuous():
    schemas = _contract_schemas()
    bad = {"property_id": str(uuid.uuid4()), "property_type": "LAND",
           "supply_mode": "PUBLIC", "land_area_m2": "250.50",
           "availability": "UNAVAILABLE", "management_mode": "ASSISTED"}
    problems = _conforms(bad, schemas["PublicPropertySummary"], schemas)
    assert any("land_area_m2" in p for p in problems)
    assert any("availability" in p for p in problems)
    assert any("management_mode" in p for p in problems)


def test_areas_are_json_numbers_equal_to_the_column(client, engine, ids):
    """`Decimal` serialized to a JSON string before this step; the contract
    declares `number`."""
    loc, pid, *_ = _listed_world(engine, ids, land=9999999999.99, built=0.01)
    item = _get(client, location_id=loc)[0]
    assert item["land_area_m2"] == 9999999999.99 and isinstance(item["land_area_m2"], float)
    assert item["built_area_m2"] == 0.01 and isinstance(item["built_area_m2"], float)


def test_seller_expectation_never_appears_in_the_public_list(client, engine, ids):
    """Mandatory test 2 (plan §6.1), its public half over HTTP. The value is
    distinctive, so the RAW body is searched for it, not only the keys."""
    loc = _location(engine)
    pid = _property(engine, loc)
    _consented_offer(engine, pid, ids.BRAHIM, expectation=987_654_321)
    r = client.get(PUB, params={"location_id": str(loc)})
    assert r.status_code == 200 and len(r.json()) == 1
    assert "seller_expectation_dzd" not in r.text
    assert "987654321" not in r.text


def test_no_field_below_the_r9_2_floor_is_rendered(client, engine, ids):
    from turab.dto.boundaries import NEVER_SERIALIZED

    loc, *_ = _listed_world(engine, ids)
    body = _get(client, location_id=loc)

    def keys(node):
        if isinstance(node, dict):
            for k, v in node.items():
                yield k
                yield from keys(v)
        elif isinstance(node, list):
            for v in node:
                yield from keys(v)

    assert set(keys(body)) & NEVER_SERIALIZED == set()
    assert {"management_mode", "claim_status", "created_by_account_id"} & set(keys(body)) \
        == set()


@pytest.mark.parametrize("visibility", ["ON_REQUEST", "PRIVATE"])
def test_the_price_is_redacted_unless_its_visibility_is_public(client, engine, ids,
                                                               visibility):
    loc = _location(engine)
    pid = _property(engine, loc)
    _consented_offer(engine, pid, ids.BRAHIM, visibility=visibility, price=3_300_000)
    offer = _get(client, location_id=loc)[0]["offers"][0]
    assert offer["asking_price_dzd"] is None
    assert offer["price_visibility"] == visibility


def test_the_price_is_shown_when_its_visibility_is_public(client, engine, ids):
    loc = _location(engine)
    pid = _property(engine, loc)
    _consented_offer(engine, pid, ids.BRAHIM, price=3_300_000)
    assert _get(client, location_id=loc)[0]["offers"][0]["asking_price_dzd"] == 3_300_000


def test_the_local_location_detail_is_withheld_by_decision_g3_12(client, engine, ids):
    """Approved decision G3-12 (Developer Spec §23 invariant 11): the
    free-text detail is withheld from the public list, at every scope; the
    numeric areas are kept (test_areas_are_json_numbers_equal_to_the_column)."""
    loc = _location(engine)
    pid = _property(engine, loc, detail="خلف مسجد الحي، الباب الأزرق")
    offer, *_ = _consented_offer(engine, pid, ids.BRAHIM)
    _run(engine, "UPDATE turab.property_offers SET permission_scope = "
                 "'PROPERTY_DETAILS_ALLOWED' WHERE offer_id = :o", o=offer)
    r = client.get(PUB, params={"location_id": str(loc)})
    assert "local_location_detail" not in r.json()[0]
    assert "الباب الأزرق" not in r.text


# --- filters -----------------------------------------------------------------------

def test_the_property_type_filter(client, engine, ids):
    loc, land, *_ = _listed_world(engine, ids, ptype="LAND")
    flat = _property(engine, loc, ptype="APARTMENT", land=None, built=80)
    _consented_offer(engine, flat, ids.BRAHIM)
    assert _ids(client, loc, property_type="LAND") == [str(land)]
    assert _ids(client, loc, property_type="APARTMENT") == [str(flat)]


@pytest.mark.parametrize("value", ["NOT_A_TYPE", "otp", "SELECT 1", "turab.x"])
def test_a_property_type_naming_no_type_matches_nothing(client, engine, ids, value):
    """The contract types it as a plain string, with no enum: an empty page,
    not a 422 (that would narrow the contract) and not a 500 (the enum cast
    it avoids)."""
    loc, *_ = _listed_world(engine, ids)
    r = client.get(PUB, params={"location_id": str(loc), "property_type": value})
    assert r.status_code == 200 and r.json() == []


def test_the_location_filter_matches_the_location_and_everything_beneath_it(client,
                                                                          engine, ids):
    """G3-14: a property recorded at any depth under the requested location is
    returned; a sibling branch's is not; a location's own property is."""
    wilaya = _location(engine)
    commune = _location(engine, parent=wilaya)
    ksar = _location(engine, parent=commune)
    sibling = _location(engine, parent=wilaya)
    at = {}
    for name, loc in (("wilaya", wilaya), ("commune", commune), ("ksar", ksar),
                      ("sibling", sibling)):
        at[name] = _property(engine, loc)
        _consented_offer(engine, at[name], ids.BRAHIM)
    def listed(loc):
        return set(_ids(client, loc, page_size=100))
    assert listed(wilaya) == {str(at[n]) for n in ("wilaya", "commune", "ksar", "sibling")}
    assert listed(commune) == {str(at["commune"]), str(at["ksar"])}
    assert listed(ksar) == {str(at["ksar"])}
    assert listed(sibling) == {str(at["sibling"])}


def test_the_location_filter_ends_on_a_cycle_in_the_hierarchy(client, engine, ids):
    """The schema does not forbid `parent_id` cycles. The recursion uses UNION,
    which discards rows already produced, so it ends; the answer is the cycle's
    members, each once."""
    a = _location(engine)
    b = _location(engine, parent=a)
    _run(engine, "UPDATE turab.locations SET parent_id = :b WHERE location_id = :a",
         a=a, b=b)
    pa, pb = _property(engine, a), _property(engine, b)
    for pid in (pa, pb):
        _consented_offer(engine, pid, ids.BRAHIM)
    assert sorted(_ids(client, a)) == sorted([str(pa), str(pb)])


def test_an_unknown_location_matches_nothing(client, engine, ids):
    _listed_world(engine, ids)
    assert _get(client, location_id=uuid.uuid4()) == []


@pytest.mark.parametrize("query", [
    {"location_id": "not-a-uuid"}, {"page": "0"}, {"page": "-1"}, {"page": "abc"},
    {"page": "1.5"}, {"page_size": "0"}, {"page_size": "101"}, {"page_size": "x"},
])
def test_a_malformed_query_is_a_typed_422(client, query):
    r = client.get(PUB, params=query)
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "VALIDATION_FAILED"


# --- paging ------------------------------------------------------------------------

def test_pages_are_newest_first_disjoint_and_complete(client, engine, ids):
    loc = _location(engine)
    made = []
    for _ in range(5):
        pid = _property(engine, loc)
        _consented_offer(engine, pid, ids.BRAHIM)
        made.append(pid)
    expected = [str(r) for r in _ordered(engine, made)]
    pages = [_ids(client, loc, page=n, page_size=2) for n in (1, 2, 3, 4)]
    assert [len(p) for p in pages] == [2, 2, 1, 0]
    assert [pid for p in pages for pid in p] == expected


def _ordered(engine, pids):
    with engine.connect() as conn:
        return conn.execute(text("""SELECT property_id FROM turab.properties
                                     WHERE property_id = ANY(:p)
                                     ORDER BY created_at DESC, property_id"""),
                            {"p": pids}).scalars().all()


def test_the_default_page_size_is_the_contracts_25(client, engine, ids):
    loc = _location(engine)
    for _ in range(26):
        pid = _property(engine, loc)
        _consented_offer(engine, pid, ids.BRAHIM)
    assert len(_ids(client, loc)) == 25
    assert len(_ids(client, loc, page=2)) == 1


# --- unauthenticated, unaudited, fail-closed ---------------------------------------

@pytest.mark.parametrize("authorization", [None, "Bearer not-a-uuid",
                                           "Bearer f3000000-0000-4000-8000-000000000099"])
def test_no_credential_is_needed_or_read(client, engine, ids, authorization):
    """`security: []`. A header sent anyway is not read, so a malformed or
    unknown bearer changes nothing."""
    loc, pid, *_ = _listed_world(engine, ids)
    headers = {"Authorization": authorization} if authorization else {}
    r = client.get(PUB, params={"location_id": str(loc)}, headers=headers)
    assert r.status_code == 200, r.text
    assert [i["property_id"] for i in r.json()] == [str(pid)]


def test_the_public_list_records_no_access_audit(client, engine, ids, sink):
    """R6.3: `getPublicProperties` is in NON_AUDITED_READ_OPERATIONS."""
    loc, *_ = _listed_world(engine, ids)
    sink.clear()
    _get(client, location_id=loc)
    assert sink.records == []


def test_public_reads_refuse_an_operation_that_is_not_public(engine):
    """Fail closed: were `getPublicProperties` ever not public, the route would
    be refused with a typed denial, not reach a role check with no subject."""
    from turab.auth.contract import build_policy_table
    from turab.auth.policy import DenyReason
    from turab.services.public_listing import PublicReads

    reads = PublicReads(session=None, policies=build_policy_table())  # type: ignore[arg-type]
    assert reads.authorize("getPublicProperties").allowed
    for operation in ("getPropertiesPropertyId", "postProperties", "noSuchOperation"):
        decision = reads.authorize(operation)
        assert not decision.allowed and decision.reason is DenyReason.NO_POLICY


def test_the_listable_availabilities_are_the_contracts():
    from turab.dto.boundaries import PUBLIC_AVAILABILITY
    from turab.services.public_listing import LISTABLE_AVAILABILITY

    declared = set(_contract_schemas()["PublicPropertySummary"]["properties"]
                   ["availability"]["enum"])
    assert set(LISTABLE_AVAILABILITY) == declared == PUBLIC_AVAILABILITY


def test_the_list_is_read_in_one_statement(engine):
    """One statement, one snapshot: the page and its offers cannot disagree
    under Read Committed (services/public_listing.py, `_PAGE`)."""
    from turab.services.public_listing import list_public_properties

    class Recording:
        def __init__(self, session):
            self.session, self.statements = session, []

        def execute(self, statement, *a, **k):
            self.statements.append(str(statement))
            return self.session.execute(statement, *a, **k)

    with Session(bind=engine, future=True) as s:
        recording = Recording(s)
        listed = list_public_properties(recording, location_id=None, property_type=None,
                                        page=1, page_size=100)
        s.rollback()
    assert listed, "nothing listed; one statement for an empty page proves little"
    assert len(recording.statements) == 1


# --- the DTO on its own: what the SQL filters in front of it cannot show ------

def _row(**over):
    row = {"property_id": uuid.uuid4(), "property_type": "LAND",
           "canonical_location_id": None, "local_location_detail": "قرب البئر",
           "land_area_m2": None, "built_area_m2": None, "supply_mode": "PUBLIC",
           "current_availability": "AVAILABLE"}
    row.update(over)
    return row


@pytest.mark.parametrize("availability", ["TEMPORARILY_UNAVAILABLE", "UNAVAILABLE"])
def test_the_dto_never_renders_an_availability_the_contract_does_not_declare(availability):
    """The list's SQL excludes these properties, so over HTTP this rule is
    masked. The DTO is also the SUMMARY_ONLY rung of an opportunity
    (`render_opportunity_for_scope`), where nothing filters in front of it."""
    from turab.dto.boundaries import PublicPropertySummary

    body = PublicPropertySummary.render(_row(current_availability=availability)).to_json()
    assert "availability" not in body


def test_the_dto_renders_areas_as_numbers_and_withholds_the_local_detail():
    from decimal import Decimal

    from turab.dto.boundaries import PublicPropertySummary

    body = PublicPropertySummary.render(
        _row(land_area_m2=Decimal("220.00"), built_area_m2=Decimal("9999999999.99"))
    ).to_json()
    assert body["land_area_m2"] == 220.0 and isinstance(body["land_area_m2"], float)
    assert body["built_area_m2"] == 9999999999.99
    assert "local_location_detail" not in body
