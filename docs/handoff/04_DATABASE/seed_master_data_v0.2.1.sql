-- TURAB — minimum master data seed v0.2.1
-- Run after schema_v0.2.1.sql
BEGIN;
SET search_path = turab, public;

-- Wilaya
INSERT INTO locations(code, canonical_ar, canonical_fr, location_type)
VALUES ('W-ADRAR','ولاية أدرار','Wilaya d''Adrar','WILAYA')
ON CONFLICT (code) DO NOTHING;

-- 16 communes of Wilaya Adrar, per TURAB Foundation baseline.
WITH w AS (SELECT location_id FROM locations WHERE code='W-ADRAR')
INSERT INTO locations(code,parent_id,canonical_ar,canonical_fr,location_type)
SELECT x.code,w.location_id,x.ar,x.fr,'COMMUNE'
FROM w CROSS JOIN (VALUES
 ('C-ADRAR','أدرار','Adrar'),
 ('C-TAMEST','تامست','Tamest'),
 ('C-REGGANE','رقان','Reggane'),
 ('C-IN-ZGHMIR','إن زغمير','In Zghmir'),
 ('C-TIT','تيت','Tit'),
 ('C-TSABIT','تسابيت','Tsabit'),
 ('C-ZAOUIT-KOUNTA','زاوية كنتة','Zaouiet Kounta'),
 ('C-AOULEF','أولف','Aoulef'),
 ('C-TIMEKTEN','تيمقتن','Timekten'),
 ('C-TAMANTIT','تامنطيط','Tamantit'),
 ('C-FENOUGHIL','فنوغيل','Fenoughil'),
 ('C-SALI','سالي','Sali'),
 ('C-AKABLI','أقبلي','Akabli'),
 ('C-OULED-AHMED-TIMMI','أولاد أحمد تيمي','Ouled Ahmed Timmi'),
 ('C-BOUDA','بودة','Bouda'),
 ('C-SEBAA','السبع','Sebaa')
) AS x(code,ar,fr)
ON CONFLICT (code) DO NOTHING;

-- Confirmed high-level structure inside Adrar commune.
WITH c AS (SELECT location_id FROM locations WHERE code='C-ADRAR')
INSERT INTO locations(code,parent_id,canonical_ar,canonical_fr,location_type)
SELECT x.code,c.location_id,x.ar,x.fr,x.t
FROM c CROSS JOIN (VALUES
 ('ADR-CENTER','وسط المدينة','Centre-ville','AREA'),
 ('ADR-KSOUR','قصور أدرار','Ksour d''Adrar','AREA'),
 ('ADR-NEW-SMB','المدينة الجديدة سيدي محمد بلكبير','Nouvelle ville Sidi Mohamed Belkebir','AREA'),
 ('ADR-NEW-TIL','المدينة الجديدة تيليلان','Nouvelle ville Tililane','AREA'),
 ('ADR-AIRPORT','طريق المطار','Route de l''aéroport','AREA')
) AS x(code,ar,fr,t)
ON CONFLICT (code) DO NOTHING;

-- Confirmed ksour under ADR-KSOUR. Ksar Tililane is intentionally distinct from ADR-NEW-TIL.
WITH p AS (SELECT location_id FROM locations WHERE code='ADR-KSOUR')
INSERT INTO locations(code,parent_id,canonical_ar,canonical_fr,location_type)
SELECT x.code,p.location_id,x.ar,x.fr,'KSAR'
FROM p CROSS JOIN (VALUES
 ('ADR-KSAR-OULED-ALI','قصر أولاد علي','Ksar Ouled Ali'),
 ('ADR-KSAR-ADGHA','قصر أدغا','Ksar Adgha'),
 ('ADR-KSAR-BARBAA','قصر بربع','Ksar Barbaa'),
 ('ADR-KSAR-OUGDIM','قصر أقديم','Ksar Ougdim'),
 ('ADR-KSAR-OULED-OUNGAL','قصر أولاد أونقال','Ksar Ouled Oungal'),
 ('ADR-KSAR-OULED-OUCHEN','قصر أولاد أوشن','Ksar Ouled Ouchen'),
 ('ADR-KSAR-TILILANE','قصر تيليلان','Ksar Tililane'),
 ('ADR-KSAR-MERAGUEN','قصر مراقن','Ksar Meraguen')
) AS x(code,ar,fr)
ON CONFLICT (code) DO NOTHING;

