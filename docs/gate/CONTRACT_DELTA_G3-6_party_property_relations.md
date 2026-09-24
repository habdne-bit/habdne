# Contract Delta · G3-6 — party–property relations

**Status:** **revision 3 — RE-CONFIRMED; the implementation basis.** The
three operations, their staff-only roles, `DECLARED`-only relations, and
§5.1 (omitted `valid_from` → server clock; `null` refused) were re-confirmed.
The confirmation carried **two corrections to this text**, applied here as
**revision 3a** — corrections of wording, not a new decision round:

- §10 said the API "never creates a relation that is not current". False: an
  explicit FUTURE `valid_from` is permitted and creates a relation that is not
  current until it starts (§5.1 already said so). Corrected.
- §7 said "all three mutating operations". Retrieve is a read; only **create**
  and **end** mutate. Corrected.

Revision 3 incorporated the decisions taken since revision 1: option A
ratified (§1); rule **6a adopted** (§6); the database backstop exists as
revision `0004`; `include_ended` uses the ratified currency predicate (§3.2);
the meaning of an omitted or null `valid_from` settled (§5.1).
**Kind:** a contract **ADDITION**, not a narrowing correction.
**Baseline:** Handoff v1.0.3 / pack v0.2.3, frozen. `openapi_v0.2.3.yaml` is
**not modified**, and this is **not** applied through the correction overlay.
**Decision it implements:** G3-6, option A, ratified in the Slice 3 plan
review.
**Target:** the next contract package (v0.2.4 or later), or adoption of this
Delta as a standalone approved addendum.

---

## 1. Why an addition, and why the overlay cannot carry it

The correction overlay may only **narrow** what the frozen contract already
declares: remove a role, tighten a schema, restrict an operation. It is
structurally incapable of introducing an operation or a field, and RFC-001 R14.1
makes the frozen document the contract. Three operations that do not exist
cannot be narrowed into existence.

The gap being closed, confirmed by inspection of the effective contract:

- No path contains "relation"; no operation creates, reads or ends a
  `party_property_relations` row.
- `PropertyCreate` and `OfferCreate` carry no `relation_code`.
- The table `party_property_relations` exists in the frozen schema, fully
  formed, with **no way to put anything in it**.

Options B (a field on `PropertyCreate`) and C (relations through the truth
layer) were rejected on principle: B binds two independent concepts and cannot
express a later or a second relation; C conflates the party **asserting** a
fact with the party **related to** the property, and reuses provenance
machinery as a domain fact.

### 1.1 G3-6 blocks more than its own deliverable — demonstrated, not argued

While drafting this Delta we found a second consequence nobody had named.
`enforce_consent_binding` (`schema_v0.2.3.sql:1092-1099`) requires, for a
**property-scoped** consent binding, that the consenting party hold an
**active relation to that property**:

```sql
ELSIF NEW.property_id IS NOT NULL THEN
  IF NOT EXISTS (
    SELECT 1 FROM party_property_relations
    WHERE party_id = grant_party AND property_id = NEW.property_id
      AND (valid_to IS NULL OR valid_to > now())
  ) THEN
    RAISE EXCEPTION 'Property consent party has no active property relation';
  END IF;
```

Run against the live database, binding a granted consent to a property with no
matching active relation:

```
>>> binding consent :cid to property :pid (no relation exists)
ERROR:  Property consent party has no active property relation
CONTEXT:  PL/pgSQL function enforce_consent_binding() line 33 at RAISE
```

**The precise statement of the gap**, adopting the reviewer's wording because
our first phrasing was looser than the facts:

> The PROPERTY consent branch is **unreachable through the operational surface
> starting from an empty database**. It remains **technically reachable** if a
> relation row is inserted directly — which is exactly what the fixtures do.

Not "impossible": impossible would be false, and the fixtures would disprove
it. The relation is not decorative — it is a precondition the database enforces
for ADR-04's resource-bound consent — and there is no operational way to
satisfy it.

Two clarifications, so this is neither overstated nor understated:

- **The public listing is not blocked.** Its consent attaches to the
  *commercial context*, i.e. an **offer**, and the trigger's offer branch
  checks `property_offers.party_id` instead — no relation required.
  `getPublicProperties` proceeds as planned.
