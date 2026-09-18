# تُراب — TURAB
Developer Reference Specification v0.1

المواصفة المرجعية للمطور — النطاق الأساسي، طبقة الحقيقة، هوية العقار، المطابقة، الفرصة والتواصل

التاريخ المرجعي: 18 سبتمبر 2026

# 0. كيفية قراءة هذه المواصفة
هذه الوثيقة ليست قائمة Features ولا تصميم واجهة بصرية. هي عقد وظيفي/معماري يشرح ما الذي يجب أن يفهمه النظام عن السوق، وما القواعد التي لا يجوز كسرها أثناء التنفيذ. عندما يوجد تعارض بين سهولة البرمجة وهذه القواعد، تُرفع المسألة إلى Design Ledger ولا يُغيَّر المنطق بصمت.

| الكلمة | المعنى للمطور |
| --- | --- |
| MUST / يجب | شرط ملزم في v0.1. كسره يغير منطق المنتج أو يهدد صحة البيانات. |
| SHOULD / ينبغي | التنفيذ المفضل. يمكن العدول عنه لسبب تقني واضح ومسجل دون كسر المبادئ. |
| MAY / يمكن | اختيار تنفيذي أو تحسين غير ملزم. |
| MUST NOT / لا يجوز | سلوك ممنوع لأنه يهدم فصلًا تأسيسيًا أو يخلق ادعاء تحقق غير صحيح أو أتمتة غير مأمونة. |

> **مبدأ حاكم** لا نبرمج ما يمكننا برمجته فقط؛ نبرمج ما يساعد النسخة 0.1 على اختبار الفرضية الأساسية: هل تستطيع تُراب تحويل طلب عقاري حقيقي وعرض متاح أو كامن إلى فرصة عقارية ذات معنى بصورة أفضل وأكثر تنظيمًا من السوق المجزأ؟

## 0.1 خريطة الوثيقة
- القسم 1–5: نطاق النظام، المبادئ، الأدوار والكيانات الأساسية.
- القسم 6–9: طبقة الحقيقة: الهوية، المصدر، الادعاءات، الزمن، التحقق والتعارض.
- القسم 10–15: REQUEST، محرك المطابقة، التشخيص، الفرصة، الصلاحيات والتواصل.
- القسم 16–20: دور AI، الـBack Office، واجهات المستخدم، العقود الخدمية والنموذج المفاهيمي للبيانات.
- القسم 21–25: الثوابت، اختبارات القبول، بيانات الاختبار، خطة التنفيذ، وما يؤجل أو يُستبعد.

# 1. تعريف المنتج والحدود غير القابلة للتفاوض
التعريف المرجعي: «تُراب منصة عقارية محلية تبدأ من حاجة المشتري، وتنظم العرض المتاح وغير المعلن، وتطابق بينهما للوصول إلى فرصة عقارية حقيقية.»

يجب على المطور قراءة كلمة «حقيقية» كمتطلب بيانات وسير عمل، لا كشعار تسويقي. الفرصة لا تعني مجرد تشابه خوارزمي؛ يجب أن تكون مبنية على REQUEST نشطة بما يكفي، PROPERTY معروفة الهوية بما يكفي، معلومات حرجة حديثة بما يكفي، صلاحيات مشاركة مناسبة، ثم مراجعة بشرية.

| المبدأ | الأثر البرمجي الإلزامي |
| --- | --- |
| REQUEST وPROPERTY كيانان أساسيان متساويان | لا تُبنى قاعدة البيانات أو الـAPI حول Listings فقط. يجب أن يكون للطلب lifecycle وتاريخ ومطابقة مستقلة. |
| PROPERTY ≠ POST / SOURCE | المنشور أو المصدر لا يصبح هو هوية العقار. عدة مصادر وعروض قد تشير إلى PROPERTY واحدة. |
| PROPERTY ≠ PROPERTY_OFFER | العقار الفيزيائي ثابت نسبيًا، أما العرض التجاري فيحمل السعر، المعلن، شروطه، الإتاحة والتفاوض وقد تتعدد عروضه. |
| MATCH ≠ OPPORTUNITY | أي تطابق محوسب هو Candidate فقط. لا ينشئ Opportunity مباشرة. |
| AI مساعد لا صاحب قرار | AI تقترح وتفسر وتكشف نقصًا/تعارضًا؛ الإنسان يعتمد/يرفض/يطلب معلومة. |
| Declared ≠ Checked ≠ Verified | لا تُرفع درجة التحقق لمجرد أن النظام استخرج معلومة أو أن المعلن صرح بها. |
| Public / Private / Potential | الظهور للعامة مستقل عن قابلية الاستخدام في المطابقة. |
| Human-in-the-loop مقصود | قرارات المراجع وسببها بيانات تعلم يجب حفظها من اليوم الأول. |

# 2. نطاق v0.1 وما لا يدخل فيه
## 2.1 داخل النطاق
- إنشاء وإدارة PARTY دون افتراض وجود USER_ACCOUNT.
- إنشاء REQUEST ذات معايير منظمة ومرونة معلومة وحالة Freshness.
- إنشاء PROPERTY وPROPERTY_OFFER وSOURCE، مع Public / Private / Potential.
- Assisted Entry بعد consent، وClaim لاحق للسجل دون نسخه.
- Property Identity candidate detection خفيف قائم على قواعد + مراجعة بشرية.
- Provenance/History كافية لمعرفة من قال ماذا ومتى وبأي مستوى تحقق.
- Matching Core: Hard Gate + Soft Ranking + Unknown/Freshness/Permission checks + Explanation.
- Match Diagnostic داخل Back Office، بما فيه Actionable Unknowns وNear Matches.
- Human Review بثلاثة قرارات: Approved / Rejected / Need More Information.
- OPPORTUNITY lifecycle + INTERACTION / COMMUNICATION timeline.
- WhatsApp Business كقناة تشغيل أولى، مع تصميم النظام ليبقى مصدر الحقيقة المنظم.

## 2.2 مؤجل أو مستبعد حاليًا
| العنصر | القرار | السبب |
| --- | --- | --- |
| AVM / Automated Valuation | مؤجل | يحتاج بيانات نظيفة وحجمًا كافيًا؛ ليس لازمًا لاختبار الفرضية. |
| CRM متقدم كامل | مؤجل | ننفذ فقط ما يخدم الطلب/العقار/المطابقة/الفرصة والتواصل. |
| Native chat بين المستخدمين | مؤجل | WhatsApp/الهاتف أكثر اتساقًا مع السوق المحلي؛ نحتاج سجلًا لا Messenger جديدًا. |
| Full Event Sourcing | مستبعد حاليًا | تعقيد غير مبرر للـPilot. نحتفظ بتاريخ حقول وأحداث حرجة فقط. |
| Knowledge Graph / RDF / W3C PROV كامل | مؤجل | نستفيد من المفهوم داخل relational model بسيط. |
| Splink/Dedupe ML production | مؤجل | نهيئ labels وقرارات المراجعين أولًا؛ القواعد تكفي للـ0.1. |
| Learning-to-Rank | مؤجل | نحتاج أولًا بيانات قرارات بشرية ونتائج فعلية. |
| Automatic preference relaxation | ممنوع | لا يجوز تغيير طلب المستخدم دون تأكيد صريح. |
| Black-box AI Match % | ممنوع | النتيجة يجب أن تكون قابلة للتفسير ومقسمة حسب المعايير. |

# 3. الجهات والأدوار
| الكيان/الدور | الوصف | ملاحظات تنفيذية |
| --- | --- | --- |
| PARTY | شخص أو مؤسسة حقيقية مرتبطة بالسوق: مالك، مشتري، وسيط، وكالة، مرقٍ... | قد توجد بلا حساب دخول. |
| USER_ACCOUNT | بيانات الدخول والهوية الرقمية لإدارة السجلات ذاتيًا. | لا يُنشئ الموظف حسابًا نشطًا نيابة عن الشخص. |
| Admin | إدارة الإعدادات والصلاحيات والمرجعيات. | صلاحيات كاملة مع Audit. |
| Operator | يدخل/يحدّث البيانات ويتصل بالأطراف ويغلق Actionable Unknowns. | لا يرفع درجة تحقق بلا إجراء. |
| Reviewer | يراجع Candidate Matches وIdentity Candidates والحالات الحساسة. | قد يكون نفس الشخص تشغيليًا في Pilot، لكن الدور منطقيًا منفصل. |
| AI Service | استخراج/تطبيع/اقتراح مطابقة/تفسير/كشف نقص أو تعارض. | كل اقتراح حساس قابل للتتبع بالنسخة والوقت. |

