"""Slice 1 mandatory tests.

Ref: IMPLEMENTATION_SLICES_v0.2.md, Slice 1 "Mandatory tests":

  1. phone verification alone creates no account unless LOGIN flow is
     explicitly completed;
  2. same phone can be related to two PARTY records;
  3. revoked consent cannot authorize a new share/activation;
  4. consent for Party A cannot bind to Request of Party B;
  5. property consent requires an active Party<->Property relationship.

Red-team equivalents: A01, A02, A03, B01, B02, B03.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from turab.services import consent as consent_service
from turab.services import parties as party_service
from turab.services.otp import (
    CheckedVerification,
    FakeVerificationProvider,
    OtpPurpose,
    VerificationRejected,
    VerificationResult,
    apply_verification,
    start_verification,
)


@pytest.fixture
def provider():
    """Stands in for the SMS/WhatsApp provider, which owns the challenge."""
    return FakeVerificationProvider()


def _verify(session, provider, *, phone, purpose):
    """Run a full provider round trip and apply the outcome."""
    started = start_verification(provider, phone_e164=phone, purpose=purpose)
    return apply_verification(
        session, provider,
        verification_id=started.verification_id,
        code=provider.code_for(started.verification_id),
    )


def _accounts_for(session, contact_point_id):
    return session.execute(
        text("SELECT count(*) FROM turab.user_accounts WHERE login_contact_point_id = :c"),
        {"c": contact_point_id},
    ).scalar_one()


# --- 1. phone verification alone creates no account (A02, A03) -------------

def test_verify_phone_control_creates_no_account(session, provider):
    """The invariant in Master §4 (11): a verified phone proves control of a
    contact point and nothing more."""
    parties_before = session.execute(text("SELECT count(*) FROM turab.parties")).scalar_one()
    accounts_before = session.execute(text("SELECT count(*) FROM turab.user_accounts")).scalar_one()

    result = _verify(session, provider, phone="+213770000001",
                     purpose=OtpPurpose.VERIFY_PHONE_CONTROL)

    assert result["verification_result"] == VerificationResult.PHONE_CONTROL_VERIFIED
    assert result["account_id"] is None
    assert result["access_token"] is None
    assert session.execute(text("SELECT count(*) FROM turab.parties")).scalar_one() == parties_before
    assert session.execute(text("SELECT count(*) FROM turab.user_accounts")).scalar_one() == accounts_before

    status = session.execute(
        text("SELECT control_status::text FROM turab.contact_points WHERE contact_point_id = :c"),
        {"c": result["contact_point_id"]},
    ).scalar_one()
    assert status == "VERIFIED_CONTROL"


def test_login_purpose_creates_no_account_when_none_exists(session, provider):
    """LOGIN is not a licence to manufacture an account either.

    Control is proved, no session is created, and the caller is told exactly
    that: `account_id` is nullable by design (§4.1).
    """
    result = _verify(session, provider, phone="+213770000002", purpose=OtpPurpose.LOGIN)
    assert result["verification_result"] == VerificationResult.PHONE_CONTROL_VERIFIED
    assert result["account_id"] is None
    assert _accounts_for(session, result["contact_point_id"]) == 0


def test_login_activates_an_existing_invited_account(session, provider, ids):
    """The explicit LOGIN completion the mandatory test contrasts with."""
    contact = uuid.uuid4()
    account = uuid.uuid4()
    session.execute(
        text(
            """INSERT INTO turab.contact_points
                 (contact_point_id, kind, normalized_value, control_status)
               VALUES (:c,'PHONE','+213770000003','UNVERIFIED')"""
        ),
        {"c": contact},
    )
    session.execute(
        text(
            """INSERT INTO turab.user_accounts
                 (account_id, party_id, status, login_contact_point_id)
               VALUES (:a, :p, 'INVITED', :c)"""
        ),
        {"a": account, "p": ids.AMINA, "c": contact},
    )

    result = _verify(session, provider, phone="+213770000003", purpose=OtpPurpose.LOGIN)
    assert result["verification_result"] == VerificationResult.SESSION_CREATED
    assert result["account_id"] == account
    assert session.execute(
        text("SELECT status::text FROM turab.user_accounts WHERE account_id=:a"),
        {"a": account},
    ).scalar_one() == "ACTIVATED"


@pytest.mark.parametrize("status", ["SUSPENDED", "DISABLED"])
def test_login_does_not_resurrect_a_disabled_account(session, provider, ids, status):
    """Proving control of a phone must not undo an administrative decision."""
    contact, account = uuid.uuid4(), uuid.uuid4()
    session.execute(
        text(
            """INSERT INTO turab.contact_points
                 (contact_point_id, kind, normalized_value, control_status)
               VALUES (:c,'PHONE','+213770000004','UNVERIFIED')"""
        ),
        {"c": contact},
    )
    session.execute(
        text(
            """INSERT INTO turab.user_accounts
                 (account_id, party_id, status, login_contact_point_id)
               VALUES (:a, :p, CAST(:s AS turab.account_status), :c)"""
        ),
        {"a": account, "p": ids.AMINA, "s": status, "c": contact},
    )
    result = _verify(session, provider, phone="+213770000004", purpose=OtpPurpose.LOGIN)
    assert result["verification_result"] == VerificationResult.PHONE_CONTROL_VERIFIED
    assert result["account_id"] is None
    assert session.execute(
        text("SELECT status::text FROM turab.user_accounts WHERE account_id=:a"),
        {"a": account},
    ).scalar_one() == status


# --- 2. same phone, two parties, no merge (A01) ---------------------------

def test_one_phone_can_reach_two_parties_without_merging(session):
    """A01 / ADR-07. The contact point is shared; the parties are not."""
    a = party_service.create_party(session, kind="PERSON", display_name="الأب")
    b = party_service.create_party(session, kind="PERSON", display_name="الابن")

    cp_a = party_service.attach_phone(
        session, party_id=a["party_id"], phone_e164="+213770000010"
    )
    cp_b = party_service.attach_phone(
        session, party_id=b["party_id"], phone_e164="+213770000010"
    )

    # one contact point, reused
    assert cp_a["contact_point_id"] == cp_b["contact_point_id"]
    # two parties, still distinct
    assert a["party_id"] != b["party_id"]
    sharing = party_service.parties_sharing(session, cp_a["contact_point_id"])
    assert set(sharing) == {a["party_id"], b["party_id"]}
    assert session.execute(
        text("SELECT count(*) FROM turab.parties WHERE party_id IN (:a,:b)"),
        {"a": a["party_id"], "b": b["party_id"]},
    ).scalar_one() == 2


def test_the_same_number_in_a_different_format_is_the_same_contact_point(session):
    """Normalisation is what makes 'the same phone' a testable idea at all."""
    a = party_service.create_party(session, kind="PERSON")
    b = party_service.create_party(session, kind="PERSON")
    first = party_service.attach_phone(
        session, party_id=a["party_id"], phone_e164="+213770000011"
    )
    second = party_service.attach_phone(
        session, party_id=b["party_id"], phone_e164="+213 770-00.00(11)"
    )
    assert first["contact_point_id"] == second["contact_point_id"]


def test_reusing_a_contact_point_does_not_transfer_its_verified_control(session, provider):
    """A second party linking a verified line inherits the link, not identity.

    Verification travels with the contact point, and neither the link nor the
    verification implies that the two parties are the same person.
    """
    a = party_service.create_party(session, kind="PERSON")
    party_service.attach_phone(session, party_id=a["party_id"], phone_e164="+213770000012")
    _verify(session, provider, phone="+213770000012",
            purpose=OtpPurpose.VERIFY_PHONE_CONTROL)

    b = party_service.create_party(session, kind="PERSON")
    cp = party_service.attach_phone(
        session, party_id=b["party_id"], phone_e164="+213770000012"
    )
    # the contact point stays verified, and B still has no account
    assert cp["control_status"] == "VERIFIED_CONTROL"
    assert _accounts_for(session, cp["contact_point_id"]) == 0


# --- 3. revoked consent authorizes nothing new (B03) ----------------------

def test_revoked_consent_cannot_bind(session, ids):
    """ADR-04: revocation blocks future authority."""
    grant = consent_service.grant_consent(
        session, party_id=ids.AMINA, scope="PRIVATE_MATCHING_ONLY",
        channel="WEB", consent_version="v1", granted_at=datetime.now(UTC),
    )
    consent_service.revoke_consent(session, consent_id=grant["consent_id"])

    with pytest.raises(consent_service.ConsentBindingRejected) as exc:
        consent_service.bind_consent(
            session, consent_id=grant["consent_id"], purpose="PRIVATE_MATCHING_ONLY",
            resource_type="REQUEST", resource_id=ids.REQ_AMINA,
        )
    assert "granted" in str(exc.value).lower()


def test_revocation_leaves_history_intact(session, ids):
    """The grant row and any existing binding survive; only future use stops."""
    grant = consent_service.grant_consent(
        session, party_id=ids.AMINA, scope="PRIVATE_MATCHING_ONLY",
        channel="WEB", consent_version="v1", granted_at=datetime.now(UTC),
    )
    binding = consent_service.bind_consent(
        session, consent_id=grant["consent_id"], purpose="PRIVATE_MATCHING_ONLY",
        resource_type="REQUEST", resource_id=ids.REQ_AMINA,
    )
    consent_service.revoke_consent(session, consent_id=grant["consent_id"])

    still_there = session.execute(
        text("SELECT count(*) FROM turab.resource_consent_bindings WHERE consent_binding_id=:b"),
        {"b": binding["consent_binding_id"]},
    ).scalar_one()
    assert still_there == 1
    assert consent_service.read_grant(session, grant["consent_id"])["status"] == "REVOKED"


def test_revoking_twice_is_not_an_error(session, ids):
    """A retry must not look like a failure when the intent is already met."""
    grant = consent_service.grant_consent(
        session, party_id=ids.AMINA, scope="PRIVATE_MATCHING_ONLY",
        channel="WEB", consent_version="v1", granted_at=datetime.now(UTC),
    )
    first = consent_service.revoke_consent(session, consent_id=grant["consent_id"])
    second = consent_service.revoke_consent(session, consent_id=grant["consent_id"])
    assert first["revoked_at"] == second["revoked_at"]


# --- 4. Party A's consent cannot bind to Party B's request (B01) ----------

def test_consent_of_party_a_cannot_bind_to_request_of_party_b(session, ids):
    grant = consent_service.grant_consent(
        session, party_id=ids.KHADIJA, scope="PRIVATE_MATCHING_ONLY",
        channel="WEB", consent_version="v1", granted_at=datetime.now(UTC),
    )
    with pytest.raises(consent_service.ConsentBindingRejected) as exc:
        consent_service.bind_consent(
            session, consent_id=grant["consent_id"], purpose="PRIVATE_MATCHING_ONLY",
            resource_type="REQUEST", resource_id=ids.REQ_AMINA,  # Amina's request
        )
    assert "party mismatch" in str(exc.value).lower()


def test_purpose_must_equal_the_granted_scope(session, ids):
    """B02. A COMMUNICATION_ARCHIVE grant is not a listing permission."""
    grant = consent_service.grant_consent(
        session, party_id=ids.AMINA, scope="COMMUNICATION_ARCHIVE",
        channel="WHATSAPP", consent_version="v1", granted_at=datetime.now(UTC),
    )
    with pytest.raises(consent_service.ConsentBindingRejected) as exc:
        consent_service.bind_consent(
            session, consent_id=grant["consent_id"], purpose="PUBLIC_LISTING_ALLOWED",
            resource_type="REQUEST", resource_id=ids.REQ_AMINA,
        )
    assert "scope" in str(exc.value).lower()


# --- 5. property consent needs an active relationship ---------------------

def test_property_binding_requires_an_active_party_property_relation(session, ids):
    """The consenting party must actually relate to the property."""
    grant = consent_service.grant_consent(
        session, party_id=ids.AMINA, scope="PUBLIC_LISTING_ALLOWED",
        channel="WEB", consent_version="v1", granted_at=datetime.now(UTC),
    )
    with pytest.raises(consent_service.ConsentBindingRejected) as exc:
        consent_service.bind_consent(
            session, consent_id=grant["consent_id"], purpose="PUBLIC_LISTING_ALLOWED",
            resource_type="PROPERTY", resource_id=ids.VILLA_SELF_MANAGED,
        )
    assert "relation" in str(exc.value).lower()


def test_property_binding_succeeds_with_an_active_relation(session, ids):
    """The positive case, without which the test above proves only that
    something failed."""
    grant = consent_service.grant_consent(
        session, party_id=ids.BRAHIM, scope="PUBLIC_LISTING_ALLOWED",
        channel="PHONE_CONFIRMED", consent_version="v1", granted_at=datetime.now(UTC),
    )
    # Brahim holds a current OWNER_DECLARED relation on this villa in the fixtures.
    binding = consent_service.bind_consent(
        session, consent_id=grant["consent_id"], purpose="PUBLIC_LISTING_ALLOWED",
        resource_type="PROPERTY", resource_id=ids.VILLA_SELF_MANAGED,
    )
    assert binding["property_id"] == ids.VILLA_SELF_MANAGED


def test_an_expired_relation_does_not_authorize_a_property_binding(session, ids):
    """`enforce_consent_binding()` requires the relation to be current."""
    grant = consent_service.grant_consent(
        session, party_id=ids.AGENCY, scope="PUBLIC_LISTING_ALLOWED",
        channel="WEB", consent_version="v1", granted_at=datetime.now(UTC),
    )
    # The agency's relation on the assisted apartment expired in the fixtures.
    with pytest.raises(consent_service.ConsentBindingRejected):
        consent_service.bind_consent(
            session, consent_id=grant["consent_id"], purpose="PUBLIC_LISTING_ALLOWED",
            resource_type="PROPERTY", resource_id=ids.ASSISTED_APARTMENT,
        )


# --- the provider boundary itself ----------------------------------------

def test_turab_stores_no_challenge_state(session, provider):
    """The decision: the provider owns the challenge, TURAB owns the outcome.

    After a full round trip the only thing TURAB has recorded is the verified
    contact point — no challenge, no code, no expiry, nowhere.
    """
    result = _verify(session, provider, phone="+213770000020",
                     purpose=OtpPurpose.VERIFY_PHONE_CONTROL)
    tables = session.execute(
        text(
            """SELECT table_name FROM information_schema.tables
                WHERE table_schema='turab' AND table_name ILIKE ANY
                      (ARRAY['%otp%','%challenge%','%verification_code%'])"""
        )
    ).scalars().all()
    assert tables == [], f"a challenge table appeared: {tables}"
    assert session.execute(
        text("SELECT verification_method FROM turab.contact_points WHERE contact_point_id=:c"),
        {"c": result["contact_point_id"]},
    ).scalar_one() == "OTP_PROVIDER"


def test_a_rejected_code_changes_nothing(session, provider):
    started = start_verification(
        provider, phone_e164="+213770000021", purpose=OtpPurpose.VERIFY_PHONE_CONTROL
    )
    with pytest.raises(VerificationRejected):
        apply_verification(
            session, provider, verification_id=started.verification_id, code="000000"
        )
    assert session.execute(
        text("SELECT count(*) FROM turab.contact_points WHERE normalized_value=:v"),
        {"v": "+213770000021"},
    ).scalar_one() == 0


def test_an_unknown_verification_is_rejected(session, provider):
    with pytest.raises(VerificationRejected):
        apply_verification(
            session, provider, verification_id=uuid.uuid4(), code="424242"
        )


def test_attempt_limits_belong_to_the_provider(session, provider):
    """Throttling is the provider's job and is not reimplemented here."""
    started = start_verification(
        provider, phone_e164="+213770000022", purpose=OtpPurpose.LOGIN
    )
    for _ in range(FakeVerificationProvider.MAX_ATTEMPTS + 1):
        with pytest.raises(VerificationRejected):
            apply_verification(
                session, provider, verification_id=started.verification_id, code="999999"
            )
    # exhausted: even the correct code no longer works
    with pytest.raises(VerificationRejected):
        apply_verification(
            session, provider, verification_id=started.verification_id, code="424242"
        )