- **Today's tests pass because the fixtures insert relation rows directly**
  (five of them). That is legitimate for a fixture, and it is also why the gap
  went unnoticed: the suite has never exercised the property-binding path
  through an operational surface able to create its precondition. We record it
  rather than let a green suite imply the path is reachable.

**See also G3-7** (`docs/gate/G3-7_consent_binding_relation_currency.md`): the
same gate checks a weaker predicate than RFC-001 R4.6 declares, ignoring
`valid_from`. G3-7 must be fixed **before or with** this Delta, so that
relations do not become creatable through the API while the gate is weak.

This raises the Delta from "a deliverable is missing" to "a declared,
implemented operation has an unreachable branch".

---

## 2. What the frozen schema already fixes

The table is frozen, so this Delta describes an API over it and **proposes no
schema change**:

```sql
CREATE TABLE party_property_relations (
  party_property_relation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  party_id    uuid NOT NULL REFERENCES parties(party_id)     ON DELETE RESTRICT,
  property_id uuid NOT NULL REFERENCES properties(property_id) ON DELETE RESTRICT,
  relation_code text NOT NULL CHECK (relation_code IN
     ('OWNER_DECLARED','BROKER','AGENCY','DEVELOPER','OCCUPANT',
      'CONTACT_PERSON','OTHER')),
  verification_level verification_level NOT NULL DEFAULT 'DECLARED',
  valid_from timestamptz,
  valid_to   timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from)
);
CREATE INDEX idx_party_property_property ON party_property_relations(property_id);
```

Four facts follow, and each removes a design choice rather than creating one:

1. `relation_code` is a **closed list of seven**, enforced by a `CHECK`. The
   API enum must be exactly these seven — no more, and no fewer.
2. `verification_level` defaults to `DECLARED` and reuses the existing
   four-level enum (`DECLARED`, `DOCUMENT_SEEN`, `DETAILS_MATCHED`,
   `PROFESSIONAL_CHECK`).
3. `valid_to > valid_from` is a database `CHECK`. Ending a relation is an
   `UPDATE` setting `valid_to`, not a delete.
4. The FROZEN schema has **no unique constraint** on `(party_id, property_id,
   relation_code)` and no exclusion constraint on overlapping periods, so it
   settles nothing about duplicates or overlaps on its own. That was a
   decision this Delta had to record, and it is now **taken and implemented**:
   rule 6a, enforced by `party_property_relations_no_overlap`, an
   `EXCLUDE USING gist` constraint added by revision
   `0004_relation_overlap_guard` — a forward migration, not an edit to the
   frozen file. See §6.

---

## 3. The three operations

### 3.1 `postPropertiesPropertyIdRelations` — create

```
POST /properties/{property_id}/relations
```

| | |
|---|---|
| roles | `ADMIN`, `OPERATOR` |
| security | `BearerAuth` |
| parameters | `property_id` (path, uuid), `Idempotency-Key` (`#/components/parameters/IdempotencyKey`) |
| request body | `PartyPropertyRelationInput`, required |
| responses | `201` `PartyPropertyRelation`; `400`, `401`, `403`, `404`, `409`, `422` → `Problem` |

```yaml
PartyPropertyRelationInput:
  type: object
  additionalProperties: false
  required: [party_id, relation_code]
  properties:
    party_id:      { type: string, format: uuid }
    relation_code:
      type: string
      enum: [OWNER_DECLARED, BROKER, AGENCY, DEVELOPER, OCCUPANT,
             CONTACT_PERSON, OTHER]
    valid_from:    { type: string, format: date-time }   # omissible, never null (§5.1)
    note:          { type: [string, "null"] }
```

**`verification_level` is deliberately absent from the input.** It is not a
field a client may set. §5 explains why, and it is the same shape as
`claims.effective_verification_level`, which the frozen schema's own comment
says API clients must not set above `DECLARED` directly.

`valid_to` is absent from the input too: a relation is created open-ended or
from a stated start, and ended through §3.3.

**`x-authorization`:**

