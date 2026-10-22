"""The pinned functions of the diagnostic (Slice 6 step 3).

Ref: `docs/gate/SLICE_6_PLAN.md` G6-2 (a), G6-3, G6-5 (i) (a), (ii) (a),
(iii)-(vi), G6-6, G6-11, decided in the review of bd54216; §3.2-§3.5;
F6-1, F6-3, F6-6, F6-8, F6-10.

Three functions, registered in `REGISTRY` and pinned (G4-2, G6-11):
- `diagnostic.value@1`: the high-value unknowns of one candidate (G6-2);
- `diagnostic.actions@1`: `suggested_actions` (G6-3);
- `diagnostic.relaxation@1`: `relaxation_scenarios` (G6-5, G6-6).

**What they read.** Only their arguments: candidate records built from the
STORED match (`diagnostic.candidate_record`), in stored form, and the stored
location chains. A record carries no commercial snapshot, so no function
can read `seller_expectation_dzd` (§3.4, R9.3).

**Self-contained** (G4-2): each reads no module-level name but the builtins,
so its pin covers all it does. They do not call each other; the wiring
(`diagnostic.py`) passes one's output to the next.

**Pure.** Nothing here reads the database or writes.
"""
from __future__ import annotations

from turab.matching.registry import REGISTRY


@REGISTRY.register("diagnostic.value", "1")
def diagnostic_value_v1(candidate):
    """G6-2 (a): the unknown that ALONE stands between the candidate and
    ELIGIBLE (spec §13.1, "alone"; API_CONTRACTS §4.9).

    A candidate has one high-value unknown when:
    - it is NEED_MORE_INFORMATION (so its hard gate is not FAIL);
    - it has exactly ONE actionable unknown: a blocking UNKNOWN criterion;
    - its freshness and permission gates are PASS.

    Returns that criterion as `[{"criterion", "ordinal"}]`, or `[]`."""
    if (candidate["eligibility"] != "NEED_MORE_INFORMATION"
            or candidate["hard_gate_status"] == "FAIL"
            or candidate["freshness_gate_status"] != "PASS"
            or candidate["permission_gate_status"] != "PASS"):
        return []
    actionable = [c for c in candidate["criteria"]
                  if c["blocking"] and c["compatibility"] == "UNKNOWN"]
    if len(actionable) != 1:
        return []
    return [{"criterion": actionable[0]["criterion"], "ordinal": actionable[0]["ordinal"]}]


