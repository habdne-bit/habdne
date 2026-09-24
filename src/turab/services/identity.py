"""Identity Lite — Slice 3, step 7.

Ref: the contract's `postIdentityCandidatesGenerate`, `getIdentityCandidates`
and `postIdentityCandidatesCandidateIdReview`; ADR-03; Developer Spec §8
(pipeline §8.1, signals §8.2, "no automatic merge"); red-team E01–E04;
`docs/gate/SLICE_3_PLAN.md` §3.10 and §6.3; `docs/gate/SLICE_3_STEP7_DELIVERY.md`.

**Signals propose; a reviewer decides.** Generation writes only
`PENDING_REVIEW` rows. No path sets `CONFIRMED_SAME` without a reviewing
account.

**`CONFIRMED_SAME` is one transaction of three steps, in the order the schema
dictates (ADR-03):**
1. the alias mapping FIRST;
2. then the candidate's status (`trg_identity_same_requires_alias` refuses the
   status without the alias);
3. then review work (`tasks`) for every open match or opportunity that points
   at the property that has just become an alias.

Nothing is deleted or rewritten: sources, offers, claims, matches and
opportunities stay as they are (E01, E04). Step 3 starts no matching and
writes no `match_candidates` row.

The alias triggers raise P0001, which carries no constraint name. So each is
preceded by a pre-check under row locks, in the same transaction, that turns
it into a typed 409 (plan §2.1). The trigger remains the backstop.
"""
from __future__ import annotations

import json
import re
import uuid
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import audit_rows

#: The contract's default (`postIdentityCandidatesGenerate`). The column's
#: own default is `rules-0.2.0`, and it is never allowed to decide (plan
#: §3.10): the version is always written explicitly.
CONTRACT_DEFAULT_VERSION = "rules-0.1.0"

#: The algorithms this code implements. A version names an algorithm, so
#: storing one we did not run would misdescribe the candidate.
KNOWN_VERSIONS = frozenset({CONTRACT_DEFAULT_VERSION})

#: rules-0.1.0 area thresholds, as the ratio of the larger area to the
#: smaller. Developer Spec §8.2 gives the categories ("مساحة متقاربة" medium;
#: "مساحة 270 مقابل 600" a contradiction), not the numbers. These numbers are
#: this version's, and changing them makes a new version.
AREA_CLOSE_MAX_RATIO = Decimal("1.10")
AREA_CONTRADICTION_MIN_RATIO = Decimal("1.50")

DECISIONS = ("CONFIRMED_SAME", "CONFIRMED_DISTINCT", "UNSURE")
#: Final decisions. UNSURE is not final: it may be reviewed again.
FINAL = frozenset({"CONFIRMED_SAME", "CONFIRMED_DISTINCT"})
REASON_CATEGORY = "IDENTITY"
CORRECTIVE_REASON = "IDENTITY_CONSOLIDATED"


class IdentityError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        self.code, self.detail = code, detail
        super().__init__(detail)


class NotFound(IdentityError):
    def __init__(self, what: str) -> None:
        super().__init__("NOT_FOUND", f"no such {what}")


class Invalid(IdentityError):
    def __init__(self, detail: str) -> None:
        super().__init__("VALIDATION_FAILED", detail)


class NotCanonical(IdentityError):
    """The three alias-structure refusals (ADR-03: no chains)."""

    def __init__(self, detail: str) -> None:
        super().__init__("IDENTITY_ALIAS_NOT_CANONICAL", detail)


class AlreadyDecided(IdentityError):
    def __init__(self) -> None:
        super().__init__(
            "IDENTITY_CANDIDATE_DECIDED",
            "this candidate carries a final decision (CONFIRMED_SAME or "
            "CONFIRMED_DISTINCT); a final decision is not reviewed again")


class ActorRequired(IdentityError):
    def __init__(self) -> None:
        super().__init__("ACTION_NOT_PERMITTED",
                         "an identity decision needs a reviewing account")


# --- rules-0.1.0 -----------------------------------------------------------

def _normalized(value: str | None) -> str | None:
    if value is None:
        return None
    collapsed = re.sub(r"\s+", " ", value).strip().casefold()
    return collapsed or None


def _area(a: Decimal | None, b: Decimal | None) -> str:
    if a is None and b is None:
        return "BOTH_UNKNOWN"
    if a is None or b is None:
        return "ONE_UNKNOWN"
    ratio = max(a, b) / min(a, b)
    if ratio <= AREA_CLOSE_MAX_RATIO:
        return "CLOSE"
    if ratio >= AREA_CONTRADICTION_MIN_RATIO:
        return "CONTRADICTION"
    return "APART"