-- A conservative alias set. Additional aliases must pass operator review before becoming canonical mappings.
INSERT INTO location_aliases(location_id, alias_text, language_code, normalized_text, source_note)
SELECT location_id, alias_text, lang, norm, 'TURAB baseline v1.0'
FROM (
 SELECT (SELECT location_id FROM locations WHERE code='ADR-NEW-TIL') AS location_id, 'تيليلان الجديدة' AS alias_text, 'ar' AS lang, 'تيليلان الجديدة' AS norm
 UNION ALL SELECT (SELECT location_id FROM locations WHERE code='ADR-NEW-TIL'), 'Tililane nouvelle ville', 'fr', 'tililane nouvelle ville'
 UNION ALL SELECT (SELECT location_id FROM locations WHERE code='ADR-KSAR-TILILANE'), 'قصر تيليلان', 'ar', 'قصر تيليلان'
 UNION ALL SELECT (SELECT location_id FROM locations WHERE code='ADR-KSAR-MERAGUEN'), 'مراقن', 'ar', 'مراقن'
 UNION ALL SELECT (SELECT location_id FROM locations WHERE code='ADR-KSAR-MERAGUEN'), 'Meraguen', 'fr', 'meraguen'
 UNION ALL SELECT (SELECT location_id FROM locations WHERE code='ADR-AIRPORT'), 'طريق المطار', 'ar', 'طريق المطار'
) a
WHERE location_id IS NOT NULL
ON CONFLICT (location_id, alias_text) DO NOTHING;

-- Core attribute definitions. Keep specialized attributes extensible rather than adding columns casually.
INSERT INTO attribute_definitions(code,label_ar,label_fr,value_type,unit,applies_to) VALUES
 ('BEDROOMS','عدد غرف النوم','Chambres','NUMBER',NULL,ARRAY['HOUSE_VILLA','APARTMENT']::property_type[]),
 ('ROOMS','عدد الغرف','Pièces','NUMBER',NULL,ARRAY['HOUSE_VILLA','APARTMENT']::property_type[]),
 ('FLOORS','عدد الطوابق','Étages','NUMBER',NULL,ARRAY['HOUSE_VILLA','BUILDING']::property_type[]),
 ('FLOOR_NUMBER','الطابق','Étage','NUMBER',NULL,ARRAY['APARTMENT','SHOP_COMMERCIAL']::property_type[]),
 ('CONSTRUCTION_STATE','حالة الإنجاز','État de construction','ENUM',NULL,NULL),
 ('RIGHT_TYPE','نوع الحق/الوضعية','Type de droit','ENUM',NULL,NULL),
 ('DOCUMENT_TYPE','نوع الوثيقة','Type de document','ENUM',NULL,NULL),
 ('DOCUMENT_STATUS','حالة الوثيقة','État du document','ENUM',NULL,NULL)
ON CONFLICT (code) DO NOTHING;

