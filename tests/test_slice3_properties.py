"""Slice 3, step 1 — the physical PROPERTY over HTTP.

Ref: IMPLEMENTATION_SLICES_v0.2.md Slice 3; `docs/gate/SLICE_3_PLAN.md` §1.1,
§3.3, §5; RFC-001 §4.4 (R4.1-R4.3), §4.2 (R4.5), R4.9, R4.12.

The scenarios named `test_s1*` are RFC-001's own matrix (its lines 590-606),
restricted to PROPERTY, and they carry the RFC's verdicts rather than ours.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from turab.auth.audit import AccessAuditor, RecordingAuditSink


@pytest.fixture
def sink():
    return RecordingAuditSink()


@pytest.fixture
def client(engine, sink):
    from turab.app import create_app

    app = create_app(engine=engine, auditor=AccessAuditor(sink))
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(autouse=True)
def clean(engine):
    """Only the idempotency keys are cleared — `prevent_core_delete()` forbids
    hard-deleting a property, so every assertion is relative or read by id."""
    yield
    with Session(bind=engine, future=True) as s:
        s.execute(text("DELETE FROM turab.idempotency_records"))
        s.commit()


def cust(ids):
    return {"Authorization": f"Bearer {ids.ACC_AMINA}"}


def staff(ids):
    return {"Authorization": f"Bearer {ids.ACC_OPERATOR}"}


def body(**over):
    base = {
        "property_type": "APARTMENT",
        "supply_mode": "PUBLIC",
        "management_mode": "SELF_MANAGED",
        "claim_status": "CLAIMED",
        "local_location_detail": "s3-prop",
    }
    base.update(over)
    return base


def _new_property(client, ids, tag, *, who=None, **over):
    r = client.post("/properties", json=body(**over),
                    headers={**(who or cust(ids)), "Idempotency-Key": f"s3-{tag}"})
    assert r.status_code == 201, r.text
    return r.json()["property_id"]


# --- creation --------------------------------------------------------------

def test_a_customer_creates_a_self_managed_property(client, ids):
    r = client.post("/properties", json=body(),
                    headers={**cust(ids), "Idempotency-Key": "s3-create"})
    assert r.status_code == 201, r.text
    got = r.json()
    assert got["property_type"] == "APARTMENT"
    assert got["supply_mode"] == "PUBLIC"
    assert got["management_mode"] == "SELF_MANAGED"
    assert got["claim_status"] == "CLAIMED"
    assert got["version"] == 1


def test_a_customer_cannot_create_an_assisted_property(client, ids):
    """ASSISTED means staff operate it on someone's behalf; it is UNCLAIMED
    until claimed. A customer creating one would be creating a record they do
    not own and cannot read back."""
    r = client.post("/properties",
                    json=body(management_mode="ASSISTED", claim_status="UNCLAIMED"),
                    headers={**cust(ids), "Idempotency-Key": "s3-assisted-cust"})
    assert r.status_code == 422, r.text


def test_staff_create_an_assisted_unclaimed_property(client, ids):
    r = client.post("/properties",
                    json=body(management_mode="ASSISTED", claim_status="UNCLAIMED"),
                    headers={**staff(ids), "Idempotency-Key": "s3-assisted-staff"})
    assert r.status_code == 201, r.text
    assert r.json()["claim_status"] == "UNCLAIMED"


def test_an_incoherent_management_pair_is_refused(client, ids):
    """The frozen schema has the same CHECK. Both are kept: the typed error
    names the rule, the CHECK makes it true of data written by anything."""
    r = client.post("/properties",
                    json=body(management_mode="ASSISTED", claim_status="CLAIMED"),
                    headers={**staff(ids), "Idempotency-Key": "s3-bad-pair"})
    assert r.status_code == 422, r.text
    assert "ASSISTED" in r.json()["detail"]


def test_creation_writes_no_party_property_relation(client, ids, engine):
    """G3-6. A relation must never be inferred from an act of creation.

    This is the test that would fail first if someone later 'helpfully' linked
    the creating party to the property.
    """
    with Session(bind=engine, future=True) as s:
        before = s.execute(
            text("SELECT count(*) FROM turab.party_property_relations")
        ).scalar_one()
    _new_property(client, ids, "no-relation")
    with Session(bind=engine, future=True) as s:
        after = s.execute(
            text("SELECT count(*) FROM turab.party_property_relations")
        ).scalar_one()
    assert after == before, "creating a property must not write a relation row"


def test_creation_records_its_provenance(client, ids, engine):
    """Read from the DATABASE, not from the response.

    The contracted representations are closed schemas, so provenance is not in
    them — exposing it needs a contract addition. What must still be true is
    that the rows are WRITTEN, and that is what this asserts.
    """
    pid = _new_property(client, ids, "prov")
    with Session(bind=engine, future=True) as s:
        rows = s.execute(
            text("""SELECT c.attribute_code, c.extracted_by AS channel
                      FROM turab.claims c WHERE c.property_id = :p"""),
            {"p": uuid.UUID(pid)},
        ).mappings().all()
    codes = {r["attribute_code"] for r in rows}
    assert "property_type" in codes and "supply_mode" in codes
    assert {r["channel"] for r in rows} == {"SELF_SERVICE"}


def test_the_response_carries_no_undeclared_key(client, ids):
    """`Property` and `OperatorPropertyView` are `allOf [PropertyCreate, ...]`
    and `PropertyCreate` is closed, so there is no additive space.

    An earlier version added `provenance` to the staff read and described it as
    additive. This test is what stops that returning.
    """
    allowed = {
        "property_id", "property_type", "canonical_location_id",
        "local_location_detail", "land_area_m2", "built_area_m2",
        "current_availability", "supply_mode", "management_mode",
        "claim_status", "availability_last_confirmed_at", "version",
        "created_at", "updated_at",
    }
    pid = _new_property(client, ids, "closed")
    for r in (client.get(f"/properties/{pid}", headers=staff(ids)),
              client.get(f"/me/properties/{pid}", headers=cust(ids))):
        assert r.status_code == 200, r.text
        extra = set(r.json()) - allowed
        assert not extra, f"undeclared keys in the response: {sorted(extra)}"


@pytest.mark.parametrize("field", ["local_location_detail", "land_area_m2",
                                   "built_area_m2", "current_availability"])
def test_create_refuses_an_explicit_null_for_an_omissible_field(client, ids, field):
    """Absent is not `null`. Only `canonical_location_id` is declared
    `anyOf [uuid, null]`; these four are plain typed properties that may be
    omitted and never sent as null."""
    r = client.post("/properties", json=body(**{field: None}),
                    headers={**cust(ids), "Idempotency-Key": f"s3-null-{field}"})
    assert r.status_code == 422, r.text


def test_create_accepts_a_null_canonical_location(client, ids):
    """The one field where null IS declared, so the refusal above is scoped
    rather than a blanket rejection of null."""
    r = client.post("/properties", json=body(canonical_location_id=None),
                    headers={**cust(ids), "Idempotency-Key": "s3-null-loc"})
    assert r.status_code == 201, r.text


def test_an_omitted_optional_field_is_absent_from_the_response(client, ids):
    """Not `null` — absent. `null` is not in the declared type of these
    fields, so emitting it would be as wrong as accepting it."""
    r = client.post("/properties",
                    json={"property_type": "LAND", "supply_mode": "PUBLIC",
                          "management_mode": "SELF_MANAGED", "claim_status": "CLAIMED"},
                    headers={**cust(ids), "Idempotency-Key": "s3-omitted"})
    assert r.status_code == 201, r.text
    got = r.json()
    assert "land_area_m2" not in got and "built_area_m2" not in got
    assert "local_location_detail" not in got
    # declared nullable, so these two ARE present and may be null
    assert "canonical_location_id" in got
    assert "availability_last_confirmed_at" in got


def test_a_property_claim_is_attributed_to_no_party(client, ids, engine):
    """A property has no `party_id`, so its observation records none.

    Inventing one would be the relation G3-6 forbids inferring, written in a
    different table.
    """
    pid = _new_property(client, ids, "noparty")
    with Session(bind=engine, future=True) as s:
        parties = s.execute(
            text("""SELECT DISTINCT o.party_id
                      FROM turab.claims c
                      JOIN turab.observations o USING (observation_id)
                     WHERE c.property_id = :p"""),
            {"p": uuid.UUID(pid)},
        ).scalars().all()
    assert parties == [None], parties


# --- patch: what it may and may not change ---------------------------------

def test_a_patch_changes_the_physical_description(client, ids):
    pid = _new_property(client, ids, "patch")
    version = client.get(f"/properties/{pid}", headers=staff(ids)).json()["version"]
    r = client.patch(f"/properties/{pid}", json={"built_area_m2": 91.5},
                     headers={**cust(ids), "If-Match-Version": str(version)})
    assert r.status_code == 200, r.text
    assert r.json()["built_area_m2"] == 91.5
    assert r.json()["version"] == version + 1


def test_patch_cannot_change_availability(client, ids):
    """Ratified G3-3. `PropertyPatch` declares five fields and
    `additionalProperties: false`; availability is not one of them, so this is
    the contract refusing it, not us declining to support it."""
    pid = _new_property(client, ids, "avail")
    version = client.get(f"/properties/{pid}", headers=staff(ids)).json()["version"]
    r = client.patch(f"/properties/{pid}",
                     json={"current_availability": "UNAVAILABLE"},
                     headers={**cust(ids), "If-Match-Version": str(version)})
    assert r.status_code == 422, r.text
    after = client.get(f"/properties/{pid}", headers=staff(ids)).json()
    assert after["current_availability"] == "UNKNOWN"
    assert after["version"] == version, "a refused patch must not bump the version"


@pytest.mark.parametrize("field", ["supply_mode", "management_mode", "claim_status"])
def test_patch_cannot_change_a_create_only_field(client, ids, field):
    pid = _new_property(client, ids, f"create-only-{field}")
    version = client.get(f"/properties/{pid}", headers=staff(ids)).json()["version"]
    r = client.patch(f"/properties/{pid}", json={field: "PUBLIC"},
                     headers={**cust(ids), "If-Match-Version": str(version)})
    assert r.status_code == 422, r.text


def test_the_service_refuses_availability_even_without_the_model(session, ids):
    """The model is the first lock; `PATCHABLE` is the second.

    A caller reaching the service directly must be refused too, and the message
    must say where availability IS changed rather than only that it is unknown.
    """
    from turab.services import properties as property_service
    from turab.services.provenance import UpdateChannel

    row = property_service.create_property(
        session, property_type="LAND", management_mode="ASSISTED",
        claim_status="UNCLAIMED", supply_mode="PRIVATE",
        created_by_account_id=ids.ACC_OPERATOR,
    )
    with pytest.raises(property_service.NotPatchable) as caught:
        property_service.patch_property(
            session, property_id=row["property_id"],
            changes={"current_availability": "UNAVAILABLE"},
            recorded_by_account_id=ids.ACC_OPERATOR,
            channel=UpdateChannel.STAFF_RECORDED,
        )
    assert "reconfirm" in str(caught.value)


def test_an_empty_free_text_field_is_accepted(client, ids):
    """R-S2-05a, on this slice's endpoint: an empty string is not a null."""
    pid = _new_property(client, ids, "empty")
    version = client.get(f"/properties/{pid}", headers=staff(ids)).json()["version"]
    r = client.patch(f"/properties/{pid}", json={"local_location_detail": ""},
                     headers={**cust(ids), "If-Match-Version": str(version)})
    assert r.status_code == 200, r.text
    assert r.json()["local_location_detail"] == ""


