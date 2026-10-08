"""Slice 5 step 4, the reads and the match queue: which test refuses which weakening.

    .venv/bin/python db/dev/mutate_slice5_step4.py [V1 W1 ...] > /outside/the/tree.txt

Each mutation weakens ONE rule of step 4 (the review of 921ed01; plan G5-5
(a) with [R4-2], G5-6 (a), G5-7 (a), G5-11; RFC-001 Appendix B):
- V: who may see an opportunity, and the frozen customer type (V5, the
  free-text location detail: review of d0e0bc9);
- W: the withholding of an entry whose field changed ([R4-2]);
- I: the internal read, staff-only and recorded;
- Q: the match queue's membership, priority, reason, order and audit.

See `mutation_runner.py`.
"""
import sys

from mutation_runner import run

VIEWS = "src/turab/services/opportunity_views.py"
LOADERS = "src/turab/auth/loaders.py"
DTO = "src/turab/dto/boundaries.py"
ACCESS = "src/turab/services/access.py"
TESTS = "tests/test_slice5_step4.py"

READ_RECORD = ('''        self._auditor.read(subject=self._subject, operation_id=operation_id,
                           trace_id=self._trace_id, resource_kind=OPPORTUNITY_KIND,
                           resource_id=opportunity_id)
        return view''')
UNKNOWN_RECORD = ('''            self._auditor.denied(
                subject=self._subject, operation_id=operation_id,
                trace_id=self._trace_id,
                reason_code=DenyReason.OBJECT_NOT_AUTHORIZED.value,
                resource_kind=OPPORTUNITY_KIND, resource_id=opportunity_id)
            return AccessDenied(DenyReason.OBJECT_NOT_AUTHORIZED)''')
QUEUE_AUDIT = ('''        self.record_list_access(
            operation_id=operation_id, resource_kind=MATCH_KIND, result_count=len(items),
            query_shape={"membership": "G5-11", "excluded_eligibility": ["REJECTED"]})
''')

#: Review of d0e0bc9: the opportunity's property type without, then with, the
#: free-text `local_location_detail` (its declaration and its rendering).
LOCATION_TEXT_OFF = (
    "    canonical_location_id: uuid.UUID | None = None\n"
    "    land_area_m2: Decimal | None = None\n"
    "    built_area_m2: Decimal | None = None\n"
    "    current_availability: str\n"
    "    availability_last_confirmed_at: datetime | None = None\n"
    "    supply_mode: str\n"
    "    version: int\n"
    "\n"
    "    @classmethod\n"
    "    def render(cls, row: Mapping[str, Any]) -> \"CustomerOpportunityPropertyView\":\n"
    "        return cls(\n"
    "            property_id=row[\"property_id\"],\n"
    "            property_type=str(row[\"property_type\"]),\n"
    "            canonical_location_id=row.get(\"canonical_location_id\"),\n")
LOCATION_TEXT_ON = LOCATION_TEXT_OFF.replace(
    "    canonical_location_id: uuid.UUID | None = None\n",
    "    canonical_location_id: uuid.UUID | None = None\n"
    "    local_location_detail: str | None = None\n").replace(
    "            canonical_location_id=row.get(\"canonical_location_id\"),\n",
    "            canonical_location_id=row.get(\"canonical_location_id\"),\n"
    "            local_location_detail=row.get(\"local_location_detail\"),\n")

