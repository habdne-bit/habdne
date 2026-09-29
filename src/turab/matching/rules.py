"""The criterion rules of the hard gate (Slice 4 step 4).

Ref: `docs/gate/SLICE_4_PLAN.md` G4-3 (b), G4-4, G4-5 (SALE), G4-6 and G4-7,
decided in the review of cc3a7fe; G4-5R (RENT price) is OPEN; Developer Spec
§11 (Compatibility + Evidence + Reason), §12.1; plan §3.4 (evidence);
`seed_master_data_v0.2.3.sql:118–160` (criterion codes, reason codes).

## What a rule is

`rule(criterion, request, prop, offer) -> dict`. It reads only its four
arguments, which are the snapshots IN THEIR STORED FORM: the canonical
JSON, parsed back with every number as `Decimal` (`snapshots.stored_form`). A
live run and a replay from stored rows therefore give a rule the same
input, and it returns the same output.

It returns the per-criterion facts of `match_criterion_results`:
`compatibility` (PASS, FAIL or UNKNOWN), `property_value`, `delta`,
`evidence_level`, `evidence_claim_id`, `reason_code`, and an `explanation`
made of fixed codes, never free text.

A rule does NOT decide `blocking`. That depends on importance (G4-4) and is
`hard_gate`'s.

## Self-contained, so that the pin covers it

A rule's pin is the sha256 of its OWN source (`registry.Rule`, G4-2). So a
rule calls no helper and reads no module constant: everything it depends on
is written inside it. `test_every_rule_is_self_contained` enforces this on
each rule's compiled code. Repetition between rules is the price of that
guarantee.

## Reason codes

Only codes of the frozen seed are emitted (acceptance condition 4: no new
reason code). Where the seed has no code for an outcome, `reason_code` is
null, and the `explanation`'s `basis` says what happened.

## Version 2 (review of f789a59), registered BESIDE version 1

G4-2: a changed rule is a new version; version 1 stays registered and
pinned. No stored match cites any version yet (no match row exists before
step 7), so version 1 is never selected. `criteria.RULES` names the versions
a new evaluation uses.
- `location@2`, `attribute_option@2`, `area_min@2`: a reason code whose
  seeded label names an importance is emitted only at that importance.
  - LOCATION_MISMATCH and DOCUMENT_MISMATCH read "Required ..." (seed lines
    135, 141): REQUIRED only.
  - AREA_BELOW_PREFERENCE reads "Area below preference" (line 142):
    PREFERRED or FLEXIBLE only.
  - Otherwise the reason is null, and `basis` names the outcome.
  - Version 1 emitted them at every importance.
- `count_min@2`: G4-18 (b), decided in the same review. An attribute that
  cannot apply to the property's type (its `applies_to`, recorded in the
  property snapshot, format 3) is FAIL. An applicable attribute that is not
  recorded stays UNKNOWN.

## R9.3

`seller_expectation_dzd` may decide a price PASS. It never appears in any
field a rule returns, and a PASS it decides is indistinguishable, in
`reason_code` and `explanation`, from a PASS on the asking price.
"""
from __future__ import annotations

from decimal import Decimal

from turab.matching.registry import REGISTRY


@REGISTRY.register("criterion.transaction_intent", "1")
def transaction_intent_v1(criterion, request, prop, offer):
    """TRANSACTION_INTENT (C01). The candidate set already evaluates only
    offers of the request's type, and the frozen trigger forbids the rest.
    The result is recorded so that a reviewer reconstructs it."""
    operator = criterion["operator"]
    wanted = criterion["value"] if operator in ("IN", "NOT_IN") else [criterion["value"]]
    offer_type = None if offer is None else offer.get("transaction_type")
    served = {"SALE": "BUY", "RENT": "RENT"}.get(offer_type)
    base = {"property_value": offer_type, "delta": None, "evidence_level": None,
            "evidence_claim_id": None}
    if served is None:
        return {**base, "compatibility": "UNKNOWN", "reason_code": None,
                "explanation": {"basis": "NO_EVALUATED_OFFER", "evidence": "NO_CLAIM_LINK"}}
    inside = served in wanted
    if operator in ("NEQ", "NOT_IN"):
        inside = not inside
    return {**base, "compatibility": "PASS" if inside else "FAIL", "reason_code": None,
            "explanation": {"basis": "OFFER_TRANSACTION_TYPE", "offer_serves": served,
                            "evidence": "NO_CLAIM_LINK"}}


