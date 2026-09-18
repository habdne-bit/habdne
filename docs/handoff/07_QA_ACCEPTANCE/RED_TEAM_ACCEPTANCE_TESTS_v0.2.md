# TURAB — Red-Team Acceptance Tests v0.2

These scenarios are implementation gates. They are designed to break the system at the exact points where the v0.1 technical pack was vulnerable.

## A. Party / Contact / Account

### A01 — shared family phone
Given the same normalized phone number is linked to Party A and Party B, when Party B is created, the system MUST NOT merge the parties. The contact point may be shared. Account activation remains explicit.

### A02 — phone verification without account
Given an unverified phone contact point, when OTP purpose is `VERIFY_PHONE_CONTROL` and succeeds, then control status becomes verified and no account is created automatically.

### A03 — assisted party without login
An operator can create PARTY + assisted property/request after consent while `USER_ACCOUNT` remains absent.

## B. Consent / Permission

### B01 — wrong-party consent binding
Consent from Party A cannot bind to Request owned by Party B.

### B02 — scope mismatch
`COMMUNICATION_ARCHIVE` consent cannot be bound as `PUBLIC_LISTING_ALLOWED`.

### B03 — revoked consent after match approval
If the permission used by an approved candidate is revoked before share, `share opportunity` must fail/revalidate. Historical match snapshot remains unchanged.

### B04 — private matching only
A property with `PRIVATE_MATCHING_ONLY` may participate in internal matching but must not appear in public browse.

## C. Request

### C01 — buy/rent isolation
BUY request can evaluate SALE offers only. RENT request can evaluate RENT offers only.

### C02 — interest is not request
Creating INTEREST does not create REQUEST. Conversion requires explicit user action and results in a new or linked Request command.

### C03 — required unknown
A required criterion whose property value is UNKNOWN yields `NEED_MORE_INFORMATION`, not PASS and not hard FAIL.

### C04 — criteria versioning
Changing request criteria changes request version and creates a new match evaluation; old match snapshots are unchanged.

### C05 — assisted request claim
Assisted/UNCLAIMED request is claimed using verified control and becomes shared/claimed without creating a duplicate request id.

## D. Property / Offer

### D01 — one property, multiple commercial offers
One physical property has Owner SALE 24M DZD, Broker SALE 27M DZD, and RENT 70k/month. Each offer remains independent.

### D02 — seller expectation privacy
Internal seller expectation may influence price compatibility but never appears in public/customer DTOs or customer explanation.

### D03 — physical freshness vs commercial freshness
Reconfirming availability of property does not automatically refresh asking price/offer terms. Reconfirming offer terms does not automatically refresh physical availability.

### D04 — public property with no active public offer
`supply_mode=PUBLIC` alone is insufficient for public browse. With all offers withdrawn or no valid public consent, the property is absent from `/public/properties`.

### D05 — potential property without offer
Potential property may be evaluated without offer id only if structured willingness/commercial context exists and re-confirmation/permission gates behave according to policy.

## E. Property Identity

### E01 — confirmed same is non-destructive
Two property records are confirmed as same. Alias→canonical mapping is created. Sources/offers/claims remain intact. No row is deleted.

### E02 — matching aliases prohibited
After identity resolution, new match evaluation against alias property must fail. Matching must use canonical property.

### E03 — similar units not same property
Two adjacent villas in one development share images/specs but are distinct physical units. Reviewer selects `CONFIRMED_DISTINCT` or appropriate reason, and no alias mapping is created.

### E04 — duplicate opportunity after identity consolidation
If alias and canonical property already have separate open opportunities for same request, identity command must surface review/consolidation work rather than silently deleting history.

## F. Truth / Evidence

### F01 — claim cannot self-upgrade
API client cannot create claim at DOCUMENT_SEEN/DETAILS_MATCHED. New claim is DECLARED.

### F02 — verification upgrade
Confirmed verification event may raise effective verification. Inconclusive event does not upgrade it.

### F03 — resolution subject mismatch
Resolved value for Property A cannot cite a source claim belonging to Property B.

### F04 — resolution attribute mismatch
Resolved `DOCUMENT_TYPE` cannot cite source claim whose attribute is `LAND_AREA`.

### F05 — temporal knowledge
Owner says on Sep 20 that property was sold Sep 5. `recorded_at` and `valid_from` must preserve the distinction.

## G. Matching

### G01 — hard fail dominates
Required document mismatch remains REJECTED regardless of excellent location/price/soft score.

### G02 — negotiable is not automatic pass
Asking price above max + `price_negotiable=YES` without confirmed reachable price yields UNKNOWN/Potential compatibility, not PASS.

### G03 — evaluated offer identity
For same property with multiple offers, criterion result must be explainable against the exact evaluated offer id/version or potential commercial snapshot.

### G04 — immutable replay
After changing request criteria, property document and offer price, GET old Match still shows old snapshots, input hash and criterion results.

### G05 — rule/policy lineage
Match points to existing matching policy and stores matching policy version consistent with it.

### G06 — no-match is valid
When no property satisfies all hard gates, result is zero eligible candidates; engine does not manufacture a recommendation.

## H. Human Review / Opportunity

### H01 — review history
Match gets `NEED_MORE_INFORMATION`, then later `APPROVED`; both review rows remain.

### H02 — approval gate
Reviewer cannot approve match when information/freshness/permission/hard gate is not PASS.

### H03 — no general opportunity create
External/customer API cannot create Opportunity directly.

### H04 — one open opportunity per pair
Same Request × same canonical Property cannot produce two open opportunities because of multiple sources/offers.

### H05 — share revalidates permission
Opportunity approved yesterday but consent revoked today cannot be shared today without valid current permission.

## I. Diagnostic / Tasks

### I01 — high-value unknown priority
Exact candidate with unknown required document generates higher-value verification task than a near match requiring buyer location relaxation.

### I02 — task completion evidence
Completing task stores outcome code, note and evidence observation in `task_completion_events` and marks task done atomically.

### I03 — relaxation does not mutate request
Suggested `+150M DZD max budget` scenario does not change request unless user confirms through request update command.

## J. Communication / Webhooks

### J01 — webhook replay
Same `(provider, provider_event_id)` delivered twice yields one processed message/interation effect.

### J02 — global provider message identity
Same provider external message id cannot be inserted under a second thread.

### J03 — communication archive permission
Communication archive behavior respects relevant consent policy and retention rules defined for pilot/legal review.

## K. Security / API Boundaries

### K01 — BOLA customer party
Customer cannot fetch another party by guessed UUID. Generic internal party endpoint excludes CUSTOMER role.

### K02 — BOLA request
Customer `/me/requests/{id}` returns only own/delegated request.

### K03 — public DTO leakage
Public property response never contains management mode, claim state, consent ids, seller expectation, staff notes or provenance internals.

### K04 — typed PATCH
Sending `status`, `consent_id`, `claim_status`, `permission_scope` or arbitrary unknown field to generic PATCH is rejected.

### K05 — idempotency replay
Repeat mutating command with same key/payload does not create duplicate row/action. Same key with altered payload returns 409.

### K06 — hard-delete defense
Application role cannot hard-delete protected REQUEST/PROPERTY/OFFER/CLAIM/RESOLUTION/OPPORTUNITY history.

---

# Release Gate

The implementation may pass Core Release Gate only when all A–H scenarios pass and all critical K scenarios pass. I/J may be deferred only until their slices are implemented, but their contracts must remain compatible from the beginning.
