"""Step 7, Identity Lite: which mechanism refuses which case.

    .venv/bin/python db/dev/mutate_identity.py [I1 I2 ...] > /outside/the/tree.txt

Each mutation removes or weakens ONE mechanism of `services/identity.py`,
then runs the shipped `tests/test_slice3_identity.py`. See `mutation_runner.py`.
"""
import sys

from mutation_runner import run

SVC = "src/turab/services/identity.py"

MUTATIONS = [
 # generation
 ("I1 the column default decides the version", SVC,
  "review_status, algorithm_version)\n                        VALUES (:a, :b, CAST(:s AS jsonb), "
  "CAST(:e AS jsonb),\n                                'PENDING_REVIEW', :v)",
  "review_status)\n                        VALUES (:a, :b, CAST(:s AS jsonb), "
  "CAST(:e AS jsonb),\n                                'PENDING_REVIEW')"),
 ("I2 an unimplemented version is accepted", SVC,
  "if version not in KNOWN_VERSIONS:", "if False:"),
 ("I3 generation writes a decided status", SVC,
  "'PENDING_REVIEW', :v)", "'UNSURE', :v)"),
 ("I4 the pair is not stored least-first", SVC,
  "SELECT LEAST(p.property_id, q.property_id)    AS a_id,\n"
  "           GREATEST(p.property_id, q.property_id) AS b_id",
  "SELECT q.property_id AS a_id,\n           p.property_id AS b_id"),
 ("I5 a pending pair is not returned again", SVC,
  'if existing["review_status"] == "PENDING_REVIEW":', "if False:"),
 ("I6 a decided pair is returned again", SVC,
  'if existing["review_status"] == "PENDING_REVIEW":', "if True:"),
 ("I7 the pair index violation is not absorbed", SVC,
  '                           None) != "ux_identity_pair":', '                           None) or True:'),
 ("I8 blocking ignores the type", SVC,
  "       AND q.property_type = p.property_type\n", ""),
 ("I9 blocking ignores the location", SVC,
  "       AND q.canonical_location_id = p.canonical_location_id\n", ""),
 ("I10 aliases are paired", SVC,
  "       AND NOT EXISTS (SELECT 1 FROM turab.property_identity_aliases x\n"
  "                        WHERE x.alias_property_id IN (p.property_id, q.property_id))\n", ""),
 ("I11 generation for an alias is allowed", SVC,
  "        if alias_of is not None:", "        if False:"),
 # rules-0.1.0
 ("I12 CLOSE threshold moved", SVC,
  'AREA_CLOSE_MAX_RATIO = Decimal("1.10")', 'AREA_CLOSE_MAX_RATIO = Decimal("1.20")'),
 ("I13 CONTRADICTION threshold moved", SVC,
  'AREA_CONTRADICTION_MIN_RATIO = Decimal("1.50")', 'AREA_CONTRADICTION_MIN_RATIO = Decimal("2.00")'),
 ("I14 local detail compared raw", SVC,
  'collapsed = re.sub(r"\\s+", " ", value).strip().casefold()', "collapsed = value"),
 ("I15 shared party never found", SVC,
  "ON ob.party_id = oa.party_id", "ON FALSE"),
 # review
 ("I16 SAME without a canonical allowed", SVC,
  "        if canonical_property_id is None:\n            raise Invalid(",
  "        if False:\n            raise Invalid("),
 ("I17 a canonical outside the pair allowed", SVC,
  "        if canonical_property_id not in pair:", "        if False:"),
 ("I18 a canonical with another decision allowed", SVC,
  "    elif canonical_property_id is not None:", "    elif False:"),
 ("I19 reason category not checked", SVC,
  "WHERE code = :c AND category = :k \"\n        \"AND active\"",
  "WHERE code = :c AND :k = :k \"\n        \"AND active\""),
 ("I20 a final decision reviewed again", SVC,
  '    if candidate["review_status"] in FINAL:', "    if False:"),
 ("I21 the candidate row not locked", SVC,
  "WHERE identity_candidate_id = :c FOR UPDATE", "WHERE identity_candidate_id = :c"),
 ("I22 the alias not written", SVC,
  "        session.execute(text(\"\"\"\n            INSERT INTO turab.property_identity_aliases",
  "        if False: session.execute(text(\"\"\"\n            INSERT INTO turab.property_identity_aliases"),
 ("I23 the pair's property rows not locked", SVC,
  "WHERE property_id IN (:x, :y) ORDER BY property_id FOR UPDATE",
  "WHERE property_id IN (:x, :y) ORDER BY property_id"),
 ("I24 canonical-is-alias not pre-checked", SVC,
  '    if facts["canon_is_alias"]:', "    if False:"),
 ("I25 alias-is-alias not pre-checked", SVC,
  '    if facts["alias_is_alias"]:', "    if False:"),
 ("I26 alias-is-canonical not pre-checked", SVC,
  '    if facts["alias_is_canonical"]:', "    if False:"),
 # the corrective effect
 ("I27 no review work raised", SVC,
  "        tasks = raise_review_work(session, alias=alias,",
  "        tasks = [] if True else raise_review_work(session, alias=alias,"),
 ("I28 a match's EARLIEST review decides", SVC,
  "ORDER BY r.reviewed_at DESC, r.match_review_id DESC",
  "ORDER BY r.reviewed_at ASC, r.match_review_id ASC"),
 ("I29 rejected matches count as open", SVC,
  "             LIMIT 1) IS DISTINCT FROM 'REJECTED'", "             LIMIT 1) IS NOT NULL OR TRUE"),
 ("I30 a match carried by an opportunity counts twice", SVC,
  "       AND NOT EXISTS (SELECT 1 FROM turab.opportunities o\n"
  "                        WHERE o.approved_match_id = m.match_id)\n", ""),
 ("I31 closed opportunities count as open", SVC,
  "WHERE o.property_id = :alias AND o.status <> 'CLOSED'", "WHERE o.property_id = :alias"),
 ("I32 duplicates on the canonical not surfaced", SVC,
  "WHERE c.property_id = :canon AND c.request_id = o.request_id",
  "WHERE FALSE AND c.request_id = o.request_id"),
 ("I33 review work not audited", SVC,
  '        audit_rows.write(session, "tasks", task_id, "INSERT", None,\n'
  '                         audit_rows.row_json(session, "tasks", task_id))\n', ""),
 # list
 ("I34 the status filter ignored", SVC,
  "OR review_status::text = CAST(:s AS text))", "OR TRUE)"),
]

if __name__ == "__main__":
    run("TURAB — step 7: which mechanism refuses which case in Identity Lite",
        "tests/test_slice3_identity.py", MUTATIONS, sys.argv[1:])