@REGISTRY.register("criterion.property_type", "1")
def property_type_v1(criterion, request, prop, offer):
    """PROPERTY_TYPE against `properties.property_type`, which is NOT NULL in
    the frozen schema, so this rule has no UNKNOWN."""
    operator = criterion["operator"]
    wanted = criterion["value"] if operator in ("IN", "NOT_IN") else [criterion["value"]]
    actual = prop["property_type"]
    inside = actual in wanted
    if operator in ("NEQ", "NOT_IN"):
        inside = not inside
    return {"property_value": actual, "delta": None, "evidence_level": None,
            "evidence_claim_id": None, "compatibility": "PASS" if inside else "FAIL",
            "reason_code": None if inside else "PROPERTY_TYPE_MISMATCH",
            "explanation": {"basis": "PROPERTY_TYPE", "evidence": "NO_CLAIM_LINK"}}


@REGISTRY.register("criterion.location", "1")
def location_v1(criterion, request, prop, offer):
    """LOCATION (G4-6, as G3-14): PASS when a requested location is the
    property's location or one of its ancestors, i.e. the property lies in
    the requested subtree. A property with no location is UNKNOWN."""
    wanted = criterion["value"] if criterion["operator"] == "IN" else [criterion["value"]]
    here = prop.get("canonical_location_id")
    base = {"property_value": here, "delta": None, "evidence_level": None,
            "evidence_claim_id": None}
    if here is None:
        return {**base, "compatibility": "UNKNOWN", "reason_code": None,
                "explanation": {"basis": "LOCATION_NOT_RECORDED", "evidence": "NO_CLAIM_LINK"}}
    ancestry = prop.get("location_ancestry")
    if not isinstance(ancestry, list) or not ancestry or ancestry[0] != here:
        raise RuntimeError("the property snapshot carries no location ancestry for its "
                           "location; the LOCATION rule refuses to guess (G4-6)")
    inside = any(w in ancestry for w in wanted)
    return {**base, "compatibility": "PASS" if inside else "FAIL",
            "reason_code": None if inside else "LOCATION_MISMATCH",
            "explanation": {"basis": "LOCATION_SUBTREE", "evidence": "NO_CLAIM_LINK"}}


@REGISTRY.register("criterion.budget_max_sale", "1")
def budget_max_sale_v1(criterion, request, prop, offer):
    """BUDGET_MAX for a SALE offer: the table of G4-5, approved for SALE.

    | case | result | reason |
    |---|---|---|
    | max is null | UNKNOWN | — |
    | ask is null | UNKNOWN | PRICE_NOT_KNOWN |
    | ask <= max | PASS | — |
    | ask > max, exp <= max | PASS (internal; R9.3) | — |
    | ask > max, negotiable YES | UNKNOWN | PRICE_NEGOTIATION_UNCONFIRMED |
    | ask > max, negotiable NO | FAIL | BUDGET_EXCEEDED |
    | ask > max, negotiable UNKNOWN | UNKNOWN | PRICE_NEGOTIATION_UNCONFIRMED |

    RENT is G4-5R, OPEN: this rule refuses anything but SALE.
    """
    if offer is None or offer.get("transaction_type") != "SALE":
        raise RuntimeError("budget_max_sale evaluates SALE offers only; a RENT price has no "
                           "approved rule (G4-5R is open)")
    maximum = criterion["value"]
    ask = offer.get("asking_price_dzd")
    negotiable = offer.get("price_negotiable")
    base = {"property_value": {"asking_price_dzd": ask, "price_negotiable": negotiable},
            "delta": None if maximum is None or ask is None else {"dzd": ask - maximum},
            "evidence_level": None, "evidence_claim_id": None}
    if maximum is None:
        return {**base, "compatibility": "UNKNOWN", "reason_code": None,
                "explanation": {"basis": "BUDGET_MAX_NOT_STATED", "evidence": "NO_CLAIM_LINK"}}
    if ask is None:
        return {**base, "compatibility": "UNKNOWN", "reason_code": "PRICE_NOT_KNOWN",
                "explanation": {"basis": "PRICE_NOT_KNOWN", "evidence": "NO_CLAIM_LINK"}}
    expectation = offer.get("seller_expectation_dzd")
    if ask <= maximum or (expectation is not None and expectation <= maximum):
        return {**base, "compatibility": "PASS", "reason_code": None,
                "explanation": {"basis": "PRICE_COMPATIBLE", "evidence": "NO_CLAIM_LINK"}}
    if negotiable == "NO":
        return {**base, "compatibility": "FAIL", "reason_code": "BUDGET_EXCEEDED",
                "explanation": {"basis": "PRICE_ABOVE_MAX_NOT_NEGOTIABLE",
                                "evidence": "NO_CLAIM_LINK"}}
    return {**base, "compatibility": "UNKNOWN", "reason_code": "PRICE_NEGOTIATION_UNCONFIRMED",
            "explanation": {"basis": "PRICE_ABOVE_MAX_NEGOTIATION_UNCONFIRMED",
                            "evidence": "NO_CLAIM_LINK"}}


