"""The truth layer: observation → claim → verification → resolution.

Slice 3, step 5. Ref: `docs/gate/SLICE_3_PLAN.md` §3.1, §3.2, §3.7 (G3-4),
§3.8, §3.9, §6.3; the contract's `ObservationInput`, `ClaimInput`,
`VerificationEventInput`, `ResolutionInput`; schema triggers
`trg_apply_verification_event`, `trg_resolution_lineage`,
`trg_property_attribute_claim`, and the four `ux_resolved_current_*` indexes.

What each layer means, and what this module refuses to blur:

  * an OBSERVATION is something seen or heard, with where it came from;
  * a CLAIM is one assertion about one attribute of one subject, born
    `DECLARED` — the contract gives the input no level field (§3.1);
  * a VERIFICATION EVENT is the only way a claim's level rises, and the
    DATABASE raises it (`trg_apply_verification_event`). This module never
    writes `effective_verification_level`: a second write would race the
    trigger (§3.1);
  * a RESOLUTION is the current operational value, chosen by an acting
    account, closing — never overwriting — the one before (§3.7).

**Subjects.** PROPERTY is delivered in full. PARTY, REQUEST and OFFER are
refused for claims and resolutions with `AttributeVocabularyUndecided`: the
controlled vocabulary (§3.9) is `attribute_definitions`, whose `applies_to`
is a list of PROPERTY TYPES and which registers no attribute of a party, a
request or an offer. Accepting a property attribute code about a party would
be permissive by accident; inventing a vocabulary for them would be a
decision. See `docs/gate/SLICE_3_STEP5_DELIVERY.md` (finding G3-11).
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import audit_rows

SUBJECT_COLUMN = {"PARTY": "party_id", "REQUEST": "request_id",
                  "PROPERTY": "property_id", "OFFER": "offer_id"}

#: The subjects the controlled vocabulary actually covers (G3-11).
DELIVERED_SUBJECTS = frozenset({"PROPERTY"})

CONFIRMING_OUTCOME = "CONFIRMED"


class TruthError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        self.code, self.detail = code, detail
        super().__init__(detail)


class NotFound(TruthError):
    def __init__(self, what: str) -> None:
        super().__init__("NOT_FOUND", f"no such {what}")


class Invalid(TruthError):
    def __init__(self, detail: str) -> None:
        super().__init__("VALIDATION_FAILED", detail)


class AttributeVocabularyUndecided(TruthError):
    def __init__(self, subject_type: str) -> None:
        super().__init__(
            "ATTRIBUTE_VOCABULARY_UNDECIDED",
            f"claims and resolutions about a {subject_type} are not available "
            "in this version: the controlled attribute vocabulary "
            "(attribute_definitions) registers property attributes only, and "
            f"no vocabulary for a {subject_type} has been decided (G3-11)",
        )


class ActorRequired(TruthError):
    """§3.7 condition 4. A resolution needs an acting account.

    The schema has no human/machine account distinction, so what this
    enforces is exactly: no resolution without an authenticated actor. A
    background job has none (it runs actor-less, `require_actor=False`), so
    it is refused. A machine holding a user's token cannot be told apart —
    stated, not claimed away.
    """

    def __init__(self) -> None:
        super().__init__(
            "ACTION_NOT_PERMITTED",
            "a resolution must be issued by an acting account; an actor-less "
            "caller such as a background job cannot issue one",
        )


def _now(session: Session) -> datetime:
    return session.execute(text("SELECT clock_timestamp()")).scalar_one()


def _exists(session: Session, table: str, column: str, value) -> bool:
    return session.execute(
        text(f"SELECT 1 FROM turab.{table} WHERE {column} = :v"), {"v": value}
    ).first() is not None


def _not_future(session: Session, when: datetime | None, field: str) -> None:
    if when is not None and when > _now(session):
        raise Invalid(f"{field} cannot be in the future; it records something "
                      "that has already happened")


# --- subjects ---------------------------------------------------------------

def _subject(session: Session, subject_type: str, subject_id: uuid.UUID, *,
             lock: bool = False) -> Mapping[str, Any]:
    """The subject row, or a refusal. PROPERTY only (G3-11); an identity alias
    is refused like every other new write aimed at one (decision F-2)."""
    if subject_type not in SUBJECT_COLUMN:
        raise Invalid(f"subject.type must be one of {sorted(SUBJECT_COLUMN)}")
    if subject_type not in DELIVERED_SUBJECTS:
        raise AttributeVocabularyUndecided(subject_type)
    row = session.execute(
        text("SELECT property_id, property_type::text AS property_type "
             "FROM turab.properties WHERE property_id = :p"
             + (" FOR UPDATE" if lock else "")),
        {"p": subject_id},
    ).mappings().first()
    if row is None:
        raise NotFound("property")
    from .properties import AliasNotCanonical, refuse_alias

    try:
        refuse_alias(session, subject_id)
    except AliasNotCanonical as exc:
        raise TruthError(exc.code, exc.detail) from exc
    return row


# --- the controlled vocabulary: ONE validator, three call sites (§3.9) -------

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_attribute(session: Session, *, property_type: str,
                       attribute_code: str, value: Any) -> Mapping[str, Any]:
    """Read `attribute_definitions` / `attribute_options`; copy nothing.

    Called by claims, resolutions and property_attributes updates alike, so
    the three cannot drift (§3.9). Returns the definition row.
    """
    definition = session.execute(
        text("""SELECT attribute_definition_id, code, value_type, active,
                       applies_to::text[] AS applies_to
                  FROM turab.attribute_definitions WHERE code = :c"""),
        {"c": attribute_code},
    ).mappings().first()
    if definition is None:
        raise Invalid(f"attribute_code {attribute_code!r} is not a registered "
                      "attribute")
    if not definition["active"]:
        raise Invalid(f"attribute_code {attribute_code!r} is not active")
    applies_to = definition["applies_to"]
    if applies_to is not None and property_type not in applies_to:
        raise Invalid(f"attribute {attribute_code!r} does not apply to a "
                      f"{property_type}; it applies to {sorted(applies_to)}")

    kind = definition["value_type"]
    if kind == "ENUM":
        registered = session.execute(
            text("""SELECT 1 FROM turab.attribute_options
                     WHERE attribute_definition_id = :d AND option_code = :o
                       AND active"""),
            {"d": definition["attribute_definition_id"],
             "o": value if isinstance(value, str) else None},
        ).first()
        if not isinstance(value, str) or registered is None:
            raise Invalid(f"{value!r} is not a registered, active option of "
                          f"{attribute_code!r}")
    elif kind == "NUMBER":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise Invalid(f"{attribute_code!r} takes a JSON number")
    elif kind == "BOOLEAN":
        if not isinstance(value, bool):
            raise Invalid(f"{attribute_code!r} takes a JSON boolean")
    elif kind == "TEXT":
        if not isinstance(value, str):
            raise Invalid(f"{attribute_code!r} takes a JSON string")
    elif kind == "DATE":
        try:
            ok = isinstance(value, str) and bool(_DATE.match(value)) \
                and date.fromisoformat(value) is not None
        except ValueError:
            ok = False
        if not ok:
            raise Invalid(f"{attribute_code!r} takes a date as YYYY-MM-DD")
    # JSON: any JSON value.
    return definition


# --- observations -----------------------------------------------------------

def record_observation(
    session: Session, *, kind: str, source_id=None, party_id=None,
    observed_at: datetime | None = None, raw_text: str | None = None,
    payload: Mapping[str, Any] | None = None,
    recorded_by_account_id: uuid.UUID,
) -> Mapping[str, Any]:
    if source_id is not None and not _exists(session, "sources", "source_id", source_id):
        raise Invalid(f"source_id {source_id} is not a known source")
    if party_id is not None and not _exists(session, "parties", "party_id", party_id):
        raise Invalid(f"party_id {party_id} is not a known party")
    _not_future(session, observed_at, "observed_at")
    row = session.execute(
        text("""INSERT INTO turab.observations
                       (kind, source_id, party_id, observed_at, raw_text, payload,
                        recorded_by_account_id)
                VALUES (CAST(:kind AS turab.observation_kind), :source, :party,
                        :observed, :raw, CAST(:payload AS jsonb), :account)
             RETURNING observation_id, recorded_at"""),
        {"kind": kind, "source": source_id, "party": party_id,
         "observed": observed_at, "raw": raw_text,
         "payload": json.dumps(dict(payload or {})),
         "account": recorded_by_account_id},
    ).mappings().one()
    audit_rows.write(session, "observations", row["observation_id"], "INSERT", None,
                     audit_rows.row_json(session, "observations", row["observation_id"]))
    return row


# --- claims -----------------------------------------------------------------

def record_claim(
    session: Session, *, subject_type: str, subject_id: uuid.UUID,
    attribute_code: str, claimed_value: Any,
    asserted_by_party_id=None, source_id=None, observation_id=None,
    extracted_by: str | None = None, extraction_model_version: str | None = None,
    extraction_confidence: float | None = None,
    observed_at: datetime | None = None, valid_from: datetime | None = None,
    valid_to: datetime | None = None, recorded_by_account_id: uuid.UUID,
) -> Mapping[str, Any]:
    """A claim is born `DECLARED` (§3.1): nothing here sets a level.

    §3.8: at least one ORIGIN among `asserted_by_party_id`, `source_id`,
    `observation_id`. `recorded_by_account_id` is who ENTERED it — not where
    it came from — and does not count. If both a source and an observation
    are named and the observation has its own source, the two must agree.
    """
    subject = _subject(session, subject_type, subject_id)
    validate_attribute(session, property_type=subject["property_type"],
                       attribute_code=attribute_code, value=claimed_value)

    if asserted_by_party_id is None and source_id is None and observation_id is None:
        raise Invalid("a claim must carry at least one origin: asserted_by_party_id, "
                      "source_id or observation_id. recorded_by_account_id says "
                      "who entered it, not where it came from")
    if asserted_by_party_id is not None and not _exists(
            session, "parties", "party_id", asserted_by_party_id):
        raise Invalid(f"asserted_by_party_id {asserted_by_party_id} is not a known party")
    if source_id is not None and not _exists(session, "sources", "source_id", source_id):
        raise Invalid(f"source_id {source_id} is not a known source")
    if observation_id is not None:
        observation = session.execute(
            text("SELECT source_id FROM turab.observations WHERE observation_id = :o"),
            {"o": observation_id},
        ).mappings().first()
        if observation is None:
            raise Invalid(f"observation_id {observation_id} is not a known observation")
        if (source_id is not None and observation["source_id"] is not None
                and observation["source_id"] != source_id):
            raise Invalid(
                f"source_id {source_id} disagrees with the source of observation "
                f"{observation_id} ({observation['source_id']}); a claim cannot "
                "name one source while citing an observation from another")
    _not_future(session, observed_at, "observed_at")
    if valid_from is not None and valid_to is not None and not valid_to > valid_from:
        raise Invalid("valid_to must be after valid_from")

    return session.execute(
        text(f"""INSERT INTO turab.claims
                        ({SUBJECT_COLUMN[subject_type]}, attribute_code, claimed_value,
                         asserted_by_party_id, source_id, observation_id,
                         extracted_by, extraction_model_version, extraction_confidence,
                         observed_at, valid_from, valid_to, recorded_by_account_id)
                 VALUES (:subject, :code, CAST(:value AS jsonb), :asserted, :source,
                         :observation, :extracted_by, :model, :confidence,
                         :observed, :vfrom, :vto, :account)
              RETURNING claim_id,
                        effective_verification_level::text AS verification_level,
                        status::text AS status"""),
        {"subject": subject_id, "code": attribute_code,
         "value": json.dumps(claimed_value), "asserted": asserted_by_party_id,
         "source": source_id, "observation": observation_id,
         "extracted_by": extracted_by, "model": extraction_model_version,
         "confidence": extraction_confidence, "observed": observed_at,
         "vfrom": valid_from, "vto": valid_to, "account": recorded_by_account_id},
    ).mappings().one()


# --- verification -----------------------------------------------------------

def record_verification(
    session: Session, *, claim_id: uuid.UUID, level: str, outcome: str,
    procedure_code: str | None = None, notes: str | None = None,
    verified_by_account_id: uuid.UUID,
) -> Mapping[str, Any]:
    """Insert the event. The DATABASE applies it (§3.1): on `CONFIRMED`,
    `GREATEST(level, NEW.level)`; on `CONFLICT_FOUND`, `CONFLICTING`; nothing
    otherwise. This function never writes the claim."""
    if not _exists(session, "claims", "claim_id", claim_id):
        raise NotFound("claim")
    row = session.execute(
        text("""INSERT INTO turab.verification_events
                       (claim_id, level, procedure_code, outcome, notes,
                        verified_by_account_id)
                VALUES (:c, CAST(:level AS turab.verification_level), :proc,
                        :outcome, :notes, :account)
             RETURNING verification_event_id, level::text AS level, outcome"""),
        {"c": claim_id, "level": level, "proc": procedure_code, "outcome": outcome,
         "notes": notes, "account": verified_by_account_id},
    ).mappings().one()
    audit_rows.write(session, "verification_events", row["verification_event_id"],
                     "INSERT", None, audit_rows.row_json(
                         session, "verification_events", row["verification_event_id"]))
    return row


# --- resolutions ------------------------------------------------------------

def resolve(
    session: Session, *, subject_type: str, subject_id: uuid.UUID,
    attribute_code: str, resolved_value: Any, source_claim_id=None,
    resolution_reason_code: str | None = None, valid_from: datetime | None = None,
    resolved_by_account_id: uuid.UUID | None,
) -> Mapping[str, Any]:
    """Record the current operational value; close the previous one (§3.7).

    Serialised on the SUBJECT row (`FOR UPDATE`, plan §6.3): two concurrent
    resolutions of one attribute both succeed, the second closing the first's
    row. The `ux_resolved_current_*` index keeps exactly one CURRENT row at
    every committed moment regardless.

    The source claim is pre-checked under a row lock on the claim, so a claim
    about another subject or attribute is a typed 422 rather than the
    `trg_resolution_lineage` exception surfacing as a 500 (§3.2).
    """
    if resolved_by_account_id is None:
        raise ActorRequired()
    subject = _subject(session, subject_type, subject_id, lock=True)
    definition = validate_attribute(session, property_type=subject["property_type"],
                                    attribute_code=attribute_code, value=resolved_value)
    column = SUBJECT_COLUMN[subject_type]

    if source_claim_id is not None:
        claim = session.execute(
            text("""SELECT party_id, request_id, property_id, offer_id, attribute_code
                      FROM turab.claims WHERE claim_id = :c FOR SHARE"""),
            {"c": source_claim_id},
        ).mappings().first()
        if claim is None:
            raise Invalid(f"source_claim_id {source_claim_id} is not a known claim")
        if claim[column] != subject_id or any(
                claim[c] is not None for c in SUBJECT_COLUMN.values() if c != column):
            raise Invalid("source_claim_id is a claim about another subject; a "
                          "resolution may cite only a claim about its own subject")
        if claim["attribute_code"] != attribute_code:
            raise Invalid(f"source_claim_id is a claim about "
                          f"{claim['attribute_code']!r}, not {attribute_code!r}")
    if resolution_reason_code is not None and not _exists(
            session, "reason_codes", "code", resolution_reason_code):
        raise Invalid(f"{resolution_reason_code!r} is not a known reason code")
    _not_future(session, valid_from, "valid_from")

    start = valid_from if valid_from is not None else _now(session)
    current = session.execute(
        text(f"""SELECT resolved_value_id, valid_from FROM turab.resolved_values
                  WHERE {column} = :s AND attribute_code = :a
                    AND valid_to IS NULL AND resolution_status = 'CURRENT'"""),
        {"s": subject_id, "a": attribute_code},
    ).mappings().first()
    if current is not None:
        if not start > current["valid_from"]:
            raise Invalid(f"valid_from must be after the current value's "
                          f"({current['valid_from'].isoformat()})")
        session.execute(
            text("""UPDATE turab.resolved_values
                       SET valid_to = :end, resolution_status = 'SUPERSEDED'
                     WHERE resolved_value_id = :r"""),
            {"end": start, "r": current["resolved_value_id"]},
        )
    row = session.execute(
        text(f"""INSERT INTO turab.resolved_values
                        ({column}, attribute_code, resolved_value, source_claim_id,
                         resolution_reason_code, resolved_by_account_id, valid_from)
                 VALUES (:s, :a, CAST(:v AS jsonb), :claim, :reason, :account, :start)
              RETURNING resolved_value_id, resolution_status::text AS resolution_status"""),
        {"s": subject_id, "a": attribute_code, "v": json.dumps(resolved_value),
         "claim": source_claim_id, "reason": resolution_reason_code,
         "account": resolved_by_account_id, "start": start},
    ).mappings().one()
    upsert_property_attribute(
        session, property_id=subject_id, property_type=subject["property_type"],
        attribute_code=attribute_code, value=resolved_value,
        resolved_claim_id=source_claim_id, definition=definition)
    return row


def upsert_property_attribute(
    session: Session, *, property_id: uuid.UUID, property_type: str,
    attribute_code: str, value: Any, resolved_claim_id=None,
    definition: Mapping[str, Any] | None = None,
) -> None:
    """The projection of the current resolved value onto `property_attributes`
    — the third call site of the one validator (§3.9). The claim/property/
    attribute agreement `trg_property_attribute_claim` enforces is already
    true here, because `resolve` pre-checked the same three facts."""
    definition = validate_attribute(session, property_type=property_type,
                                    attribute_code=attribute_code, value=value)
    existing = session.execute(
        text("""SELECT property_attribute_id FROM turab.property_attributes
                 WHERE property_id = :p AND attribute_definition_id = :d FOR UPDATE"""),
        {"p": property_id, "d": definition["attribute_definition_id"]},
    ).mappings().first()
    old = (audit_rows.row_json(session, "property_attributes",
                               existing["property_attribute_id"]) if existing else None)
    pa_id = session.execute(
        text("""INSERT INTO turab.property_attributes
                       (property_id, attribute_definition_id, value, resolved_claim_id)
                VALUES (:p, :d, CAST(:v AS jsonb), :c)
                ON CONFLICT (property_id, attribute_definition_id)
                DO UPDATE SET value = EXCLUDED.value,
                              resolved_claim_id = EXCLUDED.resolved_claim_id,
                              updated_at = now()
             RETURNING property_attribute_id"""),
        {"p": property_id, "d": definition["attribute_definition_id"],
         "v": json.dumps(value), "c": resolved_claim_id},
    ).scalar_one()
    audit_rows.write(session, "property_attributes", pa_id,
                     "UPDATE" if existing else "INSERT", old,
                     audit_rows.row_json(session, "property_attributes", pa_id))
