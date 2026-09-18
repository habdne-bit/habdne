# تُراب — TURAB
## Developer Handoff Master v1.0.1

**الحالة:** حزمة التسليم الرسمية للمطور  
**التاريخ:** 2026-09-18  
**مرجع المنتج:** `TURAB Foundation Baseline v1.0 FINAL`  
**مرجع التنفيذ التقني:** `Technical Implementation Pack v0.2` + Database Patch `v0.2.1`  
**قرار البدء:** **Conditional GO** — لا يبدأ التنفيذ الفعلي قبل اجتياز `POSTGRES_EXECUTION_GATE.md` على PostgreSQL 16+.

---

# 1. الغرض من هذه الحزمة

هذه الحزمة هي نقطة البداية الرسمية للمطور. هدفها أن تمنع الاجتهادات غير المقصودة، وتوضح الفرق بين القرارات الملزمة والخيارات المؤجلة، وتضع ترتيبًا صريحًا للمراجع عند وجود أي تعارض.

المطلوب من المطور ليس «بناء تطبيق عقارات» بالمعنى العام، بل تنفيذ النواة المحددة لتُراب كما تم اعتمادها: نظام يبدأ من **REQUEST** و**PROPERTY**، ينظم بيانات السوق ومصادرها، يكتشف المطابقات القابلة للتفسير، يمررها للمراجعة البشرية، ولا ينشئ **OPPORTUNITY** قبل استيفاء شروط المعنى والحداثة والإذن والمراجعة.

التعريف المرجعي للمنتج هو:

> **تُراب منصة عقارية محلية تبدأ من حاجة المشتري، وتنظم العرض المتاح وغير المعلن، وتطابق بينهما للوصول إلى فرصة عقارية حقيقية.**

كل قرار تقني يجب أن يحافظ على هذا التعريف وألا يحول المنتج إلى Listing Portal تقليدية أو CRM ضخم أو نظام AI ذاتي القرار.

---

# 2. حالة المشروع عند التسليم

تم تجميد الأساس المنتجـي في `Foundation Baseline v1.0 FINAL`. ثم أُعدت مواصفة مطور تفصيلية، وبعدها Schema وOpenAPI وخطة تنفيذ. خضعت الحزمة التقنية v0.1 لمراجعة Red-Team صارمة، وأُغلقت ملاحظات P0/P1 في النسخة التقنية v0.2.

الحزمة التقنية v0.2 اجتازت المراجعة الساكنة أولًا، ثم كشف PostgreSQL Execution Gate تكرار FK فعليًا في الـSchema. أُصدر Patch تصحيحي `v0.2.1` دون تغيير دلالات المنتج أو الـAPI، وتم تحسين الفحص الساكن لمنع تكرار هذا النوع. الحالة الحالية لـ`schema_v0.2.1.sql` هي **Static Audit PASS** مع:

- 48 جدولًا.
- 54 Type.
- 17 Function.
- 37 Trigger.
- 55 Index.
- 131 Foreign-Key Reference.
- 12 named cross-section FK constraints.
- 0 duplicate FK names / 0 semantic duplicate FKs detected by hardened audit.
- 16 بلدية لولاية أدرار ضمن Seed.
- OpenAPI 3.1.0.
- 61 Path.
- 64 Operation.
- 59 Component Schema.
- 527 `$ref` داخلية بدون كسر.

ويبقى Gate الإصدار الحاسم: إعادة تشغيل `schema_v0.2.1.sql` والـSeed فعليًا على PostgreSQL 16+ واختبار القيود والـTriggers. فشل v0.2 في هذا الـGate هو الذي أدى إلى Patch v0.2.1. لذلك حالة الحزمة هي:

> **Static Architecture: PASS on database patch v0.2.1**  
> **PostgreSQL Runtime Gate: PENDING RE-RUN**  
> **Implementation Status: CONDITIONAL GO**

هذا الـGate Release Blocker وليس خطوة شكلية.

---

# 3. ترتيب السلطة عند وجود تعارض

يجب على المطور اتباع ترتيب المراجع التالي. لا يجوز حل التعارض بالاجتهاد الشخصي.

| الأولوية | المرجع | ماذا يحكم؟ |
|---|---|---|
| 1 | `TURAB_Foundation_Baseline_v1.0_FINAL.docx` | معنى المنتج، المبادئ، الحدود، القرارات التأسيسية |
| 2 | `TURAB_Project_Instructions_v1.0.md` | منهج اتخاذ القرار، Design Ledger، منع Feature Creep |
| 3 | `ARCHITECTURE_DECISIONS_v0.2.md` + `TECHNICAL_PATCH_v0.2.1.md` | القرارات التقنية الملزمة وتصحيح executable database baseline |
| 4 | `TURAB_Developer_Reference_Spec_v0.1.*` | السلوك التفصيلي المطلوب من النظام |
| 5 | `API_CONTRACTS_v0.2.md` + `openapi_v0.2.yaml` | حدود الخدمات والعقود والـDTOs والصلاحيات |
| 6 | `schema_v0.2.1.sql` + `seed_master_data_v0.2.1.sql` | النموذج المادي الحالي وقواعد قاعدة البيانات |
| 7 | `IMPLEMENTATION_SLICES_v0.2.md` | ترتيب التنفيذ وStop Gates |
| 8 | `RED_TEAM_ACCEPTANCE_TESTS_v0.2.md` | حالات القبول الإلزامية |
| مرجعي فقط | ملفات `99_REFERENCE_HISTORY` | لماذا تغيرت القرارات؛ لا تُستخدم كBaseline تنفيذية |

إذا ظهر تناقض بين ملفين من نفس المستوى أو بين OpenAPI والـSchema، يتوقف التنفيذ في النقطة المتأثرة، ويُفتح قرار معماري/منتجي واضح. **لا يُسمح للمطور باختيار أحد التفسيرين بصمت.**

---

# 4. المبادئ غير القابلة للكسر

هذه ليست اقتراحات تصميمية؛ هي Invariants يجب أن تظهر في قاعدة البيانات، الخدمة، الـAPI، الاختبارات، والواجهات:

1. **REQUEST وPROPERTY كيانان أساسيان متساويان.** لا تُبنى تُراب حول الإعلانات فقط.
2. **PROPERTY ≠ POST / SOURCE.** PROPERTY هي العقار الفيزيائي، والمنشور مجرد مصدر.
3. **PROPERTY ≠ PROPERTY_OFFER.** نفس العقار يمكن أن تكون له عروض تجارية متعددة، أسعار مختلفة، أطراف مختلفة، SALE وRENT، وإذن مختلف.
4. **INTEREST ≠ REQUEST.** الضغط على «مهتم» لا ينشئ طلبًا كاملًا صامتًا.
5. **MATCH_CANDIDATE ≠ OPPORTUNITY.** المطابقة نتيجة مرشحة؛ الفرصة نتيجة مراجعة واعتماد.
6. **Human Review إلزامي قبل OPPORTUNITY في v0.1.** لا يستطيع AI أو endpoint عام إنشاء Opportunity مباشرة.
7. **Hard FAIL لا يُعوضه Ranking.** الشروط القاطعة Eligibility Gate وليست أوزانًا داخل نسبة عامة.
8. **UNKNOWN ≠ FAIL.** المعلومة الناقصة قد تخلق Task، ولا يجوز تحويلها صامتًا إلى رفض أو قبول.
9. **Declared ≠ Checked/Verified.** لا يتم رفع مستوى التحقق بدون Verification Event واضح.
10. **Public / Private / Potential** حالات حقيقية للعرض ويجب الحفاظ عليها بنيويًا.
11. **PARTY ≠ CONTACT_POINT ≠ USER_ACCOUNT.** الشخص/الجهة ليس رقم هاتف، والتحقق من الهاتف لا يفرض إنشاء حساب.
12. **Consent resource-bound وrevocable.** الموافقة مرتبطة بمورد وغرض محددين وليست إذنًا عامًا.
13. **Property Identity Resolution غير هدّام.** تأكيد أن سجلين لنفس العقار ينشئ Canonical Identity/Alias، ولا يحذف المصادر أو العروض أو التاريخ.
14. **المعلومة الحرجة تحمل Provenance.** نحتاج معرفة من قال ماذا، متى، وما مستوى التحقق.
15. **Matching historical inputs immutable.** كل Match تحفظ snapshot وhash وسياسة/Rule version تسمح بتفسير القرار لاحقًا.
16. **Freshness مستقلة للطلب والعقار والعرض التجاري.** قدم المعلومة قد يمنع Opportunity حتى لو كان التوافق عاليًا.
17. **Privacy على الخادم لا على الواجهة.** Public / Customer / Internal DTOs منفصلة، ولا نعتمد على frontend لإخفاء الأسرار.
18. **No automatic destructive merge.** لا دمج آلي للعقارات ولا حذف تاريخ بسبب تشابه.
19. **No automatic preference relaxation.** النظام يقترح التشخيص؛ لا يعدل REQUEST بدون موافقة صريحة.
20. **No black-box AI score as truth.** التفسير يجب أن يُبنى على نتائج محسوبة وقواعد معروفة.

---

# 5. النموذج المفاهيمي الذي يجب أن يفهمه المطور

## 5.1 مسار السوق إلى الحقيقة التشغيلية

```text
SOURCE / CALL / WHATSAPP / DOCUMENT / IMAGE
                    │
                    ▼
               OBSERVATION
                    │
                    ▼
                  CLAIM
                    │
        ┌───────────┼───────────┐
        │           │           │
    EVIDENCE   VERIFICATION   HISTORY
        │           │           │
        └───────────┼───────────┘
                    ▼
           RESOLVED CURRENT STATE
                    │
                    ▼
                PROPERTY
```

`PROPERTY` هي الهوية المستقرة والحالة التشغيلية الحالية؛ أما المصدر، الادعاء، الدليل، التحقق، والتاريخ فلا تُمسح عند تحديث الحالة الحالية.

## 5.2 مسار المطابقة

```text
REQUEST + CANONICAL PROPERTY + COMMERCIAL CONTEXT
                       │
                       ▼
                  HARD GATE
             PASS / FAIL / UNKNOWN
                       │
         ┌─────────────┼─────────────┐
         │             │             │
       FAIL         UNKNOWN         PASS
         │             │             │
      Reject       Info Work     Soft Ranking
                                      │
                                      ▼
                         Freshness / Permission
                                      │
                                      ▼
                           Explained Candidate
                                      │
                                      ▼
                               HUMAN REVIEW
                                      │
                                      ▼
                                OPPORTUNITY
```

## 5.3 دور AI

AI عامل مساعد فقط. يجوز له:

- استخراج حقول مقترحة من نصوص السوق.
- اكتشاف Candidate Matches.
- ترتيب المرشحين بعد Hard Gate.
- اقتراح Property Identity Candidates.
- كشف معلومات ناقصة أو تعارضات.
- صياغة تفسير مبني على Evidence محسوبة.

ولا يجوز له:

- اعتماد Opportunity وحده.
- تغيير Required/Preferred/Flexible من تلقاء نفسه.
- دمج عقارين تلقائيًا.
- رفع Verification Level دون إجراء تحقق.
- اختراع معلومة مفقودة.
- كشف Seller Expectation أو Claim خاصة إذا لم يسمح `sharing_scope`.
- إجراء تواصل حساس أو موافقات قانونية من تلقاء نفسه.

---

# 6. نقاط يجب تنفيذها كما هي

## 6.1 Matching Commercial Context

المطابقة مفهوميا `REQUEST × PROPERTY`، لكن التقييم الفعلي يجب أن يسجل العرض التجاري المستخدم `evaluated_offer_id` أو Structured Potential Context عندما لا يوجد Offer فعال. السبب: السعر، SALE/RENT، التفاوض، الإذن والـfreshness كلها قد تختلف بين عروض العقار نفسه.

Opportunity uniqueness تبقى عند:

> **REQUEST × canonical PROPERTY**

وليس REQUEST × OFFER.

## 6.2 Immutable Match Snapshots

كل `MATCH_CANDIDATE` يجب أن يحتفظ بصورة غير قابلة للتعديل من:

- request snapshot;
- property snapshot;
- commercial context snapshot;
- permission snapshot;
- freshness snapshot;
- criterion results;
- policy/rule versions;
- canonical input hash.

الهدف هو القدرة على الإجابة لاحقًا: «لماذا اقترح النظام هذا العقار في ذلك اليوم؟» حتى بعد تغير السعر أو الطلب أو الموافقة.

## 6.3 Property Identity

إذا ثبت أن P10 وP20 هما نفس العقار الفيزيائي:

- لا يُحذف أحدهما.
- يُنشأ Alias → Canonical Property.
- تبقى Sources وOffers وClaims والتاريخ.
- أي Matching جديد يجب أن يستهدف Canonical Property.
- الوحدات المتشابهة في مشروع واحد ليست تلقائيًا نفس العقار.

## 6.4 Provenance وVerification

تغيير معلومة حرجة لا يجب أن يحدث عبر Generic Repository update صامت. Domain Command يجب أن تنفذ transaction تربط أو تكتب:

1. Observation/Claim/Evidence المناسب.
2. Verification/Resolution event إن كان مطلوبًا.
3. Current operational projection.
4. Audit metadata.

## 6.5 Permission / Consent

قبل أي مشاركة أو تفعيل يعتمد على موافقة:

- تحقق من الطرف الصحيح.
- تحقق من المورد الصحيح.
- تحقق من الغرض/Scope.
- تحقق أن الموافقة لم تُسحب.
- احفظ Evidence الموافقة في Snapshot التاريخية.

السحب يمنع الاستخدام المستقبلي ولا يمحو التاريخ السابق.

## 6.6 API Security Boundaries

- Public DTO منفصل عن Customer DTO وعن Internal DTO.
- العميل يستخدم `/me/*` لموارده.
- Arbitrary UUID reads تحتاج staff authorization أو ownership check صريح.
- لا تُرجع Public/Customer APIs: seller expectation، consent internals، staff notes، provenance internals أو management metadata غير المصرح بها.
- لا Generic PATCH للحالات الحساسة؛ تستخدم Commands typed واضحة.

---

# 7. Matching Core — السلوك المطلوب

لكل Criterion يجب أن يوجد على الأقل:

- `importance = REQUIRED | PREFERRED | FLEXIBLE`
- `compatibility = PASS | FAIL | UNKNOWN`
- request value
- property/commercial value
- delta عند الحاجة
- evidence/verification status
- reason code
- rule id
- rule version

القواعد الأساسية:

- `REQUIRED + FAIL` يمنع Opportunity.
- `REQUIRED + UNKNOWN` يولد Information Work عند كون المعلومة blocking.
- `PREFERRED/FLEXIBLE` ترتب المرشحين ولا تتجاوز Hard Gate.
- `negotiable=true` لا يعني أن السعر فوق الحد الأقصى PASS تلقائيًا.
- seller expectation قد تستخدم داخليًا في التقييم لكن لا تُكشف تلقائيًا.
- No Match نتيجة صحيحة.

### أولوية العمل عند غياب Opportunity

1. تحقق هل توجد Exact/Eligible Candidate.
2. حل **Blocking Unknowns** ذات القيمة العالية.
3. أعد تأكيد المعلومات القديمة.
4. تحقق من Permission.
5. فقط بعد ذلك اقترح Minimal Meaningful Relaxation للموظف.
6. لا يتغير REQUEST إلا بعد موافقة العميل الصريحة.

---

# 8. Communication وWhatsApp

لا تبني Chat Platform خاصة من البداية. المطلوب في v0.1 هو:

- Official WhatsApp Business integration boundary.
- Communication Thread.
- Message/Interaction Timeline.
- Operator attribution.
- provider message id + replay protection.
- delivery/read status عند توفره.
- القدرة على ربط قرار هاتفي بتأكيد مكتوب لاحقًا.

الهدف هو أن تكون تُراب مصدر السجل المنظم، بينما يبقى WhatsApp قناة طبيعية للسوق.

---

# 9. ما لا يجب بناؤه الآن

لا يُضاف إلى v0.1 دون قرار جديد في Design Ledger:

- AVM أو Fair Price Engine.
- CRM متقدم عام.
- Chat proprietary كامل.
- Gamification أو credits.
- Conversational AI autonomous search كواجهة مركزية.
- financing flows.
- contract/e-signature management.
- payments.
- fractional investment.
- advanced investment analytics.
- loyalty/multi-tier subscriptions.
- full Event Sourcing architecture.
- standalone Vector Database لمجرد وجود AI.
- autonomous agents تقوم بالموافقات أو التواصل الحساس.
- blockchain / tamper-proof provenance.

قاعدة المشروع: **إذا لم تساعد الخاصية مباشرة في اختبار فرضية REQUEST + PROPERTY → OPPORTUNITY، فهي بحاجة إلى دليل قبل إضافتها.**

---

# 10. ترتيب التنفيذ الإلزامي

يجب اتباع `IMPLEMENTATION_SLICES_v0.2.md`. الترتيب المختصر:

1. **Pre-Slice Gate:** PostgreSQL schema/seed/CI proof.
2. **Slice 0:** Application Skeleton + Security Boundaries.
3. **Slice 1:** PARTY / Contact Point / Account / Consent.
4. **Slice 2:** REQUEST + Criteria + Freshness.
5. **Slice 3:** PROPERTY / OFFER / SOURCE / Truth / Identity Lite.
6. **Slice 4:** Deterministic Matching Core.
7. **Slice 5:** Human Review → OPPORTUNITY.
8. **Slice 6:** Match Diagnostic / Information Work.
9. **Slice 7:** Communication / WhatsApp Record.
10. **Slice 8:** External Acquisition / Assisted Entry / Self-service.
11. **Slice 9:** AI Assist / Advanced Identity Signals بعد إثبات النواة.

### Core Hypothesis Stop Gate

قبل إضافة AI متقدمة أو polish يجب أن ينجح المسار التالي بالكامل:

> **REQUEST → PROPERTY/OFFER → deterministic candidate → Human Review → OPPORTUNITY**

إذا لم يعمل بصورة صحيحة وقابلة للتفسير، يتوقف المشروع عند هذه النقطة لإصلاح النواة.

---

# 11. أول إجراءات المطور قبل كتابة Features

يجب تنفيذ التالي بالترتيب:

1. قراءة هذا الملف كاملًا.
2. قراءة Foundation Baseline ثم Developer Reference Spec ثم Architecture Decisions.
3. تشغيل `technical_pack_static_audit_v0.2.1.py` والتأكد من PASS.
4. تشغيل `schema_v0.2.1.sql` على PostgreSQL 16+ جديد.
5. تشغيل `seed_master_data_v0.2.1.sql` مرتين للتحقق من idempotency.
6. تنفيذ اختبارات `POSTGRES_EXECUTION_GATE.md`.
7. Parse/Lint `openapi_v0.2.yaml` في CI.
8. إنشاء CI يعيد بناء قاعدة فارغة ويشغل الاختبارات في كل Merge Request.
9. اعتماد Error Contract وIdempotency وObject Authorization من Slice 0 قبل Domain Features.
10. عدم البدء في AI قبل اجتياز Stop Gate E.

إذا فشل PostgreSQL Gate، **لا يبدأ Slice 0 بوصف الحزمة مجمدة**؛ يتم إصلاح الـSchema/Contracts أولًا وتحديث النسخة رسميًا.

---

# 12. معايير الجودة والأمان الدنيا

يجب أن يتضمن التنفيذ:

- transactions واضحة للـDomain Commands الحرجة؛
- idempotency للـmutating commands؛
- optimistic concurrency حيث نص العقد؛
- append-only histories لمراجعات Match والتاريخ الحرج؛
- object-level authorization وليس role-only authorization؛
- server-side redaction؛
- structured error responses؛
- structured logging بدون تسريب PII/claims الحساسة؛
- database constraints للحالات التي يمكن حمايتها في DB؛
- reproducible migrations/seed؛
- automated red-team regression tests؛
- no hard delete للكيانات التاريخية المحمية إلا بإجراء إداري مقصود ومراجَع.

---

# 13. سياسة التغيير أثناء التطوير

أي اقتراح يغير معنى Entity أو State أو Gate أو Privacy/Consent أو AI role أو Opportunity semantics لا يعامل كتعديل برمجي عادي.

يجب على المطور تقديم Change Proposal يتضمن:

1. المشكلة التي يحلها.
2. سبب عدم كفاية التصميم الحالي.
3. أثره على Foundation / Data Model / API / Migration / Tests.
4. تصنيفه في Design Ledger: Adopt Now / Prepare / Defer / Exclude.
5. مخاطر التعقيد أو الخصوصية أو القانون.
6. قرار صاحب المنتج قبل الدمج.

لا يغيّر المطور Contract أو Schema ثم يوثق القرار لاحقًا. **القرار أولًا، ثم التعديل المتزامن لكل artifacts المتأثرة.**

---

# 14. ملفات الحزمة وما الغرض منها

| المسار | الاستخدام |
|---|---|
| `01_PRODUCT_BASELINE/TURAB_Foundation_Baseline_v1.0_FINAL.docx` | المرجع المنتجـي الأعلى |
| `01_PRODUCT_BASELINE/TURAB_Project_Instructions_v1.0.md` | منهج التطوير وDesign Ledger |
| `02_DEVELOPER_SPEC/TURAB_Developer_Reference_Spec_v0.1.*` | السلوك التفصيلي للمطور |
| `03_ARCHITECTURE/ARCHITECTURE_DECISIONS_v0.2.md` | ADRs الملزمة |
| `03_ARCHITECTURE/REMEDIATION_REVIEW_v0.2.md` | إثبات إغلاق ملاحظات v0.1 |
| `04_DATABASE/schema_v0.2.1.sql` | PostgreSQL 16+ baseline |
| `04_DATABASE/seed_master_data_v0.2.1.sql` | Master Data / Adrar / reasons / policy |
| `04_DATABASE/POSTGRES_EXECUTION_GATE.md` | Release gate قبل الكود |
| `05_API/openapi_v0.2.yaml` | العقد الآلي للـHTTP API |
| `05_API/API_CONTRACTS_v0.2.md` | السلوك التفصيلي للـAPI |
| `05_API/API_INVENTORY_v0.2.md` | جرد العمليات |
| `06_IMPLEMENTATION/IMPLEMENTATION_SLICES_v0.2.md` | خطة البناء وStop Gates |
| `07_QA_ACCEPTANCE/RED_TEAM_ACCEPTANCE_TESTS_v0.2.md` | Edge cases واختبارات القبول |
| `07_QA_ACCEPTANCE/technical_pack_static_audit_v0.2.1.py` | فحص ساكن قابل للتكرار |
| `07_QA_ACCEPTANCE/STATIC_AUDIT_RESULTS_v0.2.1.json` | نتيجة الفحص الحالية |
| `99_REFERENCE_HISTORY/*` | تاريخ القرارات فقط؛ ليس Baseline تنفيذية |

---

# 15. الملفات القديمة التي لا يجوز استخدامها

إذا كان لدى المطور ملفات من محادثات أو حزم سابقة، يجب تجاهل ما يلي عند التنفيذ الجديد:

- أي Foundation أقدم من `v1.0 FINAL`.
- `Technical Implementation Pack v0.1`.
- `schema_v0.1.sql`.
- `openapi_v0.1.yaml`.
- `API_CONTRACTS_v0.1.md`.
- أي افتراض تقني قديم يتعارض مع `ARCHITECTURE_DECISIONS_v0.2.md`.

ملف `REFERENCE_Architecture_Review_v0.1.md` موجود فقط لفهم أسباب الإصلاح، وليس لإعادة تطبيق تصميم v0.1.

---

# 16. تعريف أول Milestone ناجح

لا نعتبر «إعداد المشروع وتشغيل السيرفر» Milestone كافيًا.

أول Milestone تقني مقبول يجب أن يثبت:

- PostgreSQL Gate اجتاز بالكامل.
- Authentication/authorization/idempotency boundaries تعمل.
- PARTY/CONTACT/ACCOUNT separation تعمل.
- REQUEST بحالاته ومعاييره وFreshness يعمل.
- PROPERTY/OFFER/SOURCE وTruth/Identity basics تعمل.
- Matching deterministic يعطي PASS/FAIL/UNKNOWN قابلة للتفسير.
- Human Review append-only تعمل.
- Opportunity لا تنشأ إلا من Approved Match وكل Gates PASS.
- DTO privacy tests تمر.
- Red-team tests ذات الصلة بالسlices المنجزة تمر في CI.

عندها فقط نعتبر النواة صالحة للانتقال إلى Diagnostic/Communication/AI Assist.

---

# 17. ما يجب على المطور تأكيد فهمه قبل البدء

يجب أن يستطيع المطور شرح هذه النقاط بكلماته قبل اعتماد Kickoff:

- لماذا PROPERTY ليست Listing؟
- لماذا نفس PROPERTY قد تملك عدة Offers؟
- لماذا Opportunity uniqueness على Request × Canonical Property؟
- لماذا INTEREST لا تساوي REQUEST؟
- لماذا Hard UNKNOWN ليس Fail؟
- لماذا seller expectation قد تستخدم داخليًا ولا تُعرض؟
- لماذا Match snapshot immutable؟
- لماذا Confirmed Same لا يعني حذف سجل؟
- لماذا Consent مرتبط بالمورد والغرض؟
- لماذا Verification Event منفصل عن Claim؟
- لماذا Public DTO ليست Internal DTO بعد حذف حقول في frontend؟
- لماذا AI تأتي بعد النواة deterministic؟
- لماذا No Match قد تكون النتيجة الصحيحة؟
- لماذا WhatsApp قناة اتصال وليس Source of Truth؟
- ما الذي يمنع OPPORTUNITY من الإنشاء؟

إذا كانت إحدى هذه النقاط غير واضحة، يرجع للمراجع قبل كتابة الكود.

---

# 18. الخلاصة التنفيذية

المطلوب بناء **نواة دقيقة قابلة للتدقيق** قبل بناء واجهة غنية أو AI متقدمة.

الأولوية ليست كثرة الخصائص، بل أن يعرف النظام بصورة موثوقة:

> من يريد ماذا؟  
> ما العقار الحقيقي؟  
> ما العروض الموجودة عليه؟  
> من أين جاءت كل معلومة؟  
> ما الذي تم التحقق منه؟  
> ما الذي تغير ومتى؟  
> هل البيانات ما تزال حديثة؟  
> هل يسمح الإذن بالمشاركة؟  
> لماذا اقترح النظام المطابقة؟  
> ماذا قرر الإنسان؟  
> ومتى أصبحت المطابقة Opportunity حقيقية؟

إذا حافظ التنفيذ على هذه الأسئلة، فإنه يطبق تُراب. إذا اختصرها إلى Listings + Search + AI Score، فإنه يبني منتجًا آخر مهما كانت الواجهة جميلة.
