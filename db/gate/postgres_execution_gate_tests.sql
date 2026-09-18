-- =============================================================================
-- TURAB — PostgreSQL Execution Gate: database-level contract tests
-- Ref: 04_DATABASE/POSTGRES_EXECUTION_GATE.md
-- Runs inside a single transaction and ROLLS BACK: leaves the database clean
-- and is safe to re-run. Any FAIL aborts with ON_ERROR_STOP=1.
-- =============================================================================
\set ON_ERROR_STOP on
SET search_path = turab, public;
BEGIN;

-- ---------- assertion helpers -------------------------------------------------
CREATE OR REPLACE FUNCTION turab_gate_expect_error(p_test text, p_sql text, p_expect text)
RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE msg text;
BEGIN
  BEGIN
    EXECUTE p_sql;
  EXCEPTION WHEN others THEN
    msg := SQLERRM;
    IF p_expect IS NULL OR position(lower(p_expect) in lower(msg)) > 0 THEN
      RAISE NOTICE 'PASS | % | blocked: %', p_test, left(msg, 95);
      RETURN;
    END IF;
    RAISE EXCEPTION 'FAIL | % | blocked, but unexpected reason: %', p_test, msg;
  END;
  RAISE EXCEPTION 'FAIL | % | statement was ALLOWED but must be blocked', p_test;
END $fn$;

CREATE OR REPLACE FUNCTION turab_gate_expect_ok(p_test text, p_sql text)
RETURNS void LANGUAGE plpgsql AS $fn$
BEGIN
  EXECUTE p_sql;
  RAISE NOTICE 'PASS | % | allowed as required', p_test;
EXCEPTION WHEN others THEN
  RAISE EXCEPTION 'FAIL | % | expected success, got: %', p_test, SQLERRM;
END $fn$;

CREATE OR REPLACE FUNCTION turab_gate_expect_true(p_test text, p_cond boolean, p_detail text)
RETURNS void LANGUAGE plpgsql AS $fn$
BEGIN
  IF p_cond IS NOT TRUE THEN
    RAISE EXCEPTION 'FAIL | % | %', p_test, p_detail;
  END IF;
  RAISE NOTICE 'PASS | % | %', p_test, p_detail;
END $fn$;

-- ---------- fixtures ----------------------------------------------------------
INSERT INTO parties (party_id, kind, status, display_name) VALUES
  ('11111111-0000-0000-0000-000000000001','PERSON','PARTY_ACTIVE','Buyer A'),
  ('11111111-0000-0000-0000-000000000002','PERSON','PARTY_ACTIVE','Seller B'),
  ('11111111-0000-0000-0000-000000000003','PERSON','PARTY_ACTIVE','Outsider C');

INSERT INTO user_accounts (account_id, party_id, status, email) VALUES
  ('22222222-0000-0000-0000-000000000001','11111111-0000-0000-0000-000000000001','ACTIVATED','staff@turab.test');

INSERT INTO properties (property_id, property_type, canonical_location_id, supply_mode,
                        management_mode, claim_status, current_availability)
SELECT p.id, 'HOUSE_VILLA', (SELECT location_id FROM locations WHERE location_type='COMMUNE' ORDER BY code LIMIT 1),
       p.mode::supply_mode, 'ASSISTED', 'UNCLAIMED', 'AVAILABLE'
FROM (VALUES
  ('33333333-0000-0000-0000-000000000001'::uuid,'PUBLIC'),
  ('33333333-0000-0000-0000-000000000002'::uuid,'PUBLIC'),
  ('33333333-0000-0000-0000-000000000003'::uuid,'PUBLIC'),
  ('33333333-0000-0000-0000-000000000004'::uuid,'POTENTIAL'),
  ('33333333-0000-0000-0000-000000000005'::uuid,'PUBLIC'),
  ('33333333-0000-0000-0000-000000000006'::uuid,'PUBLIC')
) AS p(id, mode);

INSERT INTO requests (request_id, party_id, status, transaction_intent, management_mode, claim_status,
                      desired_property_type, budget_max_dzd)
SELECT r.id, '11111111-0000-0000-0000-000000000001', 'ACTIVE', r.intent::request_transaction_intent,
       'ASSISTED', 'UNCLAIMED', 'HOUSE_VILLA', 10000000
FROM (VALUES
  ('44444444-0000-0000-0000-000000000001'::uuid,'BUY'),
  ('44444444-0000-0000-0000-000000000002'::uuid,'BUY'),
  ('44444444-0000-0000-0000-000000000003'::uuid,'RENT'),
  ('44444444-0000-0000-0000-000000000004'::uuid,'BUY')
) AS r(id, intent);

INSERT INTO property_offers (offer_id, property_id, party_id, transaction_type, status, asking_price_dzd, version) VALUES
  ('55555555-0000-0000-0000-000000000001','33333333-0000-0000-0000-000000000001','11111111-0000-0000-0000-000000000002','SALE','ACTIVE',9000000,1),
  ('55555555-0000-0000-0000-000000000002','33333333-0000-0000-0000-000000000002','11111111-0000-0000-0000-000000000002','RENT','ACTIVE',50000,1),
  ('55555555-0000-0000-0000-000000000003','33333333-0000-0000-0000-000000000003','11111111-0000-0000-0000-000000000002','SALE','ACTIVE',8000000,1),
  ('55555555-0000-0000-0000-000000000005','33333333-0000-0000-0000-000000000005','11111111-0000-0000-0000-000000000002','SALE','ACTIVE',7000000,1);