def signals_for(a: Mapping[str, Any], b: Mapping[str, Any], *,
                shared_party: bool) -> tuple[dict, dict]:
    """rules-0.1.0: the signals and their explanation for one blocked pair.

    Pure and id-free: the same inputs give the same two objects, and no
    identifier or timestamp enters them, so two pairs with equal facts get
    equal signals (plan §3.10, reproducibility).
    """
    land = _area(a["land_area_m2"], b["land_area_m2"])
    built = _area(a["built_area_m2"], b["built_area_m2"])
    da, db = _normalized(a["local_location_detail"]), _normalized(b["local_location_detail"])
    detail = "UNKNOWN" if da is None or db is None else ("EQUAL" if da == db else "DIFFERENT")
    signals = {
        "blocking": {"same_property_type": True, "same_canonical_location": True},
        "land_area": land,
        "built_area": built,
        "shared_offer_party": shared_party,
        "local_location_detail": detail,
    }
    strong = ["shared_offer_party"] if shared_party else []
    medium = sorted(["same_canonical_location"]
                    + [f"{k}_close" for k, v in (("land_area", land), ("built_area", built))
                       if v == "CLOSE"]
                    + (["local_location_detail_equal"] if detail == "EQUAL" else []))
    contradictions = sorted(f"{k}_contradiction"
                            for k, v in (("land_area", land), ("built_area", built))
                            if v == "CONTRADICTION")
    explanation = {
        "algorithm_version": CONTRACT_DEFAULT_VERSION,
        "strong": strong,
        "medium": medium,
        "contradictions": contradictions,
        "note": "signals propose; a reviewer decides (Developer Spec §8.3)",
    }
    return signals, explanation


# Blocking (Developer Spec §8.1 step 2): both canonical (neither is an alias),
# the same property type, the same known canonical location. Each unordered
# pair appears once, as (LEAST, GREATEST).
_BLOCKED_PAIRS = """
    SELECT LEAST(p.property_id, q.property_id)    AS a_id,
           GREATEST(p.property_id, q.property_id) AS b_id
      FROM turab.properties p
      JOIN turab.properties q
        ON q.property_id > p.property_id
       AND q.property_type = p.property_type
       AND q.canonical_location_id = p.canonical_location_id
     WHERE p.canonical_location_id IS NOT NULL
       AND (CAST(:focus AS uuid) IS NULL
            OR CAST(:focus AS uuid) IN (p.property_id, q.property_id))
       AND NOT EXISTS (SELECT 1 FROM turab.property_identity_aliases x
                        WHERE x.alias_property_id IN (p.property_id, q.property_id))
     ORDER BY 1, 2
"""

_FACTS = """
    SELECT property_id, land_area_m2, built_area_m2, local_location_detail
      FROM turab.properties WHERE property_id = ANY(:ids)
"""

_SHARED_PARTY = """
    SELECT EXISTS (SELECT 1 FROM turab.property_offers oa
                     JOIN turab.property_offers ob ON ob.party_id = oa.party_id
                    WHERE oa.property_id = :a AND ob.property_id = :b)
"""

_COLUMNS = """identity_candidate_id, property_a_id, property_b_id, generated_at,
              signals, explanation, review_status::text AS review_status,
              review_reason_code, review_reason_text, reviewer_account_id,
              reviewed_at, algorithm_version"""


def _candidate_for_pair(session: Session, a: uuid.UUID, b: uuid.UUID):
    return session.execute(text(f"""
        SELECT {_COLUMNS} FROM turab.property_identity_candidates
         WHERE LEAST(property_a_id, property_b_id) = :a
           AND GREATEST(property_a_id, property_b_id) = :b"""),
        {"a": a, "b": b}).mappings().first()