> Staff-only. The server validates that the party and the property both exist.
> Creating a relation grants the party's accounts **no** authority over the
> property or its offers, and the server must not treat it as an authorization
> input (RFC-001 R4.5, R4.12).

### 3.2 `getPropertiesPropertyIdRelations` — retrieve

```
GET /properties/{property_id}/relations
```

| | |
|---|---|
| roles | `ADMIN`, `OPERATOR`, `REVIEWER` |
| parameters | `property_id`; `include_ended` (query, boolean, default `false`); `Page`, `PageSize` |
| responses | `200` — `{ items: [PartyPropertyRelation], page, page_size, total }`; `401`, `403`, `404` |

`include_ended=false` returns only relations **current** at the time of the
call, using the **ratified currency predicate and no other** — the same one
`0003` put into `enforce_consent_binding()`:

```sql
valid_from IS NOT NULL
AND valid_from <= now()
AND (valid_to IS NULL OR now() < valid_to)
```

Revision 1 defined "current" by `valid_to` alone. That was the **same defect as
G3-7**, written into a second place: a future or unstarted relation would have
been listed as current while the consent gate refused it, so the list and the
gate would have disagreed about the same row. One predicate, stated once.

Historical rows are never removed, so `include_ended=true` returns the full
history.

### 3.3 `postPropertyRelationEnd` — end validity

```
POST /properties/{property_id}/relations/{relation_id}/end
```

| | |
|---|---|
| roles | `ADMIN`, `OPERATOR` |
| parameters | `property_id`, `relation_id`, `Idempotency-Key` |
| request body | `{ valid_to?: date-time, reason_code?: string }`, `additionalProperties: false` |
| responses | `200` `PartyPropertyRelation`; `400`, `401`, `403`, `404`, `409`, `422` |

An `end` operation, **not** `DELETE`: the row survives with `valid_to` set, so
the history of who was related to a property and when is never destroyed. This
matches ADR-03's non-destructive principle and the `prevent_delete_*` posture
of the frozen schema.

- `valid_to` defaults to the server's clock when omitted.
- A supplied `valid_to` must carry a timezone offset — the R-S2-05b rule — and
  must satisfy `valid_to > valid_from`, checked before SQL so it is a typed 422
  rather than a `CHECK` violation surfacing as a 500.
- Ending an already-ended relation is a typed **409**, not a silent success.
- `reason_code`, if supplied, must exist in `reason_codes`; it is **not**
  invented as a new category here.

### 3.4 Response schema

```yaml
PartyPropertyRelation:
  type: object
  additionalProperties: false
  required: [party_property_relation_id, property_id, party_id,
             relation_code, verification_level, created_at]
  properties:
    party_property_relation_id: { type: string, format: uuid }
    property_id:        { type: string, format: uuid }
    party_id:           { type: string, format: uuid }
    relation_code:      { type: string, enum: [OWNER_DECLARED, BROKER, AGENCY,
                           DEVELOPER, OCCUPANT, CONTACT_PERSON, OTHER] }
    verification_level: { type: string, enum: [DECLARED, DOCUMENT_SEEN,
                           DETAILS_MATCHED, PROFESSIONAL_CHECK] }
    valid_from:         { type: [string, "null"], format: date-time }
    valid_to:           { type: [string, "null"], format: date-time }
    created_at:         { type: string, format: date-time }
```

**No customer-facing representation is proposed.** All three operations are
staff-only, so there is no `/me` view and no public projection to get wrong.

---

## 4. Roles, and why CUSTOMER is excluded

| operation | ADMIN | OPERATOR | REVIEWER | CUSTOMER |
|---|---|---|---|---|
| create | ✔ | ✔ | — | **✘** |
| retrieve | ✔ | ✔ | ✔ | **✘** |
| end | ✔ | ✔ | — | **✘** |

A customer asserting their own relation to a property would be a
self-declaration of standing, at the exact point where the system is most
vulnerable to a false ownership claim — and it would sit uncomfortably beside
G3-2, where **PROPERTY claim eligibility is deliberately undecided**. Opening a
customer-writable relation path now would create, in substance, the very
property-party link that G3-2 refuses to decide, through a different door.

So: staff-only in this Delta. A customer-facing path is a separate decision,
and should not be taken while G3-2 is open.

