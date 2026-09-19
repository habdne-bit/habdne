# TURAB — Design Ledger

The running record of what is **adopted now**, what is **deferred**, and what
is **blocked pending a contract**. A decision that is not here is not a
decision; an implementation choice that contradicts an entry here is a defect.

Authority order is fixed by
`docs/handoff/00_START_HERE/FILE_AUTHORITY_AND_VERSION_POLICY.md`. Entries
here record approved decisions; they never override the frozen package.

---

## نعتمد الآن — Adopted now

### DL-01 · `POST /parties` is restricted to ADMIN and OPERATOR
**Decision D7 · approved 2026-09-19 · enforced by CORRECTION-001**

`POST /parties` creates a market PARTY on behalf of someone, performed by a
member of staff. No general self-service creation is adopted through it, and
`CUSTOMER` is not added to its permissions without a defined onboarding path.

Explicitly **not** implied by this entry:

- A CUSTOMER creating **their own REQUEST** remains in scope for Slice 2,
  using an account already bound to the correct party. Restricting PARTY
  creation to staff does not remove that path.
- Nothing here changes `POST /requests`, which keeps `CUSTOMER` in its roles.

Enforced at two layers, deliberately: the role gate (via the correction) and
an object gate in the route. The second is kept precisely because a create has
no object to own — if the roles ever widened again, the contract would
otherwise be the only thing standing in the way.

Evidence: `tests/test_correction_001.py`; `docs/contract/CORRECTION-001-post-parties-roles.md`.

### DL-02 · Party identity and record ownership are never inferred from a shared phone
**Decision D7 (same approval) · standing rule**

Two parties may be reachable on one number. That fact alone establishes
**nothing**: not that they are the same party, not that either controls the
other's records, and not that a verified contact point authenticates anyone.

Concretely, and each already enforced:

| Inference that is forbidden | Where it is prevented |
|---|---|
| shared phone ⇒ same party | `parties.attach_phone` reuses the contact point and never merges |
| attaching a phone ⇒ inheriting its verified control | reuse preserves `control_status`; verification belongs to the contact point |
| party link ⇒ a login path to that party's account | login resolves only `user_accounts.login_contact_point_id`, never `party_contact_points` |
| authority over a record | RFC-001 R4.5 / decision 1 — relations are never an authorization source |

Evidence: `test_one_phone_can_reach_two_parties_without_merging`,
`test_reusing_a_contact_point_does_not_transfer_its_verified_control`,
`test_attaching_a_phone_to_a_party_creates_no_login_path`,
`test_a_shared_line_does_not_authenticate_as_the_party_that_shares_it`,
`test_relationship_alone_never_grants_property_access`.

### DL-03 · A contract correction may only narrow
**Established with CORRECTION-001 · standing rule**

The frozen OpenAPI is never edited in place. Where an approved decision makes
an operation's declared roles wrong, the decision is recorded in
`docs/contract/CONTRACT_CORRECTIONS.yaml` and applied on top of the frozen
contract. A correction may only **remove** roles. Widening access is a
contract change and requires a new official handoff package.

Both invariants are enforced in `src/turab/auth/contract.py` and fail at
startup, not merely in review.

---

## مؤجَّل — Deferred, with the condition for taking it up

### DL-04 · Self-service PARTY creation
**Blocked pending a contract. Not scheduled.**

Held as an item in its own right, separate from DL-01. Before any
implementation it needs, at minimum: who may create a party for themselves and
in what state; how the new party is bound to the calling account atomically;
what prevents one account minting many parties; how duplicates against
existing market parties are detected rather than created; and what a customer
may then see and do with it.

Until that contract exists, `POST /parties` stays staff-only and no code path
creates a party on a customer's behalf.

### DL-05 · Customer delegated authority
**Deferred to a later version by decision 4 (RFC-001 §4, Q7).**

### DL-06 · Per-account claim revocation
**Deferred (RFC-001 §4.5a).** A claim, once recorded, is not revoked per
account in v0.1.