def test_null_is_refused_for_the_non_nullable_field(client, ids):
    pid = _new_property(client, ids, "nullpt")
    version = client.get(f"/properties/{pid}", headers=staff(ids)).json()["version"]
    r = client.patch(f"/properties/{pid}", json={"property_type": None},
                     headers={**cust(ids), "If-Match-Version": str(version)})
    assert r.status_code == 422, r.text


def test_a_patch_without_a_version_is_refused(client, ids):
    pid = _new_property(client, ids, "noversion")
    r = client.patch(f"/properties/{pid}", json={"built_area_m2": 50},
                     headers=cust(ids))
    assert r.status_code == 428, r.text


def test_a_stale_version_is_refused(client, ids):
    pid = _new_property(client, ids, "stale")
    r = client.patch(f"/properties/{pid}", json={"built_area_m2": 50},
                     headers={**cust(ids), "If-Match-Version": "999"})
    assert r.status_code == 409, r.text


# --- RFC-001 object authorization, PROPERTY --------------------------------

def test_s10_a_customer_reads_a_property_they_created(client, ids):
    """RFC-001 S10: creator account match -> allow (R4.1)."""
    pid = _new_property(client, ids, "s10")
    r = client.get(f"/me/properties/{pid}", headers=cust(ids))
    assert r.status_code == 200, r.text