def generate(session: Session, *, property_id: uuid.UUID | None,
             algorithm_version: str | None) -> list[Mapping[str, Any]]:
    """Propose candidates; return every PENDING_REVIEW candidate for the pairs
    considered, whether written now or already pending.

    - A pair that already has a DECIDED or UNSURE candidate is not re-opened
      and not returned; it is already in review or decided.
    - A pair already PENDING is returned unchanged: re-generation is
      idempotent (plan §3.10).
    - Two generators racing on one pair: `ux_identity_pair` admits one row.
      The other's INSERT fails inside a SAVEPOINT and reads the winner's row,
      so both calls succeed (plan §6.3, third row). No parent row is locked.
    """
    version = CONTRACT_DEFAULT_VERSION if algorithm_version is None else algorithm_version
    if version not in KNOWN_VERSIONS:
        raise Invalid("algorithm_version names no implemented algorithm; the "
                      f"implemented one is {CONTRACT_DEFAULT_VERSION}")
    if property_id is not None:
        exists = session.execute(text(
            "SELECT 1 FROM turab.properties WHERE property_id = :p"),
            {"p": property_id}).first()
        if exists is None:
            raise NotFound("property")
        alias_of = session.execute(text(
            "SELECT canonical_property_id FROM turab.property_identity_aliases "
            "WHERE alias_property_id = :p"), {"p": property_id}).scalar_one_or_none()
        if alias_of is not None:
            raise NotCanonical("this property is an identity alias; generate "
                               "candidates for its canonical property")

    pairs = session.execute(text(_BLOCKED_PAIRS), {"focus": property_id}).all()
    facts = {r["property_id"]: r for r in session.execute(
        text(_FACTS), {"ids": list({x for pair in pairs for x in pair})}).mappings()}

    out = []
    for a, b in pairs:
        existing = _candidate_for_pair(session, a, b)
        if existing is None:
            shared = session.execute(text(_SHARED_PARTY), {"a": a, "b": b}).scalar_one()
            signals, explanation = signals_for(facts[a], facts[b], shared_party=shared)
            explanation = {**explanation, "algorithm_version": version}
            try:
                with session.begin_nested():
                    row = session.execute(text(f"""
                        INSERT INTO turab.property_identity_candidates
                               (property_a_id, property_b_id, signals, explanation,
                                review_status, algorithm_version)
                        VALUES (:a, :b, CAST(:s AS jsonb), CAST(:e AS jsonb),
                                'PENDING_REVIEW', :v)
                        RETURNING {_COLUMNS}"""),
                        {"a": a, "b": b, "s": json.dumps(signals, sort_keys=True),
                         "e": json.dumps(explanation, sort_keys=True), "v": version},
                    ).mappings().one()
            except IntegrityError as exc:
                if getattr(getattr(exc.orig, "diag", None), "constraint_name",
                           None) != "ux_identity_pair":
                    raise
                existing = _candidate_for_pair(session, a, b)
            else:
                audit_rows.write(session, "property_identity_candidates",
                                 row["identity_candidate_id"], "INSERT", None,
                                 audit_rows.row_json(session, "property_identity_candidates",
                                                     row["identity_candidate_id"]))
                out.append(row)
                continue
        if existing["review_status"] == "PENDING_REVIEW":
            out.append(existing)
    return out


# --- review ------------------------------------------------------------------

def _reason(session: Session, code: str | None) -> None:
    if code is None:
        return
    ok = session.execute(text(
        "SELECT 1 FROM turab.reason_codes WHERE code = :c AND category = :k "
        "AND active"), {"c": code, "k": REASON_CATEGORY}).first()
    if ok is None:
        # The caller's text matched nothing: it is not echoed (step 5, §6.1).
        raise Invalid("reason_code is not an active IDENTITY reason code")