-- candidate factory (keeps the tests readable; snapshots offer version as the trigger requires)
CREATE OR REPLACE FUNCTION turab_gate_mk_candidate(
  p_match uuid, p_request uuid, p_property uuid, p_offer uuid,
  p_hash text DEFAULT 'hash-ok',
  p_elig text DEFAULT 'ELIGIBLE', p_hard text DEFAULT 'PASS',
  p_info text DEFAULT 'PASS', p_fresh text DEFAULT 'PASS', p_perm text DEFAULT 'PASS'
) RETURNS uuid LANGUAGE plpgsql AS $fn$
DECLARE pol matching_policies%ROWTYPE;
BEGIN
  SELECT * INTO pol FROM matching_policies WHERE active;
  INSERT INTO match_candidates (
    match_id, request_id, property_id, evaluated_offer_id,
    matching_policy_id, matching_policy_version,
    request_version, property_version, offer_version,
    eligibility, hard_gate_status, information_gate_status,
    request_freshness, property_freshness, offer_freshness,
    freshness_gate_status, permission_gate_status,
    request_snapshot, property_snapshot, input_hash)
  VALUES (
    p_match, p_request, p_property, p_offer,
    pol.matching_policy_id, pol.version,
    (SELECT version FROM requests WHERE request_id = p_request),
    (SELECT version FROM properties WHERE property_id = p_property),
    (SELECT version FROM property_offers WHERE offer_id = p_offer),
    p_elig::match_eligibility, p_hard::gate_status, p_info::gate_status,
    'FRESH','FRESH', CASE WHEN p_offer IS NULL THEN 'NOT_APPLICABLE' ELSE 'FRESH' END::freshness_state,
    p_fresh::gate_status, p_perm::gate_status,
    '{}'::jsonb, '{}'::jsonb, p_hash);
  RETURN p_match;
END $fn$;

\echo ''
\echo '== T10. exactly one active matching policy =========================='
SELECT turab_gate_expect_true('T10.seed-has-one-active',
  (SELECT count(*) FROM matching_policies WHERE active) = 1,
  'exactly one active policy after double seed');
SELECT turab_gate_expect_error('T10.second-active-rejected', $q$
  INSERT INTO matching_policies (version, name, rules, active)
  VALUES ('rules-9.9.9-test','second active','{}'::jsonb, true) $q$,
  'ux_matching_policy_one_active');
SELECT turab_gate_expect_ok('T10.inactive-policy-allowed', $q$
  INSERT INTO matching_policies (version, name, rules, active)
  VALUES ('rules-9.9.8-test','inactive draft','{}'::jsonb, false) $q$);

\echo ''
\echo '== T7. match commercial context / BUY-RENT ========================='
SELECT turab_gate_expect_error('T7.buy-request-vs-rent-offer', $q$
  SELECT turab_gate_mk_candidate('66666666-0000-0000-0000-0000000000f1',
    '44444444-0000-0000-0000-000000000002','33333333-0000-0000-0000-000000000002',
    '55555555-0000-0000-0000-000000000002') $q$,
  'transaction intent does not match');
SELECT turab_gate_expect_error('T7.rent-request-vs-sale-offer', $q$
  SELECT turab_gate_mk_candidate('66666666-0000-0000-0000-0000000000f2',
    '44444444-0000-0000-0000-000000000003','33333333-0000-0000-0000-000000000001',
    '55555555-0000-0000-0000-000000000001') $q$,
  'transaction intent does not match');
SELECT turab_gate_expect_error('T7.offer-from-another-property', $q$
  SELECT turab_gate_mk_candidate('66666666-0000-0000-0000-0000000000f3',
    '44444444-0000-0000-0000-000000000001','33333333-0000-0000-0000-000000000001',
    '55555555-0000-0000-0000-000000000003') $q$,
  'must belong to matched property');
SELECT turab_gate_expect_error('T7.non-potential-requires-offer', $q$
  SELECT turab_gate_mk_candidate('66666666-0000-0000-0000-0000000000f4',
    '44444444-0000-0000-0000-000000000001','33333333-0000-0000-0000-000000000001', NULL) $q$,
  'requires evaluated_offer_id');
SELECT turab_gate_expect_ok('T7.potential-property-without-offer', $q$
  SELECT turab_gate_mk_candidate('66666666-0000-0000-0000-0000000000f5',
    '44444444-0000-0000-0000-000000000004','33333333-0000-0000-0000-000000000004', NULL, 'hash-potential') $q$);
