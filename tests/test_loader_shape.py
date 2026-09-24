"""The SHAPE of the customer loaders — RFC-001 R10.3 and R5.2.

R10.3: object authorization is structural — the loader's query carries the
authority predicate. R5.2: filter, never fetch-then-compare.

HTTP tests cannot prove this. A loader that fetches a row by id and then
compares in Python returns the same 404 as one whose query was scoped, so
every behavioural test passes over the defect. `load_offer` shipped in exactly
that shape (review of 0a66f8e). These tests look at the statements a loader
actually sends to PostgreSQL:

  * `load_offer` sends ONE statement, and that statement names the actor;
  * no customer loader sends a statement that reads its resource table
    without an actor parameter in the SAME statement.

A pre-statement that reads OTHER tables — the alias resolution and the INV-1
claim-account guard that `load_property` and `load_request` run — reads no
resource row and is permitted by the second test by construction: it only
inspects statements that read the loader's own table.
"""
from __future__ import annotations

import re
import uuid

import pytest
from sqlalchemy import text

from turab.auth.loaders import LOADERS, ClaimAuthorityConflict, ResourceKind, load_offer

#: Each loader's resource table: reading it IS reading the resource.
_RESOURCE_TABLE = {
    ResourceKind.PARTY: "parties",
    ResourceKind.REQUEST: "requests",
    ResourceKind.PROPERTY: "properties",
    ResourceKind.OFFER: "property_offers",
    ResourceKind.OPPORTUNITY: "opportunities",
    ResourceKind.INTEREST: "interests",
    ResourceKind.CONSENT_GRANT: "consent_grants",
    ResourceKind.THREAD: "communication_threads",
}

#: Parameters that bind a statement to the actor.
_ACTOR_PARAMS = (":account_id", ":subject_party")


class _Recording:
    """A session proxy that records every statement's text, then delegates."""

    def __init__(self, session):
        self._session = session
        self.statements: list[str] = []

    def execute(self, statement, *args, **kwargs):
        self.statements.append(str(statement))
        return self._session.execute(statement, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._session, name)


def _reads(statement: str, table: str) -> bool:
    return re.search(rf"\b(?:FROM|JOIN)\s+turab\.{table}\b", statement) is not None


def test_the_resource_table_map_covers_every_loader():
    assert set(_RESOURCE_TABLE) == set(LOADERS)


@pytest.mark.parametrize("account", ["ACC_AMINA", "ACC_KHADIJA", "ACC_BRAHIM"])
@pytest.mark.parametrize("offer", ["OFFER_ON_CLAIMED", "OFFER_BROKER_SALE",
                                   "OFFER_OWNER_SALE", None])
def test_load_offer_issues_one_authority_scoped_statement(session, ids, subject_of,
                                                          account, offer):
    """Granted, refused, or unknown: always exactly one statement, and it
    carries the actor. A fetch by `offer_id` alone followed by Python checks
    — the shape this replaces — sends two or more, the first without the
    actor, and fails here."""
    recording = _Recording(session)
    offer_id = getattr(ids, offer) if offer else uuid.uuid4()
    load_offer(recording, subject_of(getattr(ids, account)), offer_id)
    assert len(recording.statements) == 1, recording.statements
    statement = recording.statements[0]
    assert _reads(statement, "property_offers")
    assert ":account_id" in statement and ":party_id" in statement


def test_a_contested_parent_is_decided_in_the_same_single_statement(session, ids,
                                                                   subject_of):
    """INV-1 is part of the predicate, not a follow-up query: the conflict is
    raised from the one statement's CONTESTED arm, which carries no offer
    data."""
    prop = session.execute(text(
        """INSERT INTO turab.properties (property_type, supply_mode,
                  management_mode, claim_status, created_by_account_id)
           VALUES ('LAND', 'PUBLIC', 'SELF_MANAGED', 'CLAIMED', :a)
           RETURNING property_id"""), {"a": ids.ACC_OPERATOR}).scalar_one()
    for account in (ids.ACC_AMINA, ids.ACC_KHADIJA):
        session.execute(text("""INSERT INTO turab.record_claim_events
                                       (property_id, claimed_by_account_id)
                                VALUES (:p, :a)"""), {"p": prop, "a": account})
    offer = session.execute(text(
        """INSERT INTO turab.property_offers (property_id, party_id, transaction_type,
                  created_by_account_id)
           VALUES (:p, :party, 'SALE', :a) RETURNING offer_id"""),
        {"p": prop, "party": ids.AMINA, "a": ids.ACC_OPERATOR}).scalar_one()

    recording = _Recording(session)
    with pytest.raises(ClaimAuthorityConflict) as raised:
        load_offer(recording, subject_of(ids.ACC_AMINA), offer)
    assert len(recording.statements) == 1
    assert raised.value.resource_id == prop
    assert raised.value.accounts == frozenset({ids.ACC_AMINA, ids.ACC_KHADIJA})


_SAMPLE_IDS = {
    ResourceKind.PARTY: "AMINA",
    ResourceKind.REQUEST: "REQ_AMINA",
    ResourceKind.PROPERTY: "CLAIMED_HOUSE",
    ResourceKind.OFFER: "OFFER_ON_CLAIMED",
}


@pytest.mark.parametrize("kind", sorted(LOADERS, key=lambda k: k.value),
                         ids=lambda k: k.value)
def test_no_customer_loader_reads_its_resource_without_the_actor(session, ids,
                                                                 subject_of, kind):
    """Every statement that reads the resource table must name the actor.

    Run against a real id where a fixture has one, and a random id otherwise;
    in both cases the loader's own statements are what is inspected.
    """
    recording = _Recording(session)
    name = _SAMPLE_IDS.get(kind)
    resource_id = getattr(ids, name) if name else uuid.uuid4()
    try:
        LOADERS[kind](recording, subject_of(ids.ACC_AMINA), resource_id)
    except ClaimAuthorityConflict:
        pass
    table = _RESOURCE_TABLE[kind]
    reading = [s for s in recording.statements if _reads(s, table)]
    assert reading, f"{kind.value}: the loader never read {table}"
    for statement in reading:
        assert any(p in statement for p in _ACTOR_PARAMS), (
            f"{kind.value}: a statement reads turab.{table} without the actor — "
            f"fetch-then-compare (R5.2):\n{statement}")
