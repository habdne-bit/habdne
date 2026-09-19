-- TURAB — PostgreSQL schema v0.2.3
-- Reference date: 2026-09-19
-- Target: PostgreSQL 16+
-- Purpose: executable baseline schema for the TURAB foundational pilot.
-- IMPORTANT: this schema implements the product invariants in TURAB Developer Reference Specification v0.1 plus v0.2 remediation decisions.
-- It intentionally avoids AVM, advanced CRM, autonomous AI decisions, full event sourcing and full knowledge-graph complexity.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS turab;
SET search_path = turab, public;

-- -----------------------------------------------------------------------------
-- 0. TYPES
-- -----------------------------------------------------------------------------

CREATE TYPE party_kind AS ENUM ('PERSON','BUSINESS');
CREATE TYPE party_status AS ENUM ('DISCOVERED','CONTACTED','CONTACT_VERIFIED','PARTY_ACTIVE','INACTIVE');
CREATE TYPE contact_control_status AS ENUM ('UNVERIFIED','VERIFIED_CONTROL');
CREATE TYPE account_status AS ENUM ('INVITED','ACTIVATED','SUSPENDED','DISABLED');
CREATE TYPE account_role AS ENUM ('ADMIN','OPERATOR','REVIEWER','CUSTOMER');
CREATE TYPE management_mode AS ENUM ('SELF_MANAGED','ASSISTED','SHARED_MANAGEMENT');
CREATE TYPE account_claim_status AS ENUM ('UNCLAIMED','CLAIMED');
CREATE TYPE contact_point_kind AS ENUM ('PHONE','EMAIL');
CREATE TYPE request_transaction_intent AS ENUM ('BUY','RENT');
CREATE TYPE consent_resource_type AS ENUM ('REQUEST','PROPERTY','PROPERTY_OFFER','COMMUNICATION_THREAD');
CREATE TYPE webhook_processing_status AS ENUM ('RECEIVED','PROCESSED','IGNORED','FAILED');

CREATE TYPE consent_scope AS ENUM (
  'ASSISTED_ENTRY',
  'PUBLIC_LISTING_ALLOWED',
  'PRIVATE_MATCHING_ONLY',
  'CONTACT_BEFORE_SHARING',
  'COMMUNICATION_ARCHIVE'
);
CREATE TYPE consent_status AS ENUM ('GRANTED','REVOKED');
CREATE TYPE consent_channel AS ENUM ('WHATSAPP','SMS','PHONE_CONFIRMED','WEB','IN_PERSON','OTHER');

CREATE TYPE external_lead_kind AS ENUM ('PROPERTY','REQUEST');
CREATE TYPE external_lead_status AS ENUM (
  'DISCOVERED','CONTACT_ATTEMPTED','CONTACTED','CONSENT_PENDING','CONSENTED','PENDING_INFO','CONVERTED','DECLINED','UNREACHABLE','CLOSED'
);

CREATE TYPE request_status AS ENUM ('RAW','CONTACTED','QUALIFIED','ACTIVE','NEEDS_CONFIRMATION','PAUSED','CLOSED');
CREATE TYPE intent_stage AS ENUM ('EXPLORING','ACTIVE_SEARCH','READY_TO_ACT');
CREATE TYPE payment_method AS ENUM ('CASH','BANK_FINANCING','MIXED','UNDECIDED');
CREATE TYPE budget_flexibility AS ENUM ('STRICT','LOW','MODERATE','HIGH','UNSPECIFIED');
CREATE TYPE criterion_importance AS ENUM ('REQUIRED','PREFERRED','FLEXIBLE');
CREATE TYPE criterion_operator AS ENUM ('EQ','NEQ','IN','NOT_IN','GTE','LTE','BETWEEN','EXISTS','BOOL','TEXT_SEMANTIC');

CREATE TYPE property_type AS ENUM ('HOUSE_VILLA','APARTMENT','LAND','SHOP_COMMERCIAL','AGRICULTURAL_PROPERTY','BUILDING','OTHER');
CREATE TYPE supply_mode AS ENUM ('PUBLIC','PRIVATE','POTENTIAL');
CREATE TYPE availability_status AS ENUM (
  'AVAILABLE','POTENTIALLY_AVAILABLE','UNDER_DISCUSSION','TEMPORARILY_UNAVAILABLE','UNAVAILABLE','NEEDS_CONFIRMATION','UNKNOWN'
);
CREATE TYPE transaction_type AS ENUM ('SALE','RENT');
CREATE TYPE offer_status AS ENUM ('DRAFT','PENDING_INFO','ACTIVE','PAUSED','WITHDRAWN','CLOSED');
CREATE TYPE price_visibility AS ENUM ('PUBLIC','ON_REQUEST','PRIVATE');
CREATE TYPE price_negotiability AS ENUM ('YES','NO','UNKNOWN');

CREATE TYPE source_kind AS ENUM (
  'USER_FORM','EMPLOYEE_ENTRY','FACEBOOK_POST','OUEDKNISS_POST','OTHER_WEB_POST','WHATSAPP','PHONE_CALL','IN_PERSON','BROKER','DOCUMENT','IMPORT','OTHER'
);
CREATE TYPE observation_kind AS ENUM ('TEXT','CALL_NOTE','MESSAGE','DOCUMENT','IMAGE','FORM_SUBMISSION','SYSTEM_IMPORT','OTHER');
CREATE TYPE evidence_kind AS ENUM ('TEXT_FRAGMENT','DOCUMENT_FILE','IMAGE_FILE','MESSAGE_REF','CALL_REF','FORM_REF','EXTERNAL_URL','OTHER');
CREATE TYPE evidence_relationship AS ENUM ('SUPPORTS','CONTRADICTS','QUALIFIES','SUPERSEDES');
CREATE TYPE verification_level AS ENUM ('DECLARED','DOCUMENT_SEEN','DETAILS_MATCHED','PROFESSIONAL_CHECK');
CREATE TYPE knowledge_claim_status AS ENUM ('ACTIVE','SUPERSEDED','REJECTED','CONFLICTING');
CREATE TYPE resolution_status AS ENUM ('CURRENT','SUPERSEDED','REVOKED');

CREATE TYPE identity_review_status AS ENUM ('PENDING_REVIEW','CONFIRMED_SAME','CONFIRMED_DISTINCT','UNSURE');

CREATE TYPE compatibility_status AS ENUM ('PASS','FAIL','UNKNOWN');
CREATE TYPE gate_status AS ENUM ('PASS','FAIL','UNKNOWN','NOT_APPLICABLE');
CREATE TYPE match_eligibility AS ENUM ('ELIGIBLE','REJECTED','NEED_MORE_INFORMATION','NEEDS_CONFIRMATION');
CREATE TYPE match_review_decision AS ENUM ('APPROVED','REJECTED','NEED_MORE_INFORMATION');
CREATE TYPE freshness_state AS ENUM ('FRESH','STALE','UNKNOWN','NOT_APPLICABLE');

CREATE TYPE task_type AS ENUM (
  'VERIFY_DOCUMENT','RECONFIRM_REQUEST','RECONFIRM_PROPERTY','CONFIRM_PRICE','CONFIRM_AVAILABILITY','CONFIRM_PERMISSION','CONTACT_PARTY','RESOLVE_IDENTITY','OTHER'
);
CREATE TYPE task_priority AS ENUM ('LOW','NORMAL','HIGH','URGENT');
CREATE TYPE task_status AS ENUM ('OPEN','IN_PROGRESS','DONE','CANCELLED');

CREATE TYPE opportunity_status AS ENUM ('NEW','SHARED','ENGAGED','CLOSED');
CREATE TYPE opportunity_validity AS ENUM ('VALID','NEEDS_CONFIRMATION','INVALID');
CREATE TYPE sharing_scope AS ENUM ('SUMMARY_ONLY','PROPERTY_DETAILS_ALLOWED','CONTACT_AFTER_CONFIRMATION');
CREATE TYPE opportunity_response AS ENUM ('INTERESTED','NEED_MORE_INFORMATION','NOT_SUITABLE');

CREATE TYPE interaction_type AS ENUM ('CALL','WHATSAPP','SMS','EMAIL','IN_PERSON','INFO_REQUEST','VISIT','NEGOTIATION','STATUS_CHANGE','NOTE','OTHER');
CREATE TYPE communication_channel AS ENUM ('WHATSAPP','PHONE','SMS','EMAIL','WEB','IN_PERSON','OTHER');
CREATE TYPE message_direction AS ENUM ('INBOUND','OUTBOUND','INTERNAL');
CREATE TYPE delivery_status AS ENUM ('QUEUED','SENT','DELIVERED','READ','FAILED','UNKNOWN');

CREATE TYPE interest_status AS ENUM ('ACTIVE','CONVERTED_TO_REQUEST','CLOSED');