SELECT turab_gate_expect_error('T7.stale-offer-version-snapshot', $q$
  INSERT INTO match_candidates (match_id, request_id, property_id, evaluated_offer_id,
    matching_policy_id, matching_policy_version, request_version, property_version, offer_version,
    eligibility, hard_gate_status, information_gate_status, request_freshness, property_freshness,
    freshness_gate_status, permission_gate_status, request_snapshot, property_snapshot, input_hash)
  SELECT '66666666-0000-0000-0000-0000000000f6','44444444-0000-0000-0000-000000000001',
    '33333333-0000-0000-0000-000000000001','55555555-0000-0000-0000-000000000001',
    matching_policy_id, version, 1, 1, 999,
    'ELIGIBLE','PASS','PASS','FRESH','FRESH','PASS','PASS','{}'::jsonb,'{}'::jsonb,'hash-stale'
  FROM matching_policies WHERE active $q$,
  'offer_version must snapshot');
SELECT turab_gate_expect_error('T7.policy-version-must-match-id', $q$
  INSERT INTO match_candidates (match_id, request_id, property_id, evaluated_offer_id,
    matching_policy_id, matching_policy_version, request_version, property_version, offer_version,
    eligibility, hard_gate_status, information_gate_status, request_freshness, property_freshness,
    freshness_gate_status, permission_gate_status, request_snapshot, property_snapshot, input_hash)
  SELECT '66666666-0000-0000-0000-0000000000f7','44444444-0000-0000-0000-000000000001',
    '33333333-0000-0000-0000-000000000001','55555555-0000-0000-0000-000000000001',
    matching_policy_id, 'wrong-version', 1, 1, 1,
    'ELIGIBLE','PASS','PASS','FRESH','FRESH','PASS','PASS','{}'::jsonb,'{}'::jsonb,'hash-polver'
  FROM matching_policies WHERE active $q$,
  'matching_policy_version must match');

\echo ''
\echo '== T6. alias -> canonical property constraint ======================'
INSERT INTO property_identity_candidates (identity_candidate_id, property_a_id, property_b_id, review_status) VALUES
  ('77777777-0000-0000-0000-000000000001','33333333-0000-0000-0000-000000000005','33333333-0000-0000-0000-000000000006','PENDING_REVIEW'),
  ('77777777-0000-0000-0000-000000000002','33333333-0000-0000-0000-000000000006','33333333-0000-0000-0000-000000000003','PENDING_REVIEW'),
  ('77777777-0000-0000-0000-000000000003','33333333-0000-0000-0000-000000000001','33333333-0000-0000-0000-000000000003','PENDING_REVIEW');

SELECT turab_gate_expect_error('T6.pair-must-match-identity-candidate', $q$
  INSERT INTO property_identity_aliases (alias_property_id, canonical_property_id,
    source_identity_candidate_id, resolved_by_account_id)
  VALUES ('33333333-0000-0000-0000-000000000005','33333333-0000-0000-0000-000000000003',
          '77777777-0000-0000-0000-000000000001','22222222-0000-0000-0000-000000000001') $q$,
  'must match identity candidate pair');

SELECT turab_gate_expect_error('T6.confirmed-same-requires-alias-mapping', $q$
  UPDATE property_identity_candidates SET review_status='CONFIRMED_SAME'
  WHERE identity_candidate_id='77777777-0000-0000-0000-000000000001' $q$,
  'requires a canonical alias mapping');

SELECT turab_gate_expect_ok('T6.alias-created-non-destructively', $q$
  INSERT INTO property_identity_aliases (alias_property_id, canonical_property_id,
    source_identity_candidate_id, resolved_by_account_id)
  VALUES ('33333333-0000-0000-0000-000000000005','33333333-0000-0000-0000-000000000006',
          '77777777-0000-0000-0000-000000000001','22222222-0000-0000-0000-000000000001') $q$);

SELECT turab_gate_expect_true('T6.alias-source-rows-preserved',
  (SELECT count(*) FROM property_offers WHERE property_id='33333333-0000-0000-0000-000000000005') = 1,
  'alias property keeps its offers/history (non-destructive merge)');

SELECT turab_gate_expect_error('T6.canonical-cannot-itself-be-alias', $q$
  INSERT INTO property_identity_aliases (alias_property_id, canonical_property_id,
    source_identity_candidate_id, resolved_by_account_id)
  VALUES ('33333333-0000-0000-0000-000000000003','33333333-0000-0000-0000-000000000005',
          '77777777-0000-0000-0000-000000000002','22222222-0000-0000-0000-000000000001') $q$,
  'cannot itself be an alias');

SELECT turab_gate_expect_error('T6.existing-canonical-cannot-become-alias', $q$
  INSERT INTO property_identity_aliases (alias_property_id, canonical_property_id,
    source_identity_candidate_id, resolved_by_account_id)
  VALUES ('33333333-0000-0000-0000-000000000006','33333333-0000-0000-0000-000000000003',
          '77777777-0000-0000-0000-000000000002','22222222-0000-0000-0000-000000000001') $q$,
  'already acting as canonical');