### DL-07 · Account provisioning and role assignment
**Gap, not a decision. Specification drafted, implementation not authorised.**

The frozen contract declares no operation for creating an account, binding it
to a party, setting its login contact point, or granting a role. Activation of
an account that already exists **is** implemented. See
`docs/contract/ACCOUNT_PROVISIONING_MINI_CONTRACT.md` for exactly what exists,
what does not, and the proposed minimal mechanism.

---

### DL-08 · ~~What makes a record claim legitimate~~ — WITHDRAWN
**Withdrawn 2026-09-19. It was not an open decision.**

The frozen contract's `x-authorization` on `postRecordsClaim` already declares
the rule: *"For customer, verified contact point and resource party
relationship are mandatory."* Recording it as an open decision was a
misclassification; it was an unimplemented requirement. Enforced by
CORRECTION-003 (`docs/contract/CORRECTION-003-claim-eligibility.md`).

### DL-08a · Claim eligibility for a PROPERTY
**Open. Fail-closed meanwhile. Not a Slice 2 deliverable.**

The adopted rule is for REQUEST claims and does not transfer: `properties` has
no `party_id`, and a property's party relationship is
`party_property_relations`, which RFC-001 decision 1 / R4.5 forbids as an
authorization source. `POST /records/claim` with `resource_type=PROPERTY` is
refused, naming the undecided rule. This will block PROPERTY claiming in
Slice 3.

### DL-09 · ~~Undefined REQUEST state transitions~~ — RESOLVED
**Adopted 2026-09-19 as CORRECTION-002.** `ACTIVE → PAUSED` and
`ACTIVE → CLOSED` are direct transitions; a request need not pass through
`NEEDS_CONFIRMATION` to be paused or closed. Reactivation is the state command
itself with `target_status=ACTIVE`; the undeclared `reactivate` field has been
removed. Table: `docs/gate/REQUEST_STATE_TRANSITIONS.md`.

### DL-10 · Nothing schedules the staleness pass
**Open, and narrowed.** Accepted for this slice: a documented administrative
command, `db/dev/run_freshness_pass.py`, which someone runs. **Freshness does
not maintain itself** — a request becomes `NEEDS_CONFIRMATION` when that
command is run and not before. What runs it, and how often, is still
undecided.

### DL-11 · `RequestPatch` cannot carry a source reference
**Open, and narrowed.** The service records the actor, the channel
(SELF_SERVICE vs STAFF_RECORDED), the previous and new values, and whether a
source was recorded. It can carry a `source_id` when one is supplied, and a
staff-recorded change asserts nothing about what the party said. What the
contract cannot yet express is the client attaching the call or message it was
working from, so `source_recorded` is `false` on every update arriving through
the contract as frozen. Accepting one needs a contract change.

### DL-12 · RFC-001 carries no text for INV-1 or INV-2
**Documentation gap, found 2026-09-19 while assembling the Slice 2 review
bundle. Not a code defect.**

```
$ grep -c "INV-" docs/rfc/RFC-001-object-level-authorization.md
0
```

The two fail-closed invariants the authorization design rests on were added
**at the moment RFC-001 was approved**, in the approval instruction, and were
never folded back into the RFC. Their text lives in the approval message, in
the closure packs, and in the docstrings of the code enforcing them — so a
reviewer asked to read these constraints from their own source finds no
canonical paragraph.

Both are enforced and tested; nothing is wrong with the implementation. What
is missing is the normative text. The remedy is to fold both into RFC-001 as
numbered rules, which edits an approved document and therefore needs a
decision.

Meanwhile: `docs/gate/INV-1-and-INV-2.md` states the approved text and maps
each half to the code and tests that enforce it.

---

## Superseded

| Entry | Was | Now |
|---|---|---|
| D1 | `If-Match` accepted as an alias | Canonical header is `If-Match-Version`, integer only, no alias |
| D2 | `parties` had no `version` | `parties.version` exists in v0.2.3; PARTY is versioned |
| D6 | schema declared itself `0.2.1` | Corrected in v0.2.3; 11/11 version claims agree |