> **قاعدة حسابات** Phone verification يمكن أن يؤكد التحكم في رقم الهاتف ويُستخدم لربط PARTY، لكنه لا يعني قانونيًا أن الهوية VERIFIED. USER_ACCOUNT طبقة منفصلة يمكن تفعيلها لاحقًا أو عدم تفعيلها مطلقًا.

# 4. النموذج المجالي الأساسي Domain Model
```text
PARTY 1 ---- 0..* USER_ACCOUNT
  |
  +---- 0..* REQUEST
  +---- 0..* PARTY_PROPERTY_RELATION ---- * PROPERTY

PROPERTY 1 ---- 0..* PROPERTY_OFFER ---- 1 PARTY
   |                    |
   |                    +---- 1..* SOURCE
   |
   +---- 0..* PROPERTY_IDENTITY_CANDIDATE (to another PROPERTY)
   +---- 0..* CLAIM / OBSERVATION / VERIFICATION_EVENT

REQUEST * ---- * PROPERTY  via MATCH_CANDIDATE
MATCH_CANDIDATE 0..1 ---- 1 OPPORTUNITY (only after human approval)

PARTY / REQUEST / PROPERTY / OPPORTUNITY
          └---- INTERACTION / COMMUNICATION_TIMELINE
```

## 4.1 الكيانات الأساسية
| الكيان | الغرض | ما لا يجب خلطه به |
| --- | --- | --- |
| PARTY | يمثل الشخص/المؤسسة في السوق | USER_ACCOUNT |
| REQUEST | حاجة بحث فعلية قابلة للحياة والمطابقة | Saved filter بسيط أو INTEREST |
| PROPERTY | العقار الفيزيائي/الأصل العقاري المستقر نسبيًا | POST أو OFFER |
| PROPERTY_OFFER | عرض تجاري لطرف معين على PROPERTY | PROPERTY نفسها |
| SOURCE | مصدر المعلومة: منشور، مكالمة، WhatsApp، وسيط، استمارة... | الحقيقة النهائية |
| MATCH_CANDIDATE | نتيجة محرك المطابقة قبل القرار البشري | OPPORTUNITY |
| OPPORTUNITY | Match تمت مراجعتها واعتبرت ذات معنى للمشاركة/التواصل | مجرد نتيجة بحث |
| INTERACTION | حدث تشغيلي: اتصال، طلب معلومة، زيارة، رد، تفاوض... | مرحلة إلزامية ثابتة |
| OBSERVATION/CLAIM | طبقة معرفة ومصدر وتاريخ للمعلومة | القيمة الحالية فقط |

# 5. حالات الكيانات State Machines
## 5.1 PARTY / ACCOUNT / Assisted Entry
```text
PARTY: DISCOVERED -> CONTACTED -> CONTACT_VERIFIED -> PARTY_ACTIVE
ACCOUNT: NO_ACCOUNT -> INVITED -> ACTIVATED
ASSISTED RECORD: DRAFT -> PENDING_CONSENT -> PENDING_INFO -> ACTIVE
CLAIM STATUS: UNCLAIMED -> CLAIMED
```

## 5.2 REQUEST
```text
RAW -> CONTACTED -> QUALIFIED -> ACTIVE
ACTIVE -> NEEDS_CONFIRMATION -> ACTIVE | PAUSED | CLOSED
PAUSED/CLOSED -> ACTIVE only by explicit reactivation or materially new request logic
```

لا تُحذف REQUEST من التاريخ لمجرد أنها توقفت. تعطيلها يوقف المطابقة الجديدة، لكنه يحتفظ بالقرارات والعقارات المعروضة والرفض والنتائج السابقة.

## 5.3 PROPERTY availability
```text
AVAILABLE
POTENTIALLY_AVAILABLE
UNDER_DISCUSSION
TEMPORARILY_UNAVAILABLE
UNAVAILABLE
UNKNOWN / NEEDS_CONFIRMATION
```

حالة الإتاحة ليست Boolean فقط. يجب حفظ availability_last_confirmed_at وconfirmed_by وconfirmation_source على الأقل للمعلومات الحرجة.

## 5.4 OPPORTUNITY
```text
status: NEW -> SHARED -> ENGAGED -> CLOSED
validity_status: VALID | NEEDS_CONFIRMATION | INVALID
```

Status يصف أين وصلت العملية؛ Validity يصف هل ما تزال الفرصة صالحة. لا تخلط الحالتين في enum واحدة.

## 5.5 External Lead -> Assisted Entry
Facebook وOuedkniss والمجموعات الخارجية قنوات Discovery/Acquisition وليست Inventory تُنسخ آليًا. المنشور الخارجي يبدأ كـEXTERNAL_LEAD. لا يتحول إلى PROPERTY/REQUEST نشطة قبل تواصل فعلي وموافقة مناسبة.

```text
EXTERNAL_LEAD
  -> CONTACT ATTEMPT
  -> PARTY identified/created
  -> CONSENT captured
  -> ASSISTED DRAFT
  -> PENDING_INFO if critical fields missing
  -> ACTIVE PROPERTY/REQUEST
  -> optional CLAIM by user account later
```

| القاعدة | المطلوب |
| --- | --- |
| No contact / no consent | لا يصبح السجل PROPERTY/REQUEST نشطة. |
| Self-service option | يُرسل رابط/دعوة ليُدخل الشخص بياناته بنفسه. |
| Assisted option | الموظف يدخل البيانات نيابة عنه ضمن نطاق الإذن. |
| Consent fields | consent_status، consent_at، consent_channel، consent_version، visibility/sharing scope. |
| Claim later | CLAIM لا ينسخ السجل؛ ينقل/يشارك الإدارة مع USER_ACCOUNT المناسبة. |
| No fake accounts | الموظف لا ينشئ كلمة مرور أو حساب دخول فعلي باسم العميل. |

# 6. طبقة الحقيقة Truth Layer
هذه الطبقة هي قلب الدقة في تُراب. الهدف ليس بناء Knowledge Graph معقدة، بل منع ضياع أصل المعلومة وتاريخها ومستوى تحققها. المطور يجب أن يميز بين ما وصل إلى النظام، وما استُخرج منه، وما نعتمده حاليًا للتشغيل.

| المفهوم | التعريف | مثال |
| --- | --- | --- |
| SOURCE | القناة أو الأصل الذي جاءت منه المعرفة | Facebook post، مكالمة مالك، WhatsApp، وثيقة، استمارة |
| OBSERVATION | واقعة دخول معلومة أو مادة إلى النظام | رسالة WhatsApp وصلت يوم 18 سبتمبر |
| CLAIM | ادعاء ذري مستخرج/مصرح به عن كيان | asking_price = 24,000,000 DZD |
| EVIDENCE | المادة التي تدعم أو تناقض Claim | صورة وثيقة، رسالة، تسجيل مرجع المكالمة، منشور |
| VERIFICATION_EVENT | إجراء قامت به تُراب للتحقق | DOCUMENT_SEEN أو DETAILS_MATCHED |
| RESOLVED CURRENT VALUE | القيمة التشغيلية المعتمدة حاليًا مع إمكانية الرجوع لأصلها | current_area = 268.5 m² based on document seen |

## 6.1 مستويات التحقق
| المستوى | المعنى | ممنوع تفسيره كـ |
| --- | --- | --- |
| DECLARED | قاله المستخدم/المصدر | تحقق قانوني |
| DOCUMENT_SEEN | اطلع موظف تُراب على وثيقة مرتبطة بالمعلومة | صحة قانونية كاملة |
| DETAILS_MATCHED | تمت مطابقة تفاصيل محددة وفق إجراء واضح | رأي مهني قانوني شامل |
| PROFESSIONAL_CHECK | محجوز مستقبلًا لإجراء مهني محدد | لا يُستخدم قبل تعريف الإجراء والجهة |