def test_s14_a_customer_cannot_read_an_assisted_unclaimed_property(client, ids):
    """RFC-001 S14: ASSISTED + UNCLAIMED -> 404 for every customer (R4.10)."""
    pid = _new_property(client, ids, "s14", who=staff(ids),
                        management_mode="ASSISTED", claim_status="UNCLAIMED")
    r = client.get(f"/me/properties/{pid}", headers=cust(ids))
    assert r.status_code == 404, r.text


def test_s12_a_relation_alone_grants_nothing(client, ids, engine):
    """RFC-001 S12: any `relation_code`, including OWNER_DECLARED, with no
    claim and not the creator -> 404 (R4.5).

    The relation row is inserted DIRECTLY by this fixture because no operation
    creates one (G3-6). That is the honest setup for this scenario and it is
    not evidence that a relations flow exists — it is evidence that a relation,
    however it got there, opens nothing.
    """
    pid = _new_property(client, ids, "s12", who=staff(ids),
                        management_mode="ASSISTED", claim_status="UNCLAIMED")
    with Session(bind=engine, future=True) as s:
        s.execute(
            text("""INSERT INTO turab.party_property_relations
                           (party_id, property_id, relation_code, valid_from)
                    VALUES (:party, :prop, 'OWNER_DECLARED', now())"""),
            {"party": ids.AMINA, "prop": uuid.UUID(pid)},
        )
        s.commit()
    r = client.get(f"/me/properties/{pid}", headers=cust(ids))
    assert r.status_code == 404, r.text
    patched = client.patch(f"/properties/{pid}", json={"built_area_m2": 12},
                           headers={**cust(ids), "If-Match-Version": "1"})
    assert patched.status_code in (403, 404), patched.text


