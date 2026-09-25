# Slice 3 — Closure record

**Slice 3 — PROPERTY / OFFER / SOURCE / Truth Layer / Identity Lite**
**Status: CLOSED at `96e36e6`, within the approved exceptions**, on the
acceptance review of 2026-09-25.
**Baseline:** Developer Handoff v1.0.3, technical pack v0.2.3, frozen.
**Plan:** `docs/gate/SLICE_3_PLAN.md`, revision 7, its final revision.

The closing decision is the reviewer's. This record states it, and its
limits, as they were given. It adds no claim of its own.

---

## 1. The decision

> I accept the closure of step 8 and STOP GATE C, and therefore of Slice 3
> at 96e36e6, within the approved exceptions. No new blocker appeared in the
> review of the two corrections.

From the same review:
- **Source fingerprint:** the fingerprint of the extracted source matches the
  reported value, `4aa193cc…4e50`.
- **Condition 11:** reading the condition as "re-checked under a lock" is
  consistent with the documented behaviour of PostgreSQL 16 at Read Committed.

## 2. The limits of the decision

These limits are part of the decision. They are not caveats added by the
implementer.

1. **The results are ours, bound to the tree.** Three results rest on our own
   runs, each bound to its tree by commit and source fingerprint:
   - the suite, 1284/1284;
   - the gate, 8/8;
   - the mutation runs.

   The reviewer did not re-run the suite on an independent PostgreSQL
   server.
2. **G3-16 is an exception for this slice only.** No contract operation lists
   a property's offers.
3. **Converting an external lead is refused** under **G3-10**, with a typed
   409.
4. **A PROPERTY claim fails closed** under **G3-2**. Claim eligibility stays
   undecided.
5. **Closure is not operational readiness.** Two gaps remain open:
   - **account provisioning** (G3-5; `ACCOUNT_PROVISIONING_MINI_CONTRACT.md`,
     DL-07, not authorised);
   - **D4**, where the bearer is an opaque account id.

   Accounts and roles still reach the database only through fixtures. No
   application path inserts an account, and `roles.grant_role` has no caller.

## 3. The evidence the decision rests on

Every row below ran on the same source, fingerprint
`4aa193ccde1d416b0e8a9bc946ae8a64ea73b02996a29507c3d65ce9dca34e50`.

| Evidence | Result | Commit | Tree | Record |
|---|---|---|---|---|
| Application suite (`record_test_run.py`) | 1284 passed, 0 failed, 0 errors, 0 skipped | `0c97a6b` | clean | `evidence/TEST-RUN-PROVENANCE.txt`, report sha256 `6abeee12…f33a` |
| PostgreSQL execution gate | 8/8 PASS; parity 67/67/67 | `0414dca` | clean | `evidence/gate-run.txt` |
| Mutations: property queue | 9/9 fail, none survive | `0ff73da` | clean | `evidence/STEP8-PROPERTY-QUEUE-MUTATIONS.txt` |
| Mutations: public list | 26/26 fail, none survive | `0ff73da` | clean | `evidence/STEP6-PUBLIC-LIST-MUTATIONS.txt` |
| Mutations: Identity Lite | 38/38 fail, none survive | `0ff73da` | clean | `evidence/STEP7-IDENTITY-MUTATIONS.txt` |
| Authorization matrix | 149 rules, 149 PASS, 0 UNPROVEN | — | — | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| STOP GATE C | all six questions answered; 7 mandatory tests pass; two documented exceptions | `96e36e6` | — | `SLICE_3_STOP_GATE_C.md`; `--check` exits 0 |

The commits `0414dca`, `0c97a6b` and `96e36e6` change only `docs/`, which the
fingerprint does not cover.

**Frozen artifacts.** Their digests are unchanged since the v0.2.3 freeze,
and `docs/handoff/verify_handoff.py` reports PASS for 36 files.

```
schema_v0.2.3.sql            789841a1a41d869ca78de256879e62950f0672c9719c40a94408c549e28d98a0
seed_master_data_v0.2.3.sql  21b31c4ed338bb4aac24ea5d724b265e5e5b941bc54dd627f3953f3c2ff6cf10
openapi_v0.2.3.yaml          b3b1eb864836d14e275d58e312f960e0e45c7e5b80d2170b54c0e8b39c1f7b72
```

## 4. What was delivered, by step

This record states closure for the slice as a whole, as of the review of
96e36e6. It does not assign separate closure dates to steps 1–4, because no
separate closure was recorded for them.