> **فصل إلزامي** extraction_confidence الخاصة بالـAI لا تساوي fact_verification_level. قد يكون AI متأكدًا 99% أنه قرأ عبارة «دفتر عقاري»، ومع ذلك تبقى المعلومة DECLARED فقط إذا كان المصدر تصريحًا.

# 7. الزمن، التاريخ، والـAudit
المعلومات العقارية تتغير، وقد نكتشف التغيير متأخرًا. لذلك يجب الفصل — على الأقل للحقول الحرجة — بين وقت وقوع/صلاحية المعلومة ووقت دخولها إلى تُراب.

| الحقل الزمني | المعنى |
| --- | --- |
| observed_at | متى رُصدت أو قيلت المعلومة. |
| recorded_at | متى أُدخلت المعلومة في نظام تُراب. |
| valid_from | من أي وقت يفترض أن تصبح Claim صحيحة في الواقع. |
| valid_to | متى انتهت صلاحيتها إن كان معلومًا. |
| last_confirmed_at | آخر مرة أعيد فيها تأكيد المعلومة الحالية. |

مثال: في 20 سبتمبر قال المالك إن العقار بيع يوم 5 سبتمبر. recorded_at=20 Sep وvalid_from لحالة UNAVAILABLE=5 Sep. هذه المعلومة تسمح لاحقًا بتفسير لماذا أنشئ Candidate في 12 سبتمبر دون اتهام النظام بأنه كان يعلم ما لم يكن قد عرفه.

## 7.1 Audit Trail مختلف عن Provenance
| البعد | السؤال الذي يجيب عنه |
| --- | --- |
| Audit | من عدل السجل داخل النظام، وما القديم والجديد ومتى؟ |
| Provenance | من أين جاءت المعلومة أصلًا؟ |
| Temporal | متى كانت/أصبحت المعلومة صحيحة؟ |
| Verification | ما الإجراء الذي قامت به تُراب للتأكد؟ |

# 8. Property Identity Resolution — هوية العقار
تُراب لا تنفذ deduplication بمعنى حذف نسخة والإبقاء على أخرى. المطلوب هو تحديد هل سجلات متعددة تشير إلى نفس العقار الفيزيائي، ثم ربطها بنفس PROPERTY مع إبقاء SOURCES وPROPERTY_OFFERS منفصلة.

## 8.1 Pipeline مرجعي للـ0.1
1. Normalization: حفظ raw input ثم إنتاج قيم canonical/normalized منفصلة.
2. Candidate Blocking: مقارنة السجل الجديد فقط بمجموعة صغيرة مرشحة حسب البلدية/المنطقة/النوع/المساحة/party/image hints.
3. Evidence Calculation: حساب إشارات المكان والخصائص والطرف والنص والصور والتناقضات.
4. Identity Candidate: إنشاء اقتراح قابل للتفسير، لا merge آلي.
5. Human Review: SAME / DISTINCT / UNSURE مع سبب.
6. Linking: إذا SAME، ترتبط السجلات بنفس PROPERTY بينما تبقى العروض والمصادر مستقلة.
7. Learning Data: حفظ قرار المراجع وسبب القرار لتدريب/تحسين النظام لاحقًا.

## 8.2 الإشارات
| الفئة | أمثلة | القوة الافتراضية |
| --- | --- | --- |
| Strong | نفس PARTY/هاتف موثوق، عدة صور متطابقة، إحداثيات شبه متطابقة، سمة نادرة متطابقة | قوية |
| Medium | نفس canonical zone، مساحة متقاربة، عدد طوابق، وصف مميز | متوسطة |
| Weak | السعر، وصف عام مثل «قريب من الطريق»، كلمات تسويقية | ضعيفة |
| Contradiction | مساحة 270 مقابل 600، إحداثيات بعيدة، طابق/قطعة مختلفة مؤكدة | قد تمنع SAME |
| Not contradiction at PROPERTY level | بيع مقابل إيجار، سعران مختلفان، وسيطان مختلفان | قد تكون Offers مختلفة لنفس PROPERTY |

## 8.3 حالات مراجعة الهوية
```text
PENDING_REVIEW
CONFIRMED_SAME
CONFIRMED_DISTINCT
UNSURE
```

> **قاعدة أمان** لا merge أو حذف آلي. حتى لو كانت درجة التشابه عالية، النظام يقترح فقط. في المشاريع السكنية قد تتشابه الصور والمساحات والأسعار بين وحدات مختلفة، لذلك يجب دعم سبب مثل SIMILAR_UNITS_SAME_DEVELOPMENT_NOT_SAME_PROPERTY.

# 9. تطبيع الموقع Location Resolution
الموقع في تُراب Entity مرجعية وليس String حرة فقط. المرجع المحلي في أدرار يسبق أي fuzzy/semantic model. يجب منع خلط «قصر تيليلان» مع «المدينة الجديدة تيليلان» رغم التشابه النصي.

| الطبقة | السلوك |
| --- | --- |
| Canonical Master | location_id، parent_id، canonical_ar/fr، aliases، type، active_for_selection. |
| Free local detail | وصف المستخدم/المعلم/الطريق يبقى محفوظًا raw. |
| Alias resolution | اقتراح أقرب canonical location عبر aliases + fuzzy matching. |
| Unknown text | UNMAPPED_LOCATION -> Operator Review. لا ينشئ النظام canonical location تلقائيًا. |
| Geometry | اختيارية لاحقًا: point/polygon عندما تتوفر بيانات موثوقة. |

## 9.1 الحد الأدنى من Master Data للسوق التجريبي
هذه القيم ليست مجرد محتوى واجهة؛ هي مرجع Canonical يجب أن تُخزن بمعرّفات ثابتة وتُستخدم في REQUEST وPROPERTY والـmatching والـanalytics. لا تُنشأ قيم Canonical جديدة آليًا من النصوص الحرة.

| المجال | القيم/القاعدة الدنيا |
| --- | --- |
| بلديات ولاية أدرار (16) | Adrar, Tamest, Reggane, In Zghmir, Tit, Tsabit, Zaouiet Kounta, Aoulef, Timekten, Tamantit, Fenoughil, Sali, Akabli, Ouled Ahmed Timmi, Bouda, Sebaa. |
| بلدية أدرار — التقسيم الأعلى | ADR-CENTER وسط المدينة؛ ADR-KSOUR قصور أدرار؛ ADR-NEW-SMB المدينة الجديدة سيدي محمد بلكبير؛ ADR-NEW-TIL المدينة الجديدة تيليلان؛ ADR-AIRPORT طريق المطار. |
| قصور أدرار المعروفة في المرجع | أولاد علي، أدغا، بربع، أقديم، أولاد أونقال، أولاد أوشن، تيليلان، مراقن/Meraguen. |
| قاعدة فاصلة | قصر تيليلان ليس هو المدينة الجديدة تيليلان، ويجب أن تكون لهما location_id مختلفة. |
| باقي البلديات | اختيار البلدية + local_detail حر في v0.1؛ لا نفتح قاموسًا تفصيليًا لكل بلدية قبل وجود استخدام فعلي. |

## 9.2 أنواع العقارات والخصائص الأساسية
| العنصر | القيم/المبدأ |
| --- | --- |
| property_type | House/Villa، Apartment، Land، Shop/Commercial، Agricultural Property، Other. ويمكن تهيئة Building structurally إذا احتاجه الـPilot. |
| construction_state | حالة مستقلة عن property_type. كلمة «كركاسة» أو الهيكل الخرساني لا تُعامل كنوع عقار. |
| shared core fields | location، area، price/price status، availability، visibility، source، declared documents، negotiability، freshness. |
| typed attributes | الخصائص المتخصصة حسب النوع تُبنى فوق Attribute Definition / Property Attribute Value بدل أعمدة عشوائية كثيرة. |