SELECT turab_gate_expect_error('T7.match-must-target-canonical-not-alias', $q$
  SELECT turab_gate_mk_candidate('66666666-0000-0000-0000-0000000000f8',
    '44444444-0000-0000-0000-000000000004','33333333-0000-0000-0000-000000000005',
    '55555555-0000-0000-0000-000000000005','hash-alias') $q$,
  'canonical properties, not identity aliases');

\echo ''
\echo '== T5. consent resource binding ===================================='
INSERT INTO consent_grants (consent_id, party_id, scope, status, channel, consent_version, granted_at) VALUES
  ('88888888-0000-0000-0000-000000000001','11111111-0000-0000-0000-000000000001','PRIVATE_MATCHING_ONLY','GRANTED','WHATSAPP','v1', now()),
  ('88888888-0000-0000-0000-000000000002','11111111-0000-0000-0000-000000000003','PRIVATE_MATCHING_ONLY','GRANTED','WHATSAPP','v1', now()),
  ('88888888-0000-0000-0000-000000000003','11111111-0000-0000-0000-000000000001','PRIVATE_MATCHING_ONLY','REVOKED','WHATSAPP','v1', now());

SELECT turab_gate_expect_error('T5.purpose-must-match-granted-scope', $q$
  INSERT INTO resource_consent_bindings (consent_id, purpose, request_id)
  VALUES ('88888888-0000-0000-0000-000000000001','PUBLIC_LISTING_ALLOWED','44444444-0000-0000-0000-000000000001') $q$,
  'does not match binding purpose');

SELECT turab_gate_expect_error('T5.consent-of-another-party-rejected', $q$
  INSERT INTO resource_consent_bindings (consent_id, purpose, request_id)
  VALUES ('88888888-0000-0000-0000-000000000002','PRIVATE_MATCHING_ONLY','44444444-0000-0000-0000-000000000001') $q$,
  'party mismatch');

SELECT turab_gate_expect_error('T5.revoked-consent-cannot-bind', $q$
  INSERT INTO resource_consent_bindings (consent_id, purpose, request_id)
  VALUES ('88888888-0000-0000-0000-000000000003','PRIVATE_MATCHING_ONLY','44444444-0000-0000-0000-000000000001') $q$,
  'must exist and be granted');

SELECT turab_gate_expect_error('T5.property-binding-needs-active-relation', $q$
  INSERT INTO resource_consent_bindings (consent_id, purpose, property_id)
  VALUES ('88888888-0000-0000-0000-000000000001','PRIVATE_MATCHING_ONLY','33333333-0000-0000-0000-000000000001') $q$,
  'no active property relation');

SELECT turab_gate_expect_error('T5.binding-must-name-exactly-one-resource', $q$
  INSERT INTO resource_consent_bindings (consent_id, purpose, request_id, property_id)
  VALUES ('88888888-0000-0000-0000-000000000001','PRIVATE_MATCHING_ONLY',
          '44444444-0000-0000-0000-000000000001','33333333-0000-0000-0000-000000000001') $q$,
  'check constraint');

SELECT turab_gate_expect_ok('T5.correct-party-resource-purpose-binds', $q$
  INSERT INTO resource_consent_bindings (consent_id, purpose, request_id)
  VALUES ('88888888-0000-0000-0000-000000000001','PRIVATE_MATCHING_ONLY','44444444-0000-0000-0000-000000000001') $q$);

SELECT turab_gate_expect_true('T5.revocation-keeps-history',
  (SELECT count(*) FROM consent_grants WHERE consent_id='88888888-0000-0000-0000-000000000003') = 1,
  'revoked grant row is retained, not deleted');

\echo ''
\echo '== T3. resolution lineage =========================================='
INSERT INTO claims (claim_id, property_id, attribute_code, claimed_value, effective_verification_level) VALUES
  ('99999999-0000-0000-0000-000000000001','33333333-0000-0000-0000-000000000001','land_area_m2','{"v":300}'::jsonb,'DECLARED');
INSERT INTO claims (claim_id, request_id, attribute_code, claimed_value) VALUES
  ('99999999-0000-0000-0000-000000000002','44444444-0000-0000-0000-000000000001','budget_max_dzd','{"v":10000000}'::jsonb);

SELECT turab_gate_expect_error('T3.attribute-must-match-source-claim', $q$
  INSERT INTO resolved_values (property_id, attribute_code, resolved_value, source_claim_id)
  VALUES ('33333333-0000-0000-0000-000000000001','built_area_m2','{"v":300}'::jsonb,
          '99999999-0000-0000-0000-000000000001') $q$,
  'attribute must match source claim');

SELECT turab_gate_expect_error('T3.subject-must-match-source-claim', $q$
  INSERT INTO resolved_values (property_id, attribute_code, resolved_value, source_claim_id)
  VALUES ('33333333-0000-0000-0000-000000000002','land_area_m2','{"v":300}'::jsonb,
          '99999999-0000-0000-0000-000000000001') $q$,
  'subject must match source claim');

SELECT turab_gate_expect_error('T3.dangling-source-claim-rejected', $q$
  INSERT INTO resolved_values (property_id, attribute_code, resolved_value, source_claim_id)
  VALUES ('33333333-0000-0000-0000-000000000001','land_area_m2','{"v":300}'::jsonb,
          '99999999-0000-0000-0000-0000000000ff') $q$,
  NULL);

