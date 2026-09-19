# Account provisioning — what exists, what does not, and a minimal contract

**Status:** specification. **Not implemented, and not authorised for
implementation.** Design Ledger **DL-07**.
**Prepared:** 2026-09-19, in answer to the instruction to state the gap
precisely rather than describe it in general terms.

---

## 1. What is implemented, path by path

The instruction asks which of four things exist. Answered one at a time,
against the code rather than against intent.

| Path | Status | Where |
|---|---|---|
| **Create a USER_ACCOUNT** | **Not implemented.** No application code inserts into `user_accounts`. | — |
| **Bind an account to a PARTY** (`user_accounts.party_id`) | **Not implemented.** No application code writes this column. | — |
| **Set the login contact point** (`login_contact_point_id`) | **Not implemented.** The column is **read** by the login flow and **written nowhere** in the application. | read at `services/otp.py:_activate_existing_account` |
| **Activate an account** | **Implemented.** `INVITED → ACTIVATED` on a verified LOGIN; `ACTIVATED` refreshes `last_login_at`; `SUSPENDED` and `DISABLED` are left alone, because proving control of a phone must not undo an administrative decision. | `services/otp.py:_activate_existing_account` |
| **Assign a role** | **Partially: a service exists, with no caller.** `services/roles.py:grant_role` enforces INV-2 and is covered by tests, but nothing invokes it — no endpoint, no command, no administrative entry point. It also performs **no actor authorization, no audit, and no self-escalation check**, because it was written as the INV-2 enforcement point, not as an operation. | `services/roles.py` |
| **Detect existing role anomalies** | **Implemented.** `find_role_anomalies` | `services/roles.py` |

Verified by inspection: `grep -rn "login_contact_point_id" src/` returns one
read and no writes; `grep -rn "grant_role" src/` returns the definition and no
call sites.

## 2. The consequence, stated plainly

Slice 1's deliverable is *"activate account from a verified login contact
point"*, and that is delivered. But an account can only be activated if it
already exists, and **nothing in TURAB can bring one into existence**. Today
accounts and roles reach the database only through `db/fixtures/dev_fixtures.sql`.

The frozen contract carries no operation for any of this: searching
`openapi_v0.2.3.yaml` for account- or role-related paths and operationIds
returns **zero** across all 64 operations. So this is not a deviation from the
contract — it is a gap the contract itself carries.

**Development of Slice 2 can proceed on controlled test accounts.** What must
not happen is declaring readiness for a real pilot on the strength of
fixtures. That is recorded here so the decision is taken deliberately.

The Slice 1 Closure Pack has been corrected to state this per-path rather than
as a single sentence.

## 3. Proposed minimal mechanism

Three operations, no more. This is deliberately **not** a user-management
system; it is the smallest set that lets a real environment exist.

### 3.1 Mechanism: administrative command, not API

All three are **CLI commands run against the database by an operator with
deployment access**, not HTTP endpoints. Three reasons:

1. **The frozen contract declares no such operations.** Adding endpoints means
   adding paths the published contract does not contain, which is exactly what
   R14.1 forbids doing from the code side. A command adds no API surface.
2. **Bootstrapping is inherently out-of-band.** The first ADMIN cannot be
   created by an authenticated ADMIN. That circularity is resolved by
   deployment access, and pretending otherwise produces a public endpoint with
   a bootstrap exemption — historically a reliable source of takeovers.
3. **Frequency.** These run at environment setup and at staff onboarding, not
   in a request path.

If a later decision wants role assignment as an API operation, it arrives as a
contract change in a new handoff package, and this specification is its
starting point.

### 3.2 `turab-admin bootstrap-admin`

Creates the first ADMIN account for an environment.

| | |
|---|---|
| **Inputs** | `--phone` (E.164), or `--email`; `--roles` (default `ADMIN`; `ADMIN,OPERATOR` for a single-operator pilot, recorded as such) |
| **Preconditions** | **Refuses if any account already holds ADMIN.** This is the whole safety property: the command works exactly once per environment. |
| **Effect** | creates `user_accounts` row (`party_id` NULL — staff have no party), creates or reuses the contact point, sets `login_contact_point_id`, status `INVITED`, grants `ADMIN` |
| **Activation** | **not** performed here. The holder activates by completing the normal OTP LOGIN flow, so account creation and proof of phone control stay separate — an account created by a command is inert until someone proves they hold the number. |
| **Audit** | one record, actor `SYSTEM:bootstrap`, with the operating-system user and host |
| **Idempotence** | re-running is refused, not silently repeated: a second ADMIN created by accident is indistinguishable from one created maliciously |

### 3.3 `turab-admin grant-role --actor <admin_account_id> --account <id> --role <ROLE>`

| | |
|---|---|
| **Attribution check** | `--actor` must name an **ACTIVATED account holding ADMIN**. This checks the id, not the operator — see §3.5.1. |
| **Self-grant** | **Refused when `--actor == --account` for any role.** Not a security barrier — one operator can hold both accounts — but it keeps any post-bootstrap privilege change out of a single unattributable step (§3.5.2). |
| **INV-2** | delegates to the existing `grant_role`: `OPERATOR + REVIEWER` is rejected at assignment time |
| **CUSTOMER role** | refused by this command — a customer role follows from a customer account, not from staff action |
| **Duplication** | `ON CONFLICT DO NOTHING` already makes a repeat grant a no-op; the command reports "already held" rather than claiming to have granted |
| **Audit** | actor account, target account, role, timestamp, and the resulting role set |
| **Revocation** | **out of scope here.** Naming it is deliberate: this contract covers granting only, and revocation needs its own rules about in-flight work. |

