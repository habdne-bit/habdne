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

import subprocess
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from turab.services import freshness, requests as request_service
from turab.services.requests import UpdateChannel


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
            channel=UpdateChannel.SELF_SERVICE,
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
            channel=UpdateChannel.SELF_SERVICE,
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
    # From RAW, none of these is defined: the only edge out of RAW is
    # CONTACTED. ACTIVE -> PAUSED and ACTIVE -> CLOSED are adopted, and are
    # tested as permitted below.
    """The contract's RequestStateCommand accepts six targets; §5.2 defines
    far fewer edges. Inventing one would add a workflow rule to TURAB by
    implementation accident."""
    with pytest.raises(request_service.UndefinedTransition) as exc:
        request_service.transition(
            session, request_id=new_request["request_id"], target_status=target,
            recorded_by_account_id=ids.ACC_OPERATOR,
        )
    assert "not a transition defined" in str(exc.value)


def test_reactivation_is_the_explicit_command_itself(session, ids, new_request):
    """§5.2: "PAUSED/CLOSED -> ACTIVE only by explicit reactivation".

    Sending `target_status=ACTIVE` to the state command from PAUSED IS that
    explicit act. An earlier draft demanded an extra `reactivate` flag — an
    undeclared field, and a second way of saying what the contract already
    expresses.

    The request is reconfirmed first because reactivation is also subject to
    the freshness condition (R-S2-04); the refusal path is below.
    """
    rid = new_request["request_id"]
    _advance_to_active(session, rid, ids)
    request_service.reconfirm(session, request_id=rid,
                              recorded_by_account_id=ids.ACC_OPERATOR)
    request_service.transition(
        session, request_id=rid, target_status="PAUSED",
        recorded_by_account_id=ids.ACC_OPERATOR,
    )
    session.flush()

    row = request_service.transition(
        session, request_id=rid, target_status="ACTIVE",
        recorded_by_account_id=ids.ACC_OPERATOR,
    )
    assert row["status"] == "ACTIVE"


def test_reactivation_does_not_refresh_the_confirmation(session, ids, new_request):
    """Reactivating must not silently renew the confirmation date."""
    rid = new_request["request_id"]
    _advance_to_active(session, rid, ids)
    request_service.reconfirm(session, request_id=rid,
                              recorded_by_account_id=ids.ACC_OPERATOR)
    request_service.transition(
        session, request_id=rid, target_status="PAUSED",
        recorded_by_account_id=ids.ACC_OPERATOR,
    )
    session.flush()
    before = request_service.read_request(session, rid)["last_confirmed_at"]

    request_service.transition(
        session, request_id=rid, target_status="ACTIVE",
        recorded_by_account_id=ids.ACC_OPERATOR,
    )
    session.flush()
    assert request_service.read_request(session, rid)["last_confirmed_at"] == before


# --- R-S2-04: reactivation is subject to the freshness condition ----------

def test_a_stale_paused_request_cannot_be_reactivated(session, ids, new_request):
    """The closing decision kept reactivation "subject to the activation and
    freshness conditions". The transition table alone does not deliver that: a
    request paused two years ago would come back ACTIVE carrying a
    confirmation nobody has checked since."""
    rid = new_request["request_id"]
    _advance_to_active(session, rid, ids)
    days, _ = freshness.request_threshold_days(session)
    session.execute(
        text("UPDATE turab.requests SET last_confirmed_at = :t WHERE request_id = :r"),
        {"t": datetime.now(UTC) - timedelta(days=days + 1), "r": rid},
    )
    request_service.transition(
        session, request_id=rid, target_status="PAUSED",
        recorded_by_account_id=ids.ACC_OPERATOR,
    )
    session.flush()

    with pytest.raises(request_service.ReactivationNeedsConfirmation) as exc:
        request_service.transition(
            session, request_id=rid, target_status="ACTIVE",
            recorded_by_account_id=ids.ACC_OPERATOR,
        )
    assert "Reconfirm it first" in str(exc.value)
    assert request_service.read_request(session, rid)["status"] == "PAUSED"