## 9.3 الحقوق والوثائق والتحقق
| المجال | القيم الدنيا |
| --- | --- |
| RIGHT / TENURE | Private ownership، possession، agricultural concession، co-ownership، inherited estate (operational state)، other، unknown. |
| DOCUMENT | land book، published title deed، administrative deed، possession certificate، agricultural concession deed، unspecified document، other، unknown. |
| document status | Available / Not available now / In process / Unclear. |
| قاعدة «بوثائق» | إذا قال المصدر «بوثائق» فقط، لا تستنتج Land Book؛ خزّن UNSPECIFIED_DOCUMENT / Need More Information. |
| العقار الفلاحي | Agricultural concession لا تُعامل كملكية خاصة؛ الحق والوثيقة منفصلان. |

## 9.4 نموذج السعر ووحداته
يجب تخزين كل المبالغ Canonically بالدينار الجزائري DZD، مع حفظ التعبير الخام عند الحاجة لأن السوق يستخدم «مليون/مليار سنتيم». AI أو parser يمكن أن يقترح التحويل، لكن القيمة الحساسة يجب تأكيدها من المستخدم/الموظف عند وجود غموض.

| الطرف | الحقول/المنطق |
| --- | --- |
| REQUEST | budget_target_dzd، budget_max_dzd، budget_flexibility. |
| PROPERTY_OFFER | asking_price_dzd، price_negotiable، seller_expectation_dzd اختياري داخلي، price_visibility. |
| Unknown price | لا يساوي Reject؛ قد ينتج Need More Information. |
| Negotiable فقط | لا يعني تلقائيًا أن السعر سيصل إلى حد المشتري؛ يعامل كتوافق محتمل/غير محسوم. |
| Future history | هيّئ الفرق بين asking / offered / agreed / closed دون بناء AVM أو fair-price engine الآن. |

# 10. نموذج REQUEST
REQUEST تمثل حاجة سوق حية، لا مجرد saved search. يجب أن تستطيع الاستمرار دون نتائج، تتوقف دون حذف، وتُعاد مطابقتها عند دخول عرض جديد أو تحديث عرض قائم.

| المجال | حقول/قيم أساسية |
| --- | --- |
| Intent | Exploring / Active Search / Ready to Act |
| Budget | budget_target_dzd، budget_max_dzd، budget_flexibility |
| Criteria importance | REQUIRED / PREFERRED / FLEXIBLE |
| Freshness | last_confirmed_at + status |
| Payment | Cash / Bank financing / Mixed / Undecided |
| Location | canonical location + allowed alternatives/structure حسب النسخة |
| Must-have / nice-to-have | تتحول إلى REQUEST_CRITERION قابلة للتفسير لا نص فقط |

## 10.1 INTEREST ≠ REQUEST
ضغط المستخدم على «مهتم بهذا العقار» ينشئ INTEREST أو INTERACTION مرتبطة بـPROPERTY، ولا ينشئ REQUEST تلقائيًا. يمكن عرض اقتراح لإنشاء REQUEST Draft من خصائص العقار إذا وافق المستخدم.

# 11. نموذج Criterion والتقييم
كل معيار طلب يجب تقييمه مستقلًا بحيث لا تضيع أسباب القرار داخل Score واحدة. الحد الأدنى لكل تقييم هو Compatibility + Evidence + Reason.

| الحقل | الغرض |
| --- | --- |
| criterion_id / type | تحديد المعيار: price, location, document, area, attribute... |
| importance | REQUIRED / PREFERRED / FLEXIBLE |
| request_value | القيمة/النطاق المطلوب. |
| property_value | القيمة الحالية المعتمدة أو UNKNOWN. |
| compatibility_status | PASS / FAIL / UNKNOWN. |
| delta | الفارق الكمي إن كان له معنى: +150M centimes، -10m²... |
| evidence_level | Declared / Document Seen / Details Matched... |
| evidence_ref | رابط إلى Claim/Evidence ذات الصلة. |
| reason_code | سبب معياري قابل للتجميع والتحليل. |
| rule_id / rule_version | أي قاعدة أنتجت النتيجة وبأي نسخة. |

> **قاعدة إلزامية** UNKNOWN ليست FAIL. إذا كان المشتري يشترط دفترًا عقاريًا ولم نعرف نوع الوثيقة، النتيجة NEED_MORE_INFORMATION وليست No Match تلقائيًا.

# 12. TURAB Matching Core v0.1
```text
REQUEST + RESOLVED PROPERTY STATE
        |
        v
1. HARD ELIGIBILITY GATE
   - REQUIRED criteria only
   - PASS / FAIL / UNKNOWN
        |
        +--> FAIL -> REJECT CANDIDATE
        +--> blocking UNKNOWN -> NEED MORE INFORMATION
        v
2. SOFT RANKING
   - PREFERRED/FLEXIBLE proximity
   - price/location/area/attributes
        |
        v
3. FRESHNESS + PERMISSION + EVIDENCE GATES
        |
        v
4. EXPLAINED MATCH CANDIDATE
        |
        v
5. HUMAN REVIEW
   APPROVE | REJECT | NEED_MORE_INFORMATION
        |
        v
6. OPPORTUNITY only after APPROVE
```

## 12.1 Hard Gate
- أي REQUIRED criterion = FAIL يمنع Opportunity.
- Required criterion = UNKNOWN لا يُحوَّل صامتًا إلى PASS أو FAIL؛ ينشئ Actionable Unknown إذا كان حاسمًا.
- لا يسمح Soft score أو Semantic similarity بتجاوز Hard FAIL.
- No valid Opportunity نتيجة صحيحة وليست Failure للنظام.

## 12.2 Soft Ranking
الـSoft Ranking يرتب المرشحين المؤهلين أو شبه المؤهلين ولا يقرر الحقيقة. يمكن للنسخة 0.1 استخدام دوال Deterministic بسيطة وقابلة للتفسير للسعر والمساحة والموقع والخصائص. لا حاجة لـLearning-to-Rank في البداية.

## 12.3 Rules constrain; semantics discover
يمكن للـsemantic layer مستقبلًا اكتشاف معنى «حي هادئ قريب من وسط المدينة» أو استخراج معايير من دارجة/فرنسية مختلطة، لكنها لا تلغي القواعد البنيوية. Semantic similarity أداة لاستكشاف المرشحين وتفسير التفضيلات اللينة، وليست بوابة صلاحية.

# 13. Match Diagnostic وActionable Unknowns
الـBack Office يجب ألا يكتفي بقائمة Matches. يجب أن يشرح أيضًا لماذا لا توجد فرصة، وما المعلومة الأكثر قيمة التي ينبغي جمعها الآن.

| النوع | التعريف | التصرف |
| --- | --- | --- |
| Blocking Unknown | معلومة ناقصة تمنع القرار وقد تحول المرشح إلى Opportunity | Task ذات أولوية عالية لجمع المعلومة. |
| Non-blocking Unknown | معلومة ناقصة مفيدة لكن لا تمنع الأهلية/القرار الحالي | لا توقف المسار ولا تُرهق الموظف بجمعها فورًا. |
| Hard Fail | تعارض مؤكد في REQUIRED criterion | Reject Candidate مع reason_code. |
| Near Match | مرشح يفشل شرطًا أو اثنين بصورة مفهومة ويمكن عرضه داخل Diagnostic لا كOpportunity | يستخدم للتشخيص/مرونة لاحقة فقط. |

## 13.1 ترتيب العمل الصحيح عند No Opportunity
1. البحث عن Exact Eligible Candidate أولًا.
2. حل High-value Blocking Unknowns التي قد تنتج Exact Match.
3. إعادة تأكيد المعلومات القديمة المؤثرة (REQUEST أو PROPERTY).
4. فحص Permission/Sharing Scope.
5. إذا بقيت النتيجة بلا فرصة: حساب Minimal Meaningful Relaxation scenarios.
6. الموظف يناقش المرونة مع العميل؛ REQUEST لا تتغير إلا بتأكيد صريح.
7. إعادة المطابقة بعد حفظ النسخة الجديدة للطلب.