MUTATIONS = [
    # --- V: visibility and the frozen type --------------------------------------------
    ("V1 an unshared opportunity is visible", LOADERS,
     "               AND o.shared_at IS NOT NULL\n", ""),
    ("V2 SUMMARY_ONLY renders the full property", DTO,
     "        if scope is SharingScope.SUMMARY_ONLY:\n            property_view = "
     "CustomerPropertySummary.render(property_row)",
     "        if False:\n            property_view = CustomerPropertySummary.render(property_row)"),
    ("V3 the customer type carries a contact", DTO,
     "    created_at: datetime | None = None\n    shared_at: datetime | None = None\n\n\n"
     "def render_opportunity_for_scope(",
     "    created_at: datetime | None = None\n    shared_at: datetime | None = None\n"
     "    contact: dict[str, Any] | None = None\n\n\ndef render_opportunity_for_scope("),
    ("V4 the customer gets the internal view", VIEWS,
     "    return _jsonable(view.model_dump())",
     "    return internal_view(session, opportunity_id)"),
    ("V5 the free-text location detail is rendered", DTO, LOCATION_TEXT_OFF,
     LOCATION_TEXT_ON),
    # --- W: the withholding -----------------------------------------------------------
    ("W1 why_real is not withheld", VIEWS,
     '"criteria": withheld(criteria, scope, snapshot=snapshot, current=prop)}',
     '"criteria": criteria}'),
    ("W2 known_differences are not withheld", VIEWS,
     '''    differences = withheld(exact_json.loads(row["known_differences"]), scope,
                           snapshot=snapshot, current=prop)''',
     '''    differences = exact_json.loads(row["known_differences"])'''),
    ("W3 only a change from or to null withholds", VIEWS,
     "        if then != now:\n",
     "        if (then is None) != (now is None):\n"),
    ("W4 a null on both sides withholds", VIEWS,
     "        if then != now:\n",
     "        if then is None or now is None or then != now:\n"),
    ("W5 the area compared as text", VIEWS,
     'return str(value) if field == "property_type" else Decimal(str(value))',
     'return str(value)'),
    ("W6 the scope is ignored", VIEWS,
     "    shown = set(match_review.SHOWN_BY_SCOPE[scope])",
     "    shown = set(FIELD_OF)"),
    # --- I: the internal read ---------------------------------------------------------
    ("I1 the read is not recorded", ACCESS, READ_RECORD, "        return view"),
    ("I2 an unknown id is not recorded", ACCESS, UNKNOWN_RECORD,
     "            return AccessDenied(DenyReason.OBJECT_NOT_AUTHORIZED)"),
    # --- Q: the match queue -----------------------------------------------------------
    ("Q1 REJECTED is queued", VIEWS,
     "     WHERE m.eligibility <> 'REJECTED'\n", "     WHERE true\n"),
    ("Q2 the latest review is ignored", VIEWS,
     "       AND (latest.decision IS NULL OR latest.decision = 'NEED_MORE_INFORMATION')\n",
     ""),
    ("Q3 an approved match stays queued", VIEWS,
     '''       AND NOT EXISTS (SELECT 1 FROM turab.opportunities o
                        WHERE o.approved_match_id = m.match_id)
''', ""),
    ("Q4 an alias's match stays queued", VIEWS,
     '''       AND NOT EXISTS (SELECT 1 FROM turab.property_identity_aliases a
                        WHERE a.alias_property_id = m.property_id)
''', ""),
    ("Q5 supersession across offers", VIEWS,
     "                          AND n.evaluated_offer_id IS NOT DISTINCT FROM "
     "m.evaluated_offer_id\n", ""),
    ("Q6 a superseded match stays queued", VIEWS,
     "                          AND (n.evaluated_at, n.created_at) > (m.evaluated_at, "
     "m.created_at))",
     "                          AND false)"),
    ("Q7 an NMI review does not show", VIEWS,
     '''        reason = ("AWAITING_INFORMATION" if row["latest_review"] == "NEED_MORE_INFORMATION"
                  else "READY_FOR_REVIEW")''',
     '''        reason = "READY_FOR_REVIEW"'''),
    ("Q8 a reason without a code is null", VIEWS,
     'reason = first.get("reason_code") or first.get("basis")',
     'reason = first.get("reason_code")'),
    ("Q9 ELIGIBLE is NORMAL", VIEWS,
     '        priority = "HIGH"\n', '        priority = "NORMAL"\n'),
    ("Q10 the order ignores the priority", VIEWS,
     "    items.sort(key=lambda pair: (PRIORITY_ORDER[pair[0][\"priority\"]],\n"
     "                                 pair[1][\"evaluated_at\"], str(pair[1][\"match_id\"])))",
     "    items.sort(key=lambda pair: (pair[1][\"evaluated_at\"], str(pair[1][\"match_id\"])))"),
    ("Q11 the queue is not audited", ACCESS, QUEUE_AUDIT, ""),
]

if __name__ == "__main__":
    run("TURAB — Slice 5 step 4: which test refuses which weakening of the reads and the queue",
        TESTS, MUTATIONS, sys.argv[1:])