SELECT turab_gate_expect_ok('T3.matching-lineage-accepted', $q$
  INSERT INTO resolved_values (resolved_value_id, property_id, attribute_code, resolved_value, source_claim_id)
  VALUES ('aaaaaaaa-0000-0000-0000-000000000001','33333333-0000-0000-0000-000000000001',
          'land_area_m2','{"v":300}'::jsonb,'99999999-0000-0000-0000-000000000001') $q$);

SELECT turab_gate_expect_error('T3.one-current-resolution-per-subject-attribute', $q$
  INSERT INTO resolved_values (property_id, attribute_code, resolved_value, source_claim_id)
  VALUES ('33333333-0000-0000-0000-000000000001','land_area_m2','{"v":350}'::jsonb,
          '99999999-0000-0000-0000-000000000001') $q$,
  'ux_resolved_current_property');

\echo ''
\echo '== T4. verification upgrade path ==================================='
SELECT turab_gate_expect_true('T4.claim-starts-declared',
  (SELECT effective_verification_level FROM claims WHERE claim_id='99999999-0000-0000-0000-000000000001') = 'DECLARED',
  'claim begins at DECLARED (declared != verified)');

INSERT INTO verification_events (claim_id, level, outcome, verified_by_account_id)
VALUES ('99999999-0000-0000-0000-000000000001','DOCUMENT_SEEN','CONFIRMED','22222222-0000-0000-0000-000000000001');
SELECT turab_gate_expect_true('T4.confirmed-event-raises-level',
  (SELECT effective_verification_level FROM claims WHERE claim_id='99999999-0000-0000-0000-000000000001') = 'DOCUMENT_SEEN',
  'CONFIRMED verification event raised DECLARED -> DOCUMENT_SEEN');

INSERT INTO verification_events (claim_id, level, outcome, verified_by_account_id)
VALUES ('99999999-0000-0000-0000-000000000001','DECLARED','CONFIRMED','22222222-0000-0000-0000-000000000001');
SELECT turab_gate_expect_true('T4.level-never-downgraded-silently',
  (SELECT effective_verification_level FROM claims WHERE claim_id='99999999-0000-0000-0000-000000000001') = 'DOCUMENT_SEEN',
  'a lower-level event does not lower the effective level (GREATEST)');

INSERT INTO verification_events (claim_id, level, outcome, verified_by_account_id)
VALUES ('99999999-0000-0000-0000-000000000002','PROFESSIONAL_CHECK','NOT_CONFIRMED','22222222-0000-0000-0000-000000000001');
SELECT turab_gate_expect_true('T4.not-confirmed-does-not-upgrade',
  (SELECT effective_verification_level FROM claims WHERE claim_id='99999999-0000-0000-0000-000000000002') = 'DECLARED',
  'NOT_CONFIRMED outcome leaves the level untouched');

INSERT INTO verification_events (claim_id, level, outcome, verified_by_account_id)
VALUES ('99999999-0000-0000-0000-000000000002','DOCUMENT_SEEN','CONFLICT_FOUND','22222222-0000-0000-0000-000000000001');
SELECT turab_gate_expect_true('T4.conflict-marks-claim-conflicting',
  (SELECT status FROM claims WHERE claim_id='99999999-0000-0000-0000-000000000002') = 'CONFLICTING',
  'CONFLICT_FOUND marks the claim CONFLICTING instead of upgrading it');

\echo ''
\echo '== T8. assisted / claim-state checks ==============================='
SELECT turab_gate_expect_error('T8.assisted-request-cannot-be-claimed', $q$
  INSERT INTO requests (party_id, status, transaction_intent, management_mode, claim_status)
  VALUES ('11111111-0000-0000-0000-000000000001','ACTIVE','BUY','ASSISTED','CLAIMED') $q$,
  'check constraint');
SELECT turab_gate_expect_error('T8.self-managed-request-cannot-be-unclaimed', $q$
  INSERT INTO requests (party_id, status, transaction_intent, management_mode, claim_status)
  VALUES ('11111111-0000-0000-0000-000000000001','ACTIVE','BUY','SELF_MANAGED','UNCLAIMED') $q$,
  'check constraint');
SELECT turab_gate_expect_error('T8.assisted-property-cannot-be-claimed', $q$
  INSERT INTO properties (property_type, management_mode, claim_status)
  VALUES ('LAND','ASSISTED','CLAIMED') $q$,
  'check constraint');
SELECT turab_gate_expect_ok('T8.shared-management-requires-claimed', $q$
  INSERT INTO requests (party_id, status, transaction_intent, management_mode, claim_status)
  VALUES ('11111111-0000-0000-0000-000000000001','ACTIVE','BUY','SHARED_MANAGEMENT','CLAIMED') $q$);
SELECT turab_gate_expect_error('T8.property-attribute-claim-must-match-subject', $q$
  INSERT INTO property_attributes (property_id, attribute_definition_id, value, resolved_claim_id)
  SELECT '33333333-0000-0000-0000-000000000002', attribute_definition_id, '{"v":1}'::jsonb,
         '99999999-0000-0000-0000-000000000001'
  FROM attribute_definitions ORDER BY code LIMIT 1 $q$,
  'same property and attribute');

