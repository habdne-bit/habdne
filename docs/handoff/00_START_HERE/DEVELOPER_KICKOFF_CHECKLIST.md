# TURAB — Developer Kickoff Checklist

The developer should complete and acknowledge this checklist before starting feature implementation.

## Understanding

- [ ] I have read the Foundation Baseline v1.0 FINAL.
- [ ] I understand REQUEST and PROPERTY are equal first-class entities.
- [ ] I understand PROPERTY ≠ SOURCE/POST and PROPERTY ≠ PROPERTY_OFFER.
- [ ] I understand INTEREST ≠ REQUEST.
- [ ] I understand MATCH_CANDIDATE ≠ OPPORTUNITY.
- [ ] I understand Human Review is mandatory before OPPORTUNITY in v0.1.
- [ ] I understand PASS / FAIL / UNKNOWN semantics and that hard FAIL cannot be ranked away.
- [ ] I understand Declared ≠ Verified and verification requires an explicit event/process.
- [ ] I understand Public / Private / Potential supply modes.
- [ ] I understand PARTY ≠ CONTACT_POINT ≠ USER_ACCOUNT.
- [ ] I understand consent is resource-bound, scoped and revocable.
- [ ] I understand property identity resolution is non-destructive.
- [ ] I understand public/customer/internal DTOs are separate server-side contracts.
- [ ] I understand AI is assistive and must not bypass deterministic/domain gates.

## Technical preflight

- [ ] `technical_pack_static_audit_v0.2.1.py` returns PASS.
- [ ] PostgreSQL 16+ clean database accepts `schema_v0.2.1.sql`.
- [ ] `seed_master_data_v0.2.1.sql` executes twice without failure.
- [ ] PostgreSQL Execution Gate tests pass.
- [ ] `openapi_v0.2.yaml` parses/lints in CI.
- [ ] CI can rebuild a clean database from zero.
- [ ] Object-level authorization tests are included from Slice 0.
- [ ] Idempotency replay and conflict tests are included from Slice 0.

## Build discipline

- [ ] I will follow `IMPLEMENTATION_SLICES_v0.2.md` in order.
- [ ] I will not introduce advanced AI before the deterministic core Stop Gate passes.
- [ ] I will not add a feature outside v0.1 scope without an approved Design Ledger decision.
- [ ] I will not use generic PATCH/repository updates to bypass domain commands for critical fields/states.
- [ ] I will not expose private/internal fields and rely on frontend hiding.
- [ ] I will preserve immutable historical inputs and review history.

**Developer:** ____________________  
**Date:** ____________________  
**Product/Technical approval:** ____________________