def review(session: Session, *, candidate_id: uuid.UUID, decision: str,
           canonical_property_id: uuid.UUID | None, reason_code: str | None,
           reason_text: str | None,
           reviewer_account_id: uuid.UUID | None) -> Mapping[str, Any]:
    if reviewer_account_id is None:
        raise ActorRequired()
    if decision not in DECISIONS:
        raise Invalid(f"decision must be one of {list(DECISIONS)}")
    candidate = session.execute(text(f"""
        SELECT {_COLUMNS} FROM turab.property_identity_candidates
         WHERE identity_candidate_id = :c FOR UPDATE"""),
        {"c": candidate_id}).mappings().first()
    if candidate is None:
        raise NotFound("identity candidate")
    if candidate["review_status"] in FINAL:
        raise AlreadyDecided()
    pair = (candidate["property_a_id"], candidate["property_b_id"])
    if decision == "CONFIRMED_SAME":
        if canonical_property_id is None:
            raise Invalid("canonical_property_id is required for CONFIRMED_SAME")
        if canonical_property_id not in pair:
            raise Invalid("canonical_property_id must be one of the candidate's pair")
    elif canonical_property_id is not None:
        raise Invalid("canonical_property_id is meaningful only for CONFIRMED_SAME; "
                      "omit it or send null")
    _reason(session, reason_code)

    before = audit_rows.row_json(session, "property_identity_candidates", candidate_id)
    tasks: list[uuid.UUID] = []
    if decision == "CONFIRMED_SAME":
        alias = pair[1] if canonical_property_id == pair[0] else pair[0]
        _lock_and_check_structure(session, alias=alias, canonical=canonical_property_id)
        # 1. The alias FIRST (trg_identity_same_requires_alias).
        session.execute(text("""
            INSERT INTO turab.property_identity_aliases
                   (alias_property_id, canonical_property_id,
                    source_identity_candidate_id, reason_code, resolved_by_account_id)
            VALUES (:alias, :canon, :c, :r, :acct)"""),
            {"alias": alias, "canon": canonical_property_id, "c": candidate_id,
             "r": reason_code, "acct": reviewer_account_id})
        audit_rows.write(session, "property_identity_aliases", alias, "INSERT", None,
                         audit_rows.row_json(session, "property_identity_aliases", alias))

    # 2. The decision. What keeps a final decision from being overwritten is
    # the check above, made AFTER `FOR UPDATE`. Under Read Committed a
    # locking read that waited returns the row's newest committed version
    # (PostgreSQL 16 documentation, §13.2.1). So a concurrent reviewer that
    # waited sees the final state and is refused by the declared rule "a
    # final decision is not reviewed again". A second predicate here would
    # guard the same column of the same locked row, and no test could prove
    # it; it is deliberately absent.
    row = session.execute(text(f"""
        UPDATE turab.property_identity_candidates
           SET review_status = CAST(:d AS turab.identity_review_status),
               review_reason_code = :r, review_reason_text = :t,
               reviewer_account_id = :acct, reviewed_at = now()
         WHERE identity_candidate_id = :c
        RETURNING {_COLUMNS}"""),
        {"d": decision, "r": reason_code, "t": reason_text,
         "acct": reviewer_account_id, "c": candidate_id}).mappings().one()
    audit_rows.write(session, "property_identity_candidates", candidate_id, "UPDATE",
                     before, audit_rows.row_json(session, "property_identity_candidates",
                                                 candidate_id))

    if decision == "CONFIRMED_SAME":
        # 3. The corrective effect (ADR-03, E04).
        tasks = raise_review_work(session, alias=alias,
                                  canonical=canonical_property_id,
                                  candidate_id=candidate_id)
    return {**row, "review_tasks": tasks}


def _lock_and_check_structure(session: Session, *, alias: uuid.UUID,
                              canonical: uuid.UUID) -> None:
    """Row locks on BOTH properties, in id order (no deadlock between two
    reviews touching the same pair), then the checks `enforce_identity_alias`
    would make. They are made after the locks, so two concurrent reviews
    cannot both pass them and build a chain."""
    session.execute(text("""
        SELECT property_id FROM turab.properties
         WHERE property_id IN (:x, :y) ORDER BY property_id FOR UPDATE"""),
        {"x": alias, "y": canonical})
    facts = session.execute(text("""
        SELECT EXISTS (SELECT 1 FROM turab.property_identity_aliases
                        WHERE alias_property_id = :alias)      AS alias_is_alias,
               EXISTS (SELECT 1 FROM turab.property_identity_aliases
                        WHERE alias_property_id = :canon)      AS canon_is_alias,
               EXISTS (SELECT 1 FROM turab.property_identity_aliases
                        WHERE canonical_property_id = :alias)  AS alias_is_canonical"""),
        {"alias": alias, "canon": canonical}).mappings().one()
    if facts["canon_is_alias"]:
        raise NotCanonical("the chosen canonical property is itself an identity "
                           "alias; choose its canonical record")
    if facts["alias_is_alias"]:
        raise NotCanonical("the other property of the pair is already an alias "
                           "of a canonical record")
    if facts["alias_is_canonical"]:
        raise NotCanonical("the other property of the pair already acts as a "
                           "canonical record; it cannot become an alias without "
                           "consolidating its aliases explicitly")


