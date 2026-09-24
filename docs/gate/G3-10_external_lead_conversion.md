# G3-10 · external-lead conversion and the leads queue — decisions requested

**Status:** DECIDED (review of `0a66f8e`). Conversion stays refused, now
**by decision**: `409 EXTERNAL_LEAD_CONVERSION_NOT_AVAILABLE`, renamed from
`…_UNDECIDED`, with a message citing the decision. The refusal writes nothing
and consumes no idempotency key. The queue choices are accepted **for this
slice only**. §4 records the decisions verbatim in substance.

## 1. What was delivered in step 3, and why only that

The plan pulled the three SOURCE operations into Slice 3 for one reason:
`ExternalLeadCreate` is the **only** declared way to create a `sources` row
(plan §1.5), and offer-source links need a source to exist.

- **Capture is delivered.** A source created through the API can now be
  linked to an offer end to end
  (`test_a_captured_source_can_be_linked_to_an_offer_end_to_end`).
- **The acquisition workflow is not.** IMPLEMENTATION_SLICES_v0.2.md places
  "External Lead queues … contact attempt outcome … assisted REQUEST/PROPERTY
  entry after consent" in **Slice 8**. Developer Reference Spec §5.5 describes
  that workflow: contact attempt → party → consent → assisted draft.
- **No contract operation moves a lead** between its ten statuses or records
  a contact attempt.

## 2. Conversion — four questions

API_CONTRACTS §4.3 says conversion "is allowed only after
contact/consent/data gates", "a PROPERTY lead cannot convert to a REQUEST and
vice versa", and it "produces one domain resource and preserves source
lineage". The body requires `party_id` and `consent_id`, and carries an
optional `target` and an open `payload`.

**Q-1 · The contact gate has no input.** A lead can only be `DISCOVERED`
through the API. Nothing records `CONTACT_ATTEMPTED`, `CONTACTED` or
`CONSENTED`.
- (a) Treat a valid `consent_id` of the named party as satisfying both the
  contact and the consent gates.
- (b) Refuse until a lead-status operation exists (Slice 8).
- (c) Add a lead-status operation as a Contract Delta.

**Q-2 · Consent binding for a PROPERTY is refused by the database.**
- `enforce_consent_binding()`, as tightened by `0003`, requires the
  consenting party to hold a **current** relation to the property.
- A property created by the conversion has none.
- Inferring a relation from a conversion is forbidden.

Options:
- (a) Do not bind at conversion. Record `consent_id` in the provenance trail
  only, and bind later once staff record a relation through G3-6.
- (b) Refuse PROPERTY conversion. Allow REQUEST conversion, whose binding
  checks `requests.party_id` and succeeds.
- (c) Require an existing relation. That is impossible for a property that
  does not yet exist, so (c) reduces to (b).

**Q-3 · The `payload` mapping.** `payload` is an open object.
- (a) Validate it as `RequestCreate` / `PropertyCreate`, with `party_id` taken
  from the body and the pair forced to `ASSISTED` / `UNCLAIMED` ("assisted
  draft", API_INVENTORY line 20).
- (b) Declare a conversion payload schema by Contract Delta.

**Q-4 · Lineage.** "Preserves source lineage":
- (a) the lead records `converted_request_id` / `converted_property_id` and
  `party_id`;
- (b) the provenance trail of the new resource carries `source_id = lead.source_id`;
- (c) both.

Nothing about conversion is implemented beyond the refusal.
`target ≠ lead_kind` will be refused as the contract states, whatever the
answers are.

## 3. The queue — provisional choices, all read-only and reversible

`getBackofficeQueuesExternalLeads` declares no parameters. It returns
`QueuePage { items: [QueueItem], next_cursor }`.

| # | Choice made | Why it is only provisional |
|---|---|---|
| Q-5 | Listed: every status except `CONVERTED`, `DECLINED`, `CLOSED`. `UNREACHABLE` **is** listed. | Listing more is the cautious side; excluding `UNREACHABLE` would hide a lead that may be retried. |
| Q-6 | `priority` is `NORMAL` for every lead. | No priority rule exists; any other value would invent one. |
| Q-7 | `kind` is `EXTERNAL_LEAD_<lead_kind>`; `reason` is the lead status. | QueueItem leaves both free-form. |
| Q-8 | Oldest first by `discovered_at`, ties broken by id. `next_cursor` is always `null`, and the list is not capped. | The operation declares no cursor or page parameter, so a cursor could not be passed back. A cap without one would hide leads silently. |

Items carry no floor field: no raw text, URL, metadata or source id.

## 4. Decisions (received with the review of `0a66f8e`)

| Question | Decision | Effect in code |
|---|---|---|
| Q-1 | **(b)** Proof of consent is not proof of a contact attempt. Conversion stays refused until a path records contact (Slice 8). | Refused. |
| Q-2 | **(b)** PROPERTY conversion is refused until an explicit path for the relation and the consent binding is defined. No relation is inferred from a conversion. | Refused. |
| Q-3 | **(b)** A conversion schema must be declared by an approved contract change before implementation. | Nothing implemented. |
| Q-4 | **(c)** When conversion exists: the lead records the produced resource id, and the produced resource's provenance carries `source_id`, in the same transaction. | Recorded as a requirement in `ConversionNotAvailable`'s docstring. Not implemented. |
| Q-5 to Q-8 | Accepted **for Slice 3 only**, exactly as documented in §3. | Unchanged. |

**Condition attached to Q-8.** Before the queue is used at operational
volume, a contract that allows paging is required. The absence of a page
parameter must never become a silent drop of items. Today nothing is dropped:
there is no cap, and `next_cursor` is always null.
