"""Who said what, when, and how it reached TURAB — for any subject.

Extracted from `requests.record_provenance` when Slice 3 needed the same
machinery for PROPERTY and OFFER. It is extracted rather than copied: two
implementations of "record where a fact came from" would drift, and the one
that drifted would be the one nobody was looking at.

`claims` carries four mutually exclusive subject columns and a
`CHECK (num_nonnulls(party_id, request_id, property_id, offer_id) = 1)`, so a
subject is exactly one of four things. `Subject` below is that choice made
explicit, and the check is the reason it cannot be two.

The distinction this module exists to keep is unchanged from Slice 2:

    **A staff member typing a value is not evidence that the party said it.**

`channel` says how the change arrived, `recorded_by_account_id` says who typed
it, and `source_reference` says which call, message or document backs it — or
is NULL, which is the honest statement that nobody recorded where it came from.

`claims.effective_verification_level` is left at its schema default of
`DECLARED` for every row written here. **Nothing in this path raises a
verification level.** That is what `verification_events` is for, and the
database raises it there through `trg_apply_verification_event`; a staff member
retyping a value is not a verification of it.
"""
from __future__ import annotations

import json
import uuid
from enum import StrEnum
from typing import Any, Mapping


#: How a recorded change reached TURAB. Distinct from WHO recorded it.
class UpdateChannel(StrEnum):
    #: The party's own account submitted it.
    SELF_SERVICE = "SELF_SERVICE"
    #: A member of staff typed it in. This says who typed it — NOT that the
    #: party said it. See `source_reference`.
    STAFF_RECORDED = "STAFF_RECORDED"


class Subject(StrEnum):
    """Which of `claims`' four subject columns this fact is about."""

    PARTY = "party_id"
    REQUEST = "request_id"
    PROPERTY = "property_id"
    OFFER = "offer_id"


def record(
    session,
    *,
    subject: Subject,
    subject_id: uuid.UUID,
    party_id: uuid.UUID | None,
    changes: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    recorded_by_account_id: uuid.UUID | None,
    channel: UpdateChannel,
    source_reference: uuid.UUID | None = None,
    note: str | None = None,
    observation_kind: str = "FORM_SUBMISSION",
) -> uuid.UUID:
    """Write one `observations` row and one `claims` row per changed field.

    `party_id` is the party the observation is *about*, which for a PROPERTY
    may legitimately be NULL: a property has no `party_id` column, and the
    party related to it lives in `party_property_relations`, which nothing may
    yet create (G3-6) and which is never an authorization source (R4.5). So a
    property observation records no party rather than inventing one — see
    `properties.py` for why that is the honest answer and not a shortcut.
    """
    channel = UpdateChannel(channel)
    subject = Subject(subject)

    payload: dict[str, Any] = {
        "channel": channel.value,
        "source_recorded": source_reference is not None,
        "after": changes,
    }
    if previous is not None:
        payload["before"] = {k: previous.get(k) for k in changes}

    observation_id = session.execute(
        _text(
            """INSERT INTO turab.observations
                      (kind, party_id, observed_at, raw_text, payload,
                       recorded_by_account_id, source_id)
               VALUES (CAST(:kind AS turab.observation_kind), :party_id,
                       clock_timestamp(), :note, CAST(:payload AS jsonb),
                       :account, :source)
            RETURNING observation_id"""
        ),
        {
            "kind": observation_kind,
            "party_id": party_id,
            "note": note,
            "payload": json.dumps(payload, default=str),
            "account": recorded_by_account_id,
            "source": source_reference,
        },
    ).scalar_one()

    for attribute_code, value in changes.items():
        session.execute(
            _text(
                f"""INSERT INTO turab.claims
                          ({subject.value}, attribute_code, claimed_value,
                           asserted_by_party_id, observation_id, source_id,
                           extracted_by, observed_at, recorded_by_account_id)
                    VALUES (:subject_id, :code, CAST(:value AS jsonb),
                            :asserted_by, :observation_id, :source,
                            :extracted_by, clock_timestamp(), :account)"""
            ),
            {
                "subject_id": subject_id,
                "code": attribute_code,
                "value": json.dumps(value, default=str),
                # Attributed to the party ONLY when the party's own account
                # submitted it. A staff-recorded change asserts nothing about
                # what the party said, so it names no asserting party.
                "asserted_by": party_id if channel is UpdateChannel.SELF_SERVICE else None,
                "observation_id": observation_id,
                "source": source_reference,
                "extracted_by": channel.value,
                "account": recorded_by_account_id,
            },
        )
    return observation_id


def read(session, *, subject: Subject, subject_id: uuid.UUID) -> list[Mapping[str, Any]]:
    """The recorded provenance for one subject, oldest first."""
    subject = Subject(subject)
    return session.execute(
        _text(
            f"""SELECT c.attribute_code, c.claimed_value, c.observation_id,
                       c.extracted_by AS channel, c.recorded_at,
                       c.recorded_by_account_id, c.asserted_by_party_id,
                       c.source_id,
                       (c.source_id IS NOT NULL) AS source_recorded,
                       c.effective_verification_level::text AS verification_level,
                       c.status::text AS status,
                       o.payload AS observation_payload
                  FROM turab.claims c
                  LEFT JOIN turab.observations o
                         ON o.observation_id = c.observation_id
                 WHERE c.{subject.value} = :s
                 ORDER BY c.recorded_at, c.attribute_code"""
        ),
        {"s": subject_id},
    ).mappings().all()


def _text(sql: str):
    from sqlalchemy import text

    return text(sql)