Neither operation is proposed as separation-sensitive: recording a relation is
not an approval step, and `SEPARATION_SENSITIVE_OPERATIONS` is about the
OPERATOR/REVIEWER split, not row-level maker/checker (the lesson recorded under
G3-4).

---

## 5. Verification level: default `DECLARED`, and no client-asserted upgrade

**The rule.** A relation is created at `DECLARED`. No client — customer or
staff — may assert a higher level through these operations. `PartyPropertyRelationInput`
has `additionalProperties: false` and **no** `verification_level` field, so the
rule is enforced at the contract boundary and cannot be bypassed by sending the
field.

**Why no upgrade path is proposed here.** Raising a verification level requires
a **declared verification mechanism** — who may verify, by what procedure, with
what evidence and what outcomes. The frozen schema has exactly that machinery
for claims (`verification_events`, with `procedure_code`, `outcome` and
`trg_apply_verification_event`), and **nothing equivalent for relations**.

Inventing an upgrade path without that mechanism would produce a verification
level that means nothing — a `PROFESSIONAL_CHECK` nobody checked. So this Delta
**declares the gap rather than filling it**: relations stay `DECLARED` until a
verification mechanism for them is designed and approved.

Two consequences, stated so neither is discovered later:

- `verification_level` is always `DECLARED` on every row these operations
  create, and there is no operation to change it.
- Any future upgrade path is a **further** contract addition, needing its own
  decision. It is not implied by this one.

---

### 5.1 What an omitted or null `valid_from` means — settled

The question the review raised: does omitting `valid_from`, or sending it as
`null`, deliberately create a relation that is **not current**, or is it set to
the server's clock?

**Decision: it is set to the server's clock, and `null` is refused.**
`PartyPropertyRelationInput` therefore declares

```yaml
    valid_from: { type: string, format: date-time }     # omissible, never null
```

— a plain typed property, not `anyOf [date-time, null]`, so an explicit `null`
is a field error. When the field is **omitted**, the server writes
`now()`.

The reasoning, because either answer is defensible and the wrong one is a trap:

- A relation created through an explicit staff command, with no start stated,
  is being recorded because it is believed to hold **now**. Writing a row that
  silently fails the currency predicate would create a relation that exists,
  reads as real in the list, and backs nothing — the most confusing possible
  outcome.
- A relation that genuinely starts later is a real case, and it stays
  expressible: send `valid_from` explicitly with a future date. It is then
  correctly **not** current until that date, in the list (§3.2) and at the
  consent gate alike.
- `NULL` remains possible in the SCHEMA, because the frozen column is nullable
  and rows may exist from before this operation. Both `0003` and `0004` define
  what such a row means (refused as not-current; included as `-infinity` in the
  overlap guard). What this Delta settles is that **this API will never create
  one**.

A test asserts each half: an omitted `valid_from` yields a row that is current
immediately, and an explicit future `valid_from` yields one that is not.

## 6. Duplicates and temporal overlap — **DECIDED: 6a, and enforced**

**Rule 6a is adopted**, not proposed: at most one relation may be **current**
at a time for the same `(party_id, property_id, relation_code)`. Creating a
second while one is current is a typed **409** naming the existing relation.

Different `relation_code` values never conflict — a party may be both
`OWNER_DECLARED` and `CONTACT_PERSON` — and two different parties may hold the
same code on one property, which is how two brokers are represented.

**It has a database backstop.** Revision `0004_relation_overlap_guard`:

```sql
ALTER TABLE turab.party_property_relations
  ADD CONSTRAINT party_property_relations_no_overlap EXCLUDE USING gist (
      party_id WITH =, property_id WITH =, relation_code WITH =,
      tstzrange(coalesce(valid_from, '-infinity'::timestamptz), valid_to, '[)') WITH &&
  );
```

Three things follow, and they replace what revision 1 had to concede:

- The rule holds for **every writer**, not only for callers who go through the
  command path. Revision 1 had to declare that 6a would be "the one uniqueness
  rule in the slice with no database backstop"; that sentence is withdrawn.
