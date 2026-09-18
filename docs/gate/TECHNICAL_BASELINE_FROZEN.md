# TURAB — Technical Baseline Freeze Record

**Status:** **FROZEN**
**Date:** 2026-09-18
**Authorised by:** Product/Technical owner, on the condition that the full gate
pass twice on a clean PostgreSQL 16.13 database using the official
`schema_v0.2.1.sql`. That condition was met — evidence in
[`GATE_RUN_REPORT.md`](GATE_RUN_REPORT.md).

---

## What is frozen

| | |
|---|---|
| **Handoff package** | TURAB Developer Handoff **v1.0.1** (official), vendored unmodified |
| **Executable database authority** | `schema_v0.2.1.sql` + `seed_master_data_v0.2.1.sql` |
| **Architecture / API baseline** | v0.2 — unchanged by this patch |
| **Product baseline** | Foundation v1.0 FINAL — unchanged |

### Pinned commit

```
f833fe7d05e160b048a6de1c4120f2c79015c3bb
```

Branch `claude/postgresql-execution-gate-yqifk7`. This commit contains the
official package byte-identical to the distributed archive, the gate harness,
and the CI workflow. It is the baseline any later change is measured against.

### Frozen artifact digests (SHA-256)

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `04_DATABASE/schema_v0.2.1.sql` | 67,336 | `9fac9fa2552d2963a8fc8c0745eea4c71a12c193c161268a073b64c216b42688` |
| `04_DATABASE/seed_master_data_v0.2.1.sql` | 12,499 | `c8edb576500e6726487deab121b85fc1f6b99f6a07cc3f87e557b123807409da` |
| `05_API/openapi_v0.2.yaml` | 124,280 | `8e4bd4fbf171adfb3724d6ebb1acdc5d72fac12503fdf67fa8aa2175bf294724` |

Each cross-checked against `TECHNICAL_PACK_MANIFEST_SHA256_v0.2.1.txt` and
`HANDOFF_MANIFEST.json`; all three sources agree.

### Gate evidence at freeze

Integrity 29/29 · hardened static audit PASS, 131 FK references · clean database
PostgreSQL 16.13 · schema PASS · seed ×2 PASS · **65/65** database assertions ·
OpenAPI PASS · **full gate PASS twice**. Live database confirms 131 foreign-key
constraints created and `schema_version = 0.2.1`.

---

## What freezing means

1. `docs/handoff/` is **never edited in place**. A correction arrives as a new
   official package, exactly as v1.0.1 superseded v1.0 — never as a patch to a
   vendored file. `verify_handoff.py` must keep reporting 29/29.
2. The frozen digests above are the reference. If CI ever computes a different
   digest for a frozen artifact, that is a defect in the checkout, not a new
   baseline.
3. Changing the frozen database baseline requires a new official package plus a
   full gate re-run, recorded here with a new pinned commit.
4. Every push and pull request re-runs the full gate
   (`.github/workflows/postgres-execution-gate.yml`). A red gate blocks the
   merge; it is not advisory.

---

## Slice 0 — now open

With the Pre-Slice Gate satisfied (`Master v1.0.1` §10), **Slice 0 — Application
Skeleton + Security Boundaries** is open. Per `IMPLEMENTATION_SLICES_v0.2.md`
and the kickoff checklist, Slice 0 must establish before any domain feature:

- the error contract;
- idempotency for mutating commands, with replay and conflict tests;
- **object-level** authorization, not role-only, with tests from the start;
- the Public / Customer / Internal DTO separation, enforced server-side.

Slices then proceed strictly in order. No advanced AI work begins before the
Core Hypothesis Stop Gate passes: `REQUEST → PROPERTY/OFFER → deterministic
candidate → Human Review → OPPORTUNITY`, working and explainable end to end.

### Standing approval boundary

Unchanged and still in force: any decision that alters the **domain model,
workflow, permissions or matching logic** requires approval *before*
implementation. Slice 0 reaches the permissions model directly — the
object-level authorization design will be raised for approval before it is
built, not after.