| Step | Content (plan §8) | Delivery record |
|---|---|---|
| 1 | PROPERTY: create, read, patch, `/me`, internal read, backoffice queue | plan §1.1 and §3; findings R-S3-P01/P02, corrected in plan revision 5. The queue was delivered in step 8 (`SLICE_3_STEP8_DELIVERY.md` §1) |
| 2 | OFFER: create, patch, state machine (G3-1), sources with primary transfer | `SLICE_3_STEP2_FINDINGS.md` |
| 3 | SOURCE: external leads, the conversion refusal (G3-10), the queue | `G3-10_external_lead_conversion.md`; `REVIEW_RESPONSE_0a66f8e.md` |
| 4 | Availability reconfirm, the restricted staleness pass, offer freshness (G3-3) | `SLICE_3_STEP4_DELIVERY.md` |
| 5 | Truth layer: observation → claim → verification → resolution | `SLICE_3_STEP5_DELIVERY.md` |
| 6 | The public list: its three conditions and its projection | `SLICE_3_STEP6_DELIVERY.md` |
| 7 | Identity Lite: generate, list, review, alias, corrective effect, resolver | `SLICE_3_STEP7_DELIVERY.md` |
| 8 | Authorization matrix, STOP GATE C, concurrency | `SLICE_3_STEP8_DELIVERY.md` |
| G3-6 | Party–property relations, through their own operations | `CONTRACT_DELTA_G3-6_party_property_relations.md`; `G3-6_DELIVERY.md`; `contract/addenda/ADD-G3-6_party_property_relations.yaml` |

**Migrations added in this slice.** Both are structural, both approved, and
neither adds a table or a column:
- `0003`: G3-7, relation currency in the consent gate;
- `0004`: the G3-6 overlap guard.

## 5. Decisions and findings

| # | Subject | Status at closure |
|---|---|---|
| G3-1 | Offer state machine | Ratified (plan §4.1) |
| G3-2 | PROPERTY claim eligibility | **Open.** Fails closed (`test_property_claiming_fails_closed`) |
| G3-3 | Availability and freshness | Ratified (plan §4.2) |
| G3-4 | Resolution authority | Resolved (plan §4.3) |
| G3-5 | Account provisioning | **Open.** An operational gap (§2.5) |
| G3-6 | Party–property relations | Decided (option A, Contract Delta); delivered |
| G3-7 | `valid_from` in the consent gate | Resolved in migration `0003` |
| G3-8 (F-1) | `management_mode` / `claim_status` in customer command responses | Applied as the numbered exception **R9.2-EX-01** (`dto/boundaries.py`) |
| G3-9 (F-2) | A write aimed at an alias property | Refused with 409 after authorization |
| G3-10 | Converting an external lead | **Refused** with a typed 409 until the conversion schema is decided |
| G3-11 | A truth-layer vocabulary for PARTY, REQUEST and OFFER | Decided, option (c): PROPERTY-only in this version; other subjects refused with 422 |
| G3-12 | `sharing_scope` and the public projection | Approved (`SLICE_3_STEP6_DELIVERY.md` §4) |
| G3-13 | Aliases in the public list | Approved: excluded; their offers are not moved |
| G3-14 | What `location_id` matches | Approved: the location and its subtree |
| G3-15 | S16i / S16j: 401 or 404 | Decided: **401** at authentication. The scenario tables of the plan and of RFC-001 are corrected |
| G3-16 | A staff list of a property's offers | **An exception for this slice only.** A later need is a contract addition |
| Condition 11 | Winner and loser | The approved wording is a declared compare-and-set **or** a declared conflict rule re-checked under a lock before the write. It is met (`SLICE_3_STEP8_DELIVERY.md` §4) |
| Queue `created_at` | The properties review queue | The property's creation time |

## 6. Carried forward, unchanged by this closure

- **No Matching.** No code path writes `match_candidates` (computed in the
  STOP GATE C document, condition 6). Starting Matching needs its own
  approval.
- **Relations are never an authorization source**
  (`test_authorization_sql_never_reads_party_property_relations`).
- **D3, D5, DL-08a, DL-10 and DL-11** keep the classification they already
  had.
- **Queues without paging.** They are accepted for this slice. A paging
  contract is needed before operational volume (review of 0a66f8e, Q-5 to
  Q-8).
- **`getBackofficeQueuesRequests`** returns an always-empty list, a
  placeholder from an earlier slice. It is not a working queue.
- **Found in the queue criteria:** "نقص" (missing) is not implemented,
  because no required-field rule is defined.
- **The evidence discipline carries into the next slice:**
  - results are bound to commit and source fingerprint;
  - the provenance record has one writer (`record_test_run.py`) and one
    checker (`run_binding.py`);
  - defects are measured before they are fixed;
  - mutation evidence is taken on a clean tree;
  - every delivered document carries a sha256.

## 7. Next

Planning the next slice, as the review directs. No code for it until its
plan is approved.