### 3.4 `turab-admin provision-customer --party <id> --phone <E.164>`

Creates a customer account bound to an existing party.

| | |
|---|---|
| **Attribution check** | `--actor` must name an ACTIVATED ADMIN or OPERATOR account (§3.5.1) |
| **Party** | must already exist. The command never creates one — that is `POST /parties`, restricted by DL-01. |
| **Binding** | `user_accounts.party_id = --party`, in the same transaction as the account row. A customer account with a null party is authorized over nothing (R3.1), so a half-completed provision must not be possible. |
| **Login contact point** | created or reused for the phone. **Reuse never transfers verified control** (DL-02) — an account bound to a shared number is still inert until its own holder completes OTP LOGIN. |
| **Duplication** | refuses if the party already has an account, and refuses if the contact point is already some other account's login point (`user_accounts` already has `UNIQUE(login_contact_point_id)`, so the second case is enforced by the schema as well as by the command) |
| **Status** | `INVITED`. Activation happens through the normal flow. |
| **Role** | grants `CUSTOMER` only |
| **Audit** | actor, party, account, contact point reference — never the number itself in metadata |

## 3.5 Two questions the review asked, answered

### 3.5.1 How is the operator's identity and authority proven?

**It is not, and the earlier draft overstated it.** That draft said `--actor`
is "verified against the database, not trusted from the command line". What
the database can verify is that the id *exists* and *holds ADMIN*. It cannot
verify that the person running the command **is** that account. Anyone able to
run the command can pass somebody else's id.

So the honest model is:

| Layer | What it is | What it proves |
|---|---|---|
| **Authority** | possession of database and deployment credentials | that the operator is entitled to run the command at all. This is the real trust boundary, and it is the same boundary that already lets that person run arbitrary SQL. |
| **`--actor`** | an **asserted** attribution | nothing about identity. It is checked only for *existence* and *role*, which prevents attributing an action to an account that could not have performed it. |

Two consequences are adopted rather than papered over:

1. The audit record must say what it knows. It records `asserted_actor` —
   never `actor_account_id` as if authenticated — alongside the operating
   system user, the host and the timestamp. A reader must be able to see that
   the attribution is a claim, not a proof.
2. **Nothing in this contract should be read as an authorization control.**
   These commands do not raise anyone's privileges beyond what database
   credentials already grant. Their value is that role assignment leaves a
   legible, INV-2-checked trail instead of being an ad-hoc `INSERT`.

Real operator authentication only becomes possible when the action moves
behind an authenticated session — i.e. if role assignment becomes an API
operation. That is a contract change, and §3.1 already says it arrives as one.

### 3.5.2 How does bootstrap work in a pilot run by one person?

The earlier draft refused `--actor == --account` for every grant and called it
self-escalation prevention. The review is right on both counts: a difference
between two account ids is **not** proof that two people are involved — one
operator with database access can hold both — and the rule must not, without
an explicit decision, make a two-person team a precondition for running a
pilot at all.

Adopted instead:

- **`bootstrap-admin` takes `--roles`,** defaulting to `ADMIN`. A
  single-operator pilot runs `--roles ADMIN,OPERATOR`. The combination is
  granted **once, at bootstrap, in the open**, and recorded as
  `bootstrap_mode: single_operator` in the audit record and in
  `schema_metadata`.
- **`grant-role` still refuses `--actor == --account`.** After bootstrap,
  self-grant is refused — not because it stops a determined operator, but so
  that a later privilege change is never invisible: it has to go through
  `bootstrap-admin` (which refuses to run twice) or through a second account.
- **INV-2 is not relaxed for anybody.** `OPERATOR + REVIEWER` remains
  rejected at assignment time, single-operator mode included. A pilot that
  needs both must accept that one person cannot be maker and checker, which is
  a real operating constraint and not a software limitation to route around.

The distinction being drawn: the separation rule stays, and the *bootstrap
exception to it is explicit, once-only and recorded* rather than arrived at by
someone quietly granting themselves a second role.

## 4. Properties the three share

- **Every command names an asserted actor.** For the two non-bootstrap
  commands that id is checked for existence and role, which is an attribution
  check and not an authentication one (§3.5.1).
- **No command activates an account.** Activation requires proving control of
  the login contact point, always, through the flow that already exists. This
  keeps the Slice 1 invariant intact: a verified phone proves control of a
  CONTACT_POINT; it does not create a PARTY or a USER_ACCOUNT, and creating an
  account does not prove anything about a phone.
- **No command creates a PARTY.** DL-01 and DL-04 hold.
- **Every command is audited** through the same `audited_transaction` wrapper
  as the request path, so R6.2's actor attribution applies unchanged.
- **Self-grant after bootstrap is refused**, so a privilege change is never
  invisible — while single-operator pilots stay possible through the explicit,
  once-only, recorded bootstrap path (§3.5.2). This is a legibility control,
  not a barrier against someone who holds database credentials.

## 5. What this specification does NOT propose

Named so the boundary is not assumed wider than it is: no user listing, no
search, no profile editing, no password or credential management, no
invitation emails, no session or token administration, no role revocation, no
bulk import, and no self-service registration of any kind (DL-04).

## 6. Status and next step

This is a specification awaiting a decision. Nothing in it is implemented, and
no part of Slice 2 depends on it. If approved, it is a small, self-contained
piece of work whose acceptance criteria are the tables above.