@REGISTRY.register("diagnostic.actions", "1")
def diagnostic_actions_v1(request_id, candidates, high_value):
    """G6-3: one entry per distinct subject of work, over the run's own
    evaluations. `high_value[i]` is `diagnostic.value@1` of `candidates[i]`.

    **Which candidates:** NEED_MORE_INFORMATION and NEEDS_CONFIRMATION only.
    An ELIGIBLE candidate waits for a human review; a REJECTED one has no
    actionable unknown (§3.3) and no entry, whatever its other reasons.

    **Which work, typed by D5's mapping (`action.next@1`), ALL of it:**
    - every actionable unknown (INFORMATION): DOCUMENT_TYPE and RIGHT_TYPE
      → VERIFY_DOCUMENT; BUDGET_MAX → CONFIRM_PRICE; any other code →
      OTHER. The entity follows the basis, as in D5: the request when its
      maximum is not stated or no rule reads the criterion; the offer when
      its price or negotiation is unknown; the property otherwise;
    - every FRESHNESS reason: the request → RECONFIRM_REQUEST, the property
      → RECONFIRM_PROPERTY, the offer's terms → CONFIRM_PRICE;
    - every PERMISSION reason → CONFIRM_PERMISSION, on the offer.

    **Priority (G6-2 (a)):** HIGH for an information entry that is the
    high-value unknown of at least one of its candidates; NORMAL otherwise.
    LOW and URGENT are not used.

    **The subject** is `(type, entity, id, gate, criterion, ordinal, basis)`.
    G6-3 names `(type, entity, id, criterion, ordinal)`; the gate and the
    basis are G6-4 (iii)'s key too, so the entry and a task raised from it
    name the same work.

    **Order, fixed and total:** HIGH first; then §13.1's classes
    (information; reconfirmation of the request, the property, the offer;
    permission); then the number of candidates, descending; then the
    entity id, the criterion and the ordinal; then the gate and the basis.

    **Never in an entry:** a value of the property, the offer or a claim, or
    a seller expectation (§3.4). Ids, codes, the basis and counts only."""
    classes = ("INFORMATION", "RECONFIRMATION", "RECONFIRMATION", "RECONFIRMATION",
               "PERMISSION")
    entries = {}
    for candidate, valued in zip(candidates, high_value, strict=True):
        if candidate["eligibility"] not in ("NEED_MORE_INFORMATION", "NEEDS_CONFIRMATION"):
            continue
        ids = {"REQUEST": request_id, "PROPERTY": candidate["property_id"],
               "PROPERTY_OFFER": candidate["offer_id"]}
        valued_keys = {(v["criterion"], v["ordinal"]) for v in valued}
        items = []
        if candidate["hard_gate_status"] != "FAIL":
            for c in candidate["criteria"]:
                if not (c["blocking"] and c["compatibility"] == "UNKNOWN"):
                    continue
                basis = c["basis"]
                if basis in ("BUDGET_MAX_NOT_STATED", "NO_DETERMINISTIC_RULE"):
                    entity = "REQUEST"
                elif basis in ("PRICE_NOT_KNOWN", "PRICE_ABOVE_MAX_NEGOTIATION_UNCONFIRMED",
                               "NO_EVALUATED_OFFER"):
                    entity = "PROPERTY_OFFER"
                else:
                    entity = "PROPERTY"
                kind = {"DOCUMENT_TYPE": "VERIFY_DOCUMENT", "RIGHT_TYPE": "VERIFY_DOCUMENT",
                        "BUDGET_MAX": "CONFIRM_PRICE"}.get(c["criterion"], "OTHER")
                high = (c["criterion"], c["ordinal"]) in valued_keys
                items.append((0, kind, "HIGH" if high else "NORMAL", {
                    "entity": entity, "id": ids[entity], "gate": "INFORMATION",
                    "criterion": c["criterion"], "ordinal": c["ordinal"],
                    "request_criterion_id": c["request_criterion_id"],
                    "reason_code": c["reason_code"], "basis": basis}))
        for r in candidate["reasons"]:
            if r["gate"] == "FRESHNESS":
                rank, entity, kind = {"REQUEST": (1, "REQUEST", "RECONFIRM_REQUEST"),
                                      "PROPERTY": (2, "PROPERTY", "RECONFIRM_PROPERTY"),
                                      "OFFER": (3, "PROPERTY_OFFER", "CONFIRM_PRICE")}[
                    r["subject"]]
                items.append((rank, kind, "NORMAL", {
                    "entity": entity, "id": ids[entity], "gate": "FRESHNESS",
                    "reason_code": r["reason_code"], "basis": r["basis"]}))
            elif r["gate"] == "PERMISSION":
                items.append((4, "CONFIRM_PERMISSION", "NORMAL", {
                    "entity": "PROPERTY_OFFER", "id": ids["PROPERTY_OFFER"],
                    "gate": "PERMISSION", "reason_code": r["reason_code"],
                    "basis": r["basis"]}))
        pair = {"property_id": candidate["property_id"], "offer_id": candidate["offer_id"]}
        for rank, kind, priority, subject in items:
            key = (kind, subject["entity"], subject["id"], subject["gate"],
                   subject.get("criterion"), subject.get("ordinal"), subject["basis"])
            entry = entries.setdefault(key, {"rank": rank, "type": kind, "priority": "NORMAL",
                                             "subject": subject, "candidates": []})
            if priority == "HIGH":
                entry["priority"] = "HIGH"
            if pair not in entry["candidates"]:
                entry["candidates"].append(pair)

    def order(entry):
        s = entry["subject"]
        return (0 if entry["priority"] == "HIGH" else 1, entry["rank"],
                -len(entry["candidates"]), str(s["id"]), s.get("criterion") or "",
                s.get("ordinal") or 0, s["gate"], s["basis"])
    out = []
    for entry in sorted(entries.values(), key=order):
        s = entry["subject"]
        out.append({
            "key": "|".join(str(x) for x in (
                entry["type"], s["entity"], s["id"], s["gate"],
                "" if s.get("criterion") is None else f"{s['criterion']}#{s['ordinal']}",
                s["basis"])),
            "type": entry["type"], "priority": entry["priority"],
            "class": classes[entry["rank"]], "subject": s,
            "candidates": sorted(entry["candidates"],
                                 key=lambda p: (str(p["property_id"]), str(p["offer_id"]))),
            "candidate_count": len(entry["candidates"])})
    return out


