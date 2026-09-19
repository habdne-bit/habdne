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

-- =============================================================================
-- DOMAIN EDGE CASES EC1-EC8
--
-- One fixture per approved decision in RFC-001 revision 2, so each decision has
-- data to be tested against. Data only: no match candidate, review or
-- opportunity is created here, because those are produced by the domain
-- commands of Slices 4-5 and never inserted by hand.
--
-- Interpretation note: "the eight domain edge cases" was read as the domain
-- situation implied by each of the eight decisions. If a different set was
-- meant, these are additive and cheap to replace.
-- =============================================================================
BEGIN;

-- Supporting accounts -------------------------------------------------------
-- A second customer (EC2), an ADMIN (EC3/EC8), and a SECOND ACCOUNT FOR AMINA'S
-- PARTY (EC1) to prove property authority is account-scoped, not party-scoped.
INSERT INTO contact_points (contact_point_id, kind, normalized_value, display_value,
                            control_status, control_verified_at, verification_method) VALUES
  ('f2000000-0000-4000-8000-000000000004','PHONE','+213661000004','0661 00 00 04','VERIFIED_CONTROL', now(),'OTP'),
  ('f2000000-0000-4000-8000-000000000005','PHONE','+213661000005','0661 00 00 05','VERIFIED_CONTROL', now(),'OTP')
ON CONFLICT (contact_point_id) DO NOTHING;

INSERT INTO parties (party_id, kind, status, display_name) VALUES
  ('f1000000-0000-4000-8000-000000000004','PERSON','PARTY_ACTIVE','خديجة (مشترية ثانية)')
ON CONFLICT (party_id) DO NOTHING;

INSERT INTO party_contact_points (party_id, contact_point_id, is_primary) VALUES
  ('f1000000-0000-4000-8000-000000000004','f2000000-0000-4000-8000-000000000004', true)
ON CONFLICT (party_id, contact_point_id) DO NOTHING;

INSERT INTO user_accounts (account_id, party_id, status, login_contact_point_id, email, activated_at) VALUES
  ('f3000000-0000-4000-8000-000000000004','f1000000-0000-4000-8000-000000000004','ACTIVATED',
   'f2000000-0000-4000-8000-000000000004', NULL, now()),
  ('f3000000-0000-4000-8000-000000000005', NULL,'ACTIVATED', NULL,'admin@turab.local', now()),
  -- EC1: same PARTY as account ...001, different ACCOUNT
  ('f3000000-0000-4000-8000-000000000006','f1000000-0000-4000-8000-000000000001','ACTIVATED',
   'f2000000-0000-4000-8000-000000000005', NULL, now())
ON CONFLICT (account_id) DO NOTHING;

INSERT INTO user_account_roles (account_id, role) VALUES
  ('f3000000-0000-4000-8000-000000000004','CUSTOMER'),
  ('f3000000-0000-4000-8000-000000000005','ADMIN'),
  ('f3000000-0000-4000-8000-000000000006','CUSTOMER')
ON CONFLICT (account_id, role) DO NOTHING;
-- EC8: no account here holds both OPERATOR and REVIEWER. RFC-001 R2.1 forbids
-- it; a test asserts the table contains no such account.

-- ---------------------------------------------------------------------------
-- EC1 - decision 1: a domain relationship is NOT authority.
--
-- Property f4...001 (the villa) already carries Brahim's OWNER_DECLARED
-- relation and the agency's BROKER relation, yet its created_by_account_id is
-- the OPERATOR account and no claim event exists for it. Under RFC-001 R4.1
-- neither related party may reach it as a customer.
--
-- The contrast: f4...004 below IS claimed, so authority exists there and the
-- difference between the two properties is exactly the claim event.
-- ---------------------------------------------------------------------------
INSERT INTO properties (property_id, property_type, canonical_location_id, local_location_detail,
                        land_area_m2, built_area_m2, current_availability,
                        availability_last_confirmed_at, supply_mode, management_mode,
                        claim_status, created_by_account_id)
SELECT 'f4000000-0000-4000-8000-000000000004','HOUSE_VILLA',
       (SELECT location_id FROM locations WHERE code='ADR-KSAR-OULED-ALI'),
       'منزل تم تأكيد ملكيته', 180.00, 150.00,'AVAILABLE', now(),'PUBLIC',
       'SHARED_MANAGEMENT','CLAIMED','f3000000-0000-4000-8000-000000000002'
ON CONFLICT (property_id) DO NOTHING;

INSERT INTO party_property_relations (party_property_relation_id, party_id, property_id,
                                      relation_code, verification_level, valid_from, valid_to) VALUES
  ('f5000000-0000-4000-8000-000000000004','f1000000-0000-4000-8000-000000000001',
   'f4000000-0000-4000-8000-000000000004','OWNER_DECLARED','DECLARED', now() - interval '90 days', NULL),
  -- EC1 (R4.6): an EXPIRED relation on a property the same party has claimed.
  -- Expiry must not revoke a claimed owner's access.
  ('f5000000-0000-4000-8000-000000000005','f1000000-0000-4000-8000-000000000001',
   'f4000000-0000-4000-8000-000000000004','CONTACT_PERSON','DECLARED',
   now() - interval '300 days', now() - interval '10 days')
