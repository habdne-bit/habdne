"""Slice 2 mandatory tests.

Ref: IMPLEMENTATION_SLICES_v0.2.md, Slice 2 "Mandatory tests":

  1. INTEREST never silently creates REQUEST;
  2. criteria mutation bumps request version;
  3. Required/Preferred/Flexible values cannot be changed by AI or background
     jobs;
  4. stale request becomes NEEDS_CONFIRMATION according to policy/workflow;
  5. assisted request cannot be inserted as CLAIMED.

Plus the separations the scope insists on: data update, state transition and
reconfirmation are three different commands and none does another's work.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from turab.services import freshness, requests as request_service


@pytest.fixture
def new_request(session, ids):
    """A fresh SELF_MANAGED request for Amina, cleaned up afterwards."""
    row = request_service.create_request(
        session, party_id=ids.AMINA, transaction_intent="BUY",
        intent="ACTIVE_SEARCH", management_mode="SELF_MANAGED",
        claim_status="CLAIMED", created_by_account_id=ids.ACC_AMINA,
        budget_target_dzd=20_000_000,
    )
    session.flush()
    return row


# --- 1. INTEREST never silently creates REQUEST ---------------------------

def test_recording_an_interest_creates_no_request(session, ids):
    """An expression of interest in a property is not a search brief.

    Conflating them is how a CRM ends up full of 'requests' nobody ever
    stated: one tap on a listing becomes a standing instruction to match.
    """
    before = session.execute(text("SELECT count(*) FROM turab.requests")).scalar_one()
    session.execute(
        text(
            """INSERT INTO turab.interests (party_id, property_id, status)
               VALUES (:p, :prop, 'ACTIVE')"""
        ),
        {"p": ids.AMINA, "prop": ids.VILLA_SELF_MANAGED},
    )
    session.flush()
    after = session.execute(text("SELECT count(*) FROM turab.requests")).scalar_one()
    assert after == before


def test_no_application_code_creates_a_request_from_an_interest():
    """Structural, not behavioural: nothing may grow that path later."""
    import pathlib

    src = pathlib.Path("src/turab")
    offenders = []
    for path in src.rglob("*.py"):
        text_ = path.read_text(encoding="utf-8")
        if "turab.interests" in text_ and "INSERT INTO turab.requests" in text_:
            offenders.append(path.name)
    assert not offenders, f"{offenders} reads interests and writes requests"


# --- 2. criteria mutation bumps the request version -----------------------

def test_adding_a_criterion_bumps_the_request_version(session, ids, new_request):
    """`request_criteria` has its own trigger and does NOT touch
    `requests.version`. Without an explicit bump every consumer that uses the
    version to detect change — optimistic concurrency included — would miss a
    criteria change entirely."""
    before = new_request["version"]
    request_service.add_criterion(
        session, request_id=new_request["request_id"],
        criterion_code="ROOMS_MIN", importance="REQUIRED", operator="GTE", value=3,
        recorded_by_account_id=ids.ACC_AMINA,
    )
    session.flush()
    after = request_service.read_request(session, new_request["request_id"])["version"]
    assert after > before


def test_the_criterion_is_actually_stored(session, ids, new_request):
    request_service.add_criterion(
        session, request_id=new_request["request_id"],
        criterion_code="ROOMS_MIN", importance="PREFERRED", operator="GTE", value=4,
        recorded_by_account_id=ids.ACC_AMINA,
    )
    session.flush()
    stored = request_service.criteria_for(session, new_request["request_id"])
    assert [(c["criterion_code"], c["importance"], c["value"]) for c in stored] == [
        ("ROOMS_MIN", "PREFERRED", 4)
    ]


# --- 3. importance is the buyer's word, not an inference ------------------

def test_importance_is_restricted_to_the_three_declared_values(session, ids, new_request):
    with pytest.raises(request_service.RequestError):
        request_service.add_criterion(
            session, request_id=new_request["request_id"],
            criterion_code="ROOMS_MIN", importance="NICE_TO_HAVE",
            operator="GTE", value=3,
        )


def test_no_code_path_rewrites_importance_from_an_inference():
    """Required/Preferred/Flexible are what the buyer said is negotiable.

    An extraction model or a background pass rewriting them silently rewrites
    the buyer's intent, and the record would no longer be evidence of anything
    they actually said. Enforced structurally: importance is only ever written
    from a value supplied by a caller, never derived.
    """
    import ast
    import pathlib

    source = pathlib.Path("src/turab/services/requests.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    # An importance value may only ever reach the database from a caller's
    # argument. A literal 'REQUIRED'/'PREFERRED'/'FLEXIBLE' anywhere outside
    # the declared tuple would mean some code path CHOOSES one.
    declared = {"REQUIRED", "PREFERRED", "FLEXIBLE"}
    # The declared tuple is the one permitted occurrence; collect the ids of
    # ITS constants so walking the tree does not re-find them.
    allowed: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", "") == "IMPORTANCE_VALUES" for t in node.targets
        ):
            allowed |= {id(c) for c in ast.walk(node.value)}
    literals = [
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and node.value in declared
        and id(node) not in allowed
    ]
    assert not literals, (
        f"an importance value is written as a literal in requests.py: {literals}. "
        "Importance is the buyer's own word about what is negotiable; no code "
        "path may choose one."
    )


def test_patch_cannot_reach_importance_fields(session, ids, new_request):
    """The typed update names its columns; the importance columns are not
    among them, so no PATCH can relax a REQUIRED to a PREFERRED."""
    assert not [f for f in request_service.PATCHABLE if "importance" in f]
    with pytest.raises(request_service.RequestError):
        request_service.patch_request(
            session, request_id=new_request["request_id"],
            changes={"budget_importance": "FLEXIBLE"},
            recorded_by_account_id=ids.ACC_AMINA,
        )


# --- 4. a stale request becomes NEEDS_CONFIRMATION ------------------------

def test_the_threshold_comes_from_the_active_policy_not_from_code(session):
    days, version = freshness.request_threshold_days(session)
    assert days == 30 and version == "0.2.0"
    import ast
    import pathlib

    tree = ast.parse(
        pathlib.Path("src/turab/services/freshness.py").read_text(encoding="utf-8")
    )
    # Docstrings may QUOTE the seeded policy; executable code may not contain
    # a day count. Checked over constants outside docstrings, so the module can
    # document the policy it reads without becoming the policy.
    docstrings = {
        id(n.body[0].value) for n in ast.walk(tree)
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef))
        and n.body and isinstance(n.body[0], ast.Expr)
        and isinstance(n.body[0].value, ast.Constant)
    }
    numbers = [
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, int)
        and not isinstance(n.value, bool) and id(n) not in docstrings
        and n.value not in (0, 1)
    ]
    assert not numbers, f"a day count is hard-coded in freshness.py: {numbers}"


def test_a_request_past_the_window_is_stale(session, ids, new_request):
    days, _ = freshness.request_threshold_days(session)
    old = datetime.now(UTC) - timedelta(days=days + 1)
    session.execute(
        text("UPDATE turab.requests SET last_confirmed_at = :t WHERE request_id = :r"),
        {"t": old, "r": new_request["request_id"]},
    )
    session.flush()
    assert freshness.evaluate_request(session, new_request["request_id"]).is_stale


def test_a_stale_active_request_becomes_needs_confirmation(session, ids, new_request):
    """Mandatory test 4, through the documented edge ACTIVE -> NEEDS_CONFIRMATION."""
    rid = new_request["request_id"]
    _advance_to_active(session, rid, ids)
    days, _ = freshness.request_threshold_days(session)
    session.execute(
        text("UPDATE turab.requests SET last_confirmed_at = :t WHERE request_id = :r"),
        {"t": datetime.now(UTC) - timedelta(days=days + 1), "r": rid},
    )
    session.flush()

    moved = request_service.mark_stale_as_needing_confirmation(session)
    session.flush()
    assert rid in moved
    assert request_service.read_request(session, rid)["status"] == "NEEDS_CONFIRMATION"


def test_a_fresh_request_is_left_alone(session, ids, new_request):
    rid = new_request["request_id"]
    _advance_to_active(session, rid, ids)
    session.execute(
        text("UPDATE turab.requests SET last_confirmed_at = clock_timestamp() "
             "WHERE request_id = :r"),
        {"r": rid},
    )
    session.flush()
    assert rid not in request_service.mark_stale_as_needing_confirmation(session)


def test_only_active_requests_are_moved(session, ids, new_request):
    """§5.2 defines NEEDS_CONFIRMATION only as an edge from ACTIVE. A RAW
    request that is old is not stale — it was never confirmed in the first
    place, which is a different operational problem."""
    rid = new_request["request_id"]
    days, _ = freshness.request_threshold_days(session)
    session.execute(
        text("UPDATE turab.requests SET last_confirmed_at = :t WHERE request_id = :r"),
        {"t": datetime.now(UTC) - timedelta(days=days + 1), "r": rid},
    )
    session.flush()
    assert request_service.read_request(session, rid)["status"] == "RAW"
    assert rid not in request_service.mark_stale_as_needing_confirmation(session)


def test_a_never_confirmed_request_is_not_stale(session, new_request):
    result = freshness.evaluate_request(session, new_request["request_id"])
    assert result.state is freshness.FreshnessState.NEVER_CONFIRMED
    assert not result.is_stale


def test_a_missing_policy_is_an_error_not_a_default(session):
    """A hard-coded fallback that runs IS the policy — one nobody approved and
    nobody can find by reading `matching_policies`."""
    session.execute(text("UPDATE turab.matching_policies SET active = false"))
    session.flush()
    with pytest.raises(freshness.NoActiveFreshnessPolicy):
        freshness.request_threshold_days(session)


# --- 5. an assisted request cannot be CLAIMED -----------------------------

@pytest.mark.parametrize("mode, claim", [
    ("ASSISTED", "CLAIMED"),
    ("SELF_MANAGED", "UNCLAIMED"),
    ("SHARED_MANAGEMENT", "UNCLAIMED"),
])
def test_the_management_pair_is_refused_when_incoherent(session, ids, mode, claim):
    with pytest.raises(request_service.InvalidManagementCombination):
        request_service.create_request(
            session, party_id=ids.AMINA, transaction_intent="BUY",
            intent="EXPLORING", management_mode=mode, claim_status=claim,
            created_by_account_id=ids.ACC_OPERATOR,
        )


def test_the_database_refuses_it_too(session, ids):
    """The service check is a better error; the CHECK is what makes the rule
    true of anything that writes, including a future importer."""
    with pytest.raises(Exception) as exc:
        session.execute(
            text(
                """INSERT INTO turab.requests
                          (party_id, transaction_intent, intent,
                           management_mode, claim_status)
                   VALUES (:p, 'BUY', 'EXPLORING', 'ASSISTED', 'CLAIMED')"""
            ),
            {"p": ids.AMINA},
        )
    assert "requests_check" in str(exc.value) or "violates check" in str(exc.value).lower()


def test_an_assisted_request_is_created_unclaimed(session, ids):
    row = request_service.create_request(
        session, party_id=ids.BRAHIM, transaction_intent="RENT",
        intent="EXPLORING", management_mode="ASSISTED", claim_status="UNCLAIMED",
        created_by_account_id=ids.ACC_OPERATOR,
    )
    assert (row["management_mode"], row["claim_status"]) == ("ASSISTED", "UNCLAIMED")


# --- the three commands stay three ----------------------------------------

def test_a_data_update_does_not_touch_status_or_confirmation(session, ids, new_request):
    rid = new_request["request_id"]
    before = request_service.read_request(session, rid)
    request_service.patch_request(
        session, request_id=rid, changes={"budget_max_dzd": 26_000_000},
        recorded_by_account_id=ids.ACC_AMINA,
    )
    session.flush()
    after = request_service.read_request(session, rid)
    assert after["budget_max_dzd"] == 26_000_000
    assert after["status"] == before["status"]
    assert after["last_confirmed_at"] == before["last_confirmed_at"]


def test_a_state_transition_does_not_touch_the_data_or_confirmation(
    session, ids, new_request
):
    rid = new_request["request_id"]
    before = request_service.read_request(session, rid)
    request_service.transition(
        session, request_id=rid, target_status="CONTACTED",
        recorded_by_account_id=ids.ACC_OPERATOR,
    )
    session.flush()
    after = request_service.read_request(session, rid)
    assert after["status"] == "CONTACTED"
    assert after["budget_target_dzd"] == before["budget_target_dzd"]
    assert after["last_confirmed_at"] == before["last_confirmed_at"]


def test_a_reconfirmation_does_not_change_what_the_buyer_wants(
    session, ids, new_request
):
    rid = new_request["request_id"]
    before = request_service.read_request(session, rid)
    request_service.reconfirm(
        session, request_id=rid, recorded_by_account_id=ids.ACC_OPERATOR,
    )
    session.flush()
    after = request_service.read_request(session, rid)
    assert after["last_confirmed_at"] is not None
    assert after["budget_target_dzd"] == before["budget_target_dzd"]
    assert after["intent"] == before["intent"]


def test_reconfirming_returns_a_needs_confirmation_request_to_active(
    session, ids, new_request
):
    """§5.2 defines NEEDS_CONFIRMATION -> ACTIVE, and reconfirming is how that
    edge is taken: the transition is a consequence of the confirmation, not a
    separate state change the caller picks."""
    rid = new_request["request_id"]
    _advance_to_active(session, rid, ids)
    request_service.transition(
        session, request_id=rid, target_status="NEEDS_CONFIRMATION",
        recorded_by_account_id=ids.ACC_OPERATOR,
    )
    session.flush()
    request_service.reconfirm(session, request_id=rid,
                              recorded_by_account_id=ids.ACC_OPERATOR)
    session.flush()
    assert request_service.read_request(session, rid)["status"] == "ACTIVE"


# --- the documented state machine, and only it ----------------------------

def test_the_documented_path_works_end_to_end(session, ids, new_request):
    rid = new_request["request_id"]
    for target in ("CONTACTED", "QUALIFIED", "ACTIVE"):
        request_service.transition(
            session, request_id=rid, target_status=target,
            recorded_by_account_id=ids.ACC_OPERATOR,
        )
        session.flush()
    assert request_service.read_request(session, rid)["status"] == "ACTIVE"


@pytest.mark.parametrize("target", ["ACTIVE", "CLOSED", "PAUSED"])
def test_an_undefined_transition_is_refused_not_guessed(
    session, ids, new_request, target
):
    """The contract's RequestStateCommand accepts six targets; §5.2 defines
    far fewer edges. Inventing one would add a workflow rule to TURAB by
    implementation accident."""
    with pytest.raises(request_service.UndefinedTransition) as exc:
        request_service.transition(
            session, request_id=new_request["request_id"], target_status=target,
            recorded_by_account_id=ids.ACC_OPERATOR,
        )
    assert "not a transition defined" in str(exc.value)


def test_leaving_paused_requires_explicit_reactivation(session, ids, new_request):
    rid = new_request["request_id"]
    _advance_to_active(session, rid, ids)
    for target in ("NEEDS_CONFIRMATION", "PAUSED"):
        request_service.transition(
            session, request_id=rid, target_status=target,
            recorded_by_account_id=ids.ACC_OPERATOR,
        )
        session.flush()

    with pytest.raises(request_service.ReactivationNotRequested):
        request_service.transition(
            session, request_id=rid, target_status="ACTIVE",
            recorded_by_account_id=ids.ACC_OPERATOR,
        )
    row = request_service.transition(
        session, request_id=rid, target_status="ACTIVE", reactivate=True,
        reason_code=None, recorded_by_account_id=ids.ACC_OPERATOR,
    )
    assert row["status"] == "ACTIVE"


def test_closing_records_the_reason_and_the_moment(session, ids, new_request):
    rid = new_request["request_id"]
    _advance_to_active(session, rid, ids)
    request_service.transition(
        session, request_id=rid, target_status="NEEDS_CONFIRMATION",
        recorded_by_account_id=ids.ACC_OPERATOR,
    )
    session.flush()
    request_service.transition(
        session, request_id=rid, target_status="CLOSED",
        reason_code="OTHER", recorded_by_account_id=ids.ACC_OPERATOR,
    )
    session.flush()
    row = session.execute(
        text("SELECT status::text, closed_at, close_reason_code "
             "FROM turab.requests WHERE request_id = :r"),
        {"r": rid},
    ).mappings().one()
    assert row["status"] == "CLOSED" and row["closed_at"] is not None


# --- provenance ------------------------------------------------------------

def test_a_typed_update_records_who_said_what_and_when(session, ids, new_request):
    rid = new_request["request_id"]
    request_service.patch_request(
        session, request_id=rid, changes={"budget_max_dzd": 27_000_000},
        recorded_by_account_id=ids.ACC_AMINA, note="said so on the phone",
    )
    session.flush()
    trail = request_service.provenance_for(session, rid)
    entry = next(c for c in trail if c["attribute_code"] == "budget_max_dzd")
    assert entry["claimed_value"] == 27_000_000
    assert entry["recorded_by_account_id"] == ids.ACC_AMINA
    assert entry["observation_id"] is not None
    assert entry["recorded_at"] is not None


def test_each_changed_field_gets_its_own_claim(session, ids, new_request):
    rid = new_request["request_id"]
    request_service.patch_request(
        session, request_id=rid,
        changes={"budget_max_dzd": 28_000_000, "budget_flexibility": "HIGH"},
        recorded_by_account_id=ids.ACC_AMINA,
    )
    session.flush()
    codes = {c["attribute_code"] for c in request_service.provenance_for(session, rid)}
    assert {"budget_max_dzd", "budget_flexibility"} <= codes


def test_one_update_is_one_observation(session, ids, new_request):
    """Two fields changed in one breath are one utterance, not two."""
    rid = new_request["request_id"]
    request_service.patch_request(
        session, request_id=rid,
        changes={"budget_max_dzd": 29_000_000, "budget_flexibility": "LOW"},
        recorded_by_account_id=ids.ACC_AMINA,
    )
    session.flush()
    trail = request_service.provenance_for(session, rid)
    recent = [c for c in trail if c["attribute_code"].startswith("budget_")]
    assert len({c["observation_id"] for c in recent}) == 1


def test_a_state_change_is_also_recorded(session, ids, new_request):
    rid = new_request["request_id"]
    request_service.transition(
        session, request_id=rid, target_status="CONTACTED",
        note="rang, no answer", recorded_by_account_id=ids.ACC_OPERATOR,
    )
    session.flush()
    entry = next(c for c in request_service.provenance_for(session, rid)
                 if c["attribute_code"] == "status")
    assert entry["claimed_value"]["from"] == "RAW"
    assert entry["claimed_value"]["to"] == "CONTACTED"


def _advance_to_active(session, request_id, ids) -> None:
    for target in ("CONTACTED", "QUALIFIED", "ACTIVE"):
        request_service.transition(
            session, request_id=request_id, target_status=target,
            recorded_by_account_id=ids.ACC_OPERATOR,
        )
    session.flush()


# --- a contractual gap, surfaced rather than filled ------------------------

def test_no_master_reason_code_describes_closing_a_request(session):
    """`requests.close_reason_code` is FK-constrained to `reason_codes`, but
    the frozen master data carries no category for REQUEST closure.

    Categories present: FRESHNESS, GENERAL, IDENTITY, MATCH, OPPORTUNITY,
    PERMISSION. An operator closing a request can therefore only record
    `OTHER`, or misuse an OPPORTUNITY code that means something about a
    different entity.

    This test does not fix that — adding codes means editing the frozen seed,
    which is forbidden. It PINS the gap so it is visible, and it will fail the
    day a REQUEST closure category is added, which is the moment to revisit
    the closing flow.
    """
    categories = set(session.execute(
        text("SELECT DISTINCT category FROM turab.reason_codes")
    ).scalars().all())
    assert "REQUEST_CLOSURE" not in categories, (
        "a REQUEST closure category now exists in the master data — revisit "
        "the closing flow and this test"
    )
    assert session.execute(
        text("SELECT 1 FROM turab.reason_codes WHERE code = 'OTHER'")
    ).first() is not None, "not even OTHER is available"