#: Open work pointing at the new alias.
#: - A match is open unless its LATEST review is REJECTED (the ordering
#:   `enforce_opportunity_gate()` itself uses: reviewed_at DESC,
#:   match_review_id DESC), or an opportunity has been created from it (the
#:   opportunity then carries it).
#: - An opportunity is open until CLOSED.
_OPEN_MATCHES = """
    SELECT m.match_id, m.request_id FROM turab.match_candidates m
     WHERE m.property_id = :alias
       AND (SELECT r.decision FROM turab.match_reviews r
             WHERE r.match_id = m.match_id
             ORDER BY r.reviewed_at DESC, r.match_review_id DESC
             LIMIT 1) IS DISTINCT FROM 'REJECTED'
       AND NOT EXISTS (SELECT 1 FROM turab.opportunities o
                        WHERE o.approved_match_id = m.match_id)
     ORDER BY m.match_id
"""
_OPEN_OPPORTUNITIES = """
    SELECT o.opportunity_id, o.request_id, o.approved_match_id,
           ARRAY(SELECT c.opportunity_id FROM turab.opportunities c
                  WHERE c.property_id = :canon AND c.request_id = o.request_id
                    AND c.status <> 'CLOSED' ORDER BY c.opportunity_id) AS duplicates
      FROM turab.opportunities o
     WHERE o.property_id = :alias AND o.status <> 'CLOSED'
     ORDER BY o.opportunity_id
"""


def raise_review_work(session: Session, *, alias: uuid.UUID, canonical: uuid.UUID,
                      candidate_id: uuid.UUID) -> list[uuid.UUID]:
    """One `RESOLVE_IDENTITY` task per open match or opportunity on the alias.

    It changes none of them. E04: when the canonical property already has an
    open opportunity for the same request, the task names it
    (`duplicate_open_opportunity_ids`), so the duplicate is surfaced as work
    rather than silently closed.
    """
    base = {"alias_property_id": str(alias), "canonical_property_id": str(canonical),
            "identity_candidate_id": str(candidate_id)}
    work = []
    for m in session.execute(text(_OPEN_MATCHES), {"alias": alias}).mappings():
        work.append((m["request_id"], m["match_id"],
                     {**base, "affected": "MATCH", "match_id": str(m["match_id"])}))
    for o in session.execute(text(_OPEN_OPPORTUNITIES),
                             {"alias": alias, "canon": canonical}).mappings():
        work.append((o["request_id"], o["approved_match_id"],
                     {**base, "affected": "OPPORTUNITY",
                      "opportunity_id": str(o["opportunity_id"]),
                      "duplicate_open_opportunity_ids": [str(d) for d in o["duplicates"]]}))
    created = []
    for request_id, match_id, payload in work:
        task_id = session.execute(text("""
            INSERT INTO turab.tasks (task_type, title, reason_code, request_id,
                                     property_id, match_id, payload)
            VALUES ('RESOLVE_IDENTITY', 'Review after identity consolidation',
                    :r, :req, :alias, :m, CAST(:p AS jsonb))
            RETURNING task_id"""),
            {"r": CORRECTIVE_REASON, "req": request_id, "alias": alias, "m": match_id,
             "p": json.dumps(payload, sort_keys=True)}).scalar_one()
        audit_rows.write(session, "tasks", task_id, "INSERT", None,
                         audit_rows.row_json(session, "tasks", task_id))
        created.append(task_id)
    return created


# --- list ----------------------------------------------------------------------

def list_candidates(session: Session, *, status: str | None, page: int,
                    page_size: int) -> tuple[list[Mapping[str, Any]], int]:
    """Newest first. `status` is compared as TEXT: the contract types it as a
    plain string with no enum, so a value naming no status returns nothing."""
    where = "(CAST(:s AS text) IS NULL OR review_status::text = CAST(:s AS text))"
    total = session.execute(text(
        f"SELECT count(*) FROM turab.property_identity_candidates WHERE {where}"),
        {"s": status}).scalar_one()
    rows = session.execute(text(f"""
        SELECT {_COLUMNS} FROM turab.property_identity_candidates WHERE {where}
         ORDER BY generated_at DESC, identity_candidate_id
         LIMIT :limit OFFSET :offset"""),
        {"s": status, "limit": page_size, "offset": (page - 1) * page_size}
    ).mappings().all()
    return list(rows), total


def view(row: Mapping[str, Any]) -> dict[str, Any]:
    """`IdentityCandidate`, field for field. Staff-only operations, so the
    audience is INTERNAL; `review_reason_text` is not in the schema and is
    not rendered."""
    return {
        "identity_candidate_id": str(row["identity_candidate_id"]),
        "property_a_id": str(row["property_a_id"]),
        "property_b_id": str(row["property_b_id"]),
        "signals": row["signals"],
        "explanation": row["explanation"],
        "review_status": row["review_status"],
        "review_reason_code": row["review_reason_code"],
        "generated_at": row["generated_at"].isoformat(),
        "algorithm_version": row["algorithm_version"],
    }