def test_a_customer_cannot_patch_another_accounts_property(client, ids):
    """R4.2: property authority is ACCOUNT-scoped, so being staff-created is
    not the only way to be refused — another account's record is not yours."""
    pid = _new_property(client, ids, "other", who=staff(ids))
    r = client.patch(f"/properties/{pid}", json={"built_area_m2": 33},
                     headers={**cust(ids), "If-Match-Version": "1"})
    assert r.status_code in (403, 404), r.text


def test_s13_authority_resolves_through_an_alias_to_the_canonical(client, ids, engine):
    """RFC-001 S13 / R4.9: a customer authorized on an alias is authorized on
    the canonical record. Identity resolution must not strip a real owner."""
    canonical = _new_property(client, ids, "s13-canon")
    alias = _new_property(client, ids, "s13-alias", who=staff(ids),
                          management_mode="ASSISTED", claim_status="UNCLAIMED")
    with Session(bind=engine, future=True) as s:
        candidate = s.execute(
            text("""INSERT INTO turab.property_identity_candidates
                           (property_a_id, property_b_id, review_status)
                    VALUES (:a, :b, 'PENDING_REVIEW')
                 RETURNING identity_candidate_id"""),
            {"a": uuid.UUID(alias), "b": uuid.UUID(canonical)},
        ).scalar_one()
        s.execute(
            text("""INSERT INTO turab.property_identity_aliases
                           (alias_property_id, canonical_property_id,
                            source_identity_candidate_id, resolved_by_account_id)
                    VALUES (:alias, :canon, :cand, :acct)"""),
            {"alias": uuid.UUID(alias), "canon": uuid.UUID(canonical),
             "cand": candidate, "acct": ids.ACC_OPERATOR},
        )
        s.commit()
    # The alias is ASSISTED/UNCLAIMED and would be refused on its own; reading
    # it resolves to the canonical the customer created, and is allowed.
    r = client.get(f"/me/properties/{alias}", headers=cust(ids))
    assert r.status_code == 200, r.text