@REGISTRY.register("criterion.area_min", "1")
def area_min_v1(criterion, request, prop, offer):
    """LAND_AREA_MIN / BUILT_AREA_MIN, GTE, against the projection columns.
    A null area is UNKNOWN."""
    column = {"LAND_AREA_MIN": "land_area_m2", "BUILT_AREA_MIN": "built_area_m2"}[
        criterion["code"]]
    minimum = criterion["value"]
    area = prop.get(column)
    base = {"property_value": area, "evidence_level": None, "evidence_claim_id": None,
            "delta": None if area is None else {"m2": area - minimum}}
    if area is None:
        return {**base, "compatibility": "UNKNOWN", "reason_code": None,
                "explanation": {"basis": "AREA_NOT_RECORDED", "evidence": "NO_CLAIM_LINK"}}
    inside = area >= minimum
    return {**base, "compatibility": "PASS" if inside else "FAIL",
            "reason_code": None if inside else "AREA_BELOW_PREFERENCE",
            "explanation": {"basis": "AREA_MINIMUM", "evidence": "NO_CLAIM_LINK"}}


@REGISTRY.register("criterion.count_min", "1")
def count_min_v1(criterion, request, prop, offer):
    """ROOMS_MIN / BEDROOMS_MIN, GTE, against the resolved attribute of the
    same name. Evidence is the claim behind the resolved value (§3.4). A
    missing or non-numeric attribute is UNKNOWN."""
    code = {"ROOMS_MIN": "ROOMS", "BEDROOMS_MIN": "BEDROOMS"}[criterion["code"]]
    minimum = criterion["value"]
    found = [a for a in prop.get("attributes") or [] if a.get("code") == code]
    base = {"evidence_level": None, "evidence_claim_id": None, "delta": None,
            "property_value": None}
    if not found:
        return {**base, "compatibility": "UNKNOWN", "reason_code": None,
                "explanation": {"basis": "ATTRIBUTE_NOT_RECORDED", "attribute": code}}
    attribute = found[0]
    value = attribute.get("value")
    base = {**base, "property_value": value, "evidence_level": attribute.get("evidence_level"),
            "evidence_claim_id": attribute.get("resolved_claim_id")}
    if not isinstance(value, Decimal):
        return {**base, "compatibility": "UNKNOWN", "reason_code": None,
                "explanation": {"basis": "ATTRIBUTE_UNREADABLE", "attribute": code}}
    inside = value >= minimum
    return {**base, "delta": {"count": value - minimum},
            "compatibility": "PASS" if inside else "FAIL", "reason_code": None,
            "explanation": {"basis": "COUNT_MINIMUM", "attribute": code}}


@REGISTRY.register("criterion.attribute_option", "1")
def attribute_option_v1(criterion, request, prop, offer):
    """DOCUMENT_TYPE / RIGHT_TYPE against the resolved attribute of the same
    code, a controlled option. Missing, unreadable, `UNKNOWN` or
    `UNSPECIFIED_DOCUMENT` is UNKNOWN: the type is not known (§11, C03, M-02).
    DOCUMENT_TYPE uses DOCUMENT_NOT_KNOWN and DOCUMENT_MISMATCH; the seed has
    no RIGHT_TYPE code, so RIGHT_TYPE's reason is null."""
    code = criterion["code"]
    operator = criterion["operator"]
    wanted = criterion["value"] if operator in ("IN", "NOT_IN") else [criterion["value"]]
    unknown_reason = "DOCUMENT_NOT_KNOWN" if code == "DOCUMENT_TYPE" else None
    found = [a for a in prop.get("attributes") or [] if a.get("code") == code]
    base = {"evidence_level": None, "evidence_claim_id": None, "delta": None,
            "property_value": None}
    if not found:
        return {**base, "compatibility": "UNKNOWN", "reason_code": unknown_reason,
                "explanation": {"basis": "ATTRIBUTE_NOT_RECORDED", "attribute": code}}
    attribute = found[0]
    value = attribute.get("value")
    base = {**base, "property_value": value, "evidence_level": attribute.get("evidence_level"),
            "evidence_claim_id": attribute.get("resolved_claim_id")}
    if not isinstance(value, str):
        return {**base, "compatibility": "UNKNOWN", "reason_code": unknown_reason,
                "explanation": {"basis": "ATTRIBUTE_UNREADABLE", "attribute": code}}
    if value in ("UNKNOWN", "UNSPECIFIED_DOCUMENT"):
        return {**base, "compatibility": "UNKNOWN", "reason_code": unknown_reason,
                "explanation": {"basis": "ATTRIBUTE_VALUE_NOT_KNOWN", "attribute": code}}
    inside = value in wanted
    if operator in ("NEQ", "NOT_IN"):
        inside = not inside
    mismatch = "DOCUMENT_MISMATCH" if code == "DOCUMENT_TYPE" else None
    return {**base, "compatibility": "PASS" if inside else "FAIL",
            "reason_code": None if inside else mismatch,
            "explanation": {"basis": "ATTRIBUTE_OPTION", "attribute": code}}


