"""Pinned engine functions beside the criterion rules: freshness, permission,
eligibility, and the soft score (review of a5ea6f5; G4-12).

Ref: `docs/gate/SLICE_4_PLAN.md` G4-2, G4-10, G4-11, G4-12, G4-13. The review
of a5ea6f5 decided:

> the logic of the freshness and permission gates and the eligibility
> precedence must be pinned before step 7 writes matches. It need not be
> squeezed into criterion rules: it may take an identity and a version of
> its own, provided its digest enters the input hash, and earlier versions
> stay replayable.

**Identity and version.** Each function here has its own `(id, version)` in
the same `REGISTRY`, under its own namespace:
- `freshness.state`: one subject's state;
- `freshness.gate`;
- `permission.binding_state`: one binding's state;
- `permission.gate`;
- `eligibility.precedence`;
- `score.soft`: G4-12. Version 2 (review of 0cf6a7a) adds the weight of the
  request's `budget_target_dzd` column; version 1 stays registered.

`REGISTRY.digest()` therefore covers them, and that digest is an input of
the match hash (G4-13). A change to any of them changes the hash. A changed
function is a NEW version, registered beside the old one (G4-2), and its pin
keeps the old one from changing silently.

**Self-contained, like the criterion rules.** A pin covers only the
function's own source. So no function here calls a helper or reads a module
constant; it reads only its arguments and these names: `datetime`,
`timedelta`, `timezone`, `Decimal`, `Fraction`, and the builtins.
`test_every_registered_function_is_self_contained` checks this.

The modules that call them are `snapshots` and `eligibility`. They record
the `id@version` they used: the snapshots as `derived_by`, eligibility as
`engine`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction

from turab.matching.registry import REGISTRY


@REGISTRY.register("freshness.state", "1")
def freshness_state_v1(confirmed_at, days, as_of):
    """G4-11, one subject. Slice 2's FRESH / STALE / NEVER_CONFIRMED, with
    NEVER_CONFIRMED mapped to UNKNOWN. STALE exactly when
    `as_of - confirmed_at > days`, the comparison of
    `services.freshness.evaluate`. `confirmed_at` is in stored form (the
    canonical UTC string) or live form."""
    if confirmed_at is None:
        return {"state": "UNKNOWN", "basis": "NEVER_CONFIRMED", "confirmed_at": None}
    last = confirmed_at if isinstance(confirmed_at, datetime) else datetime.strptime(
        confirmed_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    stale = as_of - last > timedelta(days=days)
    return {"state": "STALE" if stale else "FRESH", "basis": "STALE" if stale else "FRESH",
            "confirmed_at": last}


@REGISTRY.register("freshness.gate", "1")
def freshness_gate_v1(freshness):
    """G4-11: PASS when request, property and offer are each FRESH or
    NOT_APPLICABLE; FAIL when any is STALE; UNKNOWN otherwise. A reason is
    returned for each subject that is not fresh:
    - the seeded `*_STALE` code for STALE;
    - no code, with basis NEVER_CONFIRMED, for UNKNOWN."""
    subjects = (("request", "REQUEST_STALE"), ("property", "PROPERTY_STALE"),
                ("offer", "OFFER_STALE"))
    states = [freshness[subject]["state"] for subject, _ in subjects]
    if "STALE" in states:
        status = "FAIL"
    elif all(state in ("FRESH", "NOT_APPLICABLE") for state in states):
        status = "PASS"
    else:
        status = "UNKNOWN"
    reasons = []
    for subject, stale_code in subjects:
        entry = freshness[subject]
        if entry["state"] == "STALE":
            reasons.append({"gate": "FRESHNESS", "subject": subject.upper(),
                            "reason_code": stale_code, "basis": "STALE"})
        elif entry["state"] == "UNKNOWN":
            reasons.append({"gate": "FRESHNESS", "subject": subject.upper(),
                            "reason_code": None, "basis": entry["basis"]})
    return {"status": status, "reasons": reasons}


@REGISTRY.register("permission.binding_state", "1")
def binding_state_v1(binding, offer_party_id, as_of):
    """G4-10, one binding in stored form, in this precedence:
    1. OTHER_PARTY: the grant is not the offer's party (it does not count);
    2. SCOPE_MISMATCH: the grant's scope is not the binding's purpose (it
       does not count; the trigger checks this on write only);
    3. REVOKED: the binding is revoked, the grant's status is REVOKED, or
       the grant carries a revocation date. Any one marker is enough; a
       future date is not guessed to be ineffective (the Slice 3 rule);
    4. NOT_STARTED: the binding or the grant starts after `as_of`;
    5. CURRENT."""
    if str(binding["grant_party_id"]) != str(offer_party_id):
        return "OTHER_PARTY"
    if binding["grant_scope"] != binding["purpose"]:
        return "SCOPE_MISMATCH"
    if (binding["binding_revoked_at"] is not None or binding["grant_status"] != "GRANTED"
            or binding["grant_revoked_at"] is not None):
        return "REVOKED"
    starts = [datetime.strptime(binding[key], "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=timezone.utc) for key in ("bound_at", "granted_at")]
    if any(start > as_of for start in starts):
        return "NOT_STARTED"
    return "CURRENT"


@REGISTRY.register("permission.gate", "1")
def permission_gate_v1(permission):
    """G4-10, over the bindings that count (OTHER_PARTY and SCOPE_MISMATCH
    do not):
    - PASS when one is CURRENT;
    - FAIL (CONSENT_REVOKED) when there are some, and every one is REVOKED;
    - UNKNOWN (PERMISSION_MISSING, next action CONFIRM_PERMISSION)
      otherwise.

    The basis says which case applies. The seeded label of
    PERMISSION_MISSING ("Permission scope insufficient") is NOT an exact
    reading of "no current binding": a displayed explanation is worded from
    the basis (review of a5ea6f5)."""
    counted = [b for b in permission["bindings"]
               if b["state"] not in ("OTHER_PARTY", "SCOPE_MISMATCH")]
    if any(b["state"] == "CURRENT" for b in counted):
        return {"status": "PASS", "reasons": []}
    if counted and all(b["state"] == "REVOKED" for b in counted):
        return {"status": "FAIL", "reasons": [
            {"gate": "PERMISSION", "subject": "OFFER", "reason_code": "CONSENT_REVOKED",
             "basis": "ONLY_REVOKED_BINDINGS"}]}
    return {"status": "UNKNOWN", "reasons": [
        {"gate": "PERMISSION", "subject": "OFFER", "reason_code": "PERMISSION_MISSING",
         "basis": "NO_CURRENT_BINDING" if not counted else "NOT_STARTED",
         "next_action": "CONFIRM_PERMISSION"}]}


@REGISTRY.register("eligibility.precedence", "1")
def eligibility_precedence_v1(hard, freshness_gate, permission_gate):
    """G4-11, in this order:
    1. REJECTED if the hard gate is FAIL;
    2. otherwise NEED_MORE_INFORMATION if a blocking unknown exists;
    3. otherwise NEEDS_CONFIRMATION if freshness or permission is not PASS;
    4. otherwise ELIGIBLE.

    `reasons` keeps EVERY gate that is not PASS, whatever the eligibility,
    which is the condition of the review of f789a59. `hard` gives the hard
    gate's status, the information gate's status, and the REQUIRED failures
    and blocking unknowns, each with its criterion's reason code."""
    reasons = [{"gate": "HARD", "criterion": f["criterion"], "ordinal": f["ordinal"],
                "reason_code": f["reason_code"], "basis": "REQUIRED_FAIL"}
               for f in hard["required_failures"]]
    reasons += [{"gate": "INFORMATION", "criterion": u["criterion"], "ordinal": u["ordinal"],
                 "reason_code": u["reason_code"], "basis": "BLOCKING_UNKNOWN"}
                for u in hard["blocking_unknowns"]]
    reasons += list(freshness_gate["reasons"]) + list(permission_gate["reasons"])
    if hard["hard_gate_status"] == "FAIL":
        verdict = "REJECTED"
    elif hard["information_gate_status"] != "PASS":
        verdict = "NEED_MORE_INFORMATION"
    elif freshness_gate["status"] != "PASS" or permission_gate["status"] != "PASS":
        verdict = "NEEDS_CONFIRMATION"
    else:
        verdict = "ELIGIBLE"
    return {"eligibility": verdict, "reasons": reasons}