\echo ''
\echo '== T1. opportunity gate ============================================'
-- a fully-passing candidate, and a hard-FAIL candidate on the same request/property family
SELECT turab_gate_mk_candidate('66666666-0000-0000-0000-000000000001',
  '44444444-0000-0000-0000-000000000001','33333333-0000-0000-0000-000000000001',
  '55555555-0000-0000-0000-000000000001','hash-ok-1');
SELECT turab_gate_mk_candidate('66666666-0000-0000-0000-000000000002',
  '44444444-0000-0000-0000-000000000002','33333333-0000-0000-0000-000000000003',
  '55555555-0000-0000-0000-000000000003','hash-fail-1','REJECTED','FAIL','PASS','PASS','PASS');

SELECT turab_gate_expect_error('T1.cannot-approve-a-hard-FAIL-candidate', $q$
  INSERT INTO match_reviews (match_id, decision, reviewer_account_id)
  VALUES ('66666666-0000-0000-0000-000000000002','APPROVED','22222222-0000-0000-0000-000000000001') $q$,
  'before all opportunity gates pass');

SELECT turab_gate_expect_ok('T1.rejecting-a-failing-candidate-is-allowed', $q$
  INSERT INTO match_reviews (match_id, decision, reviewer_account_id)
  VALUES ('66666666-0000-0000-0000-000000000002','REJECTED','22222222-0000-0000-0000-000000000001') $q$);

SELECT turab_gate_expect_error('T1.no-opportunity-without-human-review', $q$
  INSERT INTO opportunities (request_id, property_id, approved_match_id, current_offer_id,
    sharing_scope, why_real, created_by_account_id)
  VALUES ('44444444-0000-0000-0000-000000000001','33333333-0000-0000-0000-000000000001',
          '66666666-0000-0000-0000-000000000001','55555555-0000-0000-0000-000000000001',
          'SUMMARY_ONLY','{}'::jsonb,'22222222-0000-0000-0000-000000000001') $q$,
  'latest human review to be approved');

SELECT turab_gate_expect_error('T1.no-opportunity-from-rejected-review', $q$
  INSERT INTO opportunities (request_id, property_id, approved_match_id, current_offer_id,
    sharing_scope, why_real, created_by_account_id)
  VALUES ('44444444-0000-0000-0000-000000000002','33333333-0000-0000-0000-000000000003',
          '66666666-0000-0000-0000-000000000002','55555555-0000-0000-0000-000000000003',
          'SUMMARY_ONLY','{}'::jsonb,'22222222-0000-0000-0000-000000000001') $q$,
  'latest human review to be approved');

-- approve the good candidate
INSERT INTO match_reviews (match_review_id, match_id, decision, reviewer_account_id, reviewed_at)
VALUES ('bbbbbbbb-0000-0000-0000-000000000001','66666666-0000-0000-0000-000000000001','APPROVED',
        '22222222-0000-0000-0000-000000000001', now() - interval '2 hours');

SELECT turab_gate_expect_error('T1.opportunity-pair-must-match-candidate', $q$
  INSERT INTO opportunities (request_id, property_id, approved_match_id, current_offer_id,
    sharing_scope, why_real, created_by_account_id)
  VALUES ('44444444-0000-0000-0000-000000000001','33333333-0000-0000-0000-000000000002',
          '66666666-0000-0000-0000-000000000001','55555555-0000-0000-0000-000000000001',
          'SUMMARY_ONLY','{}'::jsonb,'22222222-0000-0000-0000-000000000001') $q$,
  'must match approved candidate');

SELECT turab_gate_expect_error('T1.current-offer-must-equal-evaluated-offer', $q$
  INSERT INTO opportunities (request_id, property_id, approved_match_id, current_offer_id,
    sharing_scope, why_real, created_by_account_id)
  VALUES ('44444444-0000-0000-0000-000000000001','33333333-0000-0000-0000-000000000001',
          '66666666-0000-0000-0000-000000000001', NULL,
          'SUMMARY_ONLY','{}'::jsonb,'22222222-0000-0000-0000-000000000001') $q$,
  'must initially match evaluated offer');

SELECT turab_gate_expect_error('T1.unknown-approved-match-rejected', $q$
  INSERT INTO opportunities (request_id, property_id, approved_match_id, current_offer_id,
    sharing_scope, why_real, created_by_account_id)
  VALUES ('44444444-0000-0000-0000-000000000001','33333333-0000-0000-0000-000000000001',
          '66666666-0000-0000-0000-0000000000ee','55555555-0000-0000-0000-000000000001',
          'SUMMARY_ONLY','{}'::jsonb,'22222222-0000-0000-0000-000000000001') $q$,
  NULL);