# --- the internal read -----------------------------------------------------

def test_a_customer_cannot_use_the_internal_property_read(client, ids):
    pid = _new_property(client, ids, "internal")
    r = client.get(f"/properties/{pid}", headers=cust(ids))
    assert r.status_code == 403, r.text


def test_the_internal_read_is_audited(client, ids, sink):
    """R6.2/R6.3: a staff read of an arbitrary object is recorded, which is
    what satisfies the business-purpose requirement structurally."""
    pid = _new_property(client, ids, "audited")
    sink.clear()
    client.get(f"/properties/{pid}", headers=staff(ids))
    kinds = {r.resource_kind for r in sink.records}
    assert "PROPERTY" in kinds, sink.records


def test_the_customer_path_cannot_be_used_to_enumerate_properties(client, ids):
    """The test that matters: **same actor, same path, both answers equal.**

    A missing id and a real-but-unauthorized id must be indistinguishable, or
    the pair of responses becomes an enumeration oracle — a caller learns which
    UUIDs name real properties by the difference. Asserted as an equality
    rather than as two separate expectations, because two expectations can
    drift apart one commit at a time and still both look right.
    """
    missing = uuid.uuid4()
    unauthorized = _new_property(client, ids, "enum", who=staff(ids),
                                 management_mode="ASSISTED",
                                 claim_status="UNCLAIMED")

    a = client.get(f"/me/properties/{missing}", headers=cust(ids))
    b = client.get(f"/me/properties/{unauthorized}", headers=cust(ids))

    assert (a.status_code, a.json()["code"]) == (b.status_code, b.json()["code"]), (
        f"enumeration oracle: missing -> {a.status_code}/{a.json()['code']}, "
        f"unauthorized -> {b.status_code}/{b.json()['code']}"
    )
    assert a.status_code == 404, a.text


def test_a_customer_on_the_staff_path_is_refused_identically(client, ids):
    """The same equality on the other path a customer can reach.

    Here the refusal is `ROLE_NOT_PERMITTED`, decided before any object is
    looked up — so the object's existence cannot influence it, which is the
    strongest form of the property.
    """
    missing = uuid.uuid4()
    existing = _new_property(client, ids, "enum-staffpath")

    a = client.get(f"/properties/{missing}", headers=cust(ids))
    b = client.get(f"/properties/{existing}", headers=cust(ids))

    assert (a.status_code, a.json()["code"]) == (b.status_code, b.json()["code"])
    assert a.status_code == 403 and a.json()["code"] == "ROLE_NOT_PERMITTED"


def test_on_the_staff_path_an_unknown_property_is_403(client, ids):
    """403 `OBJECT_NOT_AUTHORIZED`, the same answer the REQUEST staff read
    gives for an unknown id.

    **Stated precisely, correcting an earlier docstring of ours.** On THIS
    path a 403 does in practice mean "no such property": staff are entitled to
    every property, so an existing one returns 200 and only a missing one is
    refused. That is not an enumeration oracle — it tells a staff caller
    nothing they could not learn from the backoffice queue — but it is not the
    "does not reveal existence" property either, and claiming that would have
    been a true result filed under a false cause. The property that DOES hold
    is asserted above, on the paths a customer can reach.
    """
    r = client.get(f"/properties/{uuid.uuid4()}", headers=staff(ids))
    assert r.status_code == 403, r.text
    assert r.json()["code"] == "OBJECT_NOT_AUTHORIZED"


# --- R-S3-P02: an unknown location is an input error, not a 500 ------------

def test_creating_with_an_unknown_location_is_a_typed_4xx(client, ids):
    """A well-formed UUID matching no location reached
    `properties_canonical_location_id_fkey` and surfaced as 500."""
    r = client.post("/properties", json=body(canonical_location_id=str(uuid.uuid4())),
                    headers={**cust(ids), "Idempotency-Key": "s3-fk-create"})
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "VALIDATION_FAILED"
    assert "INTERNAL_ERROR" not in r.text
    # and no raw database text leaks out
    for leak in ("fkey", "psycopg", "IntegrityError", "DETAIL:", "turab.properties"):
        assert leak not in r.text, f"database internals leaked: {leak}"