def test_an_unestablished_purpose_fails_closed(session, ids):
    """A provider that cannot carry TURAB's purpose must never yield a session.

    The account below exists and is INVITED, so a LOGIN would have activated
    it. With the purpose unknown the outcome is PHONE_CONTROL_VERIFIED and the
    account is untouched.
    """
    contact, account = uuid.uuid4(), uuid.uuid4()
    session.execute(
        text(
            """INSERT INTO turab.contact_points
                 (contact_point_id, kind, normalized_value, control_status)
               VALUES (:c,'PHONE','+213770000023','UNVERIFIED')"""
        ),
        {"c": contact},
    )
    session.execute(
        text(
            """INSERT INTO turab.user_accounts
                 (account_id, party_id, status, login_contact_point_id)
               VALUES (:a,:p,'INVITED',:c)"""
        ),
        {"a": account, "p": ids.AMINA, "c": contact},
    )

    class PurposelessProvider:
        def start(self, **_):
            raise NotImplementedError

        def check(self, **_):
            return CheckedVerification(
                approved=True, phone_e164="+213770000023", purpose=None
            )

    result = apply_verification(
        session, PurposelessProvider(), verification_id=uuid.uuid4(), code="x"
    )
    assert result["verification_result"] == VerificationResult.PHONE_CONTROL_VERIFIED
    assert result["account_id"] is None
    assert session.execute(
        text("SELECT status::text FROM turab.user_accounts WHERE account_id=:a"),
        {"a": account},
    ).scalar_one() == "INVITED"