@REGISTRY.register("diagnostic.relaxation", "1")
def diagnostic_relaxation_v1(candidates, would_reach, location_chains, subordinate_to):
    """G6-5 and G6-6: what relaxing ONE requested criterion would change.

    **Which candidates (G6-5 (ii) (a)):** D2's near matches only: REJECTED,
    exactly one REQUIRED FAIL, every other REQUIRED criterion PASS.
    `would_reach[i]` is the eligibility candidate i would reach on its stored
    facts with that failure removed (computed by the wiring with the
    precedence the match recorded), or None for a candidate that is not a
    near match.

    **How each failure is stated (G6-5 (iii)):**
    - BUDGET_MAX: RAISE_MAXIMUM by `budget_delta_dzd` = ask − max, "at the
      asking price" (G6-5 (iv); F6-1: in DZD). Read from the stored criterion
      row; it is never called the minimum, and the seller expectation is
      never read (§3.4);
    - LAND_AREA_MIN, BUILT_AREA_MIN: LOWER_MINIMUM by `area_delta_m2` =
      area − min (negative);
    - ROOMS_MIN, BEDROOMS_MIN: LOWER_MINIMUM by `count_delta` = value − min
      (negative). A FAIL because the attribute cannot apply to the type
      (`ATTRIBUTE_NOT_APPLICABLE`) has no lowering that passes it: NOT_PROPOSED;
    - LOCATION: WIDEN_AREA, by G6-6 (below);
    - PROPERTY_TYPE: ACCEPT_PROPERTY_TYPE, the property's type named;
    - DOCUMENT_TYPE, RIGHT_TYPE: ACCEPT_DOCUMENT, the property's option
      named, `only_if_user_chooses` (spec §14); never a lowering;
    - TRANSACTION_INTENT, or any failure not listed: NOT_PROPOSED (C01).

    **Aggregation (G6-5 (v)).** One scenario per criterion and distinct
    magnitude (or named value, or widened-to location). Each lists the near
    matches it would turn into a hard-gate PASS, with the eligibility each
    would reach; a numeric scenario turns every near match whose own
    magnitude is no larger, and a widening every near match under the
    location. Numeric scenarios are ordered by magnitude, smallest change
    first; widenings by the levels the request is widened, fewest first;
    named ones by count, descending, then name. Never
    "would become an opportunity": that needs a human review (Slice 5).

    **LOCATION (G6-6).** For each requested location w, in stored order:
    `common` = the first location of the property's chain in w's chain;
    `property_below` = its position in the property's chain; `widened` = its
    position in w's chain. The choice: the smallest `property_below`, then
    the smallest `widened`, then the earliest w; a w with no common ancestor
    last. None at all: `widen_to` null, level NONE. Every w is listed with
    its values. The chains are the STORED ones (F6-10), never read again.

    `subordinate_to` (G6-5 (i) (a)): the keys of the run's HIGH actions; every
    scenario carries them, as it ranks after each of them."""
    groups = {}
    for candidate, reach in zip(candidates, would_reach, strict=True):
        required = [c for c in candidate["criteria"] if c["importance"] == "REQUIRED"]
        failing = [c for c in required if c["compatibility"] == "FAIL"]
        if not (candidate["eligibility"] == "REJECTED" and len(failing) == 1
                and all(c["compatibility"] != "UNKNOWN" for c in required)):
            continue
        if reach is None:
            raise RuntimeError("a near match was given no eligibility to reach")
        c = failing[0]
        code = c["criterion"]
        near = {"property_id": candidate["property_id"], "offer_id": candidate["offer_id"],
                "would_reach": reach}
        crit = (code, c["ordinal"])
        if code == "BUDGET_MAX":
            value = c["property_value"]["asking_price_dzd"] - c["request_value"]["value"]
            group = ("NUMBER", crit, "RAISE_MAXIMUM", "budget_delta_dzd")
        elif code in ("LAND_AREA_MIN", "BUILT_AREA_MIN"):
            value = c["property_value"] - c["request_value"]["value"]
            group = ("NUMBER", crit, "LOWER_MINIMUM", "area_delta_m2")
        elif code in ("ROOMS_MIN", "BEDROOMS_MIN") and c["basis"] == "COUNT_MINIMUM":
            value = c["property_value"] - c["request_value"]["value"]
            group = ("NUMBER", crit, "LOWER_MINIMUM", "count_delta")
        elif code == "PROPERTY_TYPE":
            value = c["property_value"]
            group = ("NAMED", crit, "ACCEPT_PROPERTY_TYPE", value)
        elif code in ("DOCUMENT_TYPE", "RIGHT_TYPE"):
            value = c["property_value"]
            group = ("NAMED", crit, "ACCEPT_DOCUMENT", value)
        elif code == "LOCATION":
            operator = c["request_value"]["operator"]
            wanted = (c["request_value"]["value"] if operator == "IN"
                      else [c["request_value"]["value"]])
            here = candidate["location_ancestry"]
            evaluated = []
            for position, w in enumerate(wanted):
                chain = location_chains.get(w)
                if chain is None:
                    raise RuntimeError("a requested location has no stored chain; the "
                                       "scenario cannot be stated (F6-10)")
                ids = [x["location_id"] for x in chain]
                common = next((p for p in here if p in ids), None)
                evaluated.append({
                    "location_id": w, "position": position, "common": common,
                    "level": None if common is None
                    else chain[ids.index(common)]["location_type"],
                    "property_below": None if common is None else here.index(common),
                    "widened": None if common is None else ids.index(common)})
            chosen = sorted(evaluated, key=lambda e: (
                e["common"] is None, e["property_below"] or 0, e["widened"] or 0,
                e["position"]))[0]
            near["choice"] = {"from": chosen["location_id"],
                              "levels_widened": chosen["widened"], "evaluated": evaluated}
            near["location_ancestry"] = here
            value = chosen["common"]
            group = ("LOCATION", crit, "WIDEN_AREA", value, chosen["level"])
        else:
            value = None
            group = ("NOT_PROPOSED", crit, "NOT_PROPOSED", c["basis"])
        groups.setdefault(group, []).append((value, near))

    scenarios = []
    for group, members in groups.items():
        kind, (code, ordinal) = group[0], group[1]
        base = {"criterion": code, "ordinal": ordinal, "scenario": group[2]}
        if kind == "NUMBER":
            # Per distinct magnitude, smallest change first; each turns every
            # near match whose own change is no larger.
            for magnitude in sorted({v for v, _ in members}, key=abs):
                turned = [n for v, n in members if abs(v) <= abs(magnitude)]
                body = {group[3]: magnitude}
                if group[3] == "budget_delta_dzd":
                    body["stated_at"] = "ASKING_PRICE"
                scenarios.append(((code, ordinal, 0, abs(magnitude), ""), {
                    **base, "magnitude": body, "near_matches": turned}))
        elif kind == "NAMED":
            entry = {**base, "named": group[3], "near_matches": [n for _, n in members]}
            if group[2] == "ACCEPT_DOCUMENT":
                entry["only_if_user_chooses"] = True
            scenarios.append(((code, ordinal, 1, -len(members), str(group[3])), entry))
        elif kind == "LOCATION":
            # Widening to `target` turns every near match failing this same
            # criterion whose property lies under `target`, whichever
            # location it chose itself.
            target = group[3]
            same_criterion = [n for g, mem in groups.items()
                              if g[0] == "LOCATION" and g[1] == group[1] for _, n in mem]
            turned = [] if target is None else [
                n for n in same_criterion if target in n["location_ancestry"]]
            choices = [{"property_id": n["property_id"], "offer_id": n["offer_id"],
                        **n["choice"]} for _, n in members]
            # Ordered by the widening of the REQUEST, the scenario's magnitude:
            # the fewest levels a requested location is widened, first.
            widened = 0 if target is None else min(
                n["choice"]["levels_widened"] for _, n in members)
            scenarios.append(((code, ordinal, 2 if target is not None else 3, widened,
                               str(target)), {
                **base, "widen_to": target, "level": group[4] or "NONE",
                "choices": choices,
                "near_matches": [{k: v for k, v in n.items()
                                  if k not in ("choice", "location_ancestry")}
                                 for n in turned]}))
        else:
            scenarios.append(((code, ordinal, 4, 0, str(group[3])), {
                **base, "basis": group[3], "near_matches": [n for _, n in members]}))
    out = []
    for _, scenario in sorted(scenarios, key=lambda s: (s[0][0], s[0][1], s[0][2], s[0][3],
                                                       s[0][4])):
        scenario["near_matches"] = sorted(
            scenario["near_matches"], key=lambda n: (str(n["property_id"]), str(n["offer_id"])))
        scenario["near_match_count"] = len(scenario["near_matches"])
        scenario["subordinate_to"] = list(subordinate_to)
        out.append(scenario)
    return out