def test_a_never_confirmed_paused_request_cannot_be_reactivated(
    session, ids, new_request
):
    rid = new_request["request_id"]
    _advance_to_active(session, rid, ids)
    request_service.transition(
        session, request_id=rid, target_status="PAUSED",
        recorded_by_account_id=ids.ACC_OPERATOR,
    )
    session.flush()
    assert request_service.read_request(session, rid)["last_confirmed_at"] is None

    with pytest.raises(request_service.ReactivationNeedsConfirmation) as exc:
        request_service.transition(
            session, request_id=rid, target_status="ACTIVE",
            recorded_by_account_id=ids.ACC_OPERATOR,
        )
    assert "never confirmed" in str(exc.value)


def test_reconfirm_then_reactivate_is_the_two_step_path(session, ids, new_request):
    """`/reconfirm` deliberately does not move a PAUSED request, so the
    operator takes both steps explicitly and each is recorded."""
    rid = new_request["request_id"]
    _advance_to_active(session, rid, ids)
    days, _ = freshness.request_threshold_days(session)
    session.execute(
        text("UPDATE turab.requests SET last_confirmed_at = :t WHERE request_id = :r"),
        {"t": datetime.now(UTC) - timedelta(days=days + 1), "r": rid},
    )
    request_service.transition(
        session, request_id=rid, target_status="PAUSED",
        recorded_by_account_id=ids.ACC_OPERATOR,
    )
    session.flush()

    request_service.reconfirm(session, request_id=rid,
                              recorded_by_account_id=ids.ACC_OPERATOR)
    session.flush()
    assert request_service.read_request(session, rid)["status"] == "PAUSED", (
        "reconfirming must not reactivate on its own"
    )

    row = request_service.transition(
        session, request_id=rid, target_status="ACTIVE",
        recorded_by_account_id=ids.ACC_OPERATOR,
    )
    assert row["status"] == "ACTIVE"


def test_the_freshness_check_on_reactivation_reads_the_active_policy(
    session, ids, new_request
):
    """Not a constant in the transition code: with no active policy the
    reactivation cannot be judged, and fails rather than assuming."""
    rid = new_request["request_id"]
    _advance_to_active(session, rid, ids)
    request_service.reconfirm(session, request_id=rid,
                              recorded_by_account_id=ids.ACC_OPERATOR)
    request_service.transition(
        session, request_id=rid, target_status="PAUSED",
        recorded_by_account_id=ids.ACC_OPERATOR,
    )
    session.execute(text("UPDATE turab.matching_policies SET active = false"))
    session.flush()

    with pytest.raises(freshness.NoActiveFreshnessPolicy):
        request_service.transition(
            session, request_id=rid, target_status="ACTIVE",
            recorded_by_account_id=ids.ACC_OPERATOR,
        )


def test_a_future_confirmation_is_refused(session, ids, new_request):
    """A confirmation records something that has already happened. Accepting a
    future date would let one call place a request outside the freshness
    window indefinitely."""
    rid = new_request["request_id"]
    with pytest.raises(request_service.ConfirmationInTheFuture):
        request_service.reconfirm(
            session, request_id=rid,
            confirmed_at=datetime(2099, 1, 1, tzinfo=UTC),
            recorded_by_account_id=ids.ACC_OPERATOR,
        )
    assert request_service.read_request(session, rid)["last_confirmed_at"] is None


def test_a_historical_confirmation_is_still_accepted(session, ids, new_request):
    """Only the future is refused: recording that someone confirmed last week
    is legitimate and must keep working."""
    rid = new_request["request_id"]
    when = datetime.now(UTC) - timedelta(days=7)
    row = request_service.reconfirm(
        session, request_id=rid, confirmed_at=when,
        recorded_by_account_id=ids.ACC_OPERATOR,
    )
    assert row["last_confirmed_at"] is not None
    assert row["last_confirmed_at"] < datetime.now(UTC)


def test_reconfirming_does_not_resurrect_a_paused_or_closed_request(
    session, ids, new_request
):
    """It was stopped for a reason unrelated to freshness; confirming that its
    details are still true must not reverse a decision nobody revisited."""
    rid = new_request["request_id"]
    _advance_to_active(session, rid, ids)
    request_service.transition(
        session, request_id=rid, target_status="PAUSED",
        recorded_by_account_id=ids.ACC_OPERATOR,
    )
    session.flush()
    request_service.reconfirm(session, request_id=rid,
                              recorded_by_account_id=ids.ACC_OPERATOR)
    session.flush()
    assert request_service.read_request(session, rid)["status"] == "PAUSED"