- A partial unique index on `WHERE valid_to IS NULL` was rejected: it would
  stop two open-ended rows but allow an open-ended one to overlap a closed one
  that has not ended yet — the rule failing on the case it exists for.
  "Current" is an interval, so the constraint is over intervals.
- `valid_from IS NULL` is treated as `-infinity` **here**, while the `0003`
  consent gate **refuses** it. Not a contradiction, and worth stating because
  it reads like one: `0003` asks "can this relation be shown to be in force?",
  where an unrecorded start means no; the constraint asks "could these two rows
  describe the same period?", where a row with no start must be INCLUDED, or a
  row that cannot back a consent could still sit invisibly under the guard and
  hide a genuine conflict.

Proven by `tests/test_migration_0004_relation_overlap.py`, including a
two-connection contention test in which the loser fails with SQLSTATE `23P01`.

## 7. Idempotency and audit

- The two mutating operations — **create** (§3.1) and **end** (§3.3) — take
  `Idempotency-Key`, on the existing machinery. Retrieve (§3.2) is a read and
  takes none. A **refused** command consumes no key — the R-S2-04 rule, and a
  test asserts it for each of the two. *(Revision 3a: this read "all three
  mutating operations"; retrieve does not mutate.)*
- `party_property_relations` carries **no** `audit_*` trigger in the frozen
  schema — unlike `properties`, `property_offers`, `claims` and
  `resolved_values`. Auditing is therefore the **command layer's**
  responsibility here, through the same `audited_transaction` path every other
  command uses, and this Delta states it explicitly so it is not assumed to
  come from the database.
- Every create and end records its acting account and channel in the provenance
  trail, as all Slice 1/2 commands do. Note the table has no
  `created_by_account_id` column, so the actor lives in the trail and the audit
  row, not on the row itself — another reason the command layer must carry it.

---

## 8. The invariant this Delta must state, and keep stating

> **A party–property relation grants no access authority whatsoever.**

Not for the property, not for its offers, at any `relation_code`, at any
`verification_level`, current or expired. This is RFC-001 R4.5 and R4.12, and
the scenarios that pin it are already in the Slice 3 test plan: **S12** (any
relation, including `OWNER_DECLARED`, with no claim and not the creator →
404) and **S16h** (a relations row alone → no access to an offer → 404).

Those two tests exist **before** this Delta, precisely because the relation
must grant nothing from the moment it can first be created. Once these
operations exist, S12 and S16h stop needing a hand-inserted fixture row and
become end-to-end: create a relation through the API, then prove it opens
nothing. That change strengthens them and is the only way this Delta touches
the authorization tests.

---

## 9. Acceptance criteria, once approved

1. The three operations declared in the next contract package, with the
   schemas, roles and `x-authorization` text above.
2. `openapi_v0.2.3.yaml` unmodified; the addition is not carried by the overlay.
3. `verification_level` is `DECLARED` on every created row, with no operation
   to raise it.
4. §6's chosen rule implemented and tested, with its enforcement layer stated
   explicitly in the code and in the report.
5. Ending is non-destructive; the row survives with `valid_to` set; no path
   deletes a relation.
6. S12 and S16h re-expressed end-to-end and still proving 404.
7. A refused command consumes no idempotency key, per operation.
8. Every create and end audited through the command layer, with a test, since
   the table has no audit trigger.

## 10. What is asked

1. Re-confirmation of the three operations as specified in this revision, for
   the next contract package.
2. Confirmation of **§5.1** — an omitted `valid_from` is set to the server
   clock and `null` is refused, so this API never creates a relation whose
   start is unrecorded. An explicit **future** `valid_from` is permitted and
   creates a relation that is **not current until it starts** — in the list
   (§3.2) and at the consent gate alike. *(Revision 3a: this read "never
   creates a relation that is not current", which the future-start case
   contradicts.)*
3. Confirmation of **§5**: relations remain `DECLARED`, and a verification
   mechanism for them is a separate, later decision.

§6 is no longer a question: 6a is adopted and enforced by `0004`.

Until all three are answered, no code is written for this path, no relation row
is created, and neither `claims` nor `observations` is repurposed to create one
implicitly.

**Answered.** All three were re-confirmed, with the two corrections above.
The path is implemented against revision 3a.