> **قاعدة عالية القيمة** Information acquisition has priority over preference relaxation عندما يمكن للمعلومة الناقصة وحدها أن تنتج Exact Match. لا نسأل المشتري عن توسيع المنطقة قبل أن نتأكد من وثيقة عقار يطابق بقية الشروط.

# 14. Constraint Relaxation — تشخيص لا تعديل تلقائي
في v0.1 لا نحتاج Solver رياضيًا. يمكن لكل Candidate أن يحمل failure set مثل {budget} أو {location, document}. نستخدم أصغر مجموعات الفشل لتفسير ما يمنع السوق الحالي من إنتاج فرصة.

الـRelaxation يجب أن تكون meaningful وتحتوي magnitude، لا مجرد حذف قيد. رفع الميزانية بـ150 مليون سنتيم ليس مثل رفعها بمليار، وقبول حي مجاور ليس مثل قبول بلدية أخرى.

| مثال | تمثيل مقترح |
| --- | --- |
| السعر | budget_delta_dzd = +1,500,000 |
| المساحة | area_delta_m2 = -10 |
| الموقع | location_relaxation = adjacent_zone / same_city / other_commune |
| الوثيقة | لا تُخفض من Required تلقائيًا؛ السيناريو يعرض فقط أثر التغيير إن اختار المستخدم ذلك صراحة. |

# 15. Freshness / Permission / Opportunity Gate
## 15.1 نوعا Freshness
| النوع | السؤال |
| --- | --- |
| Request Freshness | هل المشتري ما يزال يبحث بنفس الحاجة؟ |
| Property Freshness | هل العقار ما يزال متاحًا وبالشروط الحرجة نفسها؟ |

سياسة المدة نفسها يجب أن تكون Configurable وليست hard-coded داخل الكود. قد تختلف حسب نوع العقار وحالة Public/Private/Potential وتجربة الـPilot.

## 15.2 Permission / sharing_scope
```text
SUMMARY_ONLY
PROPERTY_DETAILS_ALLOWED
CONTACT_AFTER_CONFIRMATION
```

يجب فصل ما يعرفه Matching Engine عما يسمح Explanation/Presentation بكشفه. قد يستخدم المحرك seller_expectation سرية لتقدير توافق السعر، لكن لا يجوز أن تظهر للمشتري إذا لم يسمح sharing_scope.

## 15.3 شروط إنشاء Opportunity
| Gate | الشرط |
| --- | --- |
| REQUEST | Active ومؤهلة بما يكفي وحديثة بما يكفي. |
| PROPERTY | متاحة أو Potential قابلة للتأكيد، وليست stale/unknown بشكل يمنع العرض. |
| Criteria | لا Hard FAIL مؤكد. |
| Information | لا Blocking Unknown حرج غير محلول. |
| Party | طرف قابل للتواصل مرتبط بالعقار. |
| Permission | نطاق الإذن يسمح بالمشاركة المطلوبة. |
| Human Review | Approved صراحة. |

Invariant: في أي لحظة لا توجد أكثر من Opportunity مفتوحة واحدة لنفس REQUEST × PROPERTY، حتى لو تعددت SOURCES أو PROPERTY_OFFERS. وصول Source جديد يحدّث المعرفة أو يطلق Review ولا يكرر الفرصة.

# 16. عقد التفسير Explainability Contract
التفسير يُبنى من نتائج محسوبة ومراجع أدلة، ولا يحق للـLLM اختراع سبب أو Score. Engine decides evidence; LLM may verbalize evidence.

| ما يجب أن يذكره | مثال |
| --- | --- |
| مطابقات واضحة | النوع والموقع مطابقان. |
| فروق كمية | المساحة أقل بـ8م² من Preferred target. |
| السعر | السعر داخل الحد الأقصى لكنه أعلى من target بـ100 مليون سنتيم. |
| التحقق | وجود الدفتر العقاري مصرح به ولم تتم مراجعته من تُراب. |
| Freshness | الإتاحة مؤكدة منذ 3 أيام. |
| ما لا يُكشف | seller expectation أو claim خاصة غير مسموح مشاركتها. |

> **ممنوع** لا تعرض “Match 87%” كحقيقة للمستخدم. يمكن الاحتفاظ بـinternal ordering score إن احتجنا، لكن القرار والتفسير يعتمدان على Breakdown صريح.

# 17. عقد الذكاء الاصطناعي AI Contract
## 17.1 ما يمكن للـAI فعله
- استخراج حقول مقترحة من العربية/الدارجة/الفرنسية والنصوص المختلطة.
- تطبيع السعر والوحدات والأماكن بعد التأكيد البشري عند الحساسية.
- اقتراح Property Identity candidates مع الأدلة.
- اقتراح Match Candidates وترتيبها ضمن القواعد.
- كشف Missing/Contradictory information.
- تلخيص مكالمات/محادثات إلى حقول مقترحة.
- صياغة Explanation من نتائج محرك محسوبة.
- اقتراح Task أو Relaxation scenario للموظف.

## 17.2 ما لا يجوز للـAI فعله
- إنشاء OPPORTUNITY دون Human Review في v0.1.
- دمج PROPERTY records تلقائيًا.
- تغيير REQUEST أو مرونتها تلقائيًا.
- رفع fact_verification_level دون Verification Event حقيقي.
- اختراع معلومة غير موجودة لتجاوز UNKNOWN.
- إرسال تواصل حساس أو موافقة أو مشاركة بيانات خاصة دون سياسة/مراجعة.
- كشف معلومات خاصة لأن Matching Engine استخدمها داخليًا.

## 17.3 AI Traceability
| الحقل | الهدف |
| --- | --- |
| model/provider/version | إعادة إنتاج/تحليل الاختلاف بين النماذج. |
| prompt_or_parser_version | معرفة أي منطق استخراج استُخدم. |
| input_refs | ما الـObservations/Claims التي رآها AI. |
| output | الاقتراح الخام/المنظم. |
| extraction_confidence | ثقة فنية في الاستخراج، لا تحقق الحقيقة. |
| human_decision | Approved/Corrected/Rejected + reason. |
| created_at | الزمن. |

# 18. Communication Infrastructure وWhatsApp
الحاجة الأساسية هي قناة رسمية وسجل قابل للاسترجاع، لا بناء Messenger خاص. WhatsApp Business هو القناة الطبيعية الأولى، بينما TURAB يحتفظ بالسياق المنظم والربط بالكيانات.

```text
Customer <-> TURAB WhatsApp Business <-> Communication Layer <-> Back Office
                                          |
                                          +-> PARTY
                                          +-> REQUEST
                                          +-> PROPERTY
                                          +-> OPPORTUNITY
```

| الحقل | المطلوب |
| --- | --- |
| channel | WHATSAPP / PHONE / SMS / WEB / OTHER |
| direction | INBOUND / OUTBOUND |
| party_id | من/إلى من. |
| operator_id | الموظف المسؤول. |
| context | request_id/property_id/opportunity_id عند وجوده. |
| external_message_id | عند التكامل الرسمي. |
| timestamps | sent/received/delivered/read عند توفرها. |
| message_type | text/image/document/voice/system... |
| content/reference | النص أو مرجع التخزين وفق سياسة الخصوصية. |

القرارات الجوهرية المتخذة هاتفيًا — مثل السعر، الإذن بالنشر، تغيير الإتاحة أو السماح بالمشاركة — SHOULD تؤكد كتابةً عبر قناة رسمية حيثما كان ذلك عمليًا. هذا Operational Record وليس ادعاءً بأنه دليل قانوني مضمون.

# 19. Back Office — ما يجب أن يراه الموظف
المبدأ: الشاشة تعرض ما يتطلب قرارًا الآن، لا كل ما في النظام.

