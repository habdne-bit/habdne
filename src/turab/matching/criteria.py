"""Which criteria a run evaluates, and the input a run refuses (Slice 4 step 4).

Ref: `docs/gate/SLICE_4_PLAN.md` G4-3 (b), G4-5 (SALE) and G4-5R (open),
G4-7, decided in the review of cc3a7fe; §0a evidence §E (Slice 2 accepts any
JSON value for any operator); the frozen schema's `requests` (lines
360–388) and `request_criteria` (393–407); the seed's criterion codes
(`seed_master_data_v0.2.3.sql:118–131`).

## Where criteria come from

A request states criteria twice (G4-3): as COLUMNS (`desired_property_type`,
`primary_location_id`, `budget_max_dzd`, each with an importance) and as
criterion ROWS. Both are evaluated. Each yields one criterion here, in a
fixed order:

1. TRANSACTION_INTENT from `transaction_intent`, REQUIRED (C01; it has no
   importance column, and the candidate set enforces it);
2. PROPERTY_TYPE from `desired_property_type`, when it is set;
3. LOCATION from `primary_location_id`, when it is set;
4. BUDGET_MAX from `budget_max_dzd`. When it is null, and no BUDGET_MAX row
   gives a maximum, the criterion is still emitted, with a null maximum:
   G4-5's table evaluates "max is null" to UNKNOWN;
5. every criterion row, in the snapshot's order (sort_order, code, id).

The `ordinal` of `match_criterion_results` numbers the criteria of one code
from 1, in that order.

`budget_target_dzd` and BUDGET_TARGET rows are soft only (G4-3's table,
G4-12). They are returned as DEFERRED to step 6, never dropped. A deferred
row is validated like any other first (review of f789a59): EQ only (the
target is a point, `|ask - target|` in G4-12), a whole, non-negative DZD
amount, unit none or `DZD`. A REQUIRED BUDGET_TARGET row is refused: it
cannot be a hard criterion. So is one with `blocking_if_unknown`: the flag
has no meaning for it until its rule exists (step 6).

## What is refused, with a typed refusal (`CriterionRefused`)

G4-7, decided "as proposed":
- an operator that does not suit its code;
- a value no rule can read: the wrong JSON type, a location id that names
  no location, an option that is not a registered, active option, a
  negative or fractional count, an unrecognised unit;
- a value no property can PASS (review of f789a59), at any importance:
  `DOCUMENT_TYPE EQ UNKNOWN`, `EQ UNSPECIFIED_DOCUMENT`, `RIGHT_TYPE EQ
  UNKNOWN`, an IN set of such values only, or a NOT_IN set excluding every
  value that could pass. An unknown property value is UNKNOWN, never PASS,
  so a set left with only `NOT_KNOWN_OPTIONS` can never pass. An IN set
  holding at least one known, passable option is accepted;
- a REQUIRED criterion that no deterministic rule evaluates
  (TEXT_SEMANTIC, CUSTOM_ATTRIBUTE, an unregistered code);
- such a criterion with `blocking_if_unknown = true`: it would block every
  candidate and could never be resolved, which is the REQUIRED case again.

G4-3 (b): a REQUIRED row whose EQ/IN set is provably disjoint from the
REQUIRED column of the same code. For LOCATION, two subtrees are disjoint
when neither location is an ancestor of the other.

G4-5R: a RENT request's price criterion. No rent period is defined for
`budget_max_dzd` or for a RENT `asking_price_dzd`, so no rule exists, and
the run refuses, naming G4-5R (acceptance condition 1: anything undecided
refuses with a typed error naming the rule).

A refusal names the criterion's code and id, never its value.

**Pure.** `criteria_of` reads its arguments only. `read_vocabulary` is the one
database read: which locations and options exist.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session

from turab.matching import snapshots

#: The frozen schema's `property_type` enum (line 52); a test compares it with
#: the database's.
PROPERTY_TYPES = ("HOUSE_VILLA", "APARTMENT", "LAND", "SHOP_COMMERCIAL",
                  "AGRICULTURAL_PROPERTY", "BUILDING", "OTHER")
TRANSACTION_INTENTS = ("BUY", "RENT")
SET_OPERATORS = ("EQ", "NEQ", "IN", "NOT_IN")

#: code -> (rule_id, rule_version, operators the rule reads). The versions
#: are those a NEW evaluation uses. Version 2 of four rules was registered
#: beside version 1 in the review of f789a59 (G4-2): reason codes by
#: importance, and G4-18 (b) for counts.
RULES: Mapping[str, tuple[str, str, tuple[str, ...]]] = {
    "TRANSACTION_INTENT": ("criterion.transaction_intent", "1", SET_OPERATORS),
    "PROPERTY_TYPE": ("criterion.property_type", "1", SET_OPERATORS),
    "LOCATION": ("criterion.location", "2", ("EQ", "IN")),
    "BUDGET_MAX": ("criterion.budget_max_sale", "1", ("LTE",)),
    "LAND_AREA_MIN": ("criterion.area_min", "2", ("GTE",)),
    "BUILT_AREA_MIN": ("criterion.area_min", "2", ("GTE",)),
    "ROOMS_MIN": ("criterion.count_min", "2", ("GTE",)),
    "BEDROOMS_MIN": ("criterion.count_min", "2", ("GTE",)),
    "DOCUMENT_TYPE": ("criterion.attribute_option", "2", SET_OPERATORS),
    "RIGHT_TYPE": ("criterion.attribute_option", "2", SET_OPERATORS),
}
NO_RULE = ("criterion.no_deterministic_rule", "1")
#: Soft-only codes: evaluated by the soft score, step 6 (G4-12).
DEFERRED = {"BUDGET_TARGET": "step 6 (G4-12)"}
#: The operators a deferred code accepts: the target is a point.
DEFERRED_OPERATORS = {"BUDGET_TARGET": ("EQ",)}
#: Option values that state the fact is NOT known. `attribute_option@2`
#: evaluates a property holding one of them to UNKNOWN, never PASS;
#: `test_not_known_options_are_exactly_those_the_rule_calls_unknown` holds the
#: two in agreement.
NOT_KNOWN_OPTIONS = ("UNKNOWN", "UNSPECIFIED_DOCUMENT")
#: Attribute option vocabularies read for validation.
OPTION_CODES = ("DOCUMENT_TYPE", "RIGHT_TYPE")
#: The units a rule can read, per code; None means "no unit given".
UNITS = {"BUDGET_MAX": (None, "DZD"), "BUDGET_TARGET": (None, "DZD"),
         "LAND_AREA_MIN": (None, "m2", "m²"),
         "BUILT_AREA_MIN": (None, "m2", "m²"), "ROOMS_MIN": (None,),
         "BEDROOMS_MIN": (None,)}


class CriterionRefused(ValueError):
    """The run is refused: a criterion is invalid, undecidable, or contradicts
    the request (G4-3 (b), G4-5R, G4-7). The value is never echoed."""

    def __init__(self, decision: str, problem: str, criterion_code: str,
                 request_criterion_id: str | None) -> None:
        where = ("the request's column" if request_criterion_id is None
                 else f"criterion {request_criterion_id}")
        super().__init__(f"{decision}: {criterion_code} ({where}): {problem}")
        self.decision = decision
        self.problem = problem
        self.criterion_code = criterion_code
        self.request_criterion_id = request_criterion_id


@dataclass(frozen=True, slots=True)
class Vocabulary:
    """What exists, read once per run: for every location the request names,
    its ancestry (itself first); and the active options of each option code."""
    location_ancestry: Mapping[str, tuple[str, ...]]
    options: Mapping[str, frozenset[str]]


@dataclass(frozen=True, slots=True)
class CriteriaPlan:
    criteria: tuple[dict, ...]
    deferred: tuple[dict, ...]


def _location_ids(request: Mapping[str, Any]) -> set[str]:
    ids = set()
    if request.get("primary_location_id") is not None:
        ids.add(str(request["primary_location_id"]))
    for row in request.get("criteria") or []:
        if row.get("criterion_code") == "LOCATION":
            values = row.get("value")
            for v in values if isinstance(values, list) else [values]:
                parsed = _uuid(v)
                if parsed is not None:
                    ids.add(parsed)
    return ids


def read_vocabulary(session: Session, request: Mapping[str, Any]) -> Vocabulary:
    request = snapshots.stored_form(request)
    ancestry = {}
    for location_id in sorted(_location_ids(request)):
        chain = snapshots.location_ancestry(session, uuid.UUID(location_id))
        if chain:
            ancestry[location_id] = tuple(str(x) for x in chain)
    options = {code: frozenset() for code in OPTION_CODES}
    for code, option in session.execute(text("""
            SELECT d.code, o.option_code
              FROM turab.attribute_options o
              JOIN turab.attribute_definitions d
                ON d.attribute_definition_id = o.attribute_definition_id
             WHERE o.active AND d.code = ANY(:codes)"""), {"codes": list(OPTION_CODES)}):
        options[code] = options[code] | {option}
    return Vocabulary(ancestry, options)


def _uuid(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


def _is_number(value: Any) -> bool:
    return isinstance(value, Decimal) and value.is_finite()


def _normalise(code: str, operator: str, value: Any, vocab: Vocabulary) -> Any:
    """The value in the form the rule reads, or None when no rule can read it."""
    if code in ("TRANSACTION_INTENT", "PROPERTY_TYPE", "DOCUMENT_TYPE", "RIGHT_TYPE"):
        allowed = {"TRANSACTION_INTENT": TRANSACTION_INTENTS,
                   "PROPERTY_TYPE": PROPERTY_TYPES}.get(code) or vocab.options[code]
        if operator in ("IN", "NOT_IN"):
            ok = (isinstance(value, list) and value
                  and all(isinstance(v, str) and v in allowed for v in value))
        else:
            ok = isinstance(value, str) and value in allowed
        return value if ok else None
    if code == "LOCATION":
        values = value if operator == "IN" else [value]
        if operator == "IN" and not (isinstance(value, list) and value):
            return None
        parsed = [_uuid(v) for v in values]
        if any(p is None or p not in vocab.location_ancestry for p in parsed):
            return None
        return parsed if operator == "IN" else parsed[0]
    if code in ("BUDGET_MAX", "BUDGET_TARGET", "ROOMS_MIN", "BEDROOMS_MIN"):
        ok = _is_number(value) and value >= 0 and value == value.to_integral_value()
        return value if ok else None
    if code in ("LAND_AREA_MIN", "BUILT_AREA_MIN"):
        return value if _is_number(value) and value > 0 else None
    return None


def _can_pass(code: str, operator: str, value: Any, vocab: Vocabulary) -> bool:
    """Whether some property value could PASS this (already readable)
    criterion. Only the set codes can be unsatisfiable by their value alone."""
    domain = {"TRANSACTION_INTENT": TRANSACTION_INTENTS,
              "PROPERTY_TYPE": PROPERTY_TYPES}.get(code)
    if domain is None:
        if code not in OPTION_CODES:
            return True
        domain = vocab.options[code] - set(NOT_KNOWN_OPTIONS)
    wanted = set(value if operator in ("IN", "NOT_IN") else [value])
    passing = set(domain) & wanted if operator in ("EQ", "IN") else set(domain) - wanted
    return bool(passing)


def _read_value(code: str, operator: str, operators: tuple[str, ...], row: Mapping[str, Any],
                vocab: Vocabulary, rid: str | None) -> Any:
    """G4-7: the operator, the unit, the value, and whether it can pass."""
    if operator not in operators:
        raise CriterionRefused("G4-7", f"operator {operator} does not suit {code}; "
                               f"its rule reads {', '.join(operators)}", code, rid)
    if row.get("unit") not in UNITS.get(code, (None,)):
        raise CriterionRefused("G4-7", "a unit its rule cannot read", code, rid)
    value = _normalise(code, operator, row["value"], vocab)
    if value is None:
        raise CriterionRefused("G4-7", "a value its rule cannot read", code, rid)
    if not _can_pass(code, operator, value, vocab):
        raise CriterionRefused("G4-7", "no property value can satisfy it", code, rid)
    return value


def _criterion(code: str, importance: str, operator: str, value: Any, unit: Any,
               blocking_if_unknown: bool, request_criterion_id: str | None,
               source: str) -> dict:
    return {"code": code, "importance": importance, "operator": operator, "value": value,
            "unit": unit, "blocking_if_unknown": blocking_if_unknown,
            "request_criterion_id": request_criterion_id, "source": source}


def _check_row(row: Mapping[str, Any], vocab: Vocabulary) -> dict:
    """One criterion row, validated (G4-7), with its rule attached."""
    code, operator = row["criterion_code"], row["operator"]
    importance, blocking = row["importance"], bool(row["blocking_if_unknown"])
    rid = None if row.get("request_criterion_id") is None else str(row["request_criterion_id"])
    crit = _criterion(code, importance, operator, row["value"], row.get("unit"), blocking,
                      rid, "ROW")
    if code in DEFERRED:
        if importance == "REQUIRED":
            raise CriterionRefused("G4-7", "a soft-only criterion cannot be REQUIRED",
                                   code, rid)
        if blocking:
            raise CriterionRefused("G4-7", "blocking_if_unknown has no meaning for a "
                                   "soft-only criterion until its rule exists (step 6)",
                                   code, rid)
        value = _read_value(code, operator, DEFERRED_OPERATORS[code], row, vocab, rid)
        return {**crit, "value": value, "deferred_to": DEFERRED[code]}
    if code not in RULES or operator == "TEXT_SEMANTIC":
        if importance == "REQUIRED":
            raise CriterionRefused("G4-7", "REQUIRED, and no deterministic rule evaluates it",
                                   code, rid)
        if blocking:
            raise CriterionRefused("G4-7", "blocking_if_unknown is set, and no deterministic "
                                   "rule evaluates it: it would block for good", code, rid)
        return {**crit, "rule_id": NO_RULE[0], "rule_version": NO_RULE[1]}
    rule_id, rule_version, operators = RULES[code]
    value = _read_value(code, operator, operators, row, vocab, rid)
    return {**crit, "value": value, "rule_id": rule_id, "rule_version": rule_version}


def _set_of(criterion: Mapping[str, Any]) -> list:
    value = criterion["value"]
    return value if criterion["operator"] == "IN" else [value]


def _disjoint(code: str, column_value: Any, row_values: list, vocab: Vocabulary) -> bool:
    if code == "LOCATION":
        above = vocab.location_ancestry
        return all(column_value not in above[v] and v not in above[column_value]
                   for v in row_values)
    return column_value not in row_values


def criteria_of(request: Mapping[str, Any], vocab: Vocabulary) -> CriteriaPlan:
    """The criteria of one request snapshot, read in its stored form
    (`snapshots.stored_form`), validated.

    Raises `CriterionRefused`. Runs in three passes, so the refusal a request
    receives does not depend on the order of its rows: first every row is
    validated, then contradictions are checked (G4-3 (b)), then the RENT price
    (G4-5R)."""
    request = snapshots.stored_form(request)
    rows = [_check_row(r, vocab) for r in request.get("criteria") or []]
    has_budget_row = any(r["code"] == "BUDGET_MAX" and "rule_id" in r for r in rows)

    columns = [_criterion("TRANSACTION_INTENT", "REQUIRED", "EQ",
                          request["transaction_intent"], None, False, None, "COLUMN")]
    if request.get("desired_property_type") is not None:
        columns.append(_criterion("PROPERTY_TYPE", request["property_type_importance"], "EQ",
                                  request["desired_property_type"], None, False, None,
                                  "COLUMN"))
    if request.get("primary_location_id") is not None:
        location = _uuid(str(request["primary_location_id"]))
        if location not in vocab.location_ancestry:
            raise CriterionRefused("G4-7", "the location names no location", "LOCATION", None)
        columns.append(_criterion("LOCATION", request["location_importance"], "EQ", location,
                                  None, False, None, "COLUMN"))
    if request.get("budget_max_dzd") is not None or not has_budget_row:
        columns.append(_criterion("BUDGET_MAX", request["budget_importance"], "LTE",
                                  request.get("budget_max_dzd"), "DZD", False, None,
                                  "COLUMN"))
    for column in columns:
        rule_id, rule_version, _ = RULES[column["code"]]
        column.update(rule_id=rule_id, rule_version=rule_version)
    deferred = [r for r in rows if "deferred_to" in r]
    if request.get("budget_target_dzd") is not None:
        # The column has no importance of its own (`budget_importance` is the
        # maximum's); it is soft only (G4-3's table), so none is recorded.
        deferred.insert(0, {**_criterion("BUDGET_TARGET", None, "EQ",
                                         request["budget_target_dzd"], "DZD", False, None,
                                         "COLUMN"), "deferred_to": DEFERRED["BUDGET_TARGET"]})
    evaluated = columns + [r for r in rows if "deferred_to" not in r]

    # G4-3 (b): a REQUIRED row provably disjoint from the REQUIRED column.
    required_columns = {c["code"]: c for c in columns
                        if c["importance"] == "REQUIRED" and c["value"] is not None}
    for row in evaluated:
        column = required_columns.get(row["code"])
        if (row["source"] == "ROW" and column is not None and row["importance"] == "REQUIRED"
                and row["operator"] in ("EQ", "IN")
                and row["code"] in ("TRANSACTION_INTENT", "PROPERTY_TYPE", "LOCATION")
                and _disjoint(row["code"], column["value"], _set_of(row), vocab)):
            raise CriterionRefused("G4-3", "REQUIRED, and disjoint from the request's own "
                                   "REQUIRED value: no property can satisfy both",
                                   row["code"], row["request_criterion_id"])

    # G4-5R: no rent period is defined, so a RENT price has no rule.
    if request["transaction_intent"] == "RENT":
        price = next(c for c in evaluated if c["code"] == "BUDGET_MAX")
        raise CriterionRefused("G4-5R", "a RENT price cannot be compared: the rent period "
                               "of the budget and of the asking price is not defined",
                               "BUDGET_MAX", price["request_criterion_id"])

    ordinals: dict[str, int] = {}
    for criterion in evaluated:
        ordinals[criterion["code"]] = ordinals.get(criterion["code"], 0) + 1
        criterion["ordinal"] = ordinals[criterion["code"]]
    return CriteriaPlan(tuple(evaluated), tuple(deferred))
