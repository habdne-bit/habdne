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

### DL-08 · What makes a record claim legitimate
**Open. Raised by Slice 2, not resolved.**

`POST /records/claim` does not verify that the claimant has any relationship
to the record: the `verification_contact_point_id` is not checked for verified
control, for belonging to the claiming account, or for reaching the record's
party. INV-1 governs conflicts BETWEEN claimants; it says nothing about
whether a claimant is the right person.

No disclosure results — read access still follows the account's own party
binding, so a wrongful claimant gains an ownership event and no readable
record. The exposure is a **denial of claim**: INV-1 then refuses the
rightful person's claim.

Resolving it is a Workflow and Permissions decision. DL-02 rules out the
obvious shortcut: "this phone reaches that party" must never become "this
account owns that party's records". See `docs/gate/SLICE_2_PROGRESS.md` §5 G-6.

### DL-09 · Undefined REQUEST state transitions
**Open. Fail-closed meanwhile.**

`RequestStateCommand` accepts six target states; Reference Spec §5.2 defines
far fewer edges. Undefined ones — `ACTIVE -> CLOSED` directly, `RAW -> PAUSED`
and others — are refused rather than guessed. Adding any of them is a Workflow
decision. See `SLICE_2_PROGRESS.md` §5 G-2.

### DL-10 · Nothing schedules the staleness pass
**Open.** `mark_stale_as_needing_confirmation()` exists and is tested; the
contract declares no scheduled-job operation and the handoff names no
schedule, so what calls it and how often is undecided. No timer was invented.

---

## Superseded

| Entry | Was | Now |
|---|---|---|
| D1 | `If-Match` accepted as an alias | Canonical header is `If-Match-Version`, integer only, no alias |
| D2 | `parties` had no `version` | `parties.version` exists in v0.2.3; PARTY is versioned |
| D6 | schema declared itself `0.2.1` | Corrected in v0.2.3; 11/11 version claims agree |
