# TURAB — API Inventory (generated)

**Do not edit.** Regenerate with `db/gate/generate_api_inventory.py`.

- Source: `docs/api/openapi_effective_v0.2.3.yaml`
- Source SHA-256: `0705789820848ffe2e70897b83b97e569beefa0c931e2a5524ecbe061c4431af`
- Operations: 64 · role-annotated: 57 · unauthenticated: 6

## Unauthenticated operations

This is a closed list. Any addition is a security change, not a routine one
(RFC-001 R10.4).

| operationId | Method | Path |
|---|---|---|
| `getLocations` | GET | `/locations` |
| `getMasterCriterionDefinitions` | GET | `/master/criterion-definitions` |
| `getPublicProperties` | GET | `/public/properties` |
| `postAuthOtpStart` | POST | `/auth/otp/start` |
| `postAuthOtpVerify` | POST | `/auth/otp/verify` |
| `postWebhooksWhatsapp` | POST | `/webhooks/whatsapp` |

## Authenticated operations without declared roles

Each needs an explicit policy decision before implementation.

| operationId | Method | Path |
|---|---|---|
| `getReasonCodes` | GET | `/reason-codes` |

## All operations

| operationId | Method | Path | Roles | Object authorization |
|---|---|---|---|---|
| `attachPartyPhoneContactPoint` | POST | `/parties/{party_id}/contact-points/phone` | `ADMIN`, `OPERATOR`, `CUSTOMER` | Customer may act only on resources owned/managed by authenticated party; service MUST enforce object-level authorization in addition to role. |
| `getAudit` | GET | `/audit` | `ADMIN`, `REVIEWER` | — |
| `getBackofficeQueuesExternalLeads` | GET | `/backoffice/queues/external-leads` | `ADMIN`, `OPERATOR`, `REVIEWER` | Internal queue. Filters and sorting must be deterministic and role-aware. |
| `getBackofficeQueuesMatches` | GET | `/backoffice/queues/matches` | `ADMIN`, `OPERATOR`, `REVIEWER` | Internal queue. Filters and sorting must be deterministic and role-aware. |
| `getBackofficeQueuesOpportunities` | GET | `/backoffice/queues/opportunities` | `ADMIN`, `OPERATOR`, `REVIEWER` | Internal queue. Filters and sorting must be deterministic and role-aware. |
| `getBackofficeQueuesProperties` | GET | `/backoffice/queues/properties` | `ADMIN`, `OPERATOR`, `REVIEWER` | Internal queue. Filters and sorting must be deterministic and role-aware. |
| `getBackofficeQueuesRequests` | GET | `/backoffice/queues/requests` | `ADMIN`, `OPERATOR`, `REVIEWER` | Internal queue. Filters and sorting must be deterministic and role-aware. |
| `getIdentityCandidates` | GET | `/identity/candidates` | `ADMIN`, `OPERATOR`, `REVIEWER` | — |
| `getLocations` | GET | `/locations` | — | — |
| `getMasterCriterionDefinitions` | GET | `/master/criterion-definitions` | — | — |
| `getMatchesMatchId` | GET | `/matches/{match_id}` | `ADMIN`, `OPERATOR`, `REVIEWER` | — |
| `getMeOpportunitiesOpportunityId` | GET | `/me/opportunities/{opportunity_id}` | `CUSTOMER` | Opportunity request MUST belong to caller. Response renderer MUST enforce sharing_scope and never expose seller_expectation or internal claims. |
| `getMeParty` | GET | `/me/party` | `CUSTOMER` | Bound to authenticated account.party_id; no arbitrary party id accepted. |
| `getMePropertiesPropertyId` | GET | `/me/properties/{property_id}` | `CUSTOMER` | Caller must manage/own/claim this property; otherwise 404/403. Public browsing uses /public/properties. |
| `getMeRequestsRequestId` | GET | `/me/requests/{request_id}` | `CUSTOMER` | request.party_id MUST equal authenticated account.party_id or explicit delegated authorization. |
| `getOpportunitiesOpportunityId` | GET | `/opportunities/{opportunity_id}` | `ADMIN`, `OPERATOR`, `REVIEWER` | Internal resource access; role check plus business-purpose authorization. Customer access uses /me/* endpoints. |
| `getPartiesPartyId` | GET | `/parties/{party_id}` | `ADMIN`, `OPERATOR`, `REVIEWER` | Internal resource access; role check plus business-purpose authorization. Customer access uses /me/* endpoints. |
| `getPartiesPartyIdTimeline` | GET | `/parties/{party_id}/timeline` | `ADMIN`, `OPERATOR`, `REVIEWER` | — |
| `getPropertiesPropertyId` | GET | `/properties/{property_id}` | `ADMIN`, `OPERATOR`, `REVIEWER` | Internal resource access; role check plus business-purpose authorization. Customer access uses /me/* endpoints. |
| `getPublicProperties` | GET | `/public/properties` | — | — |
| `getReasonCodes` | GET | `/reason-codes` | — | — |
| `getRequestsRequestId` | GET | `/requests/{request_id}` | `ADMIN`, `OPERATOR`, `REVIEWER` | Internal resource access; role check plus business-purpose authorization. Customer access uses /me/* endpoints. |
| `getRequestsRequestIdDiagnostic` | GET | `/requests/{request_id}/diagnostic` | `ADMIN`, `OPERATOR`, `REVIEWER` | — |
| `getTasks` | GET | `/tasks` | `ADMIN`, `OPERATOR`, `REVIEWER` | — |
| `patchOffersOfferId` | PATCH | `/offers/{offer_id}` | `ADMIN`, `OPERATOR`, `CUSTOMER` | Customer may act only on resources owned/managed by authenticated party; service MUST enforce object-level authorization in addition to role. |
| `patchPartiesPartyId` | PATCH | `/parties/{party_id}` | `ADMIN`, `OPERATOR`, `CUSTOMER` | Customer may act only on resources owned/managed by authenticated party; service MUST enforce object-level authorization in addition to role. |
| `patchPropertiesPropertyId` | PATCH | `/properties/{property_id}` | `ADMIN`, `OPERATOR`, `CUSTOMER` | Customer may act only on resources owned/managed by authenticated party; service MUST enforce object-level authorization in addition to role. |
| `patchRequestsRequestId` | PATCH | `/requests/{request_id}` | `ADMIN`, `OPERATOR`, `CUSTOMER` | Customer may act only on resources owned/managed by authenticated party; service MUST enforce object-level authorization in addition to role. |
| `postAuthOtpStart` | POST | `/auth/otp/start` | — | — |
| `postAuthOtpVerify` | POST | `/auth/otp/verify` | — | — |
| `postClaims` | POST | `/claims` | `ADMIN`, `OPERATOR` | — |
| `postClaimsClaimIdVerificationEvents` | POST | `/claims/{claim_id}/verification-events` | `ADMIN`, `OPERATOR`, `REVIEWER` | — |
| `postCommunicationThreads` | POST | `/communication/threads` | `ADMIN`, `OPERATOR` | — |
| `postCommunicationThreadsThreadIdMessages` | POST | `/communication/threads/{thread_id}/messages` | `ADMIN`, `OPERATOR` | — |
| `postConsentsBindings` | POST | `/consents/bindings` | `ADMIN`, `OPERATOR` | Server validates consent party, scope, status and resource-party consistency. |
| `postConsentsConsentIdRevoke` | POST | `/consents/{consent_id}/revoke` | `ADMIN`, `OPERATOR`, `CUSTOMER` | CUSTOMER may revoke only consent belonging to own party; staff require operational authority. |
| `postExternalLeads` | POST | `/external-leads` | `ADMIN`, `OPERATOR` | — |
| `postExternalLeadsLeadIdConvert` | POST | `/external-leads/{lead_id}/convert` | `ADMIN`, `OPERATOR` | — |
| `postIdentityCandidatesCandidateIdReview` | POST | `/identity/candidates/{candidate_id}/review` | `ADMIN`, `REVIEWER` | — |
| `postIdentityCandidatesGenerate` | POST | `/identity/candidates/generate` | `ADMIN`, `OPERATOR` | — |
| `postInterests` | POST | `/interests` | `CUSTOMER`, `ADMIN`, `OPERATOR` | Customer may act only on resources owned/managed by authenticated party; service MUST enforce object-level authorization in addition to role. |
| `postMatchesMatchIdReview` | POST | `/matches/{match_id}/review` | `ADMIN`, `REVIEWER` | — |
| `postObservations` | POST | `/observations` | `ADMIN`, `OPERATOR` | — |
| `postOffersOfferIdReconfirm` | POST | `/offers/{offer_id}/reconfirm` | `ADMIN`, `OPERATOR`, `CUSTOMER` | Customer may reconfirm only own offer; server records provenance and updates offer freshness transactionally. |
| `postOffersOfferIdSources` | POST | `/offers/{offer_id}/sources` | `ADMIN`, `OPERATOR` | — |
| `postOffersOfferIdState` | POST | `/offers/{offer_id}/state` | `ADMIN`, `OPERATOR`, `CUSTOMER` | Customer may mutate only own offer. State machine validation required. |
| `postOpportunitiesOpportunityIdClose` | POST | `/opportunities/{opportunity_id}/close` | `ADMIN`, `OPERATOR`, `REVIEWER` | — |
| `postOpportunitiesOpportunityIdResponses` | POST | `/opportunities/{opportunity_id}/responses` | `CUSTOMER`, `ADMIN`, `OPERATOR` | Customer may act only on resources owned/managed by authenticated party; service MUST enforce object-level authorization in addition to role. |
| `postOpportunitiesOpportunityIdRevalidate` | POST | `/opportunities/{opportunity_id}/revalidate` | `ADMIN`, `OPERATOR`, `REVIEWER` | — |
| `postOpportunitiesOpportunityIdShare` | POST | `/opportunities/{opportunity_id}/share` | `ADMIN`, `OPERATOR` | — |
| `postParties` | POST | `/parties` | `ADMIN`, `OPERATOR` | Customer may act only on resources owned/managed by authenticated party; service MUST enforce object-level authorization in addition to role. |
| `postPartiesPartyIdConsents` | POST | `/parties/{party_id}/consents` | `ADMIN`, `OPERATOR`, `CUSTOMER` | Customer may act only on resources owned/managed by authenticated party; service MUST enforce object-level authorization in addition to role. |
| `postProperties` | POST | `/properties` | `ADMIN`, `OPERATOR`, `CUSTOMER` | Customer may act only on resources owned/managed by authenticated party; service MUST enforce object-level authorization in addition to role. |
| `postPropertiesPropertyIdOffers` | POST | `/properties/{property_id}/offers` | `ADMIN`, `OPERATOR`, `CUSTOMER` | Customer may act only on resources owned/managed by authenticated party; service MUST enforce object-level authorization in addition to role. |
| `postPropertiesPropertyIdReconfirm` | POST | `/properties/{property_id}/reconfirm` | `ADMIN`, `OPERATOR`, `CUSTOMER` | Customer may act only on resources owned/managed by authenticated party; service MUST enforce object-level authorization in addition to role. |
| `postRecordsClaim` | POST | `/records/claim` | `CUSTOMER`, `ADMIN`, `OPERATOR` | For customer, verified contact point and resource party relationship are mandatory. Command changes ASSISTED/UNCLAIMED to SHARED_MANAGEMENT/CLAIMED transactionally; no duplicate resource is created. |
| `postRequests` | POST | `/requests` | `ADMIN`, `OPERATOR`, `CUSTOMER` | Customer may act only on resources owned/managed by authenticated party; service MUST enforce object-level authorization in addition to role. |
| `postRequestsRequestIdCriteria` | POST | `/requests/{request_id}/criteria` | `ADMIN`, `OPERATOR`, `CUSTOMER` | Customer may act only on resources owned/managed by authenticated party; service MUST enforce object-level authorization in addition to role. |
| `postRequestsRequestIdMatchingRun` | POST | `/requests/{request_id}/matching/run` | `ADMIN`, `OPERATOR`, `REVIEWER` | — |
| `postRequestsRequestIdReconfirm` | POST | `/requests/{request_id}/reconfirm` | `ADMIN`, `OPERATOR`, `CUSTOMER` | Customer may act only on resources owned/managed by authenticated party; service MUST enforce object-level authorization in addition to role. |
| `postRequestsRequestIdState` | POST | `/requests/{request_id}/state` | `ADMIN`, `OPERATOR`, `CUSTOMER` | Customer may act only on resources owned/managed by authenticated party; service MUST enforce object-level authorization in addition to role. |
| `postResolutions` | POST | `/resolutions` | `ADMIN`, `OPERATOR`, `REVIEWER` | — |
| `postTasksTaskIdComplete` | POST | `/tasks/{task_id}/complete` | `ADMIN`, `OPERATOR`, `REVIEWER` | — |
| `postWebhooksWhatsapp` | POST | `/webhooks/whatsapp` | — | — |