-- Controlled options for legal/document fields used in hard matching.
INSERT INTO attribute_options(attribute_definition_id,option_code,label_ar,label_fr,sort_order)
SELECT d.attribute_definition_id, x.code, x.ar, x.fr, x.ord
FROM attribute_definitions d
JOIN (VALUES
 ('RIGHT_TYPE','PRIVATE_OWNERSHIP','ملكية خاصة','Propriété privée',10),
 ('RIGHT_TYPE','POSSESSION','حيازة','Possession',20),
 ('RIGHT_TYPE','AGRICULTURAL_CONCESSION','امتياز فلاحي','Concession agricole',30),
 ('RIGHT_TYPE','CO_OWNERSHIP','ملكية على الشيوع','Indivision / copropriété',40),
 ('RIGHT_TYPE','INHERITED_ESTATE','تركة / إرث','Succession',50),
 ('RIGHT_TYPE','OTHER','أخرى','Autre',90),
 ('RIGHT_TYPE','UNKNOWN','غير معلوم','Inconnu',99),
 ('DOCUMENT_TYPE','LAND_BOOK','دفتر عقاري','Livret foncier',10),
 ('DOCUMENT_TYPE','PUBLISHED_TITLE_DEED','عقد ملكية مشهر','Acte publié',20),
 ('DOCUMENT_TYPE','ADMINISTRATIVE_DEED','عقد إداري','Acte administratif',30),
 ('DOCUMENT_TYPE','POSSESSION_CERTIFICATE','شهادة حيازة','Certificat de possession',40),
 ('DOCUMENT_TYPE','AGRICULTURAL_CONCESSION_DEED','عقد امتياز فلاحي','Acte de concession agricole',50),
 ('DOCUMENT_TYPE','UNSPECIFIED_DOCUMENT','وثائق غير محددة','Document non précisé',80),
 ('DOCUMENT_TYPE','OTHER','وثيقة أخرى','Autre document',90),
 ('DOCUMENT_TYPE','UNKNOWN','غير معلوم','Inconnu',99),
 ('DOCUMENT_STATUS','AVAILABLE','متوفرة','Disponible',10),
 ('DOCUMENT_STATUS','NOT_AVAILABLE_NOW','غير متوفرة حاليًا','Indisponible actuellement',20),
 ('DOCUMENT_STATUS','IN_PROCESS','قيد الإنجاز / التسوية','En cours',30),
 ('DOCUMENT_STATUS','UNCLEAR','غير واضحة','Non clair',90)
) AS x(attr,code,ar,fr,ord) ON d.code=x.attr
ON CONFLICT (attribute_definition_id, option_code) DO NOTHING;

-- Stable criterion registry. Free-text criterion names are prohibited in production data.
INSERT INTO criterion_definitions(code,label_ar,label_en,value_type) VALUES
 ('PROPERTY_TYPE','نوع العقار','Property type','ENUM'),
 ('TRANSACTION_INTENT','نوع العملية','Transaction intent','ENUM'),
 ('LOCATION','الموقع','Location','LOCATION'),
 ('BUDGET_MAX','الحد الأقصى للميزانية','Maximum budget','MONEY'),
 ('BUDGET_TARGET','الميزانية المستهدفة','Target budget','MONEY'),
 ('LAND_AREA_MIN','الحد الأدنى لمساحة الأرض','Minimum land area','NUMBER'),
 ('BUILT_AREA_MIN','الحد الأدنى للمساحة المبنية','Minimum built area','NUMBER'),
 ('DOCUMENT_TYPE','نوع الوثيقة','Document type','ENUM'),
 ('RIGHT_TYPE','نوع الحق','Right / tenure type','ENUM'),
 ('ROOMS_MIN','الحد الأدنى لعدد الغرف','Minimum rooms','NUMBER'),
 ('BEDROOMS_MIN','الحد الأدنى لعدد غرف النوم','Minimum bedrooms','NUMBER'),
 ('CUSTOM_ATTRIBUTE','خاصية إضافية منظمة','Structured custom attribute','JSON')
ON CONFLICT (code) DO NOTHING;

-- Reason codes used by matching, review, identity, closure and communication.
INSERT INTO reason_codes(code,category,label_ar,label_en) VALUES
 ('LOCATION_MISMATCH','MATCH','الموقع لا يطابق شرطًا إلزاميًا','Required location mismatch'),
 ('PROPERTY_TYPE_MISMATCH','MATCH','نوع العقار لا يطابق الطلب','Property type mismatch'),
 ('BUDGET_EXCEEDED','MATCH','السعر يتجاوز الحد الأقصى المؤكد','Confirmed price exceeds maximum budget'),
 ('PRICE_NOT_KNOWN','MATCH','السعر غير معلوم بما يكفي لاتخاذ القرار','Price not known'),
 ('PRICE_NEGOTIATION_UNCONFIRMED','MATCH','قابلية الوصول إلى ميزانية المشتري غير مؤكدة','Negotiated price compatibility not confirmed'),
 ('DOCUMENT_NOT_KNOWN','MATCH','نوع الوثيقة غير معلوم','Document type unknown'),
 ('DOCUMENT_MISMATCH','MATCH','نوع الوثيقة لا يحقق الشرط الإلزامي','Required document mismatch'),
 ('AREA_BELOW_PREFERENCE','MATCH','المساحة أقل من التفضيل','Area below preference'),
 ('REQUEST_STALE','FRESHNESS','الطلب يحتاج إعادة تأكيد','Request needs reconfirmation'),
 ('PROPERTY_STALE','FRESHNESS','العقار يحتاج إعادة تأكيد الإتاحة','Property availability needs reconfirmation'),
 ('PERMISSION_MISSING','PERMISSION','نطاق الإذن لا يسمح بالمشاركة المطلوبة','Permission scope insufficient'),
 ('SAME_PROPERTY_CONFIRMED','IDENTITY','تم تأكيد أن السجلين لنفس العقار','Same physical property confirmed'),
 ('DISTINCT_PROPERTY_CONFIRMED','IDENTITY','تم تأكيد أنهما عقاران مختلفان','Distinct properties confirmed'),
 ('SIMILAR_UNITS_SAME_DEVELOPMENT_NOT_SAME_PROPERTY','IDENTITY','وحدات متشابهة في مشروع واحد لكنها ليست العقار نفسه','Similar units in same development, distinct physical properties'),
 ('OWNER_REJECTED','OPPORTUNITY','المالك رفض المتابعة','Owner rejected'),
 ('BUYER_REJECTED','OPPORTUNITY','المشتري رفض الفرصة','Buyer rejected'),
 ('PROPERTY_UNAVAILABLE','OPPORTUNITY','العقار لم يعد متاحًا','Property unavailable'),
 ('REQUEST_CHANGED','OPPORTUNITY','تغير الطلب ماديًا','Request changed'),
 ('UNREACHABLE','OPPORTUNITY','تعذر التواصل','Unreachable'),
 ('DEAL_CONFIRMED','OPPORTUNITY','تم الإبلاغ عن إتمام الصفقة','Deal confirmed'),
 ('OFFER_STALE','FRESHNESS','الشروط التجارية تحتاج إعادة تأكيد','Commercial offer terms need reconfirmation'),
 ('CONSENT_REVOKED','PERMISSION','تم سحب الموافقة ذات الصلة','Relevant consent was revoked'),
 ('ACTIONABLE_UNKNOWN','MATCH','معلومة ناقصة قد تغيّر أهلية المطابقة','Missing information may change match eligibility'),
 ('IDENTITY_CONSOLIDATED','IDENTITY','تم توحيد هوية العقار دون حذف التاريخ','Property identity consolidated without deleting history'),
 ('DUPLICATE_OPPORTUNITY_CONSOLIDATED','OPPORTUNITY','أغلقت فرصة مكررة بعد توحيد هوية العقار','Duplicate opportunity closed after identity consolidation'),
 ('OTHER','GENERAL','سبب آخر','Other')
ON CONFLICT (code) DO NOTHING;

-- Initial deterministic policy: rules are deliberately explicit and versioned.
INSERT INTO matching_policies(version,name,rules,active,activated_at)
VALUES (
 '0.2.0',
 'TURAB deterministic foundational policy — remediated',
 '{
   "hard_gate": {
     "unknown_required": "NEED_MORE_INFORMATION",
     "confirmed_fail_required": "REJECTED"
   },
   "soft_ranking": {
     "method": "deterministic_explainable",
     "score_is_internal_only": true
   },
   "priority": ["exact_eligibility","resolve_blocking_unknowns","request_freshness","property_freshness","offer_freshness","permission","diagnostic_relaxation"],
   "freshness_threshold_days": {"request": 30, "property": 30, "offer_terms": 14},
   "automatic_request_relaxation": false,
   "human_review_required_for_opportunity": true
 }'::jsonb,
 true,
 now()
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