@REGISTRY.register("score.soft", "1")
def soft_score_v1(hard_gate_status, criteria, targets, offer):
    """G4-12, as decided in the review of a5ea6f5.

    **Null cases:**
    - **null** unless the hard gate is PASS;
    - **null** when there is no soft term at all.

    **Terms:**
    - every PREFERRED or FLEXIBLE criterion that a deterministic rule
      evaluated. A soft criterion without one carries no weight (G4-7);
    - every deferred BUDGET_TARGET.

    **Weights:** PREFERRED = 2, FLEXIBLE = 1.

    **Contribution:**
    - a criterion: 1 if PASS; 0 if FAIL or UNKNOWN;
    - a BUDGET_TARGET: its proximity `1 − min(1, |ask − target| / target)`,
      on the offer's ASKING price. `seller_expectation_dzd` is never read. A
      zero target gives 1 for a zero ask and 0 for a positive one. A missing
      ask gives 0.

    **Score:** the weighted share `Σ weight × contribution / Σ weight`. It is
    computed exactly, as a fraction, and rounded once to six decimal places,
    half up, which is how PostgreSQL rounds into `numeric(7,6)`. No decimal
    context is involved.

    RENT is G4-5R: a target on a non-SALE offer is refused."""
    if hard_gate_status != "PASS":
        return {"soft_score": None, "basis": "HARD_GATE_NOT_PASS", "terms": []}
    weight_of = {"PREFERRED": 2, "FLEXIBLE": 1}
    terms = []
    for c in criteria:
        if c["importance"] in weight_of and c["rule_id"] != "criterion.no_deterministic_rule":
            terms.append({"kind": "CRITERION", "criterion": c["criterion_code"],
                          "ordinal": c["ordinal"], "weight": weight_of[c["importance"]],
                          "contribution": Fraction(1 if c["compatibility"] == "PASS" else 0)})
    for t in targets:
        if offer is None or offer.get("transaction_type") != "SALE":
            raise RuntimeError("score.soft compares a target with SALE prices only; a RENT "
                               "price has no approved rule (G4-5R is open)")
        target = int(t["value"])
        ask = offer.get("asking_price_dzd")
        if ask is None:
            proximity, basis = Fraction(0), "PRICE_NOT_KNOWN"
        elif target == 0:
            proximity, basis = Fraction(1 if int(ask) == 0 else 0), "ZERO_TARGET"
        else:
            distance = abs(int(ask) - target)
            proximity, basis = Fraction(target - min(target, distance), target), "PROXIMITY"
        terms.append({"kind": "BUDGET_TARGET", "source": t["source"],
                      "request_criterion_id": t["request_criterion_id"],
                      "weight": weight_of[t["importance"]], "contribution": proximity,
                      "basis": basis})
    total = sum(term["weight"] for term in terms)
    if total == 0:
        return {"soft_score": None, "basis": "NO_SOFT_CRITERION", "terms": []}
    share = sum(term["weight"] * term["contribution"] for term in terms) / total
    millionths = (2 * share.numerator * 1_000_000 + share.denominator) // (2 * share.denominator)
    for term in terms:
        term["contribution"] = (f"{term['contribution'].numerator}/"
                                f"{term['contribution'].denominator}")
    return {"soft_score": Decimal(millionths).scaleb(-6), "basis": "WEIGHTED_SHARE",
            "terms": terms}


