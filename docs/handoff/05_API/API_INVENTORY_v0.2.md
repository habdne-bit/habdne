# TURAB API Inventory v0.2

| Tag | Method | Path | operationId | Roles | Summary |
|---|---|---|---|---|---|
| Audit | GET | /audit | getAudit | ADMIN,REVIEWER | Query audit history |
| Auth | POST | /auth/otp/start | postAuthOtpStart |  | Start OTP challenge |
| Auth | POST | /auth/otp/verify | postAuthOtpVerify |  | Verify OTP for phone control or account login; phone verification does not require or create an account unless purpose=LOGIN and account flow authorizes it. |
| BackOffice | GET | /backoffice/queues/external-leads | getBackofficeQueuesExternalLeads | ADMIN,OPERATOR,REVIEWER | External leads requiring action |
| BackOffice | GET | /backoffice/queues/matches | getBackofficeQueuesMatches | ADMIN,OPERATOR,REVIEWER | Candidate matches pending human decision |
| BackOffice | GET | /backoffice/queues/opportunities | getBackofficeQueuesOpportunities | ADMIN,OPERATOR,REVIEWER | Opportunities needing follow-up/revalidation |
| BackOffice | GET | /backoffice/queues/properties | getBackofficeQueuesProperties | ADMIN,OPERATOR,REVIEWER | Properties requiring review/reconfirmation |
| BackOffice | GET | /backoffice/queues/requests | getBackofficeQueuesRequests | ADMIN,OPERATOR,REVIEWER | Requests requiring qualification/reconfirmation |
| Communication | GET | /parties/{party_id}/timeline | getPartiesPartyIdTimeline | ADMIN,OPERATOR,REVIEWER | Get operational communication/interaction timeline |
| Communication | POST | /communication/threads | postCommunicationThreads | ADMIN,OPERATOR | Create communication thread linked to domain context |
| Communication | POST | /communication/threads/{thread_id}/messages | postCommunicationThreadsThreadIdMessages | ADMIN,OPERATOR | Archive/send message reference in official channel |
| Communication | POST | /webhooks/whatsapp | postWebhooksWhatsapp |  | Receive WhatsApp Business webhook |
| Consent | POST | /consents/bindings | postConsentsBindings | ADMIN,OPERATOR | Bind a granted consent to a resource and purpose |
| Consent | POST | /consents/{consent_id}/revoke | postConsentsConsentIdRevoke | ADMIN,OPERATOR,CUSTOMER | Revoke consent grant |
| External Leads | POST | /external-leads | postExternalLeads | ADMIN,OPERATOR | Capture external discovery lead; does not activate inventory |
| External Leads | POST | /external-leads/{lead_id}/convert | postExternalLeadsLeadIdConvert | ADMIN,OPERATOR | Convert consented external lead into assisted draft |
| Identity | GET | /identity/candidates | getIdentityCandidates | ADMIN,OPERATOR,REVIEWER | List property identity candidates |
| Identity | POST | /identity/candidates/generate | postIdentityCandidatesGenerate | ADMIN,OPERATOR | Generate explainable identity candidates; never merge automatically |
| Identity | POST | /identity/candidates/{candidate_id}/review | postIdentityCandidatesCandidateIdReview | ADMIN,REVIEWER | Human identity decision |
| Master Data | GET | /locations | getLocations |  | Search canonical locations |
| Master Data | GET | /reason-codes | getReasonCodes |  | List active reason codes |
| MasterData | GET | /master/criterion-definitions | getMasterCriterionDefinitions |  | List active criterion definitions |
| Matching | GET | /matches/{match_id} | getMatchesMatchId | ADMIN,OPERATOR,REVIEWER | Get explainable match candidate |
| Matching | GET | /requests/{request_id}/diagnostic | getRequestsRequestIdDiagnostic | ADMIN,OPERATOR,REVIEWER | Get latest Match Diagnostic |
| Matching | POST | /matches/{match_id}/review | postMatchesMatchIdReview | ADMIN,REVIEWER | Human match decision; APPROVED may create Opportunity only if all gates pass |
| Matching | POST | /requests/{request_id}/matching/run | postRequestsRequestIdMatchingRun | ADMIN,OPERATOR,REVIEWER | Run matching for request against current resolved property state |
| Me | GET | /me/opportunities/{opportunity_id} | getMeOpportunitiesOpportunityId | CUSTOMER | Get caller opportunity with sharing-scope redaction |
| Me | GET | /me/party | getMeParty | CUSTOMER | Get caller party projection |
| Me | GET | /me/properties/{property_id} | getMePropertiesPropertyId | CUSTOMER | Get caller-managed property |
| Me | GET | /me/requests/{request_id} | getMeRequestsRequestId | CUSTOMER | Get caller-owned request |
| Offers | POST | /offers/{offer_id}/reconfirm | postOffersOfferIdReconfirm | ADMIN,OPERATOR,CUSTOMER | Reconfirm commercial terms/freshness |
| Offers | POST | /offers/{offer_id}/state | postOffersOfferIdState | ADMIN,OPERATOR,CUSTOMER | Transition offer state |
| Opportunities | GET | /opportunities/{opportunity_id} | getOpportunitiesOpportunityId | ADMIN,OPERATOR,REVIEWER | Get opportunity with field-level redaction by sharing scope |
| Opportunities | POST | /opportunities/{opportunity_id}/close | postOpportunitiesOpportunityIdClose | ADMIN,OPERATOR,REVIEWER | Close opportunity with outcome reason |
| Opportunities | POST | /opportunities/{opportunity_id}/responses | postOpportunitiesOpportunityIdResponses | CUSTOMER,ADMIN,OPERATOR | Customer/party response to opportunity |
| Opportunities | POST | /opportunities/{opportunity_id}/revalidate | postOpportunitiesOpportunityIdRevalidate | ADMIN,OPERATOR,REVIEWER | Revalidate freshness/permission before further sharing |
| Opportunities | POST | /opportunities/{opportunity_id}/share | postOpportunitiesOpportunityIdShare | ADMIN,OPERATOR | Mark/share opportunity through allowed scope |
| Parties | GET | /parties/{party_id} | getPartiesPartyId | ADMIN,OPERATOR,REVIEWER | Get party |
| Parties | PATCH | /parties/{party_id} | patchPartiesPartyId | ADMIN,OPERATOR,CUSTOMER | Update party |
| Parties | POST | /parties | postParties | ADMIN,OPERATOR,CUSTOMER | Create a market PARTY without requiring an account |
| Parties | POST | /parties/{party_id}/consents | postPartiesPartyIdConsents | ADMIN,OPERATOR,CUSTOMER | Record granular consent |
| Parties | POST | /parties/{party_id}/contact-points/phone | attachPartyPhoneContactPoint | ADMIN,OPERATOR,CUSTOMER | Attach phone contact point to party |
| Parties | POST | /records/claim | postRecordsClaim | CUSTOMER,ADMIN,OPERATOR | Claim an assisted record after verified control |
| Properties | GET | /properties/{property_id} | getPropertiesPropertyId | ADMIN,OPERATOR,REVIEWER | Get property operational state |
| Properties | PATCH | /offers/{offer_id} | patchOffersOfferId | ADMIN,OPERATOR,CUSTOMER | Update offer; do not overwrite other parties offers |
| Properties | PATCH | /properties/{property_id} | patchPropertiesPropertyId | ADMIN,OPERATOR,CUSTOMER | Update property operational state |
| Properties | POST | /offers/{offer_id}/sources | postOffersOfferIdSources | ADMIN,OPERATOR | Link source to offer |
| Properties | POST | /properties | postProperties | ADMIN,OPERATOR,CUSTOMER | Create physical property identity |
| Properties | POST | /properties/{property_id}/offers | postPropertiesPropertyIdOffers | ADMIN,OPERATOR,CUSTOMER | Create independent commercial offer for property |
| Properties | POST | /properties/{property_id}/reconfirm | postPropertiesPropertyIdReconfirm | ADMIN,OPERATOR,CUSTOMER | Reconfirm property availability/freshness |
| Public | GET | /public/properties | getPublicProperties |  | Browse PUBLIC properties only |
| Public | POST | /interests | postInterests | CUSTOMER,ADMIN,OPERATOR | Record direct interest without creating a REQUEST |
| Requests | GET | /requests/{request_id} | getRequestsRequestId | ADMIN,OPERATOR,REVIEWER | Get request |
| Requests | PATCH | /requests/{request_id} | patchRequestsRequestId | ADMIN,OPERATOR,CUSTOMER | Update request fields without silently relaxing criteria |
| Requests | POST | /requests | postRequests | ADMIN,OPERATOR,CUSTOMER | Create request |
| Requests | POST | /requests/{request_id}/criteria | postRequestsRequestIdCriteria | ADMIN,OPERATOR,CUSTOMER | Add request criterion |
| Requests | POST | /requests/{request_id}/reconfirm | postRequestsRequestIdReconfirm | ADMIN,OPERATOR,CUSTOMER | Reconfirm request freshness |
| Requests | POST | /requests/{request_id}/state | postRequestsRequestIdState | ADMIN,OPERATOR,CUSTOMER | Transition request lifecycle |
| Tasks | GET | /tasks | getTasks | ADMIN,OPERATOR,REVIEWER | List operational tasks |
| Tasks | POST | /tasks/{task_id}/complete | postTasksTaskIdComplete | ADMIN,OPERATOR,REVIEWER | Complete focused information/reconfirmation task |
| Truth | POST | /claims | postClaims | ADMIN,OPERATOR | Record atomic claim; does not automatically become verified truth |
| Truth | POST | /claims/{claim_id}/verification-events | postClaimsClaimIdVerificationEvents | ADMIN,OPERATOR,REVIEWER | Record an explicit verification action |
| Truth | POST | /observations | postObservations | ADMIN,OPERATOR | Record observation with source/time |
| Truth | POST | /resolutions | postResolutions | ADMIN,OPERATOR,REVIEWER | Resolve current operational value from claim/evidence |