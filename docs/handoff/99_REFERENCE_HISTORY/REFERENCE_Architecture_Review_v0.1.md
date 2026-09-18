# تُراب — TURAB
## Technical Architecture Review v0.1

**تاريخ المراجعة:** 2026-09-18  
**النطاق:** `schema_v0.1.sql` + `seed_master_data_v0.1.sql` + `openapi_v0.1.yaml` + `API_CONTRACTS_v0.1.md` + `IMPLEMENTATION_SLICES_v0.1.md` + `REFERENCE_Developer_Spec_v0.1.md`  
**الغرض:** Red-team review قبل بدء أي تنفيذ فعلي لـSlice 0/1، مع محاولة كسر الـDomain Model والـAPI والـprivacy boundaries بالـedge cases الواقعية التي صُممت تُراب من أجلها.

---

# 1. الحكم التنفيذي

الحزمة **قوية مفاهيميًا لكنها ليست جاهزة للتنفيذ كما هي**.

السبب ليس أن الفكرة أو الـFoundation غير ناضجة؛ بالعكس، المبادئ الأساسية واضحة جدًا. المشكلة أن الانتقال من الـDeveloper Spec إلى الـSQL/OpenAPI أدخل عدة فجوات يمكن أن تكسر بالضبط المبادئ التي نريد حمايتها، خصوصًا عند تعدد `PROPERTY_OFFER`، تغير المعلومات بعد إنشاء Match، Assisted Entry، الخصوصية، وإعادة بناء سبب Opportunity تاريخية.

**قرار المراجعة:**

> **NO-GO for implementation against Technical Pack v0.1 as-is.**
>
> يسمح بالاستفادة منه كـreference، لكن يجب إغلاق P0 blockers وإصدار Technical Pack v0.2 قبل بدء بناء الـDomain/Matching core.

هذه نتيجة إيجابية للمشروع: اكتشاف هذه الفجوات الآن أرخص بكثير من اكتشافها بعد وجود بيانات حقيقية وواجهات ومستخدمين.

---

# 2. ما تم التحقق منه فعليًا

أجريت فحصًا يدويًا ومعماريًا، وفحصًا ساكنًا آليًا بسيطًا للحزمة.

## 2.1 نتائج الفحص الساكن

- تم اكتشاف **39 جدولًا** في الـSQL.
- تم اكتشاف **104 مرجع FK**؛ كل الأهداف التي أمكن تحليلها ساكنًا تشير إلى جداول/أعمدة موجودة.
- OpenAPI 3.1 يُقرأ بنجاح كـYAML.
- **46 paths** و**49 operations** و**36 component schemas**.
- لا توجد `$ref` محلية مفقودة.
- كل path parameter الظاهر في URI له declaration.
- **49/49 operations لا تحمل `operationId`**.
- توجد **11 أوامر POST متغيرة للحالة** لا تعرض `Idempotency-Key` رغم أن العقد السلوكي يطلب idempotency للقرارات/الإنشاءات القابلة لإعادة المحاولة.
- أربعة PATCH endpoints تقبل `additionalProperties: true` بلا whitelist حقول.
- `/public/properties` يعيد نفس `Property` schema الداخلية.

ملفات الفحص المرفقة:

- `technical_pack_static_audit.py`
- `STATIC_AUDIT_RESULTS_v0.1.json`

## 2.2 قيد مهم

لم يتم تشغيل `schema_v0.1.sql` ضد PostgreSQL حقيقي لأن البيئة الحالية لا تحتوي PostgreSQL server/client ولا يمكن جلب packages من الإنترنت. لذلك:

> هذه مراجعة معمارية/ساكنة صارمة، **وليست migration execution proof**.

يظل تنفيذ migration على PostgreSQL 16 نظيف شرطًا إلزاميًا قبل قبول v0.2.

---

# 3. P0 — Blockers يجب إغلاقها قبل التنفيذ

## P0-01 — الـMatching لا يعرف أي عرض تجاري تم استخدامه

### الوضع الحالي

- `PROPERTY` منفصلة عن `PROPERTY_OFFER` وهذا صحيح.
- السعر، `seller_expectation_dzd`، `permission_scope` و`last_confirmed_at` موجودة على `property_offers` (`schema_v0.1.sql`, تقريبًا 375–396).
- لكن `match_candidates` تحفظ `request_id + property_id` فقط، بلا `offer_id` أو commercial context (`570–591`).
- `OPPORTUNITY` أيضًا تحفظ `request_id + property_id + approved_match_id` فقط (`671–690`).
- `REQUEST` نفسها لا تحتوي transaction intent يفرق BUY/RENT، بينما Offers تملك `SALE/RENT`.

### لماذا هذا Blocker

يمكن لنفس PROPERTY أن يكون لها:

- Owner Sale Offer بسعر 2.4B.
- Broker Sale Offer بسعر 2.7B.
- Rent Offer منفصلة.
- Private offer بصلاحيات مختلفة.

لا يمكننا بعدها تفسير:

- أي سعر استُخدم في budget PASS؟
- أي permission scope اجتاز الـgate؟
- أي freshness تخص الشروط التجارية؟
- هل الطلب أصلًا شراء أم إيجار؟

### القرار المقترح

1. أضف intent صريحًا للطلب: `BUY` / `RENT` (أو اجعل pilot `BUY_ONLY` واحذف RENT مؤقتًا؛ لا نتركها مبهمة).
2. لا تجعل Opportunity فريدة حسب offer؛ تبقى uniqueness على `REQUEST × PROPERTY` كما اعتمدنا.
3. لكن Match يجب أن يحفظ **commercial context** استُخدم في التقييم:
   - `evaluated_offer_id` إن كانت هناك Offer محددة.
   - أو `commercial_context_snapshot` للحالات Potential/غير المرتبطة بعرض منشور.
4. يجب أن تسجل Opportunity `selected_offer_context` أو مرجع العرض الذي يحدد شروط المشاركة الحالية، مع السماح بتغييره عبر Review دون إنشاء Opportunity جديدة لنفس property.
5. freshness يجب أن تفصل بين:
   - physical/property availability freshness.
   - commercial terms/offer freshness.

### Acceptance test حاسم

نفس PROPERTY لها Sale Offer بسعر 24M DZD وRent Offer بـ70k/month. طلب شراء لا يجوز أن يستخدم سعر الإيجار ولا صلاحيات Offer الإيجار.

---

## P0-02 — `request_version/property_version` لا تعيد بناء الـMatch تاريخيًا

### الوضع الحالي

`match_candidates` تحفظ:

- `request_version`
- `property_version`
- `matching_policy_version`

لكن:

- تعديل `request_criteria` لا يرفع `requests.version`.
- إضافة/تعديل Claim أو `resolved_values` لا يرفع `properties.version`.
- تغيير `property_offer` له version منفصلة لا تُحفظ في Match أصلًا.
- لا توجد Request snapshot/Property snapshot/Offer snapshot محفوظة داخل Match.
- الـaudit لا يكفي لإعادة بناء الحالة المركبة، فضلًا عن أن `audit_log.entity_id` لا يُملأ حاليًا.

### لماذا هذا Blocker

الـDeveloper Spec يشترط أن نستطيع الإجابة لاحقًا:

> لماذا اقترح النظام هذا العقار في ذلك اليوم؟

النسخة الحالية لا تضمن ذلك.

### القرار المقترح للـv0.2

الأبسط والأكثر أمانًا للـPilot:

```text
match_candidates
  request_snapshot JSONB
  property_snapshot JSONB
  commercial_context_snapshot JSONB
  permission_snapshot JSONB
  freshness_snapshot JSONB
  input_hash TEXT
```

مع snapshot موحدة canonical تمثل **بالضبط inputs التي قرأها المحرك**. تبقى version numbers metadata مساعدة وليست الدليل الوحيد.

ويمكن لاحقًا الانتقال إلى aggregate revision tables إذا أثبتت الحاجة.

### Acceptance test

أنشئ Match ثم غيّر budget criterion والسعر ونوع الوثيقة. GET على الـMatch القديم يجب أن يعرض inputs القديمة ويعيد نفس criterion results دون الرجوع للحالة الحالية.

---

## P0-03 — تأكيد `CONFIRMED_SAME` لا يحل هوية العقار فعليًا

### الوضع الحالي

`property_identity_candidates` تحفظ قرار SAME/DISTINCT/UNSURE (`536–554`).

لكن لا يوجد:

- canonical_property pointer.
- identity alias/membership.
- re-parenting rule.
- invalidation/remap للـmatches.

وبالتالي يستطيع الموظف تأكيد أن P10 وP20 نفس العقار بينما يظلان `properties` مستقلتين، فتستمر المطابقة معهما كعقارين.

### لماذا هذا Blocker

هذا يكسر جوهر:

> `PROPERTY ≠ POST` و«Opportunity واحدة لكل REQUEST × PROPERTY الحقيقي».

### القرار المقترح

لـv0.2، بدون حذف تاريخ:

- أضف `canonical_property_id` self-FK أو table هوية مستقلة.
- عند `CONFIRMED_SAME`:
  - نختار canonical identity.
  - السجل الآخر يصبح alias/resolved identity، **لا يُحذف**.
  - كل الاستعلامات الجديدة والمطابقة تستخدم canonical id.
  - Offers/Sources/Claims القديمة تظل provenance صالحة، لكن Effective Property View تجمعها تحت canonical identity.
  - Existing open matches/opportunities على alias تُراجع transactionally.

لا نستخدم destructive merge.

---

## P0-04 — Consent/Permission ليست مربوطة بالموارد بطريقة آمنة

### الوضع الحالي

`consent_grants` Granular حسب scope وهذا جيد، لكن:

- REQUEST/PROPERTY تحمل `consent_id` واحدة فقط.
- لا يوجد ضمان أن consent تخص نفس `party_id` صاحب المورد.
- لا يوجد ضمان أن scope هي `ASSISTED_ENTRY` أو `PUBLIC_LISTING_ALLOWED` المناسبة للعملية.
- `property_offers.permission_scope` يمكن أن تقول `PROPERTY_DETAILS_ALLOWED` دون lineage مباشر إلى consent.
- لا يوجد endpoint واضح للـrevocation.

### الخطر

قد يصبح Assisted/Public record مفعّلًا بموافقة خاطئة، لطرف آخر، أو scope مختلفة.

### القرار المقترح

استبدل/أكمل `consent_id` بعلاقة صريحة مثل:

```text
resource_consent_bindings
  consent_id
  resource_type
  resource_id
  purpose
```

أو أضف subject إلى `consent_grants` نفسها. ويجب أن يتحقق PermissionService من:

- نفس Party.
- Scope المطلوبة.
- grant كانت فعالة في وقت القرار.
- revocation الحالي قبل share/new opportunity.

`permission_gate` يجب أن يحفظ snapshot لمصدر الإذن الذي اعتمد عليه.

---

## P0-05 — Privacy contract غير قابل للفرض من OpenAPI الحالي

### الوضع الحالي

`/public/properties` يعيد `#/components/schemas/Property`، و`Property` مبنية فوق `PropertyCreate` التي تتضمن حقولًا داخلية مثل:

- `management_mode`
- `consent_id`
- `claim_status`
- `supply_mode`

أيضًا GET لـParty/Request/Property/Opportunity يسمح لـ`CUSTOMER` عبر `x-roles`، لكن لا يوجد object-level authorization contract يحدد أن العميل يرى **موارده فقط** أو Opportunity موجّهة له.

### لماذا هذا Blocker

الـrole وحده لا يمنع IDOR/BOLA: عميل يعرف UUID لعميل آخر قد يحصل على بياناته إذا نفذ المطور x-roles حرفيًا فقط.

### القرار المقترح

افصل DTOs:

- `PublicPropertySummary`
- `CustomerPropertyView`
- `OperatorPropertyView`
- `CustomerOpportunityView`
- `InternalOpportunityView`

واكتب Object Authorization Matrix صريحة:

```text
CUSTOMER + Party -> only self/authorized party
CUSTOMER + Request -> only owned/claimed request
CUSTOMER + Property -> own managed property OR public projection only
CUSTOMER + Opportunity -> only opportunity whose request belongs to caller
```

والحقول الداخلية لا تدخل schema العامة أصلًا، بدل الاعتماد فقط على “لا ترسلها”.

---

## P0-06 — PATCH العام يسمح بتجاوز الـDomain Commands

### الوضع الحالي

هذه endpoints تقبل arbitrary object:

- `PATCH /parties/{id}`
- `PATCH /requests/{id}`
- `PATCH /properties/{id}`
- `PATCH /offers/{id}`

مع أن API Contract نفسه يقول إن status transitions والموافقة والـfreshness يجب أن تمر عبر Commands.

### الخطر

مطور قد يسمح بطريق الخطأ بـ:

- `PATCH request.status=ACTIVE`
- تغيير `current_availability` دون reconfirm event.
- تغيير `consent_id`/supply mode بلا gate.
- تعديل permission مباشرة.

### القرار المقترح

- استبدل كل generic patch بـtyped patch schemas مع `additionalProperties: false`.
- استبعد state/gate/consent fields من patch العادي.
- استخدم Commands منفصلة للحالات الحساسة.
- `MATCH_CANDIDATE` تصبح immutable بعد الإنشاء.
- `opportunity.request_id/property_id/approved_match_id` immutable.
- Opportunity gate يجب أن يحمي update أيضًا من أي تغيير يخرق المرجعية، لا INSERT فقط.

---

## P0-07 — Truth Layer تسمح بخطأ lineage صامت

### الوضع الحالي

يمكن تقنيًا أن:

- `resolved_values.source_claim_id` تشير إلى Claim تخص Property أخرى أو attribute آخر.
- `property_attributes.resolved_claim_id` تشير إلى Claim مختلفة.
- `claims.verification_level` يُكتب مباشرة، وفي الوقت نفسه توجد `verification_events` مستقلة.
- API `ClaimInput` يسمح أصلًا بإرسال `verification_level=DOCUMENT_SEEN/DETAILS_MATCHED` مباشرة.

### لماذا هذا Blocker

هذا يسمح بتحويل AI/Operator write إلى “Verified” دون Verification Event ويكسر المبدأ:

> Declared ≠ Checked/Verified.

### القرار المقترح

1. `ClaimInput` لا يسمح بإنشاء Claim أعلى من `DECLARED` إلا import migration موثوق.
2. المستوى الفعال يُشتق من أحدث Verification Event صالح أو يحافظ عليه trigger/service projection غير قابل للتعديل مباشرة.
3. Trigger/Domain check: `source_claim_id` يجب أن يطابق نفس subject ونفس attribute.
4. `resolved_value` الحالية لا تُستبدل إلا transactionally: supersede old + insert new + update operational projection.

---

## P0-08 — يوجد أكثر من “Source of Current Truth” بلا عقد مزامنة

### الوضع الحالي

لدينا current fields مباشرة:

- `properties.land_area_m2`, `built_area_m2`, `current_availability`...
- `property_offers.asking_price_dzd`...
- `requests.budget_*`...

ولدينا في الوقت نفسه:

- Claims
- `resolved_values`
- `property_attributes.resolved_claim_id`

لكن الحزمة لا تقول بدقة أي طبقة authoritative وكيف تتزامن atomically.

### الخطر

المطور قد يحدث property column وينسى claim/resolution، أو العكس. عندها Matching تقرأ قيمة، وBack Office تعرض قيمة أخرى.

### القرار المقترح

اعتماد مبدأ واضح للـv0.2:

> **Core tables are the operational projection; Claims/Observations are immutable lineage. Every change to a critical current fact goes through one Domain Command that atomically writes provenance + resolution + projection.**

ولا يسمح بكتابة core critical facts من repository عام خارج هذه commands.

---

# 4. P1 — High-priority issues

## P1-01 — `audit_log.entity_id` لا يُملأ

الـtrigger يكتب `NULL` للـentity_id في INSERT/UPDATE/DELETE (`schema`, 841–875)، مع أن هناك index مبنيًا عليه.

**الإصلاح:** generic trigger يأخذ PK column عبر `TG_ARGV` ويستخرج UUID من OLD/NEW، أو audit functions مخصصة للجداول الأساسية.

---

## P1-02 — Match review history تُختزل إلى صف واحد

`match_reviews.match_id` = UNIQUE. حالة `NEED_MORE_INFORMATION -> APPROVED` ستعدل الصف أو تمنع قرارًا ثانيًا. التعلم يحتاج sequence كامل للقرارات.

**الإصلاح:** اجعل reviews append-only، ويمكن حفظ `current_review_decision` projection منفصلة أو query لآخر review.

---

## P1-03 — Task completion contract لا يملك مكانًا لحفظ نتيجة الإغلاق

API `/tasks/{id}/complete` يقبل:

- `outcome_code`
- `note`
- `evidence_observation_id`

لكن جدول `tasks` لا يحفظها؛ لديه فقط `completed_at` و`payload`.

**الإصلاح:** fields صريحة أو `task_completion_events` append-only.

---

## P1-04 — Idempotency مذكورة لكن غير مكتملة

لا يوجد idempotency store في schema، و11 أوامر POST لا تعرض header في OpenAPI.

**الإصلاح:** `idempotency_records(actor_id, route_key, idem_key, request_hash, response_ref, status, expires_at)` + coverage موحدة لكل command القابل للتكرار/webhook.

---

## P1-05 — phone/account source of truth مزدوج وغير مناسب للأرقام المشتركة

- `party_phones.phone_e164` UNIQUE عالميًا.
- `user_accounts.phone_e164` نسخة مستقلة UNIQUE.

قد يكون نفس رقم الهاتف مستعملًا لعائلة/شركة/وسيط، ولا ينبغي أن يصبح الهاتف هوية الشخص نفسها.

**الإصلاح:** حساب login يرتبط بوسيلة اتصال verified عبر FK، أو ContactPoint مستقل. وإذا قررنا أن الرقم لا يمكن أن يرتبط إلا Party واحدة في Pilot، يجب توثيق القرار كقيد سوق صريح لا نتيجة عرضية للschema.

---

## P1-06 — Assisted records قد تبدأ `CLAIMED` بالخطأ

`requests.claim_status` و`properties.claim_status` default = `CLAIMED`، بينما Assisted Entry المرجعي يبدأ `UNCLAIMED`.

**الإصلاح:** لا default عام؛ domain command يحدد claim status حسب management mode. أضف CHECK/trigger يمنع `ASSISTED + CLAIMED` بلا claim event/account linkage صالح.

---

## P1-07 — matching policy integrity ناقصة

- `match_candidates.matching_policy_version` ليست FK.
- لا يوجد partial unique index يضمن Policy active واحدة.
- seed لا يحدد freshness thresholds فعلية.

**الإصلاح:** FK إلى `matching_policies(version)`, unique partial active, versioned config صريحة للـfreshness.

---

## P1-08 — freshness التجارية مفقودة

لدينا property freshness وoffer `last_confirmed_at`، لكن Match تحفظ `property_freshness` فقط.

**الإصلاح:** `commercial_freshness`/`offer_freshness` ضمن gates/snapshot، لأن السعر والإذن قد يقدمان أسرع من هوية العقار نفسها.

---

## P1-09 — Master Data القانونية الأساسية غير معرفة فعليًا

Seed يعرّف attribute codes `RIGHT_TYPE`, `DOCUMENT_TYPE`, `DOCUMENT_STATUS` لكنه لا يعرّف allowed options التي ثبتناها في Foundation.

**الإصلاح:** reference tables/options versioned لنوع الحق/الوثيقة/الحالة. لا نتركها free JSON/strings إذا كانت Hard Criteria.

---

## P1-10 — Reason Code drift

الـDeveloper Spec يذكر `DEAL_REPORTED` في موضع، بينما seed/API تستخدم `DEAL_CONFIRMED`. توجد أيضًا أسماء مختلفة مثل `BUDGET_OVER_MAX` مقابل `BUDGET_EXCEEDED`.

**الإصلاح:** reason code registry واحدة هي المصدر الرسمي وتُولد منها OpenAPI/seed/tests.

---

## P1-11 — Back Office Queues غير ممثلة بالكامل في الـAPI

لا توجد list/query contracts واضحة لـ:

- external leads queue
- requests queue
- properties queue
- pending match reviews
- opportunities needing follow-up

GET by id لا يكفي لتشغيل Back Office الذي وصفناه.

---

## P1-12 — Consent revocation وphone-control flows ناقصة في API

لا يوجد command واضح:

- revoke consent
- bind OTP VERIFY_PHONE إلى Party phone دون إنشاء Account

`/auth/otp/verify` يتطلب `account_id` في response، وهذا يتعارض مع PARTY يمكن أن توجد بلا USER_ACCOUNT ويظل الهاتف verified control.

---

## P1-13 — Public publication eligibility ناقصة

`PUBLIC PROPERTY` لا تكفي وحدها للعرض للعامة. يجب وجود commercial/public context صالح:

- offer active/relevant
- permission يسمح
- ليست withdrawn
- price visibility applied
- confidential fields redacted

الـendpoint الحالي يصف فقط “PUBLIC properties”.

---

## P1-14 — Communication links يمكن أن تربط كيانات غير متسقة

Thread يمكن أن يشير إلى Party A + Request of Party B + Opportunity أخرى بلا check. نفس الشيء Interactions/Tasks.

**الإصلاح:** service-level consistency invariants + tests. في البيانات الحساسة يفضل trigger لبعض العلاقات الأساسية.

---

## P1-15 — WhatsApp dedup/replay يحتاج provider identity صريحة

`UNIQUE(thread_id, external_message_ref)` مفيد، لكنه يفترض أن thread resolved correctly قبل dedup. نحتاج provider/channel identity + webhook event id/replay protection.

---

## P1-16 — Hard-delete behavior يتعارض مع حفظ التاريخ

Core subjects لديها عدة `ON DELETE CASCADE`. لا توجد DELETE endpoints، لكن schema نفسها تسمح بمحو Claims/history إذا استُخدمت صلاحية DB خاطئة.

**الإصلاح:** application DB role بلا DELETE على core entities، أو triggers/RESTRICT + soft closure. Join tables التقنية فقط يمكن أن تعتمد CASCADE حيث لا يمس provenance.

---

# 5. P2 / Quality improvements

1. **كل 49 OpenAPI operations بلا `operationId`** — أضف IDs ثابتة قبل code generation/SDK/tests.
2. `Idempotency-Key` و`If-Match` معرفة كـoptional؛ للـcommands الحساسة يجب تحديد أين تصبح Required.
3. Inputs ينبغي أن تستخدم `additionalProperties: false` افتراضيًا لتقليل over-posting.
4. `is_primary` في `party_phones` و`property_offer_sources` لا يضمن واحدة فقط؛ أضف partial unique إن كان semantics “واحدة”.
5. `attribute_code` و`criterion_code` free text؛ نحتاج registry أو validator مركزي يمنع typos من أن تصبح بيانات دائمة.
6. AI trace موجود كـ`ai_trace_ref` فقط؛ يجب تحديد contract أدنى: provider/model/prompt_or_parser_version/trace_id، سواء داخليًا أو عبر observability backend.
7. `/locations` محمي Bearer حاليًا، بينما UX المعتمد يسمح بملء Request/Browse قبل login؛ master location read ينبغي أن يكون public أو anonymous-safe.
8. pagination page-based مقبولة للPilot، لكن queues الحية قد تستفيد لاحقًا من cursor/keyset.

---

# 6. Edge-case Red Team Matrix

| ID | السيناريو | المتوقع وفق Foundation | v0.1 الحالية |
|---|---|---|---|
| E01 | نفس PROPERTY، Owner offer 2.4B وBroker offer 2.7B | Match يعرف العرض/السعر المستخدم؛ Opportunity واحدة | **Ambiguous/Fail** — no offer context |
| E02 | نفس PROPERTY للبيع وللإيجار | Request intent يمنع cross-transaction match | **Fail** — no request transaction intent |
| E03 | Potential property بلا public offer | يمكن Candidate داخلي مع willingness/reconfirm | **Ambiguous** |
| E04 | تعديل Required criterion بعد Match | الـMatch القديم يبقى replayable | **Fail** — request version لا يلتقط child criterion |
| E05 | document resolved value يتغير بعد Match | history القديم ثابت | **Fail** — property version لا يتغير ولا snapshot |
| E06 | offer price يتغير بعد Match | old match يحتفظ commercial snapshot | **Fail** |
| E07 | consent revoked بعد approval وقبل share | share يُمنع/revalidate | **Partial/Ambiguous** |
| E08 | private seller expectation استُخدمت في score | لا تظهر للعميل | **Risk** — DTO separation غير machine-enforced |
| E09 | reviewer: NEED_INFO ثم APPROVE | القرارين محفوظان | **Fail** — one review row |
| E10 | P10 وP20 confirmed same physical property | canonical identity واحدة بلا حذف provenance | **Fail** — decision لا يطبق identity |
| E11 | resolved value تستند إلى Claim من Property أخرى | ممنوع | **Fail** — no subject check |
| E12 | Customer يطلب Party UUID لشخص آخر | 403/404 | **Underspecified** — role فقط |
| E13 | رقم واتساب عائلي/شركة مشترك | لا يُجبر على دمج Parties | **Conflict** — global unique phone |
| E14 | PROPERTY external lead يُحوّل إلى REQUEST | ممنوع إلا explicit corrected workflow | **DB permits both refs** |
| E15 | duplicated webhook بعد retry | message واحدة | **Partial** |
| E16 | task complete with evidence | evidence/outcome محفوظ | **Fail** — API fields absent in DB |
| E17 | PUBLIC property لكن كل offers withdrawn | لا تظهر في public browse | **Underspecified** |
| E18 | hard delete property by DB user | history لا تضيع | **Fail/Risk** — cascades |
| E19 | generic PATCH sets request.status مباشرة | ممنوع | **Risk/Fail** |
| E20 | 0 exact matches | 0 opportunity + diagnostic | **Conceptually covered** |
| E21 | required document UNKNOWN | Need Info, لا Fail | **Covered conceptually** |
| E22 | seller says “negotiable” only above max | UNKNOWN/Potential price | **Covered in spec, needs offer context** |
| E23 | same physical property three sources | one property identity, sources preserved | **Model supports sources but identity application incomplete** |
| E24 | Ksar Tililane vs New City Tililane | distinct canonical IDs | **Covered by seed** |

---

# 7. خمسة قرارات معمارية يجب تثبيتها في v0.2

## Decision A — Matching Commercial Context

**المقترح:** Request تحمل transaction intent. Match تظل Request×Property لكن تحفظ offer/commercial context التي استُخدمت. Opportunity تبقى واحدة لكل pair وتستطيع تحديث/اختيار Offer دون تكرار الفرصة.

**Design Ledger:** نعتمد الآن؛ ضروري لصحة الـCore.

## Decision B — Match Snapshot Strategy

**المقترح:** immutable canonical JSON snapshots + hash لكل Match في 0.2 بدل بناء versioned aggregate/event sourcing كامل.

**Design Ledger:** نعتمد الآن؛ minimal architecture تحقق auditability بأقل تعقيد.

## Decision C — Canonical Property Identity

**المقترح:** confirmed duplicate يصبح alias إلى canonical property، لا destructive merge. كل matching الجديد يستخدم canonical ID.

**Design Ledger:** نعتمد الآن.

## Decision D — Consent Binding

**المقترح:** consent مربوطة resource/purpose مع party consistency، ولا نعتمد `consent_id` عامة واحدة كدليل لكل permissions.

**Design Ledger:** نعتمد الآن.

## Decision E — Operational Projection

**المقترح:** Core tables = current operational projection؛ Claims/Observations/Verification = lineage. كل تعديل critical fact command واحد يكتب الاثنين transactionally.

**Design Ledger:** نعتمد الآن.

---

# 8. تغييرات يمكن تطبيقها مباشرة دون قرار منتج جديد

هذه إصلاحات هندسية لا تغير فلسفة TURAB:

- populate audit `entity_id`.
- operationIds لكل OpenAPI operation.
- typed PATCH schemas.
- idempotency store + header coverage.
- `matching_policy_version` FK + one active policy.
- append-only match review history.
- task completion event/fields.
- consent revoke command.
- public/customer/internal DTO separation.
- object authorization matrix.
- controlled document/right options.
- reason-code registry normalization.
- public location lookup anonymous-safe.
- partial unique primary phone/source where semantics require.
- provider webhook dedup/replay contract.

---

# 9. Gate قبل بدء التنفيذ

لا أوصي ببدء Slice 0/1 من pack v0.1 ثم “نصلح لاحقًا”، لأن بعض التغييرات تمس IDs والعلاقات والـAPI contracts.

الترتيب الصحيح الآن:

```text
1. Approve P0 architectural decisions
2. Produce Technical Pack v0.2
3. Execute schema on clean PostgreSQL 16
4. Run OpenAPI validator + generated client/server smoke test
5. Run red-team acceptance suite
6. Freeze v0.2
7. Start Slice 0
```

## Definition of Ready for v0.2

لا نعتبر الحزمة جاهزة إلا إذا:

- BUY/RENT or pilot scope واضح وغير قابل للخلط.
- Match commercial context محفوظة.
- Match historical inputs replayable.
- SAME identity يطبق canonicalization فعلية.
- Consent/permission lineage قابلة للإثبات.
- Public DTO لا تحتوي internal fields.
- Object authorization موثق ومختبر.
- Generic patch bypass مغلق.
- Truth resolution لا تقبل claim من subject/attribute خطأ.
- Verification لا يمكن ترقيتها بمجرد Claim write.
- critical current state/provenance يكتبان atomically.
- review history محفوظة.
- task outcome/evidence محفوظة.
- idempotency/audit يعملان فعليًا.
- migration يمر على PostgreSQL حقيقي.

---

# 10. الخلاصة

**الـFoundation سليمة؛ الفجوة في ترجمة بعض المبادئ إلى عقود تقنية قابلة للفرض.**

أخطر خطأ لو بدأنا البرمجة الآن هو أن نبني “Matching بين Request وProperty” ثم نكتشف لاحقًا أن السعر والإذن والـfreshness جاءت من Offer غير محفوظة في الـMatch، وأن النسخ التاريخية غير قابلة لإعادة البناء، وأن `CONFIRMED_SAME` لا يوحد هوية العقار فعليًا.

لذلك المراجعة لا تقترح إضافة Features؛ بل العكس: **تغلق الثغرات التي قد تجعل النظام يتصرف مثل CRUD عقاري عادي رغم أن الـFoundation صُممت لتكون أكثر دقة.**

الخطوة الصحيحة التالية هي إصدار **TURAB Technical Implementation Pack v0.2 — Remediated** بعد اعتماد القرارات الخمسة أعلاه، وليس بدء الكود على v0.1.
