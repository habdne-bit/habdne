# Migration Notes — Technical Pack v0.1 → v0.2

v0.1 was reviewed and explicitly declared NO-GO before implementation. Therefore v0.2 is intended to be used as a **fresh baseline**, not as a production migration.

If a developer created a disposable v0.1 development database, the recommended action is:

1. export any synthetic fixtures worth keeping;
2. drop/recreate the development database;
3. run `schema_v0.2.sql`;
4. run `seed_master_data_v0.2.sql`;
5. adapt fixtures to the v0.2 contracts.

A direct in-place SQL migration is intentionally not supplied because major pre-production corrections are structural:

- `party_phones` → `contact_points` + many-to-many party links;
- request transaction intent added;
- direct request/property consent reference replaced by resource-scoped binding;
- match snapshots/commercial context added;
- match review changed to append-only history;
- canonical property aliasing added;
- verification semantics changed;
- customer/public DTO boundaries changed.

Building a one-off migration before any real data exists would add unnecessary complexity and could create false compatibility expectations.