| Queue | متى يدخل العنصر |
| --- | --- |
| Requests needing qualification | طلب ناقص أو غامض أو Freshness منتهية. |
| Properties needing review | تعارض/نقص/إتاحة قديمة أو Identity candidate. |
| External Leads | اكتشافات لم تصبح PARTY/PROPERTY/REQUEST نشطة بعد. |
| AI Candidate Matches | Candidates تنتظر Approved/Rejected/Need More Information. |
| Opportunities follow-up | فرص Valid تحتاج interaction/follow-up. |
| Stale data | حقول حرجة تحتاج reconfirmation. |
| Identity Resolution | Possible same-property pairs تنتظر حكمًا. |

## 19.1 شاشة Match Review المرجعية
- ملخص REQUEST ومعايير Required/Preferred/Flexible.
- ملخص PROPERTY + Offer/Source relevant.
- Criterion-by-criterion PASS/FAIL/UNKNOWN + evidence level.
- Freshness وPermission status.
- Known differences وActionable Unknowns.
- AI/Rule explanation وrule_version.
- ثلاثة قرارات فقط: APPROVE / REJECT / NEED_MORE_INFORMATION.
- في REJECT يجب reason_code، وفي NEED_MORE_INFORMATION يجب Task محددة مثل «تأكد من نوع الوثيقة» لا «اتصل بالعميل» فقط.

## 19.2 Match Diagnostic
يجب أن تستطيع صفحة REQUEST عرض: Opportunities ready، Candidates requiring info، Near matches، أهم blockers، وأفضل next action. هذا يسمح للموظف بفهم السوق حول الطلب بدل رؤية شاشة “0 نتائج”.

# 20. واجهة المستخدم الخارجية — العقود الوظيفية الأساسية
| المسار | العقد الوظيفي |
| --- | --- |
| أبحث عن عقار | إنشاء REQUEST قصيرة؛ التحقق بالهاتف عند الحفظ؛ لا وعد بالنتيجة؛ النظام يواصل المطابقة لاحقًا. |
| لدي عقار | إنشاء PROPERTY/OFFER؛ اختيار مفهوم للمستخدم يعكس Public/Private/Potential دون فرض المصطلحات التقنية. |
| تصفح العقارات | Public Properties فقط؛ Direct Interest لا يتحول تلقائيًا إلى REQUEST. |
| Opportunity View | تعرض لماذا قد تناسب، الفروق المعروفة، مستوى التحقق بصياغة دقيقة، وإجراءات: مهتم / أحتاج معلومات / غير مناسب. |
| غير مناسب | سبب سريع + تعليق اختياري؛ يستخدم كfeedback ولا يغير REQUEST تلقائيًا. |

# 21. نموذج بيانات مفاهيمي مقترح — ليس Migration نهائية
الأسماء التالية مرجعية لتثبيت المعنى. يمكن للمطور تعديل الشكل الفعلي بعد Design Review، لكن لا يجوز إسقاط الفواصل المنطقية.

## PARTY
| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| party_id | UUID | نعم | المعرف الداخلي. |
| party_type | ENUM | نعم | PERSON/BUSINESS. |
| display_name | TEXT | نعم | الاسم. |
| phone_normalized | TEXT | حسب الحالة | رقم موحد. |
| phone_verification_status | ENUM | نعم | UNVERIFIED/VERIFIED_CONTROL... |
| created_at | TIMESTAMP | نعم |  |

## REQUEST
| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| request_id | UUID | نعم |  |
| party_id | FK | نعم | صاحب الطلب. |
| status | ENUM | نعم | RAW/CONTACTED/QUALIFIED/ACTIVE/PAUSED/CLOSED... |
| intent_stage | ENUM | نعم | EXPLORING/ACTIVE_SEARCH/READY_TO_ACT |
| budget_target_dzd | BIGINT | لا |  |
| budget_max_dzd | BIGINT | لا |  |
| budget_flexibility | ENUM/TEXT | لا |  |
| last_confirmed_at | TIMESTAMP | لا | Freshness. |
| version | INT | نعم | نسخة منطقية للتتبع. |

## PROPERTY
| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| property_id | UUID | نعم | هوية الأصل العقاري. |
| property_type | ENUM | نعم |  |
| canonical_location_id | FK | لا |  |
| current_availability | ENUM | نعم |  |
| availability_last_confirmed_at | TIMESTAMP | لا |  |
| visibility_mode | ENUM | نعم | PUBLIC/PRIVATE/POTENTIAL semantics |
| version | INT | نعم |  |

## PROPERTY_OFFER
| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| offer_id | UUID | نعم |  |
| property_id | FK | نعم |  |
| party_id | FK | نعم | الطرف الذي يقدم العرض. |
| transaction_type | ENUM | نعم | SALE/RENT... |
| asking_price_dzd | BIGINT | لا |  |
| price_negotiable | BOOL/ENUM | لا |  |
| seller_expectation_dzd | BIGINT | لا | حقل داخلي/سري إن جُمع. |
| price_visibility | ENUM | نعم | PUBLIC/ON_REQUEST/PRIVATE |
| status | ENUM | نعم |  |

## MATCH_CANDIDATE
| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| match_id | UUID | نعم |  |
| request_id | FK | نعم |  |
| property_id | FK | نعم |  |
| evaluated_at | TIMESTAMP | نعم |  |
| request_version | INT | نعم | snapshot ref |
| property_version | INT | نعم | snapshot ref |
| matching_policy_version | TEXT | نعم |  |
| review_status | ENUM | نعم | PENDING/APPROVED/REJECTED/NEED_INFO |
| review_reason | TEXT/CODE | لا |  |

## OPPORTUNITY
| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| opportunity_id | UUID | نعم |  |
| request_id | FK | نعم |  |
| property_id | FK | نعم |  |
| approved_match_id | FK | نعم |  |
| status | ENUM | نعم | NEW/SHARED/ENGAGED/CLOSED |
| validity_status | ENUM | نعم | VALID/NEEDS_CONFIRMATION/INVALID |
| sharing_scope | ENUM | نعم |  |
| why_real | TEXT/JSON | نعم | أسباب منظمة/مقروءة. |
| known_differences | JSON | لا |  |
| last_confirmed_at | TIMESTAMP | لا |  |

## CLAIM / FIELD_HISTORY
| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| claim_id | UUID | نعم | يمكن تبسيطه في 0.1. |
| subject_type | TEXT | نعم | PROPERTY/OFFER/REQUEST/PARTY |
| subject_id | UUID | نعم |  |
| attribute_code | TEXT | نعم |  |
| claimed_value | JSON/TEXT | نعم |  |
| source_id | FK | لا |  |
| asserted_by_party_id | FK | لا |  |
| observed_at | TIMESTAMP | لا |  |
| recorded_at | TIMESTAMP | نعم |  |
| valid_from | TIMESTAMP | لا |  |
| valid_to | TIMESTAMP | لا |  |
| verification_level | ENUM | نعم |  |

## PROPERTY_IDENTITY_CANDIDATE
| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| candidate_id | UUID | نعم |  |
| property_a_id | FK | نعم |  |
| property_b_id | FK | نعم |  |
| signals | JSON | نعم | location/text/image/party/contradiction... |
| review_status | ENUM | نعم | PENDING/SAME/DISTINCT/UNSURE |
| review_reason | TEXT/CODE | لا |  |
| reviewer_id | FK | لا |  |

# 22. عقود خدمات/API مرجعية
هذه ليست أسماء endpoints ملزمة، لكنها توضح الحدود المنطقية المطلوبة بين الخدمات. المطور يمكنه تنفيذ REST/GraphQL/monolith services بشرط الحفاظ على العقود السلوكية.

| Service | الوظائف الأساسية |
| --- | --- |
| PartyService | find/create party، verify phone control، relationships، claim ownership/management. |
| RequestService | create/update/version/activate/pause/reconfirm، criteria management. |
| PropertyService | create/update، offers/sources، availability/visibility، canonical fields. |
| IdentityService | generate candidates، explain signals، review SAME/DISTINCT/UNSURE. |
| TruthService | record observation/claim/history، verification events، resolve current values. |
| MatchingService | evaluate(request, property)، generate candidates، diagnostics، relaxation scenarios. |
| ReviewService | approve/reject/need-info مع reason/task. |
| OpportunityService | create only from approved match، share/engage/close/revalidate. |
| CommunicationService | timeline، WhatsApp/webhook refs، link interactions to domain entities. |
| AuditService | old/new values، actor، timestamp، context. |

## 22.1 مثال نتيجة Matching قابلة للتفسير
```text
{
  "request_id": "R-001",
  "property_id": "P-008",
  "eligibility": "NEED_MORE_INFORMATION",
  "criteria": [
    {"code":"property_type","importance":"REQUIRED","status":"PASS"},
    {"code":"location","importance":"REQUIRED","status":"PASS"},
    {"code":"budget_max","importance":"REQUIRED","status":"PASS"},
    {
      "code":"document_type",
      "importance":"REQUIRED",
      "status":"UNKNOWN",
      "blocking": true,
      "reason_code":"DOCUMENT_NOT_KNOWN"
    }
  ],
  "freshness": {"request":"FRESH","property":"FRESH"},
  "permission": "PASS",
  "next_action": {"type":"VERIFY_DOCUMENT","priority":"HIGH"},
  "matching_policy_version":"0.1.0"
}
```

# 23. الثوابت Business Invariants
1. أي Hard FAIL مؤكد يمنع إنشاء OPPORTUNITY.
2. Hard UNKNOWN لا يتحول صامتًا إلى PASS أو FAIL.
3. Rank #1 لا يعني Opportunity إذا Freshness أو Permission أو Blocking Unknown تفشل.
4. حل معلومة ناقصة عالية القيمة يسبق اقتراح تغيير تفضيل المستخدم عندما يمكن أن ينتج Exact Match.
5. Constraint Relaxation لا تعدل REQUEST تلقائيًا.
6. نفس REQUEST × PROPERTY لا ينتجان أكثر من Opportunity مفتوحة واحدة بسبب تعدد Sources/Offers.
7. Explanation لا تكشف claim خاصة أو seller_expectation غير مسموح بها.
8. No valid Opportunity مخرج صحيح.
9. AI لا ترفع verification level ولا تدمج PROPERTY تلقائيًا.
10. حذف/إغلاق سجل لا يمحو History أو Claims الحرجة المطلوبة للتدقيق.
11. Public visibility لا تعني أن كل التفاصيل قابلة للمشاركة؛ sharing_scope يحكم التفصيل.
12. Phone verified لا يساوي identity legally verified.

# 24. Acceptance Tests المرجعية
| ID | السيناريو | النتيجة المتوقعة |
| --- | --- | --- |
| M-01 | Required location FAIL مع بقية المعايير ممتازة | REJECT CANDIDATE؛ لا Opportunity. |
| M-02 | Required document UNKNOWN | NEED_MORE_INFORMATION + blocking task. |
| M-03 | Asking أعلى من max لكن seller expectation مؤكدة داخليًا ضمن max | يمكن PASS/POTENTIAL حسب policy؛ لا كشف expectation للمشتري. |
| M-04 | Negotiable فقط دون حد تفاوض مؤكد والسعر أعلى من max | UNKNOWN/POTENTIAL PRICE؛ لا PASS تلقائي. |
| M-05 | Property stale لكن كل المعايير PASS | NEEDS_CONFIRMATION قبل Opportunity. |
| M-06 | Request stale | لا مشاركة Opportunity جديدة قبل reconfirm حسب policy. |
| M-07 | Private property + sharing_scope SUMMARY_ONLY | Opportunity قد تنشأ، لكن presentation تحجب التفاصيل غير المسموحة. |
| M-08 | نفس Property جاءت من Facebook ووسيط | Opportunity واحدة؛ Sources/Offers متعددة. |
| M-09 | Identity candidate high similarity | لا merge آلي؛ يدخل Review. |
| M-10 | صورتان متشابهتان لوحدتين في مشروع واحد | يمكن DISTINCT مع reason SIMILAR_UNITS. |
| M-11 | Owner claim 270m² ثم document seen 268.5m² | History يحتفظ بالاثنين؛ resolved current may adopt 268.5 وفق rule/reviewer. |
| M-12 | No exact matches لكن P08 يطابق كل شيء والوثيقة UNKNOWN | next_action = VERIFY_DOCUMENT قبل relaxation. |
| M-13 | بعد حل unknown لا توجد فرصة؛ أقرب عقار يفشل location فقط | Diagnostic يعرض location relaxation scenario دون تعديل request. |
| M-14 | Buyer rejects 3 opportunities بسبب نفس المنطقة | AI may flag possible preference mismatch؛ لا تغير REQUEST تلقائيًا. |
| M-15 | Property sold on 5 Sep, learned on 20 Sep | temporal history differentiates valid_from from recorded_at. |
| O-01 | Human approves candidate مستوفية gates | Create one Opportunity. |
| O-02 | Human rejects candidate | No Opportunity; reason stored. |
| O-03 | Need More Information | Create task; candidate remains non-opportunity. |

# 25. Dataset صناعي أولي لاختبار المحرك
هذه المجموعة مرجعية وليست بيانات سوق حقيقية. الغرض منها إجبار المحرك على التعامل مع حالات أدرار الصعبة بدل اختبارات Happy Path فقط.

| ID | وصف مختصر | التشخيص المتوقع |
| --- | --- | --- |
| P01 | تيليلان الجديدة، فيلا 260م²، 2.35B centimes، Land Book declared، متاح مؤكد منذ يومين | Eligible candidate مع verification=Declared. |
| P02 | تيليلان، 300م²، asking 2.55B، seller expectation داخلي 2.40B، Private | Eligible/Potential حسب policy؛ privacy gate. |
| P03 | طريق المطار، 300م²، 2.20B، Land Book checked | Hard fail إذا location=Tililane Required؛ Near Match. |
| P04 | تيليلان، 280م²، 2.30B، document unknown | Need info: document. |
| P05 | تيليلان، 270م²، 2.10B، possession certificate | Hard fail إذا Land Book Required. |
| P06 | تيليلان، 290م²، 2.45B، negotiable، last confirmed 30 days | Need info: price compatibility + freshness. |
| P07 | تيليلان، Potential، 320م²، expected 2.38B | Reconfirm willingness before Opportunity. |
| P08 | تيليلان، 255م²، 2.18B، document unknown، availability fresh | High-value actionable unknown. |

## 25.1 Request test R-001
```text
type = VILLA [REQUIRED]
location = ADR-NEW-TIL [REQUIRED]
budget_max = 24,000,000 DZD [REQUIRED]
document = LAND_BOOK [REQUIRED]
land_area >= 250m2 [PREFERRED]
intent_stage = READY_TO_ACT
request_last_confirmed_at = 2 days ago
```

# 26. تسلسل التنفيذ المقترح
| المرحلة | النطاق | شرط الخروج |
| --- | --- | --- |
| A. Core Domain | PARTY/ACCOUNT/REQUEST/PROPERTY/OFFER/SOURCE + states + audit basics | يمكن إنشاء السيناريوهات يدويًا دون AI. |
| B. Truth & History Lite | field provenance/history + verification level + timestamps | كل معلومة حرجة قابلة لتتبع المصدر والتاريخ. |
| C. Matching Rules | criterion model + PASS/FAIL/UNKNOWN + hard/soft + reason codes | اختبارات M-01..M-06 تمر. |
| D. Human Review & Opportunity | review decisions + tasks + opportunity gates | لا Opportunity دون Approved match. |
| E. Match Diagnostic | blocking unknowns + blockers + near matches + next action | No-result cases تصبح قابلة للتشخيص. |
| F. Identity Resolution Lite | blocking rules + text/party/location signals + human review | اختبارات M-08..M-10 تمر. |
| G. Communication Timeline | WhatsApp-ready model + interactions + consent confirmations | السياق محفوظ حتى دون inbox متقدم. |
| H. AI Assist | extraction/summarization/explanation/traces | AI لا تكسر أي invariant ويمكن إيقافها دون كسر النظام. |
| I. Optimization later | image hash, pg_trgm/pgvector, probabilistic ER, LTR | فقط بعد وجود بيانات فعلية تبررها. |

