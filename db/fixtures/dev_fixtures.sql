-- =============================================================================
-- TURAB — development fixtures
-- Ref: IMPLEMENTATION_SLICES_v0.2.md, Slice -1 ("test fixtures for Adrar
--      locations, parties, requests, properties/offers and consents").
--
-- A small, coherent Adrar world for local development and manual testing.
-- Idempotent: fixed UUIDs + ON CONFLICT DO NOTHING, safe to run repeatedly.
-- Loads on top of schema_v0.2.1.sql + seed_master_data_v0.2.1.sql.
--
-- NOT test data for the gate. The gate suite builds its own fixtures inside a
-- transaction it rolls back; these persist in a developer database.
--
-- Deliberately contains NO match candidate, review or opportunity: those are
-- produced by the domain commands of Slices 4-5, never inserted by hand.
-- =============================================================================
\set ON_ERROR_STOP on
SET search_path = turab, public;
BEGIN;

-- ---------------------------------------------------------------------------
-- Parties: two individuals and one agency
-- ---------------------------------------------------------------------------
INSERT INTO parties (party_id, kind, status, display_name) VALUES
  ('f1000000-0000-4000-8000-000000000001','PERSON','PARTY_ACTIVE','أمينة (مشترية)'),
  ('f1000000-0000-4000-8000-000000000002','PERSON','PARTY_ACTIVE','ابراهيم (مالك)'),
  ('f1000000-0000-4000-8000-000000000003','BUSINESS','PARTY_ACTIVE','وكالة الصحراء العقارية')
ON CONFLICT (party_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Contact points. One phone is shared by two parties on purpose: ADR-07 says a
-- contact point is not a party, and a shared phone must never merge them.
-- ---------------------------------------------------------------------------
INSERT INTO contact_points (contact_point_id, kind, normalized_value, display_value,
                            control_status, control_verified_at, verification_method) VALUES
  ('f2000000-0000-4000-8000-000000000001','PHONE','+213661000001','0661 00 00 01','VERIFIED_CONTROL', now(),'OTP'),
  ('f2000000-0000-4000-8000-000000000002','PHONE','+213661000002','0661 00 00 02','VERIFIED_CONTROL', now(),'OTP'),
  ('f2000000-0000-4000-8000-000000000003','PHONE','+213661000003','0661 00 00 03','UNVERIFIED', NULL, NULL)
ON CONFLICT (contact_point_id) DO NOTHING;

INSERT INTO party_contact_points (party_id, contact_point_id, is_primary, relationship_note) VALUES
  ('f1000000-0000-4000-8000-000000000001','f2000000-0000-4000-8000-000000000001', true, NULL),
  ('f1000000-0000-4000-8000-000000000002','f2000000-0000-4000-8000-000000000002', true, NULL),
  ('f1000000-0000-4000-8000-000000000003','f2000000-0000-4000-8000-000000000003', true, NULL),
  -- same verified phone also reaches the agency; the parties stay separate
  ('f1000000-0000-4000-8000-000000000003','f2000000-0000-4000-8000-000000000002', false,
   'shared line: broker reachable on the owner''s phone')
ON CONFLICT (party_id, contact_point_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Accounts. Amina is a customer with a party; staff accounts have none, which
-- exercises the nullable user_accounts.party_id path.
-- ---------------------------------------------------------------------------
INSERT INTO user_accounts (account_id, party_id, status, login_contact_point_id, email, activated_at) VALUES
  ('f3000000-0000-4000-8000-000000000001','f1000000-0000-4000-8000-000000000001','ACTIVATED',
   'f2000000-0000-4000-8000-000000000001', NULL, now()),
  ('f3000000-0000-4000-8000-000000000002', NULL,'ACTIVATED', NULL,'operator@turab.local', now()),
  ('f3000000-0000-4000-8000-000000000003', NULL,'ACTIVATED', NULL,'reviewer@turab.local', now())
ON CONFLICT (account_id) DO NOTHING;

-- Roles kept separate: the operator who records truth is not the reviewer who
-- approves it (maker-checker, see docs/rfc/RFC-001).
INSERT INTO user_account_roles (account_id, role) VALUES
  ('f3000000-0000-4000-8000-000000000001','CUSTOMER'),
  ('f3000000-0000-4000-8000-000000000002','OPERATOR'),
  ('f3000000-0000-4000-8000-000000000003','REVIEWER')
ON CONFLICT (account_id, role) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Properties, anchored to the two distinct Tililane locations from the master
-- seed. Same name, different places: the villa is in the ksar, the land is in
-- the new city.
-- ---------------------------------------------------------------------------
INSERT INTO properties (property_id, property_type, canonical_location_id, local_location_detail,
                        land_area_m2, built_area_m2, current_availability,
                        availability_last_confirmed_at, supply_mode, management_mode,
                        claim_status, created_by_account_id)
SELECT v.pid, v.ptype::property_type,
       (SELECT location_id FROM locations WHERE code = v.loc_code),
       v.detail, v.land, v.built, v.avail::availability_status, now(),
       v.mode::supply_mode, v.mgmt::management_mode, v.claim::account_claim_status,
       'f3000000-0000-4000-8000-000000000002'
FROM (VALUES
  ('f4000000-0000-4000-8000-000000000001'::uuid,'HOUSE_VILLA','ADR-KSAR-TILILANE',
   'قرب المسجد العتيق', 220.00, 180.00,'AVAILABLE','PUBLIC','SELF_MANAGED','CLAIMED'),
  ('f4000000-0000-4000-8000-000000000002'::uuid,'LAND','ADR-NEW-TIL',
   'قطعة أرضية بالمدينة الجديدة', 400.00, NULL,'UNKNOWN','POTENTIAL','ASSISTED','UNCLAIMED'),
  ('f4000000-0000-4000-8000-000000000003'::uuid,'APARTMENT','ADR-CENTER',
   'وسط المدينة، الطابق الثاني', NULL, 95.00,'AVAILABLE','PRIVATE','ASSISTED','UNCLAIMED')
) AS v(pid, ptype, loc_code, detail, land, built, avail, mode, mgmt, claim)
ON CONFLICT (property_id) DO NOTHING;

-- Who may speak for which property. This, not a column on properties, is what
-- customer authorization reads (RFC-001 §4.1).
INSERT INTO party_property_relations (party_property_relation_id, party_id, property_id,
                                      relation_code, verification_level, valid_from, valid_to) VALUES
  ('f5000000-0000-4000-8000-000000000001','f1000000-0000-4000-8000-000000000002',
   'f4000000-0000-4000-8000-000000000001','OWNER_DECLARED','DECLARED', now() - interval '60 days', NULL),
  ('f5000000-0000-4000-8000-000000000002','f1000000-0000-4000-8000-000000000003',
   'f4000000-0000-4000-8000-000000000001','BROKER','DECLARED', now() - interval '30 days', NULL),
  -- expired on purpose: exercises the currency predicate in RFC-001 R4.1
  ('f5000000-0000-4000-8000-000000000003','f1000000-0000-4000-8000-000000000003',
   'f4000000-0000-4000-8000-000000000003','BROKER','DECLARED',
   now() - interval '400 days', now() - interval '35 days')
ON CONFLICT (party_property_relation_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Offers. The villa carries two SALE offers at different prices from different
-- parties, plus a RENT offer: PROPERTY != PROPERTY_OFFER (Master §4, invariant 3).
-- seller_expectation_dzd is internal and must never reach a customer DTO.
-- ---------------------------------------------------------------------------
INSERT INTO property_offers (offer_id, property_id, party_id, transaction_type, status,
                             asking_price_dzd, price_negotiable, seller_expectation_dzd,
                             price_visibility, last_confirmed_at,
                             commercial_terms_last_confirmed_at, permission_scope,
                             created_by_account_id) VALUES
  ('f6000000-0000-4000-8000-000000000001','f4000000-0000-4000-8000-000000000001',
   'f1000000-0000-4000-8000-000000000002','SALE','ACTIVE', 24000000,'YES', 22500000,
   'PUBLIC', now(), now(),'PROPERTY_DETAILS_ALLOWED','f3000000-0000-4000-8000-000000000002'),
  ('f6000000-0000-4000-8000-000000000002','f4000000-0000-4000-8000-000000000001',
   'f1000000-0000-4000-8000-000000000003','SALE','ACTIVE', 27000000,'UNKNOWN', NULL,
   'ON_REQUEST', now(), now(),'SUMMARY_ONLY','f3000000-0000-4000-8000-000000000002'),
  ('f6000000-0000-4000-8000-000000000003','f4000000-0000-4000-8000-000000000001',
   'f1000000-0000-4000-8000-000000000002','RENT','ACTIVE', 70000,'YES', NULL,
   'PUBLIC', now(), now(),'SUMMARY_ONLY','f3000000-0000-4000-8000-000000000002'),
  -- stale on purpose: freshness gate material for Slice 4
  ('f6000000-0000-4000-8000-000000000004','f4000000-0000-4000-8000-000000000003',
   'f1000000-0000-4000-8000-000000000003','RENT','ACTIVE', 45000,'NO', NULL,
   'PRIVATE', now() - interval '200 days', now() - interval '200 days','SUMMARY_ONLY',
   'f3000000-0000-4000-8000-000000000002')
ON CONFLICT (offer_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Requests. One self-managed BUY, one assisted RENT.
-- ---------------------------------------------------------------------------
INSERT INTO requests (request_id, party_id, status, transaction_intent, intent, payment,
                      desired_property_type, primary_location_id, local_location_detail,
                      budget_target_dzd, budget_max_dzd, budget_flexibility,
                      last_confirmed_at, management_mode, claim_status, created_by_account_id)
SELECT v.rid, v.party, v.status::request_status, v.intent::request_transaction_intent,
       v.stage::intent_stage, v.pay::payment_method, v.ptype::property_type,
       (SELECT location_id FROM locations WHERE code = v.loc_code),
       v.detail, v.target, v.maxb, v.flex::budget_flexibility, v.conf,
       v.mgmt::management_mode, v.claim::account_claim_status, v.acct
FROM (VALUES
  ('f7000000-0000-4000-8000-000000000001'::uuid,'f1000000-0000-4000-8000-000000000001'::uuid,
   'ACTIVE','BUY','ACTIVE_SEARCH','CASH','HOUSE_VILLA','ADR-KSAR-TILILANE',
   'يفضل قرب المسجد', 23000000::bigint, 25000000::bigint,'MODERATE', now(),
   'SELF_MANAGED','CLAIMED','f3000000-0000-4000-8000-000000000001'::uuid),
  ('f7000000-0000-4000-8000-000000000002'::uuid,'f1000000-0000-4000-8000-000000000003'::uuid,
   'QUALIFIED','RENT','EXPLORING','UNDECIDED','APARTMENT','ADR-CENTER',
   'سكن للموظفين', 40000::bigint, 60000::bigint,'LOW', now() - interval '120 days',
   'ASSISTED','UNCLAIMED','f3000000-0000-4000-8000-000000000002'::uuid)
) AS v(rid, party, status, intent, stage, pay, ptype, loc_code, detail,
       target, maxb, flex, conf, mgmt, claim, acct)
ON CONFLICT (request_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Consents. Grants are not proof for a resource; the binding is (ADR-04). The
-- trigger enforce_consent_binding() validates party, scope and resource
-- relationship, so these rows also prove the fixture world is coherent.
-- ---------------------------------------------------------------------------
INSERT INTO consent_grants (consent_id, party_id, scope, status, channel, consent_version,
                            granted_at, revoked_at, created_by_account_id) VALUES
  ('f8000000-0000-4000-8000-000000000001','f1000000-0000-4000-8000-000000000001',
   'PRIVATE_MATCHING_ONLY','GRANTED','WHATSAPP','consent-v1', now() - interval '10 days', NULL,
   'f3000000-0000-4000-8000-000000000002'),
  ('f8000000-0000-4000-8000-000000000002','f1000000-0000-4000-8000-000000000002',
   'PUBLIC_LISTING_ALLOWED','GRANTED','PHONE_CONFIRMED','consent-v1', now() - interval '20 days', NULL,
   'f3000000-0000-4000-8000-000000000002'),
  ('f8000000-0000-4000-8000-000000000003','f1000000-0000-4000-8000-000000000003',
   'ASSISTED_ENTRY','GRANTED','IN_PERSON','consent-v1', now() - interval '30 days', NULL,
   'f3000000-0000-4000-8000-000000000002'),
  -- revoked on purpose: future shares must fail, history must survive (ADR-04)
  ('f8000000-0000-4000-8000-000000000004','f1000000-0000-4000-8000-000000000003',
   'PUBLIC_LISTING_ALLOWED','REVOKED','WHATSAPP','consent-v1',
   now() - interval '40 days', now() - interval '5 days','f3000000-0000-4000-8000-000000000002')
ON CONFLICT (consent_id) DO NOTHING;

INSERT INTO resource_consent_bindings (consent_binding_id, consent_id, purpose,
                                       request_id, property_id, offer_id, thread_id,
                                       bound_by_account_id) VALUES
  ('f9000000-0000-4000-8000-000000000001','f8000000-0000-4000-8000-000000000001',
   'PRIVATE_MATCHING_ONLY','f7000000-0000-4000-8000-000000000001', NULL, NULL, NULL,
   'f3000000-0000-4000-8000-000000000002'),
  ('f9000000-0000-4000-8000-000000000002','f8000000-0000-4000-8000-000000000002',
   'PUBLIC_LISTING_ALLOWED', NULL, NULL,'f6000000-0000-4000-8000-000000000001', NULL,
   'f3000000-0000-4000-8000-000000000002'),
  ('f9000000-0000-4000-8000-000000000003','f8000000-0000-4000-8000-000000000003',
   'ASSISTED_ENTRY','f7000000-0000-4000-8000-000000000002', NULL, NULL, NULL,
   'f3000000-0000-4000-8000-000000000002')
ON CONFLICT (consent_binding_id) DO NOTHING;

COMMIT;

\echo ''
\echo 'TURAB development fixtures loaded.'
SELECT 'parties'        AS entity, count(*) FROM parties
UNION ALL SELECT 'contact_points', count(*) FROM contact_points
UNION ALL SELECT 'user_accounts',  count(*) FROM user_accounts
UNION ALL SELECT 'properties',     count(*) FROM properties
UNION ALL SELECT 'property_offers',count(*) FROM property_offers
UNION ALL SELECT 'requests',       count(*) FROM requests
UNION ALL SELECT 'consent_grants', count(*) FROM consent_grants
UNION ALL SELECT 'consent_bindings',count(*) FROM resource_consent_bindings
ORDER BY 1;