ON CONFLICT (party_property_relation_id) DO NOTHING;

-- The claim event: THIS is the authority, and it names an ACCOUNT.
-- Account ...001 may reach the property; account ...006, same party, may not.
INSERT INTO record_claim_events (claim_event_id, request_id, property_id,
                                 claimed_by_account_id, claimed_at,
                                 verification_contact_point_id) VALUES
  ('fa000000-0000-4000-8000-000000000001', NULL,'f4000000-0000-4000-8000-000000000004',
   'f3000000-0000-4000-8000-000000000001', now() - interval '80 days',
   'f2000000-0000-4000-8000-000000000001')
ON CONFLICT (claim_event_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- EC2 - decision 2: 404 conceals, 403 prohibits.
-- Khadija owns a request of her own. Probing Amina's request must yield 404;
-- a staff-only action on her OWN request must yield 403.
-- ---------------------------------------------------------------------------
INSERT INTO requests (request_id, party_id, status, transaction_intent, intent, payment,
                      desired_property_type, primary_location_id, budget_target_dzd,
                      budget_max_dzd, budget_flexibility, last_confirmed_at,
                      management_mode, claim_status, created_by_account_id)
SELECT 'f7000000-0000-4000-8000-000000000003','f1000000-0000-4000-8000-000000000004',
       'ACTIVE','BUY','ACTIVE_SEARCH','BANK_FINANCING','APARTMENT',
       (SELECT location_id FROM locations WHERE code='ADR-CENTER'),
       8000000, 9500000,'STRICT', now(),'SELF_MANAGED','CLAIMED',
       'f3000000-0000-4000-8000-000000000004'
ON CONFLICT (request_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- EC3 - decision 3: roles are literal, no inheritance.
-- ADMIN account f3...005 holds ONLY 'ADMIN'. Because the contract lists ADMIN
-- explicitly on every staff operation, a literal check still admits it. If any
-- code ever computed ADMIN as a superset, this fixture would not detect it -
-- what detects it is S18/S19: OPERATOR must be refused /matches/{id}/review
-- and REVIEWER must be refused /observations.
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- EC4 - decision 4: no delegated authority in v0.1.
-- The agency is BROKER on the villa f4...001 and would, in any delegation
-- model, act for the owner. With delegation unimplemented the agency has no
-- customer access to that property or to the owner's request. It keeps its own
-- offer (f6...002), which it owns directly.
-- Amina's request f7...001 also has no delegate: no row anywhere confers it.
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- EC5 - decision 5: /reason-codes excludes CUSTOMER.
-- Customer accounts f3...001, ...004 and ...006 hold ONLY the CUSTOMER role and
-- must be refused; OPERATOR/REVIEWER/ADMIN accounts must be allowed. The reason
-- codes themselves come from the master seed, not from here.
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- EC6 - decision 6: sharing scopes, and the floor that no scope lifts.
-- An offer at each of the three permission_scope values, plus internal data
-- that must never surface at ANY scope: an internal price expectation, a
-- private claim, and a source carrying private raw text and an external URL.
-- ---------------------------------------------------------------------------
INSERT INTO property_offers (offer_id, property_id, party_id, transaction_type, status,
                             asking_price_dzd, price_negotiable, seller_expectation_dzd,
                             price_visibility, last_confirmed_at,
                             commercial_terms_last_confirmed_at, permission_scope,
                             created_by_account_id) VALUES
  -- the third scope, absent from the base fixtures
  ('f6000000-0000-4000-8000-000000000005','f4000000-0000-4000-8000-000000000004',
   'f1000000-0000-4000-8000-000000000001','SALE','ACTIVE', 19500000,'YES', 18000000,
   'ON_REQUEST', now(), now(),'CONTACT_AFTER_CONFIRMATION','f3000000-0000-4000-8000-000000000002')
ON CONFLICT (offer_id) DO NOTHING;

INSERT INTO sources (source_id, kind, external_url, external_ref, title, raw_text,
                     captured_at, metadata, created_by_account_id) VALUES
  ('fb000000-0000-4000-8000-000000000001','FACEBOOK_POST',
   'https://example.invalid/private-post/12345','fb:12345',
   'منشور خاص',
   'صاحب المنزل مستعجل ويقبل 18 مليون نقدا - معلومة خاصة لا تنشر',
   now() - interval '15 days',
   '{"private": true, "operator_note": "do not repeat to buyers"}'::jsonb,
   'f3000000-0000-4000-8000-000000000002')
ON CONFLICT (source_id) DO NOTHING;

INSERT INTO observations (observation_id, source_id, kind, party_id, observed_at,
                          raw_text, payload, recorded_by_account_id) VALUES
  ('fc000000-0000-4000-8000-000000000001','fb000000-0000-4000-8000-000000000001',
   'CALL_NOTE','f1000000-0000-4000-8000-000000000001', now() - interval '15 days',
   'مكالمة: البائع يقبل أقل من السعر المعلن',
   '{"channel":"phone"}'::jsonb,'f3000000-0000-4000-8000-000000000002')
ON CONFLICT (observation_id) DO NOTHING;

-- A private claim about the offer. Matching may read it; no customer DTO may.
INSERT INTO claims (claim_id, offer_id, attribute_code, claimed_value,
                    asserted_by_party_id, source_id, observation_id,
                    observed_at, effective_verification_level, status,
                    recorded_by_account_id) VALUES
  ('fd000000-0000-4000-8000-000000000001','f6000000-0000-4000-8000-000000000005',
   'seller_expectation_dzd','{"amount":18000000,"currency":"DZD","private":true}'::jsonb,
   'f1000000-0000-4000-8000-000000000001','fb000000-0000-4000-8000-000000000001',
   'fc000000-0000-4000-8000-000000000001', now() - interval '15 days',
   'DECLARED','ACTIVE','f3000000-0000-4000-8000-000000000002')
ON CONFLICT (claim_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- EC7 - decision 7: deny by default.
-- An orphan property: created_by_account_id IS NULL, no relation, no claim
-- event, no offer. No rule reaches it, so no customer may. It also exercises
-- the null-safety guard in RFC-001 R4.3 - a NULL creator must match nobody,
-- not everybody.
-- ---------------------------------------------------------------------------
INSERT INTO properties (property_id, property_type, canonical_location_id, local_location_detail,
                        current_availability, supply_mode, management_mode,
                        claim_status, created_by_account_id)
SELECT 'f4000000-0000-4000-8000-000000000005','LAND',
       (SELECT location_id FROM locations WHERE code='ADR-KSAR-ADGHA'),
       'قطعة بلا مالك معروف بعد','UNKNOWN','POTENTIAL','ASSISTED','UNCLAIMED', NULL
ON CONFLICT (property_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- EC8 - decision 8: maker-checker preserved.
-- Accounts stay single-purpose: ...002 OPERATOR, ...003 REVIEWER, ...005 ADMIN.
-- No account holds OPERATOR and REVIEWER together. Asserted below.
-- ---------------------------------------------------------------------------
DO $$
DECLARE violators int;
BEGIN
  SELECT count(*) INTO violators
  FROM user_account_roles o
  JOIN user_account_roles r ON r.account_id = o.account_id
  WHERE o.role = 'OPERATOR' AND r.role = 'REVIEWER';
  IF violators > 0 THEN
    RAISE EXCEPTION 'EC8: % account(s) hold both OPERATOR and REVIEWER; RFC-001 R2.1 forbids this', violators;
  END IF;
END $$;

COMMIT;

\echo ''
\echo 'Edge cases EC1-EC8 loaded.'
SELECT 'claimed properties (authority exists)' AS check, count(*)::text AS value FROM record_claim_events
UNION ALL SELECT 'orphan properties (created_by NULL)',
  (SELECT count(*)::text FROM properties WHERE created_by_account_id IS NULL)
UNION ALL SELECT 'distinct permission_scope values on offers',
  (SELECT count(DISTINCT permission_scope)::text FROM property_offers)
UNION ALL SELECT 'accounts holding OPERATOR and REVIEWER',
  (SELECT count(*)::text FROM user_account_roles o JOIN user_account_roles r
     ON r.account_id=o.account_id WHERE o.role='OPERATOR' AND r.role='REVIEWER')
UNION ALL SELECT 'accounts sharing one party',
  (SELECT count(*)::text FROM user_accounts WHERE party_id='f1000000-0000-4000-8000-000000000001');

-- =============================================================================
-- MARKET / DOMAIN EDGE FIXTURES MF1-MF8
--
-- The eight market situations the product must represent correctly, each
-- traceable to a red-team acceptance case. Data only: the later-slice BEHAVIOUR
-- (public-browse exclusion, matching gates, opportunity creation, identity
-- review commands) is NOT implemented here. These fixtures exist so that when
-- those slices are built there is already a world that exercises them.
--
--   MF1 owner + broker offers on one PROPERTY        -> D01
--   MF2 all offers withdrawn                         -> D04
--   MF3 POTENTIAL property without public offer      -> D05
--   MF4 LAND_BOOK-required request, UNKNOWN document -> C03
--   MF5 active -> withdrawn consent                  -> B03
--   MF6 PARTY without USER_ACCOUNT                   -> A03
--   MF7 shared phone without party merge             -> A01
--   MF8 adjacent similar units confirmed distinct    -> E03
-- =============================================================================
BEGIN;

-- ---------------------------------------------------------------------------
-- MF1 - one physical property, several independent commercial offers (D01)
-- Owner SALE 24M, broker SALE 27M, owner RENT 70k/month. Already present on
-- property f4...001 from the base fixtures; asserted here so the guarantee is
-- explicit rather than incidental, and so a later edit that collapses offers
-- into the property fails loudly.
-- ---------------------------------------------------------------------------
DO $$
DECLARE sale_offers int; rent_offers int; distinct_parties int;
BEGIN
  SELECT count(*) FILTER (WHERE transaction_type='SALE'),
         count(*) FILTER (WHERE transaction_type='RENT'),
         count(DISTINCT party_id)
    INTO sale_offers, rent_offers, distinct_parties
  FROM property_offers WHERE property_id='f4000000-0000-4000-8000-000000000001';
  IF sale_offers < 2 OR rent_offers < 1 OR distinct_parties < 2 THEN
    RAISE EXCEPTION 'MF1: expected >=2 SALE, >=1 RENT from >=2 parties on one property; got % / % / %',
      sale_offers, rent_offers, distinct_parties;
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- MF2 - PUBLIC property whose offers are ALL withdrawn (D04)
-- supply_mode=PUBLIC is not sufficient for public browse. This property must be
-- absent from /public/properties once that endpoint exists.
-- ---------------------------------------------------------------------------
INSERT INTO properties (property_id, property_type, canonical_location_id, local_location_detail,
                        land_area_m2, built_area_m2, current_availability,
                        availability_last_confirmed_at, supply_mode, management_mode,
                        claim_status, created_by_account_id)
SELECT 'f4000000-0000-4000-8000-000000000006','APARTMENT',
       (SELECT location_id FROM locations WHERE code='ADR-NEW-SMB'),
       'شقة سُحبت كل عروضها', NULL, 88.00,'AVAILABLE', now(),'PUBLIC',
       'ASSISTED','UNCLAIMED','f3000000-0000-4000-8000-000000000002'
ON CONFLICT (property_id) DO NOTHING;

INSERT INTO property_offers (offer_id, property_id, party_id, transaction_type, status,
                             asking_price_dzd, price_negotiable, price_visibility,
                             last_confirmed_at, commercial_terms_last_confirmed_at,
                             permission_scope, created_by_account_id) VALUES
  ('f6000000-0000-4000-8000-000000000006','f4000000-0000-4000-8000-000000000006',
   'f1000000-0000-4000-8000-000000000002','SALE','WITHDRAWN', 11000000,'UNKNOWN','PUBLIC',
   now() - interval '45 days', now() - interval '45 days','PROPERTY_DETAILS_ALLOWED',
   'f3000000-0000-4000-8000-000000000002'),
  ('f6000000-0000-4000-8000-000000000007','f4000000-0000-4000-8000-000000000006',
   'f1000000-0000-4000-8000-000000000003','RENT','CLOSED', 55000,'NO','PUBLIC',
   now() - interval '60 days', now() - interval '60 days','SUMMARY_ONLY',
   'f3000000-0000-4000-8000-000000000002')
ON CONFLICT (offer_id) DO NOTHING;

DO $$
DECLARE live int;
BEGIN
  SELECT count(*) INTO live FROM property_offers
   WHERE property_id='f4000000-0000-4000-8000-000000000006'
     AND status NOT IN ('WITHDRAWN','CLOSED');
  IF live <> 0 THEN
    RAISE EXCEPTION 'MF2: property must have no live offer; found %', live;
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- MF3 - POTENTIAL property with no public offer at all (D05)
-- May be evaluated only from a structured willingness context, never from an
-- offer id. Property f4...002 from the base fixtures is POTENTIAL; this adds
-- the structured willingness the rule requires, recorded as provenance rather
-- than invented as a column.
-- ---------------------------------------------------------------------------
INSERT INTO sources (source_id, kind, title, raw_text, captured_at, metadata,
                     created_by_account_id) VALUES
  ('fb000000-0000-4000-8000-000000000002','PHONE_CALL','استعداد مبدئي للبيع',
   'المالك غير معروض رسميا لكنه مستعد للبيع حول 6 ملايين إذا جاء مشتر جاد',
   now() - interval '25 days','{"willingness": true}'::jsonb,
   'f3000000-0000-4000-8000-000000000002')
ON CONFLICT (source_id) DO NOTHING;

INSERT INTO observations (observation_id, source_id, kind, party_id, observed_at,
                          raw_text, payload, recorded_by_account_id) VALUES
  ('fc000000-0000-4000-8000-000000000002','fb000000-0000-4000-8000-000000000002',
   'CALL_NOTE','f1000000-0000-4000-8000-000000000002', now() - interval '25 days',
   'استعداد للبيع دون عرض معلن',
   '{"indicative_price_dzd": 6000000, "transaction_type": "SALE"}'::jsonb,
   'f3000000-0000-4000-8000-000000000002')
ON CONFLICT (observation_id) DO NOTHING;

INSERT INTO claims (claim_id, property_id, attribute_code, claimed_value,
                    asserted_by_party_id, source_id, observation_id, observed_at,
                    effective_verification_level, status, recorded_by_account_id) VALUES
  ('fd000000-0000-4000-8000-000000000002','f4000000-0000-4000-8000-000000000002',
   'POTENTIAL_WILLINGNESS',
   '{"willing_to_sell": true, "indicative_price_dzd": 6000000, "transaction_type": "SALE"}'::jsonb,
   'f1000000-0000-4000-8000-000000000002','fb000000-0000-4000-8000-000000000002',
   'fc000000-0000-4000-8000-000000000002', now() - interval '25 days',
   'DECLARED','ACTIVE','f3000000-0000-4000-8000-000000000002')
ON CONFLICT (claim_id) DO NOTHING;

DO $$
DECLARE offers int;
BEGIN
  SELECT count(*) INTO offers FROM property_offers
   WHERE property_id='f4000000-0000-4000-8000-000000000002';
  IF offers <> 0 THEN
    RAISE EXCEPTION 'MF3: POTENTIAL property must carry no offer; found %', offers;
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- MF4 - REQUIRED document criterion vs UNKNOWN property value (C03)
-- Request demands DOCUMENT_TYPE = LAND_BOOK as REQUIRED and blocking when
-- unknown. The candidate property's document type is genuinely UNKNOWN, not
-- absent-by-accident. Correct later behaviour is NEED_MORE_INFORMATION:
-- neither PASS nor hard FAIL. UNKNOWN != FAIL (Master section 4, invariant 8).
-- ---------------------------------------------------------------------------
INSERT INTO requests (request_id, party_id, status, transaction_intent, intent, payment,
                      desired_property_type, primary_location_id, budget_target_dzd,
                      budget_max_dzd, budget_flexibility, last_confirmed_at,
                      management_mode, claim_status, created_by_account_id)
SELECT 'f7000000-0000-4000-8000-000000000004','f1000000-0000-4000-8000-000000000004',
       'ACTIVE','BUY','READY_TO_ACT','CASH','LAND',
       (SELECT location_id FROM locations WHERE code='ADR-KSOUR'),
       5000000, 7000000,'STRICT', now(),'SELF_MANAGED','CLAIMED',
       'f3000000-0000-4000-8000-000000000004'
ON CONFLICT (request_id) DO NOTHING;

INSERT INTO request_criteria (request_criterion_id, request_id, criterion_code, importance,
                              operator, value, blocking_if_unknown, sort_order, source_note) VALUES
  ('fe000000-0000-4000-8000-000000000001','f7000000-0000-4000-8000-000000000004',
   'DOCUMENT_TYPE','REQUIRED','EQ','"LAND_BOOK"'::jsonb, true, 10,
   'المشتري يشترط دفترا عقاريا'),
  ('fe000000-0000-4000-8000-000000000002','f7000000-0000-4000-8000-000000000004',
   'LAND_AREA_MIN','PREFERRED','GTE','300'::jsonb, false, 20, NULL)
ON CONFLICT (request_criterion_id) DO NOTHING;

-- The property whose document type is explicitly UNKNOWN, not missing.
INSERT INTO properties (property_id, property_type, canonical_location_id, local_location_detail,
                        land_area_m2, current_availability, availability_last_confirmed_at,
                        supply_mode, management_mode, claim_status, created_by_account_id)
SELECT 'f4000000-0000-4000-8000-000000000007','LAND',
       (SELECT location_id FROM locations WHERE code='ADR-KSAR-BARBAA'),
       'أرض وثيقتها غير معروفة', 350.00,'AVAILABLE', now(),'PUBLIC',
       'ASSISTED','UNCLAIMED','f3000000-0000-4000-8000-000000000002'
ON CONFLICT (property_id) DO NOTHING;

INSERT INTO property_attributes (property_attribute_id, property_id, attribute_definition_id, value)
SELECT 'ff000000-0000-4000-8000-000000000001','f4000000-0000-4000-8000-000000000007',
       attribute_definition_id, '"UNKNOWN"'::jsonb
FROM attribute_definitions WHERE code='DOCUMENT_TYPE'
ON CONFLICT (property_attribute_id) DO NOTHING;

INSERT INTO property_offers (offer_id, property_id, party_id, transaction_type, status,
                             asking_price_dzd, price_negotiable, price_visibility,
                             last_confirmed_at, commercial_terms_last_confirmed_at,
                             permission_scope, created_by_account_id) VALUES
  ('f6000000-0000-4000-8000-000000000008','f4000000-0000-4000-8000-000000000007',
   'f1000000-0000-4000-8000-000000000002','SALE','ACTIVE', 6500000,'YES','PUBLIC',
   now(), now(),'PROPERTY_DETAILS_ALLOWED','f3000000-0000-4000-8000-000000000002')
ON CONFLICT (offer_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- MF5 - consent active, then withdrawn (B03)
-- Grant f8...004 is already REVOKED in the base fixtures but was never bound.
-- Here a grant is bound to a resource while active and then revoked, which is
-- the case that matters: a binding whose grant died under it. Any later share
-- depending on it must fail or revalidate; history must survive untouched.
-- ---------------------------------------------------------------------------
INSERT INTO consent_grants (consent_id, party_id, scope, status, channel, consent_version,
                            granted_at, revoked_at, created_by_account_id) VALUES
  ('f8000000-0000-4000-8000-000000000005','f1000000-0000-4000-8000-000000000002',
   'CONTACT_BEFORE_SHARING','GRANTED','PHONE_CONFIRMED','consent-v1',
   now() - interval '50 days', NULL,'f3000000-0000-4000-8000-000000000002')
ON CONFLICT (consent_id) DO NOTHING;

-- Bound while the grant is still GRANTED: enforce_consent_binding() requires it.
--
-- NOTE for anyone extending these fixtures: ON CONFLICT DO NOTHING is NOT enough
-- here. A BEFORE INSERT trigger fires before conflict resolution, so on a second
-- load enforce_consent_binding() would see the now-revoked grant and abort the
-- whole file. The row must not be offered to the trigger at all, hence the
-- WHERE NOT EXISTS guard.
INSERT INTO resource_consent_bindings (consent_binding_id, consent_id, purpose,
                                       request_id, property_id, offer_id, thread_id,
                                       bound_at, bound_by_account_id, notes)
SELECT 'f9000000-0000-4000-8000-000000000004','f8000000-0000-4000-8000-000000000005',
       'CONTACT_BEFORE_SHARING', NULL, NULL,'f6000000-0000-4000-8000-000000000001', NULL,
       now() - interval '49 days','f3000000-0000-4000-8000-000000000002',
       'MF5: bound while active, grant revoked afterwards'
WHERE NOT EXISTS (
  SELECT 1 FROM resource_consent_bindings
   WHERE consent_binding_id='f9000000-0000-4000-8000-000000000004'
);

-- Now revoke the grant. The binding row is deliberately left in place: ADR-04
-- says revocation blocks future use and never erases history.
UPDATE consent_grants
   SET status='REVOKED', revoked_at = now() - interval '2 days'
 WHERE consent_id='f8000000-0000-4000-8000-000000000005'
   AND status <> 'REVOKED';

DO $$
DECLARE binding_alive int; grant_revoked int;
BEGIN
  SELECT count(*) INTO binding_alive FROM resource_consent_bindings
   WHERE consent_binding_id='f9000000-0000-4000-8000-000000000004' AND revoked_at IS NULL;
  SELECT count(*) INTO grant_revoked FROM consent_grants
   WHERE consent_id='f8000000-0000-4000-8000-000000000005' AND status='REVOKED';
  IF binding_alive <> 1 OR grant_revoked <> 1 THEN
    RAISE EXCEPTION 'MF5: expected a surviving binding under a revoked grant; got % / %',
      binding_alive, grant_revoked;
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- MF6 - PARTY with no USER_ACCOUNT (A03)
-- An operator records a party and an assisted property for it after consent,
-- while no account exists. PARTY != USER_ACCOUNT (ADR-07). No customer may
-- reach this record: there is no account to be authorized.
-- ---------------------------------------------------------------------------
INSERT INTO parties (party_id, kind, status, display_name, notes) VALUES
  ('f1000000-0000-4000-8000-000000000005','PERSON','CONTACTED','سي محمد (بدون حساب)',
   'سجل مساعد: لا يملك حسابا ولا يريد إنشاءه حاليا')
ON CONFLICT (party_id) DO NOTHING;

INSERT INTO contact_points (contact_point_id, kind, normalized_value, display_value,
                            control_status) VALUES
  ('f2000000-0000-4000-8000-000000000006','PHONE','+213661000006','0661 00 00 06','UNVERIFIED')
ON CONFLICT (contact_point_id) DO NOTHING;

INSERT INTO party_contact_points (party_id, contact_point_id, is_primary) VALUES
  ('f1000000-0000-4000-8000-000000000005','f2000000-0000-4000-8000-000000000006', true)
ON CONFLICT (party_id, contact_point_id) DO NOTHING;

INSERT INTO consent_grants (consent_id, party_id, scope, status, channel, consent_version,
                            granted_at, created_by_account_id) VALUES
  ('f8000000-0000-4000-8000-000000000006','f1000000-0000-4000-8000-000000000005',
   'ASSISTED_ENTRY','GRANTED','IN_PERSON','consent-v1', now() - interval '12 days',
   'f3000000-0000-4000-8000-000000000002')
ON CONFLICT (consent_id) DO NOTHING;

INSERT INTO properties (property_id, property_type, canonical_location_id, local_location_detail,
                        land_area_m2, current_availability, supply_mode, management_mode,
                        claim_status, created_by_account_id)
SELECT 'f4000000-0000-4000-8000-000000000008','AGRICULTURAL_PROPERTY',
       (SELECT location_id FROM locations WHERE code='ADR-KSAR-MERAGUEN'),
       'أرض فلاحية مسجلة مساعدةً', 5000.00,'AVAILABLE','PRIVATE',
       'ASSISTED','UNCLAIMED','f3000000-0000-4000-8000-000000000002'
ON CONFLICT (property_id) DO NOTHING;

DO $$
DECLARE accounts int;
BEGIN
  SELECT count(*) INTO accounts FROM user_accounts
   WHERE party_id='f1000000-0000-4000-8000-000000000005';
  IF accounts <> 0 THEN
    RAISE EXCEPTION 'MF6: this party must have no account; found %', accounts;
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- MF7 - one phone, two parties, no merge (A01)
-- The base fixtures already share contact point f2...002 between Brahim and the
-- agency. Asserted here so that any future "helpful" deduplication that merges
-- parties on a matching phone fails loudly at fixture load.
-- ---------------------------------------------------------------------------
DO $$
DECLARE sharers int; still_separate int;
BEGIN
  SELECT count(DISTINCT party_id) INTO sharers
  FROM party_contact_points WHERE contact_point_id='f2000000-0000-4000-8000-000000000002';
  SELECT count(*) INTO still_separate FROM parties
   WHERE party_id IN ('f1000000-0000-4000-8000-000000000002',
                      'f1000000-0000-4000-8000-000000000003');
  IF sharers < 2 OR still_separate <> 2 THEN
    RAISE EXCEPTION 'MF7: one phone must reach 2 parties that remain separate; got % / %',
      sharers, still_separate;
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- MF8 - adjacent similar units, confirmed DISTINCT (E03)
-- Two neighbouring villas in one development sharing specs. A reviewer has
-- ruled CONFIRMED_DISTINCT, so NO alias mapping exists and none may be created.
-- The trigger enforce_identity_same_requires_alias() only guards CONFIRMED_SAME,
-- so nothing in the database stops a later process from aliasing these two: the
-- guarantee is behavioural and belongs in the Slice 9 identity work.
-- ---------------------------------------------------------------------------
INSERT INTO properties (property_id, property_type, canonical_location_id, local_location_detail,
                        land_area_m2, built_area_m2, current_availability,
                        availability_last_confirmed_at, supply_mode, management_mode,
                        claim_status, created_by_account_id)
SELECT v.pid,'HOUSE_VILLA',
       (SELECT location_id FROM locations WHERE code='ADR-NEW-TIL'),
       v.detail, 200.00, 160.00,'AVAILABLE', now(),'PUBLIC',
       'ASSISTED','UNCLAIMED','f3000000-0000-4000-8000-000000000002'
FROM (VALUES
  ('f4000000-0000-4000-8000-000000000009'::uuid,'فيلا رقم 12، نفس النموذج'),
  ('f4000000-0000-4000-8000-00000000000a'::uuid,'فيلا رقم 14، نفس النموذج')
) AS v(pid, detail)
ON CONFLICT (property_id) DO NOTHING;

INSERT INTO property_identity_candidates (identity_candidate_id, property_a_id, property_b_id,
                                          generated_at, signals, explanation, review_status,
                                          review_reason_text, reviewer_account_id, reviewed_at,
                                          algorithm_version) VALUES
  ('77777777-0000-4000-8000-00000000000a','f4000000-0000-4000-8000-000000000009',
   'f4000000-0000-4000-8000-00000000000a', now() - interval '6 days',
   '{"same_development": true, "identical_specs": true, "shared_images": true}'::jsonb,
   '{"note": "same model and development, adjacent plots"}'::jsonb,
   'CONFIRMED_DISTINCT','وحدتان متجاورتان متطابقتان في النموذج لكنهما عقاران ماديان مختلفان',
   'f3000000-0000-4000-8000-000000000003', now() - interval '5 days','rules-0.2.0')
ON CONFLICT (identity_candidate_id) DO NOTHING;

DO $$
DECLARE aliases int; status identity_review_status;
BEGIN
  SELECT count(*) INTO aliases FROM property_identity_aliases
   WHERE source_identity_candidate_id='77777777-0000-4000-8000-00000000000a';
  SELECT review_status INTO status FROM property_identity_candidates
   WHERE identity_candidate_id='77777777-0000-4000-8000-00000000000a';
  IF aliases <> 0 OR status <> 'CONFIRMED_DISTINCT' THEN
    RAISE EXCEPTION 'MF8: CONFIRMED_DISTINCT must leave no alias mapping; got % alias(es), status %',
      aliases, status;
  END IF;
END $$;

COMMIT;

\echo ''
\echo 'Market edge fixtures MF1-MF8 loaded.'
SELECT 'MF1 offers on one property'        AS fixture,
       (SELECT count(*)::text FROM property_offers WHERE property_id='f4000000-0000-4000-8000-000000000001') AS value
UNION ALL SELECT 'MF2 live offers (must be 0)',
       (SELECT count(*)::text FROM property_offers
         WHERE property_id='f4000000-0000-4000-8000-000000000006' AND status NOT IN ('WITHDRAWN','CLOSED'))
UNION ALL SELECT 'MF3 POTENTIAL property offers (must be 0)',
       (SELECT count(*)::text FROM property_offers WHERE property_id='f4000000-0000-4000-8000-000000000002')
UNION ALL SELECT 'MF4 blocking REQUIRED criteria',
       (SELECT count(*)::text FROM request_criteria
         WHERE request_id='f7000000-0000-4000-8000-000000000004' AND importance='REQUIRED' AND blocking_if_unknown)
UNION ALL SELECT 'MF5 live bindings under revoked grants',
       (SELECT count(*)::text FROM resource_consent_bindings b JOIN consent_grants g USING (consent_id)
         WHERE g.status='REVOKED' AND b.revoked_at IS NULL)
UNION ALL SELECT 'MF6 parties with no account',
       (SELECT count(*)::text FROM parties p
         WHERE NOT EXISTS (SELECT 1 FROM user_accounts a WHERE a.party_id=p.party_id))
UNION ALL SELECT 'MF7 parties on the shared phone',
       (SELECT count(DISTINCT party_id)::text FROM party_contact_points
         WHERE contact_point_id='f2000000-0000-4000-8000-000000000002')
UNION ALL SELECT 'MF8 CONFIRMED_DISTINCT pairs with no alias',
       (SELECT count(*)::text FROM property_identity_candidates c
         WHERE c.review_status='CONFIRMED_DISTINCT'
           AND NOT EXISTS (SELECT 1 FROM property_identity_aliases a
                            WHERE a.source_identity_candidate_id=c.identity_candidate_id));

-- ---------------------------------------------------------------------------
-- Claim eligibility fixtures (contract x-authorization on postRecordsClaim)
--
-- The contract requires, for a customer claim, "verified contact point and
-- resource party relationship". The base fixtures had no record that a real
-- account could legitimately claim — every assisted record belonged to a party
-- with no account — so the condition could only ever be tested negatively.
--
--   * f7...005  an ASSISTED/UNCLAIMED request for KHADIJA's party, which
--               account f3...004 (bound to that party, login contact point
--               f2...004, which reaches that party) may legitimately claim;
--   * f3...007  an account for BRAHIM whose login contact point is the SHARED
--               line f2...002. That line also reaches the agency, so this
--               account is the test that a shared phone does not let one
--               party's account claim another party's record (DL-02).
-- ---------------------------------------------------------------------------

INSERT INTO user_accounts (account_id, party_id, status, login_contact_point_id,
                           email, activated_at)
SELECT 'f3000000-0000-4000-8000-000000000007'::uuid,
       'f1000000-0000-4000-8000-000000000002'::uuid, 'ACTIVATED',
       'f2000000-0000-4000-8000-000000000002'::uuid, NULL, now()
WHERE NOT EXISTS (
  SELECT 1 FROM user_accounts WHERE account_id='f3000000-0000-4000-8000-000000000007');

INSERT INTO user_account_roles (account_id, role)
SELECT 'f3000000-0000-4000-8000-000000000007'::uuid, 'CUSTOMER'::account_role
WHERE NOT EXISTS (
  SELECT 1 FROM user_account_roles
   WHERE account_id='f3000000-0000-4000-8000-000000000007' AND role='CUSTOMER');

INSERT INTO requests (request_id, party_id, status, transaction_intent, intent,
                      payment, desired_property_type, primary_location_id,
                      budget_target_dzd, budget_max_dzd, budget_flexibility,
                      last_confirmed_at, management_mode, claim_status,
                      created_by_account_id)
SELECT 'f7000000-0000-4000-8000-000000000005'::uuid,
       'f1000000-0000-4000-8000-000000000004'::uuid,
       'QUALIFIED','BUY','ACTIVE_SEARCH','CASH','APARTMENT',
       (SELECT location_id FROM locations WHERE code='ADR-CENTER'),
       18000000::bigint, 22000000::bigint,'MODERATE', now() - interval '3 days',
       'ASSISTED','UNCLAIMED','f3000000-0000-4000-8000-000000000002'::uuid
WHERE NOT EXISTS (
  SELECT 1 FROM requests WHERE request_id='f7000000-0000-4000-8000-000000000005');

DO $$
DECLARE eligible int;
BEGIN
  -- The point of the fixture: exactly one account may legitimately claim
  -- f7...005, and it is the one bound to that request's party.
  SELECT count(*) INTO eligible
  FROM user_accounts a
  JOIN requests r ON r.party_id = a.party_id
  JOIN party_contact_points pcp
    ON pcp.party_id = r.party_id AND pcp.contact_point_id = a.login_contact_point_id
  JOIN contact_points cp
    ON cp.contact_point_id = a.login_contact_point_id
   AND cp.control_status = 'VERIFIED_CONTROL'
  WHERE r.request_id = 'f7000000-0000-4000-8000-000000000005'
    AND a.status = 'ACTIVATED';
  IF eligible <> 1 THEN
    RAISE EXCEPTION 'claim fixture: expected exactly one eligible claimant, found %', eligible;
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- EC1 extended: TWO eligible accounts for ONE party.
--
-- `user_accounts` f3...001 and f3...006 are both bound to party f1...001. For
-- INV-1's write half to be testable AFTER claim eligibility is enforced, both
-- must be able to pass eligibility — otherwise "a second claim by another
-- account is rejected" can only be reached by an ineligible account, and the
-- test would be proving eligibility rather than INV-1.
--
-- So f3...006's login contact point is linked to the same party, and f7...006
-- is an ASSISTED/UNCLAIMED request for it that either account may claim.
-- ---------------------------------------------------------------------------

INSERT INTO party_contact_points (party_id, contact_point_id, is_primary,
                                  relationship_note)
SELECT 'f1000000-0000-4000-8000-000000000001'::uuid,
       'f2000000-0000-4000-8000-000000000005'::uuid, false,
       'second account for the same party (EC1)'
WHERE NOT EXISTS (
  SELECT 1 FROM party_contact_points
   WHERE party_id='f1000000-0000-4000-8000-000000000001'
     AND contact_point_id='f2000000-0000-4000-8000-000000000005');

INSERT INTO requests (request_id, party_id, status, transaction_intent, intent,
                      payment, desired_property_type, primary_location_id,
                      budget_target_dzd, budget_max_dzd, budget_flexibility,
                      last_confirmed_at, management_mode, claim_status,
                      created_by_account_id)
SELECT 'f7000000-0000-4000-8000-000000000006'::uuid,
       'f1000000-0000-4000-8000-000000000001'::uuid,
       'QUALIFIED','RENT','EXPLORING','UNDECIDED','APARTMENT',
       (SELECT location_id FROM locations WHERE code='ADR-CENTER'),
       30000::bigint, 40000::bigint,'MODERATE', now() - interval '5 days',
       'ASSISTED','UNCLAIMED','f3000000-0000-4000-8000-000000000002'::uuid
WHERE NOT EXISTS (
  SELECT 1 FROM requests WHERE request_id='f7000000-0000-4000-8000-000000000006');