SELECT turab_gate_expect_ok('T1.approved-candidate-yields-opportunity', $q$
  INSERT INTO opportunities (opportunity_id, request_id, property_id, approved_match_id, current_offer_id,
    sharing_scope, why_real, created_by_account_id)
  VALUES ('cccccccc-0000-0000-0000-000000000001','44444444-0000-0000-0000-000000000001',
          '33333333-0000-0000-0000-000000000001','66666666-0000-0000-0000-000000000001',
          '55555555-0000-0000-0000-000000000001','SUMMARY_ONLY','{}'::jsonb,
          '22222222-0000-0000-0000-000000000001') $q$);

\echo ''
\echo '== T2. append-only match review, latest decision wins =============='
SELECT turab_gate_expect_error('T2.match-review-cannot-be-updated', $q$
  UPDATE match_reviews SET decision='REJECTED'
  WHERE match_review_id='bbbbbbbb-0000-0000-0000-000000000001' $q$,
  'immutable');
SELECT turab_gate_expect_error('T2.match-review-cannot-be-deleted', $q$
  DELETE FROM match_reviews WHERE match_review_id='bbbbbbbb-0000-0000-0000-000000000001' $q$,
  'immutable');
SELECT turab_gate_expect_error('T2.match-candidate-snapshot-is-immutable', $q$
  UPDATE match_candidates SET soft_score=0.5
  WHERE match_id='66666666-0000-0000-0000-000000000001' $q$,
  'immutable');
SELECT turab_gate_expect_error('T2.match-candidate-cannot-be-deleted', $q$
  DELETE FROM match_candidates WHERE match_id='66666666-0000-0000-0000-000000000001' $q$,
  'immutable');

-- a later review supersedes an earlier APPROVED one, without deleting it
SELECT turab_gate_mk_candidate('66666666-0000-0000-0000-000000000003',
  '44444444-0000-0000-0000-000000000004','33333333-0000-0000-0000-000000000003',
  '55555555-0000-0000-0000-000000000003','hash-ok-3');
INSERT INTO match_reviews (match_id, decision, reviewer_account_id, reviewed_at)
VALUES ('66666666-0000-0000-0000-000000000003','APPROVED','22222222-0000-0000-0000-000000000001', now() - interval '3 hours');
INSERT INTO match_reviews (match_id, decision, reviewer_account_id, reviewed_at)
VALUES ('66666666-0000-0000-0000-000000000003','NEED_MORE_INFORMATION','22222222-0000-0000-0000-000000000001', now() - interval '1 hour');

SELECT turab_gate_expect_true('T2.review-history-is-appended-not-replaced',
  (SELECT count(*) FROM match_reviews WHERE match_id='66666666-0000-0000-0000-000000000003') = 2,
  'both decisions retained in history');
SELECT turab_gate_expect_true('T2.latest_match_reviews-view-returns-newest',
  (SELECT decision FROM latest_match_reviews WHERE match_id='66666666-0000-0000-0000-000000000003') = 'NEED_MORE_INFORMATION',
  'the view resolves to the most recent decision');
SELECT turab_gate_expect_error('T2.superseded-approval-cannot-create-opportunity', $q$
  INSERT INTO opportunities (request_id, property_id, approved_match_id, current_offer_id,
    sharing_scope, why_real, created_by_account_id)
  VALUES ('44444444-0000-0000-0000-000000000004','33333333-0000-0000-0000-000000000003',
          '66666666-0000-0000-0000-000000000003','55555555-0000-0000-0000-000000000003',
          'SUMMARY_ONLY','{}'::jsonb,'22222222-0000-0000-0000-000000000001') $q$,
  'latest human review to be approved');

\echo ''
\echo '== T11. one open opportunity per Request x canonical Property ======'
-- a second, independently valid candidate for the SAME request x property pair
SELECT turab_gate_mk_candidate('66666666-0000-0000-0000-000000000004',
  '44444444-0000-0000-0000-000000000001','33333333-0000-0000-0000-000000000001',
  '55555555-0000-0000-0000-000000000001','hash-ok-1-bis');
INSERT INTO match_reviews (match_id, decision, reviewer_account_id)
VALUES ('66666666-0000-0000-0000-000000000004','APPROVED','22222222-0000-0000-0000-000000000001');

SELECT turab_gate_expect_error('T11.second-open-opportunity-blocked', $q$
  INSERT INTO opportunities (request_id, property_id, approved_match_id, current_offer_id,
    sharing_scope, why_real, created_by_account_id)
  VALUES ('44444444-0000-0000-0000-000000000001','33333333-0000-0000-0000-000000000001',
          '66666666-0000-0000-0000-000000000004','55555555-0000-0000-0000-000000000001',
          'SUMMARY_ONLY','{}'::jsonb,'22222222-0000-0000-0000-000000000001') $q$,
  'ux_one_open_opportunity_per_pair');

UPDATE opportunities SET status='CLOSED', closed_at=now()
WHERE opportunity_id='cccccccc-0000-0000-0000-000000000001';