# --- 6. a party link is not a login path ----------------------------------
#
# Not in the handoff's mandatory list, but it is the question those five leave
# open. A02 proves verification creates no account and A01 proves a shared
# contact point never merges parties. Together they invite the inverse
# question: if a customer ATTACHES a phone to their own party, does that phone
# now reach their account? If it did, a customer could attach any number,
# verify it, and be handed a session — the merge A01 forbids, arriving through
# the login door instead.

def test_attaching_a_phone_to_a_party_creates_no_login_path(session, provider, ids):
    """`party_contact_points` and `user_accounts.login_contact_point_id` are
    different relationships, and only the second one authenticates."""
    before = session.execute(
        text("""SELECT account_id, login_contact_point_id, status::text
                  FROM turab.user_accounts ORDER BY account_id""")
    ).mappings().all()

    # Amina attaches a number she does not control to her OWN party — which
    # the object gate permits, because it is her party.
    stranger = "+213770000501"
    party_service.attach_phone(session, party_id=ids.AMINA, phone_e164=stranger)
    session.flush()

    after = session.execute(
        text("""SELECT account_id, login_contact_point_id, status::text
                  FROM turab.user_accounts ORDER BY account_id""")
    ).mappings().all()
    assert [dict(r) for r in after] == [dict(r) for r in before], (
        "attaching a contact point to a party must not touch any account's "
        "login contact point"
    )

    # And the login flow on that number yields no session: no account names it
    # as its login contact point, and the party link is not consulted.
    result = _verify(session, provider, phone=stranger, purpose=OtpPurpose.LOGIN)
    assert result["verification_result"] == VerificationResult.PHONE_CONTROL_VERIFIED.value
    assert result["account_id"] is None
    assert result["access_token"] is None