@REGISTRY.register("criterion.no_deterministic_rule", "1")
def no_deterministic_rule_v1(criterion, request, prop, offer):
    """G4-7: a PREFERRED or FLEXIBLE criterion that no deterministic rule can
    evaluate (TEXT_SEMANTIC, CUSTOM_ATTRIBUTE, an unregistered code) is
    recorded UNKNOWN, so a reviewer sees it. It never passes silently (§3.2),
    and semantics never decide (§12.3)."""
    return {"property_value": None, "delta": None, "evidence_level": None,
            "evidence_claim_id": None, "compatibility": "UNKNOWN", "reason_code": None,
            "explanation": {"basis": "NO_DETERMINISTIC_RULE"}}


# --- version 2 (review of f789a59) ------------------------------------------------------------

@REGISTRY.register("criterion.location", "2")
def location_v2(criterion, request, prop, offer):
    """LOCATION (G4-6, as G3-14): PASS when a requested location is the
    property's location or one of its ancestors. A property with no location
    is UNKNOWN. LOCATION_MISMATCH ("Required location mismatch") only for a
    REQUIRED criterion."""
    wanted = criterion["value"] if criterion["operator"] == "IN" else [criterion["value"]]
    here = prop.get("canonical_location_id")
    base = {"property_value": here, "delta": None, "evidence_level": None,
            "evidence_claim_id": None}
    if here is None:
        return {**base, "compatibility": "UNKNOWN", "reason_code": None,
                "explanation": {"basis": "LOCATION_NOT_RECORDED", "evidence": "NO_CLAIM_LINK"}}
    ancestry = prop.get("location_ancestry")
    if not isinstance(ancestry, list) or not ancestry or ancestry[0] != here:
        raise RuntimeError("the property snapshot carries no location ancestry for its "
                           "location; the LOCATION rule refuses to guess (G4-6)")
    inside = any(w in ancestry for w in wanted)
    mismatch = "LOCATION_MISMATCH" if criterion["importance"] == "REQUIRED" else None
    return {**base, "compatibility": "PASS" if inside else "FAIL",
            "reason_code": None if inside else mismatch,
            "explanation": {"basis": "LOCATION_SUBTREE", "evidence": "NO_CLAIM_LINK"}}


@REGISTRY.register("criterion.area_min", "2")
def area_min_v2(criterion, request, prop, offer):
    """LAND_AREA_MIN / BUILT_AREA_MIN, GTE, against the projection columns.
    A null area is UNKNOWN. AREA_BELOW_PREFERENCE ("Area below preference")
    only for a PREFERRED or FLEXIBLE criterion; a REQUIRED FAIL has no seeded
    code, so its reason is null."""
    column = {"LAND_AREA_MIN": "land_area_m2", "BUILT_AREA_MIN": "built_area_m2"}[
        criterion["code"]]
    minimum = criterion["value"]
    area = prop.get(column)
    base = {"property_value": area, "evidence_level": None, "evidence_claim_id": None,
            "delta": None if area is None else {"m2": area - minimum}}
    if area is None:
        return {**base, "compatibility": "UNKNOWN", "reason_code": None,
                "explanation": {"basis": "AREA_NOT_RECORDED", "evidence": "NO_CLAIM_LINK"}}
    inside = area >= minimum
    below = None if criterion["importance"] == "REQUIRED" else "AREA_BELOW_PREFERENCE"
    return {**base, "compatibility": "PASS" if inside else "FAIL",
            "reason_code": None if inside else below,
            "explanation": {"basis": "AREA_MINIMUM", "evidence": "NO_CLAIM_LINK"}}