-- -----------------------------------------------------------------------------
-- 1. COMMON FUNCTIONS
-- -----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION bump_version_and_timestamp()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.version := OLD.version + 1;
  NEW.updated_at := now();
  RETURN NEW;
END $$;

-- -----------------------------------------------------------------------------
-- 2. MASTER DATA
-- -----------------------------------------------------------------------------

CREATE TABLE schema_metadata (
  key text PRIMARY KEY,
  value text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO schema_metadata(key,value) VALUES
  ('schema_version','0.2.3'),
  ('reference_spec','TURAB Developer Reference Specification v0.1 + Technical Architecture Remediation v0.2')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now();

CREATE TABLE locations (
  location_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  parent_id uuid REFERENCES locations(location_id) ON DELETE RESTRICT,
  canonical_ar text NOT NULL,
  canonical_fr text,
  location_type text NOT NULL CHECK (location_type IN ('WILAYA','COMMUNE','AREA','KSAR','NEIGHBORHOOD','LANDMARK','OTHER')),
  confidence_level text NOT NULL DEFAULT 'CONFIRMED' CHECK (confidence_level IN ('CONFIRMED','CANDIDATE','UNMAPPED')),
  active_for_selection boolean NOT NULL DEFAULT true,
  latitude numeric(9,6),
  longitude numeric(9,6),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((latitude IS NULL AND longitude IS NULL) OR (latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180))
);
CREATE INDEX idx_locations_parent ON locations(parent_id);
CREATE TRIGGER trg_locations_updated BEFORE UPDATE ON locations FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE location_aliases (
  alias_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  location_id uuid NOT NULL REFERENCES locations(location_id) ON DELETE CASCADE,
  alias_text text NOT NULL,
  language_code text,
  normalized_text text,
  source_note text,
  is_confirmed boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(location_id, alias_text)
);
CREATE INDEX idx_location_aliases_text ON location_aliases(alias_text);

CREATE TABLE attribute_definitions (
  attribute_definition_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  label_ar text NOT NULL,
  label_fr text,
  value_type text NOT NULL CHECK (value_type IN ('TEXT','NUMBER','BOOLEAN','ENUM','DATE','JSON')),
  unit text,
  applies_to property_type[],
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE attribute_options (
  attribute_option_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  attribute_definition_id uuid NOT NULL REFERENCES attribute_definitions(attribute_definition_id) ON DELETE RESTRICT,
  option_code text NOT NULL,
  label_ar text NOT NULL,
  label_fr text,
  active boolean NOT NULL DEFAULT true,
  sort_order smallint NOT NULL DEFAULT 100,
  UNIQUE(attribute_definition_id, option_code)
);

CREATE TABLE criterion_definitions (
  code text PRIMARY KEY,
  label_ar text NOT NULL,
  label_en text,
  value_type text NOT NULL CHECK (value_type IN ('TEXT','NUMBER','BOOLEAN','ENUM','DATE','JSON','LOCATION','MONEY')),
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE reason_codes (
  code text PRIMARY KEY,
  category text NOT NULL,
  label_ar text NOT NULL,
  label_en text,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- 3. PARTY / ACCOUNTS / CONSENT
-- -----------------------------------------------------------------------------

CREATE TABLE parties (
  party_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind party_kind NOT NULL,
  status party_status NOT NULL DEFAULT 'DISCOVERED',
  display_name text,
  legal_name text,
  notes text,
  version integer NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_parties_status ON parties(status);
CREATE TRIGGER trg_parties_version BEFORE UPDATE ON parties FOR EACH ROW EXECUTE FUNCTION bump_version_and_timestamp();

CREATE TABLE contact_points (
  contact_point_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind contact_point_kind NOT NULL,
  normalized_value text NOT NULL,
  display_value text,
  control_status contact_control_status NOT NULL DEFAULT 'UNVERIFIED',
  control_verified_at timestamptz,
  verification_method text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(kind, normalized_value)
);
CREATE TRIGGER trg_contact_points_updated BEFORE UPDATE ON contact_points FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE party_contact_points (
  party_id uuid NOT NULL REFERENCES parties(party_id) ON DELETE RESTRICT,
  contact_point_id uuid NOT NULL REFERENCES contact_points(contact_point_id) ON DELETE RESTRICT,
  is_primary boolean NOT NULL DEFAULT false,
  relationship_note text,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(party_id, contact_point_id)
);
CREATE INDEX idx_party_contact_points_party ON party_contact_points(party_id);
CREATE UNIQUE INDEX ux_party_primary_contact_kind ON party_contact_points(party_id, is_primary) WHERE is_primary;

CREATE TABLE user_accounts (
  account_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  party_id uuid REFERENCES parties(party_id) ON DELETE SET NULL,
  status account_status NOT NULL DEFAULT 'INVITED',
  login_contact_point_id uuid REFERENCES contact_points(contact_point_id) ON DELETE RESTRICT,
  email text,
  activated_at timestamptz,
  last_login_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(login_contact_point_id),
  UNIQUE(email)
);
CREATE TRIGGER trg_user_accounts_updated BEFORE UPDATE ON user_accounts FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE user_account_roles (
  account_id uuid NOT NULL REFERENCES user_accounts(account_id) ON DELETE CASCADE,
  role account_role NOT NULL,
  granted_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(account_id, role)
);

-- Consent is granular: one row per scope, optionally tied to a specific request/property later.
CREATE TABLE consent_grants (
  consent_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  party_id uuid NOT NULL REFERENCES parties(party_id) ON DELETE CASCADE,
  scope consent_scope NOT NULL,
  status consent_status NOT NULL DEFAULT 'GRANTED',
  channel consent_channel NOT NULL,
  consent_version text NOT NULL,
  granted_at timestamptz NOT NULL,
  revoked_at timestamptz,
  evidence_observation_id uuid,
  notes text,
  created_by_account_id uuid REFERENCES user_accounts(account_id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (revoked_at IS NULL OR revoked_at >= granted_at)
);
CREATE INDEX idx_consent_party_scope ON consent_grants(party_id, scope, status);

-- Resource-scoped consent bindings. A grant is not enough by itself; the binding proves which resource/purpose it authorizes.
CREATE TABLE resource_consent_bindings (
  consent_binding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  consent_id uuid NOT NULL REFERENCES consent_grants(consent_id) ON DELETE RESTRICT,
  purpose consent_scope NOT NULL,
  request_id uuid,
  property_id uuid,
  offer_id uuid,
  thread_id uuid,
  bound_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz,
  bound_by_account_id uuid REFERENCES user_accounts(account_id) ON DELETE SET NULL,
  notes text,
  CHECK (num_nonnulls(request_id, property_id, offer_id, thread_id) = 1),
  CHECK (revoked_at IS NULL OR revoked_at >= bound_at)
);
CREATE INDEX idx_consent_bindings_consent ON resource_consent_bindings(consent_id, purpose);
CREATE UNIQUE INDEX ux_active_consent_binding_request ON resource_consent_bindings(consent_id,purpose,request_id) WHERE request_id IS NOT NULL AND revoked_at IS NULL;
CREATE UNIQUE INDEX ux_active_consent_binding_property ON resource_consent_bindings(consent_id,purpose,property_id) WHERE property_id IS NOT NULL AND revoked_at IS NULL;
CREATE UNIQUE INDEX ux_active_consent_binding_offer ON resource_consent_bindings(consent_id,purpose,offer_id) WHERE offer_id IS NOT NULL AND revoked_at IS NULL;
CREATE UNIQUE INDEX ux_active_consent_binding_thread ON resource_consent_bindings(consent_id,purpose,thread_id) WHERE thread_id IS NOT NULL AND revoked_at IS NULL;

CREATE TABLE record_claim_events (
  claim_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id uuid,
  property_id uuid,
  claimed_by_account_id uuid NOT NULL REFERENCES user_accounts(account_id) ON DELETE RESTRICT,
  claimed_at timestamptz NOT NULL DEFAULT now(),
  verification_contact_point_id uuid REFERENCES contact_points(contact_point_id) ON DELETE RESTRICT,
  CHECK (num_nonnulls(request_id, property_id) = 1)
);

-- -----------------------------------------------------------------------------
-- 4. SOURCES / EXTERNAL LEADS
-- -----------------------------------------------------------------------------

CREATE TABLE sources (
  source_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind source_kind NOT NULL,
  external_url text,
  external_ref text,
  title text,
  raw_text text,
  captured_at timestamptz,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_account_id uuid REFERENCES user_accounts(account_id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_sources_kind ON sources(kind);
CREATE INDEX idx_sources_external_ref ON sources(external_ref);

CREATE TABLE external_leads (
  external_lead_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_kind external_lead_kind NOT NULL,
  source_id uuid NOT NULL REFERENCES sources(source_id) ON DELETE RESTRICT,
  status external_lead_status NOT NULL DEFAULT 'DISCOVERED',
  raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  discovered_at timestamptz NOT NULL DEFAULT now(),
  party_id uuid REFERENCES parties(party_id) ON DELETE SET NULL,
  converted_request_id uuid,
  converted_property_id uuid,
  last_contact_at timestamptz,
  close_reason_code text REFERENCES reason_codes(code),
  created_by_account_id uuid REFERENCES user_accounts(account_id) ON DELETE SET NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_external_leads_queue ON external_leads(status, discovered_at);
CREATE TRIGGER trg_external_leads_updated BEFORE UPDATE ON external_leads FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- -----------------------------------------------------------------------------
-- 5. REQUEST
-- -----------------------------------------------------------------------------

CREATE TABLE requests (
  request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  party_id uuid NOT NULL REFERENCES parties(party_id) ON DELETE RESTRICT,
  status request_status NOT NULL DEFAULT 'RAW',
  transaction_intent request_transaction_intent NOT NULL DEFAULT 'BUY',
  intent intent_stage NOT NULL DEFAULT 'EXPLORING',
  payment payment_method NOT NULL DEFAULT 'UNDECIDED',
  desired_property_type property_type,
  property_type_importance criterion_importance NOT NULL DEFAULT 'REQUIRED',
  primary_location_id uuid REFERENCES locations(location_id) ON DELETE RESTRICT,
  location_importance criterion_importance NOT NULL DEFAULT 'REQUIRED',
  local_location_detail text,
  budget_target_dzd bigint CHECK (budget_target_dzd IS NULL OR budget_target_dzd >= 0),
  budget_max_dzd bigint CHECK (budget_max_dzd IS NULL OR budget_max_dzd >= 0),
  budget_importance criterion_importance NOT NULL DEFAULT 'REQUIRED',
  budget_flexibility budget_flexibility NOT NULL DEFAULT 'UNSPECIFIED',
  last_confirmed_at timestamptz,
  management_mode management_mode NOT NULL,
  claim_status account_claim_status NOT NULL,
  version integer NOT NULL DEFAULT 1 CHECK (version > 0),
  created_by_account_id uuid REFERENCES user_accounts(account_id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  closed_at timestamptz,
  close_reason_code text REFERENCES reason_codes(code),
  CHECK (budget_target_dzd IS NULL OR budget_max_dzd IS NULL OR budget_target_dzd <= budget_max_dzd),
  CHECK ((management_mode = 'ASSISTED' AND claim_status = 'UNCLAIMED') OR
         (management_mode IN ('SELF_MANAGED','SHARED_MANAGEMENT') AND claim_status = 'CLAIMED'))
);
CREATE INDEX idx_requests_active ON requests(status, last_confirmed_at);
CREATE INDEX idx_requests_location ON requests(primary_location_id);
CREATE TRIGGER trg_requests_version BEFORE UPDATE ON requests FOR EACH ROW EXECUTE FUNCTION bump_version_and_timestamp();

CREATE TABLE request_criteria (
  request_criterion_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id uuid NOT NULL REFERENCES requests(request_id) ON DELETE CASCADE,
  criterion_code text NOT NULL,
  importance criterion_importance NOT NULL,
  operator criterion_operator NOT NULL,
  value jsonb NOT NULL,
  unit text,
  blocking_if_unknown boolean NOT NULL DEFAULT false,
  sort_order smallint NOT NULL DEFAULT 100,
  source_note text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(request_id, criterion_code, sort_order)
);
CREATE INDEX idx_request_criteria_request ON request_criteria(request_id);
CREATE TRIGGER trg_request_criteria_updated BEFORE UPDATE ON request_criteria FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- -----------------------------------------------------------------------------
-- 6. PROPERTY / OFFERS / RELATIONS
-- -----------------------------------------------------------------------------

CREATE TABLE properties (
  property_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  property_type property_type NOT NULL,
  canonical_location_id uuid REFERENCES locations(location_id) ON DELETE RESTRICT,
  local_location_detail text,
  land_area_m2 numeric(12,2) CHECK (land_area_m2 IS NULL OR land_area_m2 > 0),
  built_area_m2 numeric(12,2) CHECK (built_area_m2 IS NULL OR built_area_m2 > 0),
  current_availability availability_status NOT NULL DEFAULT 'UNKNOWN',
  availability_last_confirmed_at timestamptz,
  supply_mode supply_mode NOT NULL DEFAULT 'PUBLIC',
  management_mode management_mode NOT NULL,
  claim_status account_claim_status NOT NULL,
  version integer NOT NULL DEFAULT 1 CHECK (version > 0),
  created_by_account_id uuid REFERENCES user_accounts(account_id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((management_mode = 'ASSISTED' AND claim_status = 'UNCLAIMED') OR
         (management_mode IN ('SELF_MANAGED','SHARED_MANAGEMENT') AND claim_status = 'CLAIMED'))
);
CREATE INDEX idx_properties_lookup ON properties(property_type, canonical_location_id, current_availability, supply_mode);
CREATE TRIGGER trg_properties_version BEFORE UPDATE ON properties FOR EACH ROW EXECUTE FUNCTION bump_version_and_timestamp();

CREATE TABLE property_attributes (
  property_attribute_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  property_id uuid NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
  attribute_definition_id uuid NOT NULL REFERENCES attribute_definitions(attribute_definition_id) ON DELETE RESTRICT,
  value jsonb NOT NULL,
  resolved_claim_id uuid,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(property_id, attribute_definition_id)
);

CREATE TABLE property_offers (
  offer_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  property_id uuid NOT NULL REFERENCES properties(property_id) ON DELETE RESTRICT,
  party_id uuid NOT NULL REFERENCES parties(party_id) ON DELETE RESTRICT,
  transaction_type transaction_type NOT NULL,
  status offer_status NOT NULL DEFAULT 'DRAFT',
  asking_price_dzd bigint CHECK (asking_price_dzd IS NULL OR asking_price_dzd >= 0),
  raw_price_text text,
  price_negotiable price_negotiability NOT NULL DEFAULT 'UNKNOWN',
  seller_expectation_dzd bigint CHECK (seller_expectation_dzd IS NULL OR seller_expectation_dzd >= 0),
  price_visibility price_visibility NOT NULL DEFAULT 'PUBLIC',
  last_confirmed_at timestamptz,
  commercial_terms_last_confirmed_at timestamptz,
  permission_scope sharing_scope NOT NULL DEFAULT 'SUMMARY_ONLY',
  version integer NOT NULL DEFAULT 1 CHECK (version > 0),
  created_by_account_id uuid REFERENCES user_accounts(account_id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (seller_expectation_dzd IS NULL OR transaction_type = 'SALE')
);
CREATE INDEX idx_property_offers_property ON property_offers(property_id, status);
CREATE INDEX idx_property_offers_party ON property_offers(party_id);
CREATE TRIGGER trg_property_offers_version BEFORE UPDATE ON property_offers FOR EACH ROW EXECUTE FUNCTION bump_version_and_timestamp();

CREATE TABLE property_offer_sources (
  offer_id uuid NOT NULL REFERENCES property_offers(offer_id) ON DELETE CASCADE,
  source_id uuid NOT NULL REFERENCES sources(source_id) ON DELETE RESTRICT,
  is_primary boolean NOT NULL DEFAULT false,
  linked_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(offer_id, source_id)
);

CREATE TABLE party_property_relations (
  party_property_relation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  party_id uuid NOT NULL REFERENCES parties(party_id) ON DELETE RESTRICT,
  property_id uuid NOT NULL REFERENCES properties(property_id) ON DELETE RESTRICT,
  relation_code text NOT NULL CHECK (relation_code IN ('OWNER_DECLARED','BROKER','AGENCY','DEVELOPER','OCCUPANT','CONTACT_PERSON','OTHER')),
  verification_level verification_level NOT NULL DEFAULT 'DECLARED',
  valid_from timestamptz,
  valid_to timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from)
);
CREATE INDEX idx_party_property_property ON party_property_relations(property_id);

-- -----------------------------------------------------------------------------
-- 7. TRUTH / PROVENANCE / TEMPORAL / VERIFICATION
-- -----------------------------------------------------------------------------

CREATE TABLE observations (
  observation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id uuid REFERENCES sources(source_id) ON DELETE SET NULL,
  kind observation_kind NOT NULL,
  party_id uuid REFERENCES parties(party_id) ON DELETE SET NULL,
  observed_at timestamptz,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  raw_text text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  recorded_by_account_id uuid REFERENCES user_accounts(account_id) ON DELETE SET NULL
);
CREATE INDEX idx_observations_source ON observations(source_id);


CREATE TABLE evidence_artifacts (
  evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  observation_id uuid REFERENCES observations(observation_id) ON DELETE SET NULL,
  kind evidence_kind NOT NULL,
  storage_ref text,
  external_ref text,
  content_hash text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  captured_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE claims (
  claim_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  party_id uuid REFERENCES parties(party_id) ON DELETE RESTRICT,
  request_id uuid REFERENCES requests(request_id) ON DELETE RESTRICT,
  property_id uuid REFERENCES properties(property_id) ON DELETE RESTRICT,
  offer_id uuid REFERENCES property_offers(offer_id) ON DELETE RESTRICT,
  attribute_code text NOT NULL,
  claimed_value jsonb NOT NULL,
  asserted_by_party_id uuid REFERENCES parties(party_id) ON DELETE SET NULL,
  source_id uuid REFERENCES sources(source_id) ON DELETE SET NULL,
  observation_id uuid REFERENCES observations(observation_id) ON DELETE SET NULL,
  extracted_by text,
  extraction_model_version text,
  extraction_confidence numeric(5,4) CHECK (extraction_confidence IS NULL OR extraction_confidence BETWEEN 0 AND 1),
  observed_at timestamptz,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  valid_from timestamptz,
  valid_to timestamptz,
  effective_verification_level verification_level NOT NULL DEFAULT 'DECLARED',
  status knowledge_claim_status NOT NULL DEFAULT 'ACTIVE',
  supersedes_claim_id uuid REFERENCES claims(claim_id) ON DELETE SET NULL,
  recorded_by_account_id uuid REFERENCES user_accounts(account_id) ON DELETE SET NULL,
  CHECK (num_nonnulls(party_id, request_id, property_id, offer_id) = 1),
  CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from)
);
CREATE INDEX idx_claims_property_attr ON claims(property_id, attribute_code) WHERE property_id IS NOT NULL;
CREATE INDEX idx_claims_request_attr ON claims(request_id, attribute_code) WHERE request_id IS NOT NULL;
CREATE INDEX idx_claims_offer_attr ON claims(offer_id, attribute_code) WHERE offer_id IS NOT NULL;


CREATE TABLE claim_evidence (
  claim_id uuid NOT NULL REFERENCES claims(claim_id) ON DELETE CASCADE,
  evidence_id uuid NOT NULL REFERENCES evidence_artifacts(evidence_id) ON DELETE CASCADE,
  relationship evidence_relationship NOT NULL DEFAULT 'SUPPORTS',
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(claim_id, evidence_id, relationship)
);

CREATE TABLE verification_events (
  verification_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_id uuid NOT NULL REFERENCES claims(claim_id) ON DELETE CASCADE,
  level verification_level NOT NULL,
  procedure_code text,
  outcome text NOT NULL CHECK (outcome IN ('CONFIRMED','NOT_CONFIRMED','CONFLICT_FOUND','INCONCLUSIVE')),
  notes text,
  verified_by_account_id uuid REFERENCES user_accounts(account_id) ON DELETE SET NULL,
  verified_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_verification_claim ON verification_events(claim_id, verified_at DESC);

CREATE TABLE resolved_values (
  resolved_value_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  party_id uuid REFERENCES parties(party_id) ON DELETE RESTRICT,
  request_id uuid REFERENCES requests(request_id) ON DELETE RESTRICT,
  property_id uuid REFERENCES properties(property_id) ON DELETE RESTRICT,
  offer_id uuid REFERENCES property_offers(offer_id) ON DELETE RESTRICT,
  attribute_code text NOT NULL,
  resolved_value jsonb NOT NULL,
  source_claim_id uuid REFERENCES claims(claim_id) ON DELETE RESTRICT,
  resolution_status resolution_status NOT NULL DEFAULT 'CURRENT',
  resolution_reason_code text REFERENCES reason_codes(code),
  resolved_by_account_id uuid REFERENCES user_accounts(account_id) ON DELETE SET NULL,
  valid_from timestamptz NOT NULL DEFAULT now(),
  valid_to timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (num_nonnulls(party_id, request_id, property_id, offer_id) = 1),
  CHECK (valid_to IS NULL OR valid_to > valid_from)
);
CREATE UNIQUE INDEX ux_resolved_current_party ON resolved_values(party_id, attribute_code)
  WHERE party_id IS NOT NULL AND valid_to IS NULL AND resolution_status = 'CURRENT';
CREATE UNIQUE INDEX ux_resolved_current_request ON resolved_values(request_id, attribute_code)
  WHERE request_id IS NOT NULL AND valid_to IS NULL AND resolution_status = 'CURRENT';
CREATE UNIQUE INDEX ux_resolved_current_property ON resolved_values(property_id, attribute_code)
  WHERE property_id IS NOT NULL AND valid_to IS NULL AND resolution_status = 'CURRENT';
CREATE UNIQUE INDEX ux_resolved_current_offer ON resolved_values(offer_id, attribute_code)
  WHERE offer_id IS NOT NULL AND valid_to IS NULL AND resolution_status = 'CURRENT';

-- -----------------------------------------------------------------------------
-- 8. PROPERTY IDENTITY RESOLUTION
-- -----------------------------------------------------------------------------

CREATE TABLE property_identity_candidates (
  identity_candidate_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  property_a_id uuid NOT NULL REFERENCES properties(property_id) ON DELETE RESTRICT,
  property_b_id uuid NOT NULL REFERENCES properties(property_id) ON DELETE RESTRICT,
  generated_at timestamptz NOT NULL DEFAULT now(),
  signals jsonb NOT NULL DEFAULT '{}'::jsonb,
  explanation jsonb NOT NULL DEFAULT '{}'::jsonb,
  review_status identity_review_status NOT NULL DEFAULT 'PENDING_REVIEW',
  review_reason_code text REFERENCES reason_codes(code),
  review_reason_text text,
  reviewer_account_id uuid REFERENCES user_accounts(account_id) ON DELETE SET NULL,
  reviewed_at timestamptz,
  algorithm_version text NOT NULL DEFAULT 'rules-0.2.0',
  CHECK (property_a_id <> property_b_id)
);
CREATE UNIQUE INDEX ux_identity_pair ON property_identity_candidates (
  LEAST(property_a_id, property_b_id), GREATEST(property_a_id, property_b_id)
);
CREATE INDEX idx_identity_pending ON property_identity_candidates(review_status, generated_at);

CREATE TABLE property_identity_aliases (
  alias_property_id uuid PRIMARY KEY REFERENCES properties(property_id) ON DELETE RESTRICT,
  canonical_property_id uuid NOT NULL REFERENCES properties(property_id) ON DELETE RESTRICT,
  source_identity_candidate_id uuid NOT NULL UNIQUE REFERENCES property_identity_candidates(identity_candidate_id) ON DELETE RESTRICT,
  reason_code text REFERENCES reason_codes(code),
  resolved_by_account_id uuid NOT NULL REFERENCES user_accounts(account_id) ON DELETE RESTRICT,
  resolved_at timestamptz NOT NULL DEFAULT now(),
  CHECK (alias_property_id <> canonical_property_id)
);
CREATE INDEX idx_property_identity_canonical ON property_identity_aliases(canonical_property_id);

-- -----------------------------------------------------------------------------
-- 9. MATCHING / DIAGNOSTIC / REVIEW
-- -----------------------------------------------------------------------------

CREATE TABLE matching_policies (
  matching_policy_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  version text NOT NULL UNIQUE,
  name text NOT NULL,
  rules jsonb NOT NULL,
  active boolean NOT NULL DEFAULT false,
  immutable boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  activated_at timestamptz
);

CREATE UNIQUE INDEX ux_matching_policy_one_active ON matching_policies(active) WHERE active;

CREATE TABLE match_candidates (
  match_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id uuid NOT NULL REFERENCES requests(request_id) ON DELETE RESTRICT,
  property_id uuid NOT NULL REFERENCES properties(property_id) ON DELETE RESTRICT,
  evaluated_offer_id uuid REFERENCES property_offers(offer_id) ON DELETE RESTRICT,
  matching_policy_id uuid NOT NULL REFERENCES matching_policies(matching_policy_id) ON DELETE RESTRICT,
  matching_policy_version text NOT NULL,
  request_version integer NOT NULL,
  property_version integer NOT NULL,
  offer_version integer,
  evaluated_at timestamptz NOT NULL DEFAULT now(),
  eligibility match_eligibility NOT NULL,
  hard_gate_status gate_status NOT NULL,
  information_gate_status gate_status NOT NULL,
  request_freshness freshness_state NOT NULL,
  property_freshness freshness_state NOT NULL,
  offer_freshness freshness_state NOT NULL DEFAULT 'NOT_APPLICABLE',
  freshness_gate_status gate_status NOT NULL,
  permission_gate_status gate_status NOT NULL,
  soft_score numeric(7,6) CHECK (soft_score IS NULL OR soft_score BETWEEN 0 AND 1),
  request_snapshot jsonb NOT NULL,
  property_snapshot jsonb NOT NULL,
  commercial_context_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  permission_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  freshness_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  input_hash text NOT NULL,
  explanation jsonb NOT NULL DEFAULT '{}'::jsonb,
  next_action jsonb,
  generated_by text NOT NULL DEFAULT 'RULE_ENGINE',
  ai_trace_ref text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(request_id, property_id, matching_policy_id, input_hash)
);
CREATE INDEX idx_match_queue ON match_candidates(eligibility, evaluated_at DESC);
CREATE INDEX idx_match_request ON match_candidates(request_id, evaluated_at DESC);

CREATE TABLE match_criterion_results (
  match_criterion_result_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  match_id uuid NOT NULL REFERENCES match_candidates(match_id) ON DELETE RESTRICT,
  request_criterion_id uuid REFERENCES request_criteria(request_criterion_id) ON DELETE SET NULL,
  criterion_code text NOT NULL,
  ordinal smallint NOT NULL DEFAULT 1,
  importance criterion_importance NOT NULL,
  request_value jsonb,
  property_value jsonb,
  compatibility compatibility_status NOT NULL,
  blocking boolean NOT NULL DEFAULT false,
  delta jsonb,
  evidence_level verification_level,
  evidence_claim_id uuid REFERENCES claims(claim_id) ON DELETE SET NULL,
  reason_code text REFERENCES reason_codes(code),
  rule_id text NOT NULL,
  rule_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(match_id, criterion_code, ordinal)
);
CREATE INDEX idx_match_criterion_match ON match_criterion_results(match_id);

CREATE TABLE match_reviews (
  match_review_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  match_id uuid NOT NULL REFERENCES match_candidates(match_id) ON DELETE RESTRICT,
  decision match_review_decision NOT NULL,
  reason_code text REFERENCES reason_codes(code),
  reason_text text,
  reviewer_account_id uuid NOT NULL REFERENCES user_accounts(account_id) ON DELETE RESTRICT,
  reviewed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE match_diagnostic_runs (
  diagnostic_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id uuid NOT NULL REFERENCES requests(request_id) ON DELETE RESTRICT,
  request_version integer NOT NULL,
  matching_policy_id uuid NOT NULL REFERENCES matching_policies(matching_policy_id) ON DELETE RESTRICT,
  matching_policy_version text NOT NULL,
  request_snapshot jsonb NOT NULL,
  input_hash text NOT NULL,
  run_at timestamptz NOT NULL DEFAULT now(),
  ready_opportunity_count integer NOT NULL DEFAULT 0 CHECK (ready_opportunity_count >= 0),
  actionable_unknown_count integer NOT NULL DEFAULT 0 CHECK (actionable_unknown_count >= 0),
  near_match_count integer NOT NULL DEFAULT 0 CHECK (near_match_count >= 0),
  blocker_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  suggested_actions jsonb NOT NULL DEFAULT '[]'::jsonb,
  relaxation_scenarios jsonb NOT NULL DEFAULT '[]'::jsonb
);
CREATE INDEX idx_diagnostic_request ON match_diagnostic_runs(request_id, run_at DESC);

-- -----------------------------------------------------------------------------
-- 10. TASKS
-- -----------------------------------------------------------------------------

CREATE TABLE tasks (
  task_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_type task_type NOT NULL,
  priority task_priority NOT NULL DEFAULT 'NORMAL',
  status task_status NOT NULL DEFAULT 'OPEN',
  title text NOT NULL,
  reason_code text REFERENCES reason_codes(code),
  party_id uuid REFERENCES parties(party_id) ON DELETE SET NULL,
  request_id uuid REFERENCES requests(request_id) ON DELETE RESTRICT,
  property_id uuid REFERENCES properties(property_id) ON DELETE RESTRICT,
  match_id uuid REFERENCES match_candidates(match_id) ON DELETE RESTRICT,
  assigned_account_id uuid REFERENCES user_accounts(account_id) ON DELETE SET NULL,
  due_at timestamptz,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  CHECK (completed_at IS NULL OR completed_at >= created_at)
);
CREATE INDEX idx_tasks_queue ON tasks(status, priority, created_at);

CREATE TABLE task_completion_events (
  task_completion_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id uuid NOT NULL REFERENCES tasks(task_id) ON DELETE RESTRICT,
  outcome_code text REFERENCES reason_codes(code),
  note text,
  evidence_observation_id uuid REFERENCES observations(observation_id) ON DELETE SET NULL,
  completed_by_account_id uuid NOT NULL REFERENCES user_accounts(account_id) ON DELETE RESTRICT,
  completed_at timestamptz NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- 11. OPPORTUNITY
-- -----------------------------------------------------------------------------

CREATE TABLE opportunities (
  opportunity_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id uuid NOT NULL REFERENCES requests(request_id) ON DELETE RESTRICT,
  property_id uuid NOT NULL REFERENCES properties(property_id) ON DELETE RESTRICT,
  approved_match_id uuid NOT NULL UNIQUE REFERENCES match_candidates(match_id) ON DELETE RESTRICT,
  current_offer_id uuid REFERENCES property_offers(offer_id) ON DELETE RESTRICT,
  current_permission_binding_id uuid,
  commercial_context_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  permission_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  status opportunity_status NOT NULL DEFAULT 'NEW',
  validity_status opportunity_validity NOT NULL DEFAULT 'VALID',
  sharing_scope sharing_scope NOT NULL,
  why_real jsonb NOT NULL,
  known_differences jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_by_account_id uuid NOT NULL REFERENCES user_accounts(account_id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  shared_at timestamptz,
  engaged_at timestamptz,
  last_confirmed_at timestamptz,
  last_activity_at timestamptz,
  closed_at timestamptz,
  close_reason_code text REFERENCES reason_codes(code),
  CHECK (closed_at IS NULL OR closed_at >= created_at)
);
CREATE UNIQUE INDEX ux_one_open_opportunity_per_pair ON opportunities(request_id, property_id)
  WHERE status <> 'CLOSED';
CREATE INDEX idx_opportunity_queue ON opportunities(status, validity_status, last_activity_at);

CREATE TABLE opportunity_responses (
  opportunity_response_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  opportunity_id uuid NOT NULL REFERENCES opportunities(opportunity_id) ON DELETE CASCADE,
  party_id uuid REFERENCES parties(party_id) ON DELETE SET NULL,
  response opportunity_response NOT NULL,
  reason_code text REFERENCES reason_codes(code),
  comment text,
  responded_at timestamptz NOT NULL DEFAULT now()
);

-- Enforce the core invariant: no opportunity may be created from a non-approved or non-eligible candidate.
CREATE OR REPLACE FUNCTION enforce_opportunity_gate()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  c match_candidates%ROWTYPE;
  latest_decision match_review_decision;
BEGIN
  SELECT * INTO c FROM match_candidates WHERE match_id = NEW.approved_match_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'approved_match_id % does not exist', NEW.approved_match_id;
  END IF;

  SELECT decision INTO latest_decision
  FROM match_reviews
  WHERE match_id = NEW.approved_match_id
  ORDER BY reviewed_at DESC, match_review_id DESC
  LIMIT 1;

  IF latest_decision IS DISTINCT FROM 'APPROVED' THEN
    RAISE EXCEPTION 'Opportunity requires the latest human review to be APPROVED';
  END IF;

  IF c.request_id <> NEW.request_id OR c.property_id <> NEW.property_id THEN
    RAISE EXCEPTION 'Opportunity request/property must match approved candidate';
  END IF;

  IF c.eligibility <> 'ELIGIBLE'
     OR c.hard_gate_status <> 'PASS'
     OR c.information_gate_status <> 'PASS'
     OR c.freshness_gate_status <> 'PASS'
     OR c.permission_gate_status <> 'PASS' THEN
    RAISE EXCEPTION 'Opportunity gate not satisfied for match %', NEW.approved_match_id;
  END IF;

  IF TG_OP = 'INSERT' AND NEW.current_offer_id IS DISTINCT FROM c.evaluated_offer_id THEN
    RAISE EXCEPTION 'Opportunity current_offer_id must initially match evaluated offer';
  END IF;

  RETURN NEW;
END $$;
CREATE TRIGGER trg_opportunity_gate BEFORE INSERT OR UPDATE OF approved_match_id, request_id, property_id ON opportunities
FOR EACH ROW EXECUTE FUNCTION enforce_opportunity_gate();

CREATE OR REPLACE FUNCTION enforce_approved_review_gate()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE c match_candidates%ROWTYPE;
BEGIN
  IF NEW.decision = 'APPROVED' THEN
    SELECT * INTO c FROM match_candidates WHERE match_id = NEW.match_id;
    IF c.eligibility <> 'ELIGIBLE'
       OR c.hard_gate_status <> 'PASS'
       OR c.information_gate_status <> 'PASS'
       OR c.freshness_gate_status <> 'PASS'
       OR c.permission_gate_status <> 'PASS' THEN
      RAISE EXCEPTION 'Cannot approve match % before all opportunity gates pass', NEW.match_id;
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_match_review_gate BEFORE INSERT ON match_reviews
FOR EACH ROW EXECUTE FUNCTION enforce_approved_review_gate();

-- -----------------------------------------------------------------------------
-- 12. INTEREST / COMMUNICATION / INTERACTION
-- -----------------------------------------------------------------------------

CREATE TABLE interests (
  interest_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  party_id uuid NOT NULL REFERENCES parties(party_id) ON DELETE CASCADE,
  property_id uuid NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
  status interest_status NOT NULL DEFAULT 'ACTIVE',
  created_at timestamptz NOT NULL DEFAULT now(),
  converted_request_id uuid REFERENCES requests(request_id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX ux_active_interest_per_pair ON interests(party_id, property_id) WHERE status = 'ACTIVE';

CREATE TABLE communication_threads (
  thread_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  channel communication_channel NOT NULL,
  party_id uuid REFERENCES parties(party_id) ON DELETE SET NULL,
  request_id uuid REFERENCES requests(request_id) ON DELETE SET NULL,
  property_id uuid REFERENCES properties(property_id) ON DELETE SET NULL,
  opportunity_id uuid REFERENCES opportunities(opportunity_id) ON DELETE SET NULL,
  external_thread_ref text,
  opened_at timestamptz NOT NULL DEFAULT now(),
  last_message_at timestamptz,
  archived_at timestamptz,
  created_by_account_id uuid REFERENCES user_accounts(account_id) ON DELETE SET NULL
);
CREATE INDEX idx_threads_party ON communication_threads(party_id, last_message_at DESC);
CREATE INDEX idx_threads_opportunity ON communication_threads(opportunity_id, last_message_at DESC);

CREATE TABLE communication_messages (
  message_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  thread_id uuid NOT NULL REFERENCES communication_threads(thread_id) ON DELETE RESTRICT,
  provider text,
  external_message_ref text,
  direction message_direction NOT NULL,
  message_type text NOT NULL DEFAULT 'TEXT',
  body_text text,
  media_ref text,
  delivery_status delivery_status NOT NULL DEFAULT 'UNKNOWN',
  occurred_at timestamptz NOT NULL,
  sent_by_account_id uuid REFERENCES user_accounts(account_id) ON DELETE SET NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(provider, external_message_ref)
);
CREATE INDEX idx_messages_thread_time ON communication_messages(thread_id, occurred_at);

CREATE TABLE interactions (
  interaction_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  interaction_type interaction_type NOT NULL,
  channel communication_channel,
  party_id uuid REFERENCES parties(party_id) ON DELETE SET NULL,
  request_id uuid REFERENCES requests(request_id) ON DELETE SET NULL,
  property_id uuid REFERENCES properties(property_id) ON DELETE SET NULL,
  opportunity_id uuid REFERENCES opportunities(opportunity_id) ON DELETE SET NULL,
  thread_id uuid REFERENCES communication_threads(thread_id) ON DELETE SET NULL,
  summary text,
  outcome_code text REFERENCES reason_codes(code),
  occurred_at timestamptz NOT NULL,
  operator_account_id uuid REFERENCES user_accounts(account_id) ON DELETE SET NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_interactions_party_time ON interactions(party_id, occurred_at DESC);
CREATE INDEX idx_interactions_opportunity_time ON interactions(opportunity_id, occurred_at DESC);

CREATE TABLE idempotency_records (
  idempotency_record_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_account_id uuid REFERENCES user_accounts(account_id) ON DELETE SET NULL,
  route_key text NOT NULL,
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  response_status integer,
  response_body jsonb,
  response_resource_ref text,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  UNIQUE(actor_account_id, route_key, idempotency_key)
);
CREATE INDEX idx_idempotency_expiry ON idempotency_records(expires_at);

CREATE TABLE webhook_events (
  webhook_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider text NOT NULL,
  provider_event_id text NOT NULL,
  event_type text,
  payload jsonb NOT NULL,
  processing_status webhook_processing_status NOT NULL DEFAULT 'RECEIVED',
  received_at timestamptz NOT NULL DEFAULT now(),
  processed_at timestamptz,
  error_text text,
  UNIQUE(provider, provider_event_id)
);

-- -----------------------------------------------------------------------------
-- 13. AUDIT
-- -----------------------------------------------------------------------------

CREATE TABLE audit_log (
  audit_id bigserial PRIMARY KEY,
  entity_table text NOT NULL,
  entity_id uuid,
  action text NOT NULL CHECK (action IN ('INSERT','UPDATE','DELETE')),
  old_row jsonb,
  new_row jsonb,
  actor_account_id uuid REFERENCES user_accounts(account_id) ON DELETE SET NULL,
  context jsonb NOT NULL DEFAULT '{}'::jsonb,
  occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_entity ON audit_log(entity_table, entity_id, occurred_at DESC);

CREATE OR REPLACE FUNCTION audit_row_change()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  actor uuid;
  entity uuid;
  ctx jsonb;
  row_json jsonb;
  pk_col text := TG_ARGV[0];
BEGIN
  BEGIN
    actor := NULLIF(current_setting('app.account_id', true), '')::uuid;
  EXCEPTION WHEN others THEN
    actor := NULL;
  END;
  BEGIN
    ctx := COALESCE(NULLIF(current_setting('app.audit_context', true), '')::jsonb, '{}'::jsonb);
  EXCEPTION WHEN others THEN
    ctx := '{}'::jsonb;
  END;

  IF TG_OP = 'DELETE' THEN
    row_json := to_jsonb(OLD);
  ELSE
    row_json := to_jsonb(NEW);
  END IF;

  IF pk_col IS NOT NULL AND pk_col <> '' THEN
    entity := NULLIF(row_json ->> pk_col, '')::uuid;
  END IF;

  IF TG_OP = 'DELETE' THEN
    INSERT INTO audit_log(entity_table, entity_id, action, old_row, actor_account_id, context)
    VALUES (TG_TABLE_NAME, entity, TG_OP, to_jsonb(OLD), actor, ctx);
    RETURN OLD;
  ELSIF TG_OP = 'UPDATE' THEN
    INSERT INTO audit_log(entity_table, entity_id, action, old_row, new_row, actor_account_id, context)
    VALUES (TG_TABLE_NAME, entity, TG_OP, to_jsonb(OLD), to_jsonb(NEW), actor, ctx);
    RETURN NEW;
  ELSE
    INSERT INTO audit_log(entity_table, entity_id, action, new_row, actor_account_id, context)
    VALUES (TG_TABLE_NAME, entity, TG_OP, to_jsonb(NEW), actor, ctx);
    RETURN NEW;
  END IF;
END $$;

-- Audit important mutable tables. Actor/context should be set by the application per transaction.
CREATE TRIGGER audit_requests AFTER INSERT OR UPDATE OR DELETE ON requests FOR EACH ROW EXECUTE FUNCTION audit_row_change('request_id');
CREATE TRIGGER audit_properties AFTER INSERT OR UPDATE OR DELETE ON properties FOR EACH ROW EXECUTE FUNCTION audit_row_change('property_id');
CREATE TRIGGER audit_property_offers AFTER INSERT OR UPDATE OR DELETE ON property_offers FOR EACH ROW EXECUTE FUNCTION audit_row_change('offer_id');
CREATE TRIGGER audit_consent AFTER INSERT OR UPDATE OR DELETE ON consent_grants FOR EACH ROW EXECUTE FUNCTION audit_row_change('consent_id');
CREATE TRIGGER audit_claims AFTER INSERT OR UPDATE OR DELETE ON claims FOR EACH ROW EXECUTE FUNCTION audit_row_change('claim_id');
CREATE TRIGGER audit_resolved_values AFTER INSERT OR UPDATE OR DELETE ON resolved_values FOR EACH ROW EXECUTE FUNCTION audit_row_change('resolved_value_id');
CREATE TRIGGER audit_match_reviews AFTER INSERT OR UPDATE OR DELETE ON match_reviews FOR EACH ROW EXECUTE FUNCTION audit_row_change('match_review_id');
CREATE TRIGGER audit_opportunities AFTER INSERT OR UPDATE OR DELETE ON opportunities FOR EACH ROW EXECUTE FUNCTION audit_row_change('opportunity_id');

-- -----------------------------------------------------------------------------
-- 14. V0.2 REMEDIATION INVARIANTS
-- -----------------------------------------------------------------------------

ALTER TABLE request_criteria
  ADD CONSTRAINT fk_request_criteria_definition FOREIGN KEY (criterion_code) REFERENCES criterion_definitions(code) ON DELETE RESTRICT;

ALTER TABLE property_attributes
  ADD CONSTRAINT fk_property_attribute_resolved_claim FOREIGN KEY (resolved_claim_id) REFERENCES claims(claim_id) ON DELETE SET NULL;

ALTER TABLE opportunities
  ADD CONSTRAINT fk_opportunity_permission_binding FOREIGN KEY (current_permission_binding_id) REFERENCES resource_consent_bindings(consent_binding_id) ON DELETE SET NULL;

ALTER TABLE resource_consent_bindings
  ADD CONSTRAINT fk_consent_binding_request FOREIGN KEY (request_id) REFERENCES requests(request_id) ON DELETE RESTRICT,
  ADD CONSTRAINT fk_consent_binding_property FOREIGN KEY (property_id) REFERENCES properties(property_id) ON DELETE RESTRICT,
  ADD CONSTRAINT fk_consent_binding_offer FOREIGN KEY (offer_id) REFERENCES property_offers(offer_id) ON DELETE RESTRICT,
  ADD CONSTRAINT fk_consent_binding_thread FOREIGN KEY (thread_id) REFERENCES communication_threads(thread_id) ON DELETE RESTRICT;

ALTER TABLE record_claim_events
  ADD CONSTRAINT fk_claim_event_request FOREIGN KEY (request_id) REFERENCES requests(request_id) ON DELETE RESTRICT,
  ADD CONSTRAINT fk_claim_event_property FOREIGN KEY (property_id) REFERENCES properties(property_id) ON DELETE RESTRICT;

CREATE OR REPLACE FUNCTION enforce_consent_binding()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  grant_party uuid;
  grant_scope consent_scope;
  grant_status consent_status;
  resource_party uuid;
BEGIN
  SELECT party_id, scope, status INTO grant_party, grant_scope, grant_status
  FROM consent_grants WHERE consent_id = NEW.consent_id;
  IF NOT FOUND OR grant_status <> 'GRANTED' THEN
    RAISE EXCEPTION 'Consent grant must exist and be GRANTED';
  END IF;
  IF grant_scope <> NEW.purpose THEN
    RAISE EXCEPTION 'Consent grant scope % does not match binding purpose %', grant_scope, NEW.purpose;
  END IF;

  IF NEW.request_id IS NOT NULL THEN
    SELECT party_id INTO resource_party FROM requests WHERE request_id = NEW.request_id;
    IF resource_party IS DISTINCT FROM grant_party THEN
      RAISE EXCEPTION 'Request consent party mismatch';
    END IF;
  ELSIF NEW.offer_id IS NOT NULL THEN
    SELECT party_id INTO resource_party FROM property_offers WHERE offer_id = NEW.offer_id;
    IF resource_party IS DISTINCT FROM grant_party THEN
      RAISE EXCEPTION 'Offer consent party mismatch';
    END IF;
  ELSIF NEW.property_id IS NOT NULL THEN
    IF NOT EXISTS (
      SELECT 1 FROM party_property_relations
      WHERE party_id = grant_party AND property_id = NEW.property_id
        AND (valid_to IS NULL OR valid_to > now())
    ) THEN
      RAISE EXCEPTION 'Property consent party has no active property relation';
    END IF;
  ELSIF NEW.thread_id IS NOT NULL THEN
    SELECT party_id INTO resource_party FROM communication_threads WHERE thread_id = NEW.thread_id;
    IF resource_party IS DISTINCT FROM grant_party THEN
      RAISE EXCEPTION 'Communication thread consent party mismatch';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_consent_binding BEFORE INSERT OR UPDATE ON resource_consent_bindings
FOR EACH ROW EXECUTE FUNCTION enforce_consent_binding();

CREATE OR REPLACE FUNCTION enforce_resolution_lineage()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  c claims%ROWTYPE;
BEGIN
  IF NEW.source_claim_id IS NULL THEN
    RETURN NEW;
  END IF;
  SELECT * INTO c FROM claims WHERE claim_id = NEW.source_claim_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'source_claim_id does not exist';
  END IF;
  IF c.attribute_code <> NEW.attribute_code THEN
    RAISE EXCEPTION 'Resolved value attribute must match source claim attribute';
  END IF;
  IF c.party_id IS DISTINCT FROM NEW.party_id
     OR c.request_id IS DISTINCT FROM NEW.request_id
     OR c.property_id IS DISTINCT FROM NEW.property_id
     OR c.offer_id IS DISTINCT FROM NEW.offer_id THEN
    RAISE EXCEPTION 'Resolved value subject must match source claim subject';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_resolution_lineage BEFORE INSERT OR UPDATE ON resolved_values
FOR EACH ROW EXECUTE FUNCTION enforce_resolution_lineage();

CREATE OR REPLACE FUNCTION apply_verification_event()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.outcome = 'CONFIRMED' THEN
    UPDATE claims
      SET effective_verification_level = GREATEST(effective_verification_level, NEW.level)
      WHERE claim_id = NEW.claim_id;
  ELSIF NEW.outcome = 'CONFLICT_FOUND' THEN
    UPDATE claims SET status = 'CONFLICTING' WHERE claim_id = NEW.claim_id;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_apply_verification_event AFTER INSERT ON verification_events
FOR EACH ROW EXECUTE FUNCTION apply_verification_event();

CREATE OR REPLACE FUNCTION enforce_property_attribute_claim()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  claim_property uuid;
  claim_code text;
  def_code text;
BEGIN
  IF NEW.resolved_claim_id IS NULL THEN RETURN NEW; END IF;
  SELECT property_id, attribute_code INTO claim_property, claim_code FROM claims WHERE claim_id = NEW.resolved_claim_id;
  SELECT code INTO def_code FROM attribute_definitions WHERE attribute_definition_id = NEW.attribute_definition_id;
  IF claim_property IS DISTINCT FROM NEW.property_id OR claim_code IS DISTINCT FROM def_code THEN
    RAISE EXCEPTION 'property_attributes.resolved_claim_id must reference same property and attribute';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_property_attribute_claim BEFORE INSERT OR UPDATE ON property_attributes
FOR EACH ROW EXECUTE FUNCTION enforce_property_attribute_claim();

CREATE OR REPLACE FUNCTION enforce_match_commercial_context()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  r requests%ROWTYPE;
  p properties%ROWTYPE;
  o property_offers%ROWTYPE;
  pol matching_policies%ROWTYPE;
BEGIN
  SELECT * INTO r FROM requests WHERE request_id = NEW.request_id;
  SELECT * INTO p FROM properties WHERE property_id = NEW.property_id;
  SELECT * INTO pol FROM matching_policies WHERE matching_policy_id = NEW.matching_policy_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'Matching policy missing'; END IF;
  IF pol.version <> NEW.matching_policy_version THEN
    RAISE EXCEPTION 'matching_policy_version must match matching_policy_id';
  END IF;
  IF EXISTS (SELECT 1 FROM property_identity_aliases WHERE alias_property_id = NEW.property_id) THEN
    RAISE EXCEPTION 'Matches must target canonical properties, not identity aliases';
  END IF;

  IF NEW.evaluated_offer_id IS NOT NULL THEN
    SELECT * INTO o FROM property_offers WHERE offer_id = NEW.evaluated_offer_id;
    IF NOT FOUND OR o.property_id <> NEW.property_id THEN
      RAISE EXCEPTION 'Evaluated offer must belong to matched property';
    END IF;
    IF (r.transaction_intent = 'BUY' AND o.transaction_type <> 'SALE')
       OR (r.transaction_intent = 'RENT' AND o.transaction_type <> 'RENT') THEN
      RAISE EXCEPTION 'Request transaction intent does not match evaluated offer';
    END IF;
    IF NEW.offer_version IS DISTINCT FROM o.version THEN
      RAISE EXCEPTION 'offer_version must snapshot evaluated offer version';
    END IF;
  ELSIF p.supply_mode <> 'POTENTIAL' THEN
    RAISE EXCEPTION 'Non-potential property match requires evaluated_offer_id';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_match_commercial_context BEFORE INSERT ON match_candidates
FOR EACH ROW EXECUTE FUNCTION enforce_match_commercial_context();

CREATE OR REPLACE FUNCTION enforce_opportunity_offer_context()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  o property_offers%ROWTYPE;
  r requests%ROWTYPE;
BEGIN
  IF NEW.current_offer_id IS NULL THEN RETURN NEW; END IF;
  SELECT * INTO o FROM property_offers WHERE offer_id = NEW.current_offer_id;
  SELECT * INTO r FROM requests WHERE request_id = NEW.request_id;
  IF NOT FOUND OR o.property_id <> NEW.property_id THEN
    RAISE EXCEPTION 'Opportunity current offer must belong to opportunity property';
  END IF;
  IF (r.transaction_intent = 'BUY' AND o.transaction_type <> 'SALE')
     OR (r.transaction_intent = 'RENT' AND o.transaction_type <> 'RENT') THEN
    RAISE EXCEPTION 'Opportunity current offer transaction type incompatible with request';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_opportunity_offer_context BEFORE INSERT OR UPDATE OF current_offer_id ON opportunities
FOR EACH ROW EXECUTE FUNCTION enforce_opportunity_offer_context();

CREATE OR REPLACE FUNCTION enforce_identity_alias()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  c property_identity_candidates%ROWTYPE;
BEGIN
  IF EXISTS (SELECT 1 FROM property_identity_aliases WHERE alias_property_id = NEW.canonical_property_id) THEN
    RAISE EXCEPTION 'Canonical property cannot itself be an alias';
  END IF;
  IF EXISTS (SELECT 1 FROM property_identity_aliases WHERE canonical_property_id = NEW.alias_property_id) THEN
    RAISE EXCEPTION 'A property already acting as canonical cannot later become an alias; consolidate explicitly';
  END IF;
  SELECT * INTO c FROM property_identity_candidates WHERE identity_candidate_id = NEW.source_identity_candidate_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'Identity candidate missing'; END IF;
  IF NOT ((c.property_a_id = NEW.alias_property_id AND c.property_b_id = NEW.canonical_property_id)
       OR (c.property_b_id = NEW.alias_property_id AND c.property_a_id = NEW.canonical_property_id)) THEN
    RAISE EXCEPTION 'Alias/canonical pair must match identity candidate pair';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_identity_alias BEFORE INSERT OR UPDATE ON property_identity_aliases
FOR EACH ROW EXECUTE FUNCTION enforce_identity_alias();

CREATE OR REPLACE FUNCTION enforce_identity_same_requires_alias()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.review_status = 'CONFIRMED_SAME' AND OLD.review_status IS DISTINCT FROM 'CONFIRMED_SAME' THEN
    IF NOT EXISTS (SELECT 1 FROM property_identity_aliases WHERE source_identity_candidate_id = NEW.identity_candidate_id) THEN
      RAISE EXCEPTION 'CONFIRMED_SAME requires a canonical alias mapping in the same transaction';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_identity_same_requires_alias BEFORE UPDATE ON property_identity_candidates
FOR EACH ROW EXECUTE FUNCTION enforce_identity_same_requires_alias();

CREATE OR REPLACE FUNCTION touch_request_from_criterion()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE rid uuid;
BEGIN
  IF TG_OP = 'DELETE' THEN rid := OLD.request_id; ELSE rid := NEW.request_id; END IF;
  UPDATE requests SET updated_at = now() WHERE request_id = rid;
  IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END $$;
CREATE TRIGGER trg_request_criterion_touch AFTER INSERT OR UPDATE OR DELETE ON request_criteria
FOR EACH ROW EXECUTE FUNCTION touch_request_from_criterion();

CREATE OR REPLACE FUNCTION touch_subject_from_resolution()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE rv resolved_values%ROWTYPE;
BEGIN
  IF TG_OP = 'DELETE' THEN rv := OLD; ELSE rv := NEW; END IF;
  IF rv.request_id IS NOT NULL THEN UPDATE requests SET updated_at=now() WHERE request_id=rv.request_id; END IF;
  IF rv.property_id IS NOT NULL THEN UPDATE properties SET updated_at=now() WHERE property_id=rv.property_id; END IF;
  IF rv.offer_id IS NOT NULL THEN UPDATE property_offers SET updated_at=now() WHERE offer_id=rv.offer_id; END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END $$;
CREATE TRIGGER trg_resolution_touch AFTER INSERT OR UPDATE OR DELETE ON resolved_values
FOR EACH ROW EXECUTE FUNCTION touch_subject_from_resolution();

CREATE OR REPLACE FUNCTION prevent_immutable_history_change()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Historical TURAB record is immutable; append a new decision/event instead';
END $$;
CREATE TRIGGER prevent_match_candidate_update BEFORE UPDATE OR DELETE ON match_candidates FOR EACH ROW EXECUTE FUNCTION prevent_immutable_history_change();
CREATE TRIGGER prevent_match_review_update BEFORE UPDATE OR DELETE ON match_reviews FOR EACH ROW EXECUTE FUNCTION prevent_immutable_history_change();

CREATE OR REPLACE FUNCTION prevent_core_delete()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Hard delete prohibited for core TURAB records; close/supersede instead';
END $$;
CREATE TRIGGER prevent_delete_requests BEFORE DELETE ON requests FOR EACH ROW EXECUTE FUNCTION prevent_core_delete();
CREATE TRIGGER prevent_delete_properties BEFORE DELETE ON properties FOR EACH ROW EXECUTE FUNCTION prevent_core_delete();
CREATE TRIGGER prevent_delete_offers BEFORE DELETE ON property_offers FOR EACH ROW EXECUTE FUNCTION prevent_core_delete();
CREATE TRIGGER prevent_delete_claims BEFORE DELETE ON claims FOR EACH ROW EXECUTE FUNCTION prevent_core_delete();
CREATE TRIGGER prevent_delete_resolutions BEFORE DELETE ON resolved_values FOR EACH ROW EXECUTE FUNCTION prevent_core_delete();
CREATE TRIGGER prevent_delete_opportunities BEFORE DELETE ON opportunities FOR EACH ROW EXECUTE FUNCTION prevent_core_delete();

CREATE VIEW latest_match_reviews AS
SELECT DISTINCT ON (match_id) *
FROM match_reviews
ORDER BY match_id, reviewed_at DESC, match_review_id DESC;

-- -----------------------------------------------------------------------------
-- 15. LATE FKs / CROSS-SECTION CONSTRAINTS
-- v0.2.1: single authoritative declarations retained here; earlier duplicates removed.
-- -----------------------------------------------------------------------------

ALTER TABLE external_leads
  ADD CONSTRAINT fk_external_lead_request FOREIGN KEY (converted_request_id) REFERENCES requests(request_id) ON DELETE SET NULL,
  ADD CONSTRAINT fk_external_lead_property FOREIGN KEY (converted_property_id) REFERENCES properties(property_id) ON DELETE SET NULL,
  ADD CONSTRAINT ck_external_lead_conversion_kind CHECK (
    (lead_kind = 'REQUEST' AND converted_property_id IS NULL) OR
    (lead_kind = 'PROPERTY' AND converted_request_id IS NULL)
  ),
  ADD CONSTRAINT ck_external_lead_converted_target CHECK (
    status <> 'CONVERTED' OR
    (lead_kind = 'REQUEST' AND converted_request_id IS NOT NULL) OR
    (lead_kind = 'PROPERTY' AND converted_property_id IS NOT NULL)
  );

ALTER TABLE consent_grants
  ADD CONSTRAINT fk_consent_evidence_observation FOREIGN KEY (evidence_observation_id) REFERENCES observations(observation_id) ON DELETE SET NULL;

-- -----------------------------------------------------------------------------
-- 16. COMMENTS / GUARANTEES
-- -----------------------------------------------------------------------------

COMMENT ON TABLE properties IS 'Physical real-estate identity. MUST NOT be treated as a listing/post.';
COMMENT ON TABLE property_offers IS 'Commercial offer by a party for a physical PROPERTY. Multiple offers may coexist.';
COMMENT ON TABLE match_candidates IS 'Machine/rule-generated candidate only. MUST NOT be shown as an Opportunity before human approval and all gates pass.';
COMMENT ON TABLE opportunities IS 'Human-approved meaningful match. Creation is guarded by database trigger.';
COMMENT ON COLUMN property_offers.seller_expectation_dzd IS 'Internal/confidential negotiating signal. MUST NOT be exposed unless sharing policy explicitly permits.';
COMMENT ON COLUMN match_candidates.soft_score IS 'Internal ordering aid only. MUST NOT be presented as truth or override hard gates.';
COMMENT ON TABLE resolved_values IS 'Operational current resolution separate from source claims; keeps lineage to source_claim_id.';

CREATE INDEX idx_match_reviews_latest ON match_reviews(match_id, reviewed_at DESC);
CREATE INDEX idx_match_offer ON match_candidates(evaluated_offer_id);
CREATE INDEX idx_consent_binding_request ON resource_consent_bindings(request_id) WHERE request_id IS NOT NULL;
CREATE INDEX idx_consent_binding_property ON resource_consent_bindings(property_id) WHERE property_id IS NOT NULL;
CREATE INDEX idx_consent_binding_offer ON resource_consent_bindings(offer_id) WHERE offer_id IS NOT NULL;
CREATE UNIQUE INDEX ux_offer_primary_source ON property_offer_sources(offer_id) WHERE is_primary;

COMMENT ON TABLE resource_consent_bindings IS 'Resource-scoped proof that a consent grant authorizes a specific purpose for a specific TURAB resource.';
COMMENT ON TABLE property_identity_aliases IS 'Non-destructive canonicalization: alias property record points to the canonical physical PROPERTY identity.';
COMMENT ON COLUMN match_candidates.input_hash IS 'Hash of canonical immutable matching inputs; historical replay must not depend on current mutable state.';
COMMENT ON COLUMN claims.effective_verification_level IS 'Derived operational verification level. API clients MUST NOT set this above DECLARED directly.';
COMMENT ON TABLE idempotency_records IS 'Server-side replay protection for mutating API commands.';
COMMENT ON TABLE webhook_events IS 'Provider event replay protection and processing audit, including WhatsApp webhooks.';

COMMIT;