@REGISTRY.register("score.soft", "2")
def soft_score_v2(hard_gate_status, criteria, targets, offer):
    """G4-12, as decided in the review of a5ea6f5, AND the weight of the
    request's `budget_target_dzd` COLUMN, decided in the review of 0cf6a7a
    (option (a)): it weighs 2, as a PREFERRED criterion, whatever
    `budget_importance` says (that importance stays the maximum's). The
    column is its own term (source COLUMN). A BUDGET_TARGET row beside it is
    another term, with its own weight; the two are never merged. Version 1
    never received a column (it was refused); everything else is version 1's.

    **Null cases:**
    - **null** unless the hard gate is PASS;
    - **null** when there is no soft term at all.

    **Terms:**
    - every PREFERRED or FLEXIBLE criterion that a deterministic rule
      evaluated. A soft criterion without one carries no weight (G4-7);
    - every deferred BUDGET_TARGET.

    **Weights:** PREFERRED = 2, FLEXIBLE = 1.

    **Contribution:**
    - a criterion: 1 if PASS; 0 if FAIL or UNKNOWN;
    - a BUDGET_TARGET: its proximity `1 − min(1, |ask − target| / target)`,
      on the offer's ASKING price. `seller_expectation_dzd` is never read. A
      zero target gives 1 for a zero ask and 0 for a positive one. A missing
      ask gives 0.

    **Score:** the weighted share `Σ weight × contribution / Σ weight`. It is
    computed exactly, as a fraction, and rounded once to six decimal places,
    half up, which is how PostgreSQL rounds into `numeric(7,6)`. No decimal
    context is involved.

    RENT is G4-5R: a target on a non-SALE offer is refused."""
    if hard_gate_status != "PASS":
        return {"soft_score": None, "basis": "HARD_GATE_NOT_PASS", "terms": []}
    weight_of = {"PREFERRED": 2, "FLEXIBLE": 1}
    terms = []
    for c in criteria:
        if c["importance"] in weight_of and c["rule_id"] != "criterion.no_deterministic_rule":
            terms.append({"kind": "CRITERION", "criterion": c["criterion_code"],
                          "ordinal": c["ordinal"], "weight": weight_of[c["importance"]],
                          "contribution": Fraction(1 if c["compatibility"] == "PASS" else 0)})
    for t in targets:
        if offer is None or offer.get("transaction_type") != "SALE":
            raise RuntimeError("score.soft compares a target with SALE prices only; a RENT "
                               "price has no approved rule (G4-5R is open)")
        target = int(t["value"])
        ask = offer.get("asking_price_dzd")
        if ask is None:
            proximity, basis = Fraction(0), "PRICE_NOT_KNOWN"
        elif target == 0:
            proximity, basis = Fraction(1 if int(ask) == 0 else 0), "ZERO_TARGET"
        else:
            distance = abs(int(ask) - target)
            proximity, basis = Fraction(target - min(target, distance), target), "PROXIMITY"
        column = t["source"] == "COLUMN"
        terms.append({"kind": "BUDGET_TARGET", "source": t["source"],
                      "request_criterion_id": t["request_criterion_id"],
                      "weight": 2 if column else weight_of[t["importance"]],
                      "weight_basis": "COLUMN_AS_PREFERRED" if column else "IMPORTANCE",
                      "contribution": proximity, "basis": basis})
    total = sum(term["weight"] for term in terms)
    if total == 0:
        return {"soft_score": None, "basis": "NO_SOFT_CRITERION", "terms": []}
    share = sum(term["weight"] * term["contribution"] for term in terms) / total
    millionths = (2 * share.numerator * 1_000_000 + share.denominator) // (2 * share.denominator)
    for term in terms:
        term["contribution"] = (f"{term['contribution'].numerator}/"
                                f"{term['contribution'].denominator}")
    return {"soft_score": Decimal(millionths).scaleb(-6), "basis": "WEIGHTED_SHARE",
            "terms": terms}