SELECT turab_gate_expect_ok('T11.after-closing-a-new-opportunity-is-allowed', $q$
  INSERT INTO opportunities (opportunity_id, request_id, property_id, approved_match_id, current_offer_id,
    sharing_scope, why_real, created_by_account_id)
  VALUES ('cccccccc-0000-0000-0000-000000000002','44444444-0000-0000-0000-000000000001',
          '33333333-0000-0000-0000-000000000001','66666666-0000-0000-0000-000000000004',
          '55555555-0000-0000-0000-000000000001','SUMMARY_ONLY','{}'::jsonb,
          '22222222-0000-0000-0000-000000000001') $q$);

SELECT turab_gate_expect_true('T11.closed-opportunity-is-retained',
  (SELECT count(*) FROM opportunities WHERE request_id='44444444-0000-0000-0000-000000000001'
     AND property_id='33333333-0000-0000-0000-000000000001') = 2,
  'closing supersedes without deleting the earlier opportunity');

SELECT turab_gate_expect_error('T11.one-opportunity-per-approved-match', $q$
  INSERT INTO opportunities (request_id, property_id, approved_match_id, current_offer_id,
    sharing_scope, why_real, created_by_account_id)
  VALUES ('44444444-0000-0000-0000-000000000001','33333333-0000-0000-0000-000000000001',
          '66666666-0000-0000-0000-000000000004','55555555-0000-0000-0000-000000000001',
          'SUMMARY_ONLY','{}'::jsonb,'22222222-0000-0000-0000-000000000001') $q$,
  NULL);

\echo ''
\echo '== T9. protected hard deletes ======================================'
SELECT turab_gate_expect_error('T9.requests-not-hard-deletable', $q$
  DELETE FROM requests WHERE request_id='44444444-0000-0000-0000-000000000001' $q$,
  'hard delete prohibited');
SELECT turab_gate_expect_error('T9.properties-not-hard-deletable', $q$
  DELETE FROM properties WHERE property_id='33333333-0000-0000-0000-000000000001' $q$,
  'hard delete prohibited');
SELECT turab_gate_expect_error('T9.offers-not-hard-deletable', $q$
  DELETE FROM property_offers WHERE offer_id='55555555-0000-0000-0000-000000000001' $q$,
  'hard delete prohibited');
SELECT turab_gate_expect_error('T9.claims-not-hard-deletable', $q$
  DELETE FROM claims WHERE claim_id='99999999-0000-0000-0000-000000000001' $q$,
  'hard delete prohibited');
SELECT turab_gate_expect_error('T9.resolved-values-not-hard-deletable', $q$
  DELETE FROM resolved_values WHERE resolved_value_id='aaaaaaaa-0000-0000-0000-000000000001' $q$,
  'hard delete prohibited');
SELECT turab_gate_expect_error('T9.opportunities-not-hard-deletable', $q$
  DELETE FROM opportunities WHERE opportunity_id='cccccccc-0000-0000-0000-000000000002' $q$,
  'hard delete prohibited');

\echo ''
\echo '== Provenance / audit sanity ======================================='
SELECT turab_gate_expect_true('AUDIT.critical-mutations-are-recorded',
  (SELECT count(*) FROM audit_log WHERE entity_table IN
     ('requests','properties','property_offers','opportunities','claims','match_reviews')) > 0,
  'audit_log captured critical-entity mutations');

\echo ''
\echo '== T12. Adrar location integrity (Slice -1 mandatory) ============='
-- "Ksar Tililane and New City Tililane remain distinct canonical locations"
-- IMPLEMENTATION_SLICES_v0.2.md, Slice -1 mandatory tests.
SELECT turab_gate_expect_true('T12.tililane-pair-both-seeded',
  (SELECT count(*) FROM locations WHERE code IN ('ADR-KSAR-TILILANE','ADR-NEW-TIL')) = 2,
  'both Tililane locations exist after a double seed');
SELECT turab_gate_expect_true('T12.tililane-distinct-identities',
  (SELECT count(DISTINCT location_id) FROM locations
     WHERE code IN ('ADR-KSAR-TILILANE','ADR-NEW-TIL')) = 2,
  'Ksar Tililane and New City Tililane are two distinct canonical locations');
SELECT turab_gate_expect_true('T12.tililane-different-types',
  (SELECT location_type FROM locations WHERE code='ADR-KSAR-TILILANE') = 'KSAR'
  AND (SELECT location_type FROM locations WHERE code='ADR-NEW-TIL') = 'AREA',
  'the ksar is KSAR and the new city is AREA; a shared name is not a shared place');
SELECT turab_gate_expect_true('T12.tililane-aliases-not-crossed',
  (SELECT count(*) FROM location_aliases a
     JOIN locations l ON l.location_id = a.location_id
    WHERE l.code = 'ADR-NEW-TIL' AND a.normalized_text = 'قصر تيليلان') = 0,
  'the ksar alias never resolves to the new city');
SELECT turab_gate_expect_error('T12.location-code-is-unique', $q$
  INSERT INTO locations (code, canonical_ar, location_type)
  VALUES ('ADR-KSAR-TILILANE','تكرار','KSAR') $q$,
  NULL);

\echo ''
\echo '== GATE RESULT ====================================================='
SELECT 'ALL DATABASE-LEVEL CONTRACT TESTS PASSED' AS gate_result;

ROLLBACK;