def test_the_refused_creation_consumes_no_idempotency_key(client, ids, engine):
    k = "s3-fk-retry"
    bad = client.post("/properties", json=body(canonical_location_id=str(uuid.uuid4())),
                      headers={**cust(ids), "Idempotency-Key": k})
    assert bad.status_code == 422, bad.text
    with Session(bind=engine, future=True) as s:
        used = s.execute(
            text("SELECT count(*) FROM turab.idempotency_records "
                 "WHERE idempotency_key = :k"), {"k": k},
        ).scalar_one()
    assert used == 0, "a refused command must leave its key free"
    good = client.post("/properties", json=body(),
                       headers={**cust(ids), "Idempotency-Key": k})
    assert good.status_code == 201, good.text


def test_patching_to_an_unknown_location_changes_nothing(client, ids, engine):
    """The refusal must leave the row, the version AND the trail untouched.

    **On idempotency keys here.** The review asked for "the refused PATCH
    consumes no key". `patchPropertiesPropertyId` has
    `requires_idempotency = False` — the contract declares `If-Match-Version`
    for the four PATCH operations instead, because a version-checked update is
    already idempotent: a replay carries a version that is no longer current.
    So this command records no key at all, and asserting one is not consumed
    would be asserting nothing. The key guarantee is proven where it applies,
    on POST, by the test above.

    (A first version of this test did assert it — and passed a key that
    `_new_property` had already used for the creation, so it was measuring its
    own helper. The same trap as `s2-tz-naive` in Slice 2; caught the same way,
    by the assertion failing for the wrong reason.)
    """
    pid = _new_property(client, ids, "fk-patch")
    before = client.get(f"/properties/{pid}", headers=staff(ids)).json()
    with Session(bind=engine, future=True) as s:
        claims_before = s.execute(
            text("SELECT count(*) FROM turab.claims WHERE property_id = :p"),
            {"p": uuid.UUID(pid)},
        ).scalar_one()

    r = client.patch(f"/properties/{pid}",
                     json={"canonical_location_id": str(uuid.uuid4())},
                     headers={**cust(ids), "If-Match-Version": str(before["version"])})
    assert r.status_code == 422, r.text
    assert "INTERNAL_ERROR" not in r.text
    for leak in ("fkey", "psycopg", "IntegrityError", "DETAIL:"):
        assert leak not in r.text, f"database internals leaked: {leak}"

    after = client.get(f"/properties/{pid}", headers=staff(ids)).json()
    assert after == before, "a refused patch must change nothing, version included"
    with Session(bind=engine, future=True) as s:
        claims_after = s.execute(
            text("SELECT count(*) FROM turab.claims WHERE property_id = :p"),
            {"p": uuid.UUID(pid)},
        ).scalar_one()
    assert claims_after == claims_before, "a refused patch must record no provenance"


def test_the_patch_command_declares_no_idempotency_key(client, ids):
    """Pins the fact the test above relies on, so it cannot drift silently.

    If `patchPropertiesPropertyId` ever starts requiring a key, this fails and
    the docstring above stops being true at the same moment.
    """
    from turab.auth.contract import build_policy_table

    policies = build_policy_table()
    assert policies.get("patchPropertiesPropertyId").requires_idempotency is False
    assert policies.get("postProperties").requires_idempotency is True


def test_a_known_location_still_works(client, ids, engine):
    """The scoping test: the refusal must be about the missing row, not about
    the field being present at all."""
    with Session(bind=engine, future=True) as s:
        loc = s.execute(text("SELECT location_id FROM turab.locations LIMIT 1")).scalar_one()
    r = client.post("/properties", json=body(canonical_location_id=str(loc)),
                    headers={**cust(ids), "Idempotency-Key": "s3-fk-ok"})
    assert r.status_code == 201, r.text
    assert r.json()["canonical_location_id"] == str(loc)