# 27. متطلبات غير وظيفية
| المجال | المتطلب |
| --- | --- |
| Auditability | كل قرار حساس قابل لإرجاعه إلى actor/time/source/rule version. |
| Explainability | كل Match/Reject/Need-info قابل لتفسير معياري لا نص AI فقط. |
| Privacy | الحد الأدنى من البيانات، فصل internal/private fields، sharing_scope enforcement في service layer لا UI فقط. |
| Security | صلاحيات role-based، secrets خارج الكود، log وصول للأفعال الحساسة. |
| Data Integrity | FK/unique constraints وtransactional writes للقرارات المترابطة. |
| Idempotency | webhooks/imports/assisted entry يجب ألا تنشئ تكرارًا عند retry. |
| Localization | Arabic-first، دعم aliases الفرنسية/اللاتينية، DZD canonical monetary storage. |
| Configurability | freshness thresholds، matching policy، reason codes قابلة للإصدار دون hard-code مبعثر. |
| Observability | logs/metrics للـmatching/review/queue latency دون تسريب محتوى حساس. |
| Portability | لا نعتمد مبكرًا على stack يصعب تغييره؛ PostgreSQL يمكن أن يبقى source of truth. |

# 28. Reason Codes مقترحة
يجب استخدام أكواد مستقرة للتحليل مع نص عربي/فرنسي للواجهة. لا تعتمد التحليلات على نص حر فقط.

| الفئة | أمثلة أكواد |
| --- | --- |
| Matching fail | TYPE_MISMATCH, LOCATION_MISMATCH, BUDGET_OVER_MAX, DOCUMENT_INCOMPATIBLE, AREA_BELOW_REQUIRED |
| Unknown | DOCUMENT_NOT_KNOWN, PRICE_COMPATIBILITY_UNKNOWN, AVAILABILITY_STALE, OWNER_WILLINGNESS_UNKNOWN |
| Permission | NO_PERMISSION_TO_SHARE, SUMMARY_ONLY, CONTACT_REQUIRES_CONFIRMATION |
| Identity | SAME_CONFIRMED_BY_OWNER, MULTIPLE_IMAGES_MATCH, DISTINCT_DIFFERENT_PLOT, DISTINCT_SIMILAR_UNITS |
| Opportunity close | BUYER_REJECTED, OWNER_REJECTED, PROPERTY_UNAVAILABLE, REQUEST_CHANGED, UNREACHABLE, DEAL_REPORTED, OTHER |
| Request feedback | PRICE, LOCATION, AREA, CONDITION, DOCUMENT, OTHER |

# 29. Design Ledger — قرارات هذه الجولة التقنية
| الفكرة | التصنيف | ملاحظة |
| --- | --- | --- |
| Hybrid Matching: rules + structured + semantics + human | نعتمد الآن | الـsemantic optional في أول implementation، لكن الحدود مع rules ثابتة. |
| Property Identity Resolution | نعتمد بنيويًا الآن | تنفيذ rule-based + human review أولًا. |
| Image perceptual hash | نهيئ له | مفيد للإعلانات متعددة المصادر؛ ليس شرطًا لإطلاق slice الأول. |
| Provenance/Claims/Temporal lite | نعتمد الآن | لا Full knowledge graph. |
| Match Diagnostic | نعتمد الآن Back Office | جزء أساسي من تعلم التشغيل. |
| Constraint Relaxation | نهيئ تدريجيًا | تشخيص فقط؛ لا auto-change. |
| AI trace + human feedback dataset | نهيئ من البداية | أساس تعلم لاحق. |
| Learning-to-Rank / MaxSAT / probabilistic ER | نؤجل | بعد بيانات كافية. |
| Autonomous merging / autonomous opportunity | نستبعد | يتعارض مع Human-in-the-loop. |

# 30. Definition of Done للمطور قبل اعتبار Matching Core v0.1 صالحًا
- يمكن تشغيل السيناريو الكامل: REQUEST + PROPERTY -> Candidate -> Human Review -> OPPORTUNITY.
- يمكن إعادة بناء سبب كل Candidate من criterion results وrule version.
- يمكن تمثيل PASS/FAIL/UNKNOWN دون التواءات أو null semantics غامضة.
- لا Opportunity تتجاوز hard/freshness/permission gates.
- كل Need More Information ينتج Task محددة قابلة للغلق.
- Match Diagnostic يميز exact/near/unknown blockers ويقترح next action واضحًا.
- History يحتفظ بتغير السعر/availability/document claims المهمة ومصادرها.
- Identity Review لا يمحو Source/Offer عند تأكيد SAME property.
- sharing_scope مطبق في backend/service layer.
- AI يمكن تعطيلها ويستمر Core deterministic في العمل.
- اختبارات القبول المرجعية تمر آليًا قدر الإمكان، مع حالات review البشرية موثقة.
- أي تغيير في هذه القواعد بعد ذلك يدخل Design Ledger/Versioned policy ولا يعدل بصمت في الكود.

# 31. الخلاصة التنفيذية للمطور
> **ما الذي نبنيه فعليًا؟** نحن لا نبني موقع إعلانات مع فلتر ذكي. نحن نبني نظامًا يعرف أي عقار نتحدث عنه، من أين جاءت كل معلومة عنه، مدى حداثتها والتحقق منها، ثم يقارن الحالة التشغيلية الحالية للعقار بطلب حي وفق قيود صريحة، ويحوّل المطابقة إلى Opportunity فقط بعد مراجعة بشرية.

```text
RAW MARKET INFO
   -> PROPERTY IDENTITY
   -> PROVENANCE / CLAIMS / CURRENT RESOLUTION
   -> REQUEST CRITERIA
   -> HARD GATE (PASS/FAIL/UNKNOWN)
   -> SOFT RANKING
   -> FRESHNESS + PERMISSION
   -> EXPLAINED MATCH CANDIDATE
   -> HUMAN REVIEW
   -> OPPORTUNITY
   -> INTERACTIONS / OUTCOMES / LEARNING
```

أهم جودة للنظام ليست أن يعطي Matching كثيرة، بل أن يمنع Match غير صالحة من أن تبدو Opportunity، وأن يشرح بوضوح ما ينقصنا وما الذي ينبغي فعله بعد ذلك.

# ملحق A — أمثلة على قرارات صحيحة وخاطئة
| الحالة | سلوك خاطئ | سلوك TURAB الصحيح |
| --- | --- | --- |
| وثيقة مجهولة | رفض العقار | NEED_MORE_INFORMATION إذا الوثيقة Required. |
| سعر أعلى قليلًا ومعلن Negotiable فقط | اعتباره Match تلقائيًا | PRICE UNKNOWN/POTENTIAL حتى يتأكد نطاق التفاوض. |
| نفس العقار من مصدرين | حذف أحد الإعلانات | ربطهما PROPERTY واحدة مع OFFER/SOURCE مستقلة. |
| AI فهم “دفتر عقاري” | رفعها Verified | تبقى Declared؛ AI extraction confidence منفصلة. |
| No exact match | توصية بأقرب عقار رغم Hard Fail | 0 Opportunity + Diagnostic/near matches. |
| Buyer rejected عدة Opportunities | تغيير request تلقائيًا | اقتراح مراجعة للموظف فقط. |
| Private seller expectation | عرضها في explanation | استخدام داخلي دون disclosure إذا sharing_scope لا يسمح. |

# ملحق B — أسئلة يجب على المطور طرحها قبل أي Shortcut
- هل هذا التبسيط يخلط PROPERTY مع POST/OFFER؟
- هل سيمحو مصدر المعلومة أو تاريخها؟
- هل يحول UNKNOWN إلى FAIL أو PASS بلا دليل؟
- هل يجعل AI صاحب القرار بدل المراجع؟
- هل يكشف معلومة داخلية لمجرد أن المحرك استخدمها؟
- هل سيصعب لاحقًا معرفة لماذا أنشئت Opportunity؟
- هل نضيف Infrastructure أو Feature لا تختبر فرضية 0.1؟
- إذا كان الجواب نعم، يجب فتح Design Ledger قبل التنفيذ.