@REGISTRY.register("criterion.count_min", "2")
def count_min_v2(criterion, request, prop, offer):
    """ROOMS_MIN / BEDROOMS_MIN, GTE, against the resolved attribute of the
    same name, with its claim (§3.4).

    G4-18 (b): when the attribute cannot apply to the property's type (its
    `applies_to` in the snapshot does not list the type), the fact cannot
    exist, and the result is FAIL. An applicable attribute that is not
    recorded, or not numeric, is UNKNOWN. The seed has no code for either
    outcome, so the reason is null."""
    code = {"ROOMS_MIN": "ROOMS", "BEDROOMS_MIN": "BEDROOMS"}[criterion["code"]]
    minimum = criterion["value"]
    applies = prop.get("attribute_applies_to")
    if not isinstance(applies, dict) or code not in applies:
        raise RuntimeError("the property snapshot records no applicability for the "
                           "attribute; count_min@2 refuses to guess (G4-18)")
    base = {"evidence_level": None, "evidence_claim_id": None, "delta": None,
            "property_value": None}
    types = applies[code]
    if types is not None and prop.get("property_type") not in types:
        return {**base, "compatibility": "FAIL", "reason_code": None,
                "explanation": {"basis": "ATTRIBUTE_NOT_APPLICABLE", "attribute": code}}
    found = [a for a in prop.get("attributes") or [] if a.get("code") == code]
    if not found:
        return {**base, "compatibility": "UNKNOWN", "reason_code": None,
                "explanation": {"basis": "ATTRIBUTE_NOT_RECORDED", "attribute": code}}
    attribute = found[0]
    value = attribute.get("value")
    base = {**base, "property_value": value, "evidence_level": attribute.get("evidence_level"),
            "evidence_claim_id": attribute.get("resolved_claim_id")}
    if not isinstance(value, Decimal):
        return {**base, "compatibility": "UNKNOWN", "reason_code": None,
                "explanation": {"basis": "ATTRIBUTE_UNREADABLE", "attribute": code}}
    inside = value >= minimum
    return {**base, "delta": {"count": value - minimum},
            "compatibility": "PASS" if inside else "FAIL", "reason_code": None,
            "explanation": {"basis": "COUNT_MINIMUM", "attribute": code}}


@REGISTRY.register("criterion.attribute_option", "2")
def attribute_option_v2(criterion, request, prop, offer):
    """DOCUMENT_TYPE / RIGHT_TYPE against the resolved attribute of the same
    code. Missing, unreadable, `UNKNOWN` or `UNSPECIFIED_DOCUMENT` is UNKNOWN
    (§11, C03, M-02). DOCUMENT_NOT_KNOWN ("Document type unknown") at any
    importance; DOCUMENT_MISMATCH ("Required document mismatch") only for a
    REQUIRED criterion. The seed has no RIGHT_TYPE code."""
    code = criterion["code"]
    operator = criterion["operator"]
    wanted = criterion["value"] if operator in ("IN", "NOT_IN") else [criterion["value"]]
    unknown_reason = "DOCUMENT_NOT_KNOWN" if code == "DOCUMENT_TYPE" else None
    found = [a for a in prop.get("attributes") or [] if a.get("code") == code]
    base = {"evidence_level": None, "evidence_claim_id": None, "delta": None,
            "property_value": None}
    if not found:
        return {**base, "compatibility": "UNKNOWN", "reason_code": unknown_reason,
                "explanation": {"basis": "ATTRIBUTE_NOT_RECORDED", "attribute": code}}
    attribute = found[0]
    value = attribute.get("value")
    base = {**base, "property_value": value, "evidence_level": attribute.get("evidence_level"),
            "evidence_claim_id": attribute.get("resolved_claim_id")}
    if not isinstance(value, str):
        return {**base, "compatibility": "UNKNOWN", "reason_code": unknown_reason,
                "explanation": {"basis": "ATTRIBUTE_UNREADABLE", "attribute": code}}
    if value in ("UNKNOWN", "UNSPECIFIED_DOCUMENT"):
        return {**base, "compatibility": "UNKNOWN", "reason_code": unknown_reason,
                "explanation": {"basis": "ATTRIBUTE_VALUE_NOT_KNOWN", "attribute": code}}
    inside = value in wanted
    if operator in ("NEQ", "NOT_IN"):
        inside = not inside
    required = criterion["importance"] == "REQUIRED"
    mismatch = "DOCUMENT_MISMATCH" if code == "DOCUMENT_TYPE" and required else None
    return {**base, "compatibility": "PASS" if inside else "FAIL",
            "reason_code": None if inside else mismatch,
            "explanation": {"basis": "ATTRIBUTE_OPTION", "attribute": code}}