@pytest.mark.parametrize("target", ["PAUSED", "CLOSED"])
def test_an_active_request_may_be_paused_or_closed_directly(
    session, ids, new_request, target
):
    """Adopted: a request is not required to pass through NEEDS_CONFIRMATION
    in order to be paused or closed."""
    rid = new_request["request_id"]
    _advance_to_active(session, rid, ids)
    row = request_service.transition(
        session, request_id=rid, target_status=target,
        reason_code="REQUEST_WITHDRAWN" if target == "CLOSED" else None,
        recorded_by_account_id=ids.ACC_OPERATOR,
    )
    assert row["status"] == target


def test_closing_records_the_reason_and_the_moment(session, ids, new_request):
    rid = new_request["request_id"]
    _advance_to_active(session, rid, ids)
    request_service.transition(
        session, request_id=rid, target_status="CLOSED",
        reason_code="REQUEST_FULFILLED", recorded_by_account_id=ids.ACC_OPERATOR,
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
        recorded_by_account_id=ids.ACC_AMINA,
            channel=UpdateChannel.SELF_SERVICE, note="said so on the phone",
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
            channel=UpdateChannel.SELF_SERVICE,
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
            channel=UpdateChannel.SELF_SERVICE,
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

def test_the_adopted_closure_reasons_exist(session):
    codes = session.execute(
        text("""SELECT code FROM turab.reason_codes
                 WHERE category = 'REQUEST_CLOSURE' AND active ORDER BY code""")
    ).scalars().all()
    assert codes == [
        "REQUEST_CLOSED_OTHER", "REQUEST_FULFILLED", "REQUEST_WITHDRAWN"
    ]


def test_closing_requires_a_reason(session, ids, new_request):
    rid = new_request["request_id"]
    _advance_to_active(session, rid, ids)
    with pytest.raises(request_service.ClosureReasonRequired):
        request_service.transition(
            session, request_id=rid, target_status="CLOSED",
            recorded_by_account_id=ids.ACC_OPERATOR,
        )


@pytest.mark.parametrize("code", ["OTHER", "BUYER_REJECTED", "REQUEST_STALE"])
def test_a_reason_from_another_category_is_refused(session, ids, new_request, code):
    """An OPPORTUNITY code describes a different entity; the historical
    GENERAL/OTHER keeps its own meaning and is not repurposed."""
    rid = new_request["request_id"]
    _advance_to_active(session, rid, ids)
    with pytest.raises(request_service.UnknownReasonCode):
        request_service.transition(
            session, request_id=rid, target_status="CLOSED", reason_code=code,
            recorded_by_account_id=ids.ACC_OPERATOR,
        )


def test_the_other_closure_reason_requires_a_note(session, ids, new_request):
    rid = new_request["request_id"]
    _advance_to_active(session, rid, ids)
    with pytest.raises(request_service.ClosureNoteRequired):
        request_service.transition(
            session, request_id=rid, target_status="CLOSED",
            reason_code="REQUEST_CLOSED_OTHER", note="   ",
            recorded_by_account_id=ids.ACC_OPERATOR,
        )
    row = request_service.transition(
        session, request_id=rid, target_status="CLOSED",
        reason_code="REQUEST_CLOSED_OTHER", note="moved to another city",
        recorded_by_account_id=ids.ACC_OPERATOR,
    )
    assert row["status"] == "CLOSED"


def test_closing_is_not_a_substitute_for_staleness_or_pausing(session):
    """The adopted codes describe what the REQUESTER reported. None of them
    means 'we lost track of it' — that is NEEDS_CONFIRMATION — and none means
    'on hold', which is PAUSED."""
    assert set(request_service.TRANSITIONS["ACTIVE"]) == {
        "NEEDS_CONFIRMATION", "PAUSED", "CLOSED"
    }
    assert request_service.CLOSURE_CATEGORY == "REQUEST_CLOSURE"


# --- G-1: the actor is not the source ------------------------------------

def test_a_self_service_change_is_attributed_to_the_party(session, ids, new_request):
    rid = new_request["request_id"]
    request_service.patch_request(
        session, request_id=rid, changes={"budget_max_dzd": 31_000_000},
        recorded_by_account_id=ids.ACC_AMINA,
        channel=UpdateChannel.SELF_SERVICE,
    )
    session.flush()
    entry = _entry(session, rid, "budget_max_dzd")
    assert entry["channel"] == "SELF_SERVICE"
    assert entry["asserted_by_party_id"] == ids.AMINA
    assert entry["recorded_by_account_id"] == ids.ACC_AMINA


def test_a_staff_recorded_change_asserts_nothing_about_the_party(
    session, ids, new_request
):
    """The rule this whole mechanism exists for: a staff member typing a value
    is NOT evidence that the customer asked for it."""
    rid = new_request["request_id"]
    request_service.patch_request(
        session, request_id=rid, changes={"budget_max_dzd": 32_000_000},
        recorded_by_account_id=ids.ACC_OPERATOR,
        channel=UpdateChannel.STAFF_RECORDED,
    )
    session.flush()
    entry = _entry(session, rid, "budget_max_dzd")
    assert entry["channel"] == "STAFF_RECORDED"
    assert entry["recorded_by_account_id"] == ids.ACC_OPERATOR
    assert entry["asserted_by_party_id"] is None, (
        "a staff-recorded change must not be attributed to the party"
    )


def test_the_absence_of_a_source_is_recorded_as_such(session, ids, new_request):
    """`RequestPatch` carries no field for a call or message reference, so
    there is none to record. The record says so rather than staying silent."""
    rid = new_request["request_id"]
    request_service.patch_request(
        session, request_id=rid, changes={"budget_max_dzd": 33_000_000},
        recorded_by_account_id=ids.ACC_OPERATOR,
        channel=UpdateChannel.STAFF_RECORDED,
    )
    session.flush()
    entry = _entry(session, rid, "budget_max_dzd")
    assert entry["source_recorded"] is False
    assert entry["source_id"] is None


def test_a_recorded_source_is_carried_when_one_exists(session, ids, new_request):
    """The service can carry one; only the contract cannot yet supply it."""
    rid = new_request["request_id"]
    source_id = session.execute(
        text("""INSERT INTO turab.sources (kind, title)
                VALUES ('PHONE_CALL', 'call note') RETURNING source_id"""),
    ).scalar_one()
    request_service.patch_request(
        session, request_id=rid, changes={"budget_max_dzd": 34_000_000},
        recorded_by_account_id=ids.ACC_OPERATOR,
        channel=UpdateChannel.STAFF_RECORDED, source_reference=source_id,
    )
    session.flush()
    entry = _entry(session, rid, "budget_max_dzd")
    assert entry["source_recorded"] is True
    assert entry["source_id"] == source_id


def test_the_previous_value_is_recorded(session, ids, new_request):
    rid = new_request["request_id"]
    before = request_service.read_request(session, rid)["budget_target_dzd"]
    request_service.patch_request(
        session, request_id=rid, changes={"budget_target_dzd": 21_000_000},
        recorded_by_account_id=ids.ACC_AMINA,
        channel=UpdateChannel.SELF_SERVICE,
    )
    session.flush()
    entry = _entry(session, rid, "budget_target_dzd")
    assert entry["observation_payload"]["before"]["budget_target_dzd"] == before
    assert entry["observation_payload"]["after"]["budget_target_dzd"] == 21_000_000


def test_no_update_raises_the_verification_level(session, ids, new_request):
    """Raising it is what `verification_events` is for. A staff member
    retyping a value is not a verification of it."""
    rid = new_request["request_id"]
    for channel, account in (
        (UpdateChannel.SELF_SERVICE, ids.ACC_AMINA),
        (UpdateChannel.STAFF_RECORDED, ids.ACC_OPERATOR),
    ):
        request_service.patch_request(
            session, request_id=rid, changes={"budget_max_dzd": 35_000_000},
            recorded_by_account_id=account, channel=channel,
        )
        session.flush()
    levels = {
        c["verification_level"]
        for c in request_service.provenance_for(session, rid)
    }
    assert levels == {"DECLARED"}


def _entry(session, request_id, attribute_code):
    entries = [
        c for c in request_service.provenance_for(session, request_id)
        if c["attribute_code"] == attribute_code
    ]
    assert entries, f"no provenance recorded for {attribute_code}"
    return entries[-1]


# --- G-5: the freshness pass is a command someone runs --------------------
#
# These four tests run the real command in a SUBPROCESS, so their data has to
# be genuinely committed — the `session` fixture wraps each test in a rolled
# back transaction that another connection cannot see.

def _committed_active_request(engine, ids, *, confirmed_days_ago: int):
    """A committed ACTIVE request, aged as asked. Left behind afterwards:
    `prevent_core_delete()` forbids hard-deleting a core record, and a test
    that worked around that trigger would be testing an impossible database.
    """
    with Session(bind=engine, future=True) as s:
        row = request_service.create_request(
            s, party_id=ids.AMINA, transaction_intent="BUY",
            intent="ACTIVE_SEARCH", management_mode="SELF_MANAGED",
            claim_status="CLAIMED", created_by_account_id=ids.ACC_AMINA,
        )
        rid = row["request_id"]
        for target in ("CONTACTED", "QUALIFIED", "ACTIVE"):
            request_service.transition(
                s, request_id=rid, target_status=target,
                recorded_by_account_id=ids.ACC_OPERATOR,
            )
        s.execute(
            text("UPDATE turab.requests SET last_confirmed_at = :t "
                 "WHERE request_id = :r"),
            {"t": datetime.now(UTC) - timedelta(days=confirmed_days_ago), "r": rid},
        )
        s.commit()
    return rid


def _status(engine, request_id) -> str:
    with Session(bind=engine, future=True) as s:
        return s.execute(
            text("SELECT status::text FROM turab.requests WHERE request_id = :r"),
            {"r": request_id},
        ).scalar_one()


def _run_pass(engine, *args) -> subprocess.CompletedProcess:
    import os
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    url = engine.url.render_as_string(hide_password=False)
    return subprocess.run(
        [str(root / ".venv" / "bin" / "python"),
         str(root / "db" / "dev" / "run_freshness_pass.py"), *args],
        cwd=root, capture_output=True, text=True,
        env={**os.environ, "TURAB_DATABASE_URL": url},
    )


def test_the_freshness_command_moves_stale_requests(engine, ids):
    rid = _committed_active_request(engine, ids, confirmed_days_ago=40)
    result = _run_pass(engine)
    assert result.returncode == 0, result.stderr
    assert str(rid) in result.stdout
    assert _status(engine, rid) == "NEEDS_CONFIRMATION"


def test_running_it_twice_moves_nothing_the_second_time(engine, ids):
    """Re-running must be safe: the first run leaves nothing for the second."""
    rid = _committed_active_request(engine, ids, confirmed_days_ago=45)
    first = _run_pass(engine)
    second = _run_pass(engine)
    assert first.returncode == second.returncode == 0, first.stderr + second.stderr
    assert str(rid) in first.stdout
    assert str(rid) not in second.stdout
    assert _status(engine, rid) == "NEEDS_CONFIRMATION"


def test_a_reconfirmed_request_is_left_alone_by_the_pass(engine, ids):
    rid = _committed_active_request(engine, ids, confirmed_days_ago=50)
    with Session(bind=engine, future=True) as s:
        request_service.reconfirm(s, request_id=rid,
                                  recorded_by_account_id=ids.ACC_OPERATOR)
        s.commit()

    result = _run_pass(engine)
    assert result.returncode == 0, result.stderr
    assert str(rid) not in result.stdout
    assert _status(engine, rid) == "ACTIVE"


def test_the_dry_run_changes_nothing(engine, ids):
    rid = _committed_active_request(engine, ids, confirmed_days_ago=55)
    result = _run_pass(engine, "--dry-run")
    assert result.returncode == 0, result.stderr
    assert str(rid) in result.stdout
    assert _status(engine, rid) == "ACTIVE", "a dry run must not move anything"


def test_nothing_in_the_application_calls_the_pass_by_itself():
    """There is no scheduler. A report claiming self-maintaining freshness
    would be wrong, and this test is what keeps that honest."""
    import pathlib

    callers = [
        path.name for path in pathlib.Path("src/turab").rglob("*.py")
        if "mark_stale_as_needing_confirmation(" in path.read_text(encoding="utf-8")
        and path.name != "requests.py"
    ]
    assert not callers, f"{callers} invoke the pass; there is no scheduler"