def test_a_shared_line_does_not_authenticate_as_the_party_that_shares_it(
    session, provider, ids
):
    """A01's shared line, pointed at the login door.

    Brahim's verified phone already reaches the agency party. Link it to
    AMINA's party as well — Amina is the fixture's only party WITH an account,
    which is what makes this test able to fail: a resolver that walked
    `party_contact_points` instead of `user_accounts.login_contact_point_id`
    would now hand this caller Amina's session.
    """
    shared = "+213661000002"
    party_service.attach_phone(session, party_id=ids.AMINA, phone_e164=shared)
    session.flush()

    linked_parties = session.execute(
        text("""SELECT count(*) FROM turab.party_contact_points pcp
                  JOIN turab.contact_points cp USING (contact_point_id)
                 WHERE cp.normalized_value = :v"""),
        {"v": shared},
    ).scalar_one()
    assert linked_parties >= 3, "the premise of this test is a shared line"

    result = _verify(session, provider, phone=shared, purpose=OtpPurpose.LOGIN)

    # The line now has a legitimate OWNER account (Brahim's, whose login
    # contact point it is). So the assertion is sharper than "nobody": LOGIN
    # resolves to the account that NAMES this line as its login contact
    # point, and to nobody else — not to Amina, who merely had it attached to
    # her party, and not to the agency, which also shares it.
    assert result["account_id"] == ids.ACC_BRAHIM
    assert result["account_id"] != ids.ACC_AMINA, (
        "a phone attached to a party must not authenticate as that party"
    )
    assert _accounts_for(session, result["contact_point_id"]) == 1
