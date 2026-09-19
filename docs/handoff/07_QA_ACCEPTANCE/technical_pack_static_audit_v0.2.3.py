#!/usr/bin/env python3
from pathlib import Path
import re, json, yaml, sys, hashlib
BASE=Path(__file__).resolve().parents[1]
QA=BASE/'07_QA_ACCEPTANCE'
SQL=BASE/'04_DATABASE'/'schema_v0.2.3.sql'
SEED=BASE/'04_DATABASE'/'seed_master_data_v0.2.3.sql'
OAS=BASE/'05_API'/'openapi_v0.2.3.yaml'
errors=[]; warnings=[]; metrics={}

def err(code,msg): errors.append({'code':code,'message':msg})
def warn(code,msg): warnings.append({'code':code,'message':msg})

sql=SQL.read_text()
seed=SEED.read_text()
try: oas=yaml.safe_load(OAS.read_text())
except Exception as e:
    err('OAS_PARSE',str(e)); oas={}

# SQL structural checks
patterns={
 'tables':r'CREATE TABLE\s+([a-zA-Z0-9_]+)',
 'types':r'CREATE TYPE\s+([a-zA-Z0-9_]+)',
 'functions':r'CREATE OR REPLACE FUNCTION\s+([a-zA-Z0-9_]+)',
 'triggers':r'CREATE TRIGGER\s+([a-zA-Z0-9_]+)',
 'indexes':r'CREATE(?: UNIQUE)? INDEX\s+([a-zA-Z0-9_]+)'
}
found={k:re.findall(v,sql) for k,v in patterns.items()}
for k,vals in found.items():
    dups=sorted({v for v in vals if vals.count(v)>1})
    if dups: err('SQL_DUP_'+k.upper(),f'Duplicate {k}: {dups}')
    metrics[k]=len(vals)
if sql.count('(')!=sql.count(')'): err('SQL_PAREN','Unbalanced parentheses')
if sql.count('$$')%2: err('SQL_DOLLAR','Unbalanced $$ function delimiters')
if 'BEGIN;' not in sql or not re.search(r'COMMIT;\s*$',sql): err('SQL_TX','Schema not wrapped in transaction')

blocks={m.group(1):m.group(2) for m in re.finditer(r'CREATE TABLE\s+(\w+)\s*\((.*?)\n\);',sql,re.S)}
if len(blocks)!=metrics['tables']: err('SQL_TABLE_PARSE',f'Only parsed {len(blocks)} of {metrics["tables"]} CREATE TABLE statements')
cols={}
for name,b in blocks.items():
    c=set()
    for line in b.splitlines():
        line=line.strip()
        if not line or line.startswith(('CHECK','UNIQUE','PRIMARY','FOREIGN','CONSTRAINT')): continue
        m=re.match(r'([a-zA-Z_][\w]*)\s+',line)
        if m:c.add(m.group(1))
    cols[name]=c
for m in re.finditer(r'REFERENCES\s+(\w+)\s*\((\w+)\)',sql):
    table,col=m.group(1),m.group(2)
    if table not in blocks: err('SQL_FK_TABLE',f'Missing FK target table {table}')
    elif col not in cols[table]: err('SQL_FK_COLUMN',f'Missing FK target column {table}.{col}')
metrics['foreign_key_refs']=len(re.findall(r'REFERENCES\s+\w+\s*\(\w+\)',sql))

# Named and semantic duplicate FK checks. The v0.2 runtime gate exposed that
# counting FK references is insufficient: PostgreSQL rejects a duplicate
# constraint name and silently tolerates redundant same-semantics FKs with
# different names. Both are release blockers for the baseline.
alter_blocks=[]
for am in re.finditer(r'ALTER\s+TABLE\s+([a-zA-Z_][\w]*)\s+(.*?);', sql, re.I|re.S):
    table=am.group(1)
    body=am.group(2)
    for fm in re.finditer(
        r'ADD\s+CONSTRAINT\s+([a-zA-Z_][\w]*)\s+FOREIGN\s+KEY\s*\(([^)]+)\)\s+'
        r'REFERENCES\s+([a-zA-Z_][\w]*)\s*\(([^)]+)\)([^,;]*)',
        body, re.I|re.S
    ):
        alter_blocks.append({
            'table':table,
            'name':fm.group(1),
            'cols':' '.join(fm.group(2).split()).lower(),
            'ref_table':fm.group(3).lower(),
            'ref_cols':' '.join(fm.group(4).split()).lower(),
            'tail':' '.join(fm.group(5).split()).upper(),
        })
from collections import defaultdict
by_name=defaultdict(list); by_sem=defaultdict(list)
for fk in alter_blocks:
    by_name[(fk['table'].lower(),fk['name'].lower())].append(fk)
    by_sem[(fk['table'].lower(),fk['cols'],fk['ref_table'],fk['ref_cols'],fk['tail'])].append(fk)
for key,vals in by_name.items():
    if len(vals)>1:
        err('SQL_DUP_CONSTRAINT_NAME',f'Duplicate FK constraint name on {key[0]}: {key[1]}')
for key,vals in by_sem.items():
    if len(vals)>1:
        names=sorted({v['name'] for v in vals})
        err('SQL_DUP_FK_SEMANTICS',f'Redundant FK on {key[0]}({key[1]}) -> {key[2]}({key[3]}), constraints={names}')
metrics['named_alter_fks']=len(alter_blocks)
funcs=set(found['functions'])
for m in re.finditer(r'CREATE TRIGGER\s+(\w+).*?ON\s+(\w+).*?EXECUTE FUNCTION\s+(\w+)\s*\(',sql,re.S):
    tr,table,fn=m.groups()
    if table not in blocks: err('SQL_TRIGGER_TABLE',f'{tr} targets missing table {table}')
    if fn not in funcs: err('SQL_TRIGGER_FUNCTION',f'{tr} calls missing function {fn}')


# v0.2.3 preserves v0.2.2 D2 PARTY optimistic-concurrency checks
party_block=blocks.get('parties','')
if not re.search(r'\bversion\s+integer\s+NOT NULL\s+DEFAULT 1\s+CHECK\s*\(version > 0\)', party_block, re.I):
    err('SQL_PARTY_VERSION','parties.version integer NOT NULL DEFAULT 1 CHECK (version > 0) missing')
party_triggers=[m.groups() for m in re.finditer(r'CREATE TRIGGER\s+(\w+).*?ON\s+parties\s+.*?EXECUTE FUNCTION\s+(\w+)\s*\(',sql,re.S|re.I)]
if not any(fn.lower()=='bump_version_and_timestamp' for _,fn in party_triggers):
    err('SQL_PARTY_VERSION_TRIGGER','PARTY must use bump_version_and_timestamp()')
if any(fn.lower()=='set_updated_at' for _,fn in party_triggers):
    err('SQL_PARTY_OLD_TRIGGER','timestamp-only PARTY trigger remains')

# Expected remediation markers
must_sql=[
 ('contact_points','contact point model'),('resource_consent_bindings','resource consent binding'),('property_identity_aliases','canonical property aliasing'),
 ('request_snapshot jsonb','match request snapshot'),('commercial_context_snapshot jsonb','commercial snapshot'),('input_hash text','input hash'),
 ('task_completion_events','task completion history'),('idempotency_records','idempotency store'),('webhook_events','webhook replay store'),
 ('latest_match_reviews','latest review view'),('prevent_match_candidate_update','match immutability'),('enforce_resolution_lineage','truth lineage guard')
]
for token,label in must_sql:
    if token not in sql: err('SQL_REMEDIATION_MISSING',f'Missing {label}: {token}')
for forbidden in ['party_phones','consent_id uuid REFERENCES consent_grants(consent_id)']:
    if forbidden in sql: err('SQL_V01_PATTERN',f'Obsolete v0.1 pattern remains: {forbidden}')
if re.search(r'\bmatch_id\s+uuid\s+NOT NULL UNIQUE REFERENCES match_candidates\(match_id\)', sql):
    err('SQL_V01_PATTERN','Obsolete single-row match review constraint remains')
# Request transaction intent and assisted claim invariant
if 'transaction_intent request_transaction_intent' not in sql: err('SQL_TX_INTENT','Request transaction intent missing')
if "management_mode = 'ASSISTED' AND claim_status = 'UNCLAIMED'" not in sql: err('SQL_ASSISTED_CLAIM','Assisted claim invariant missing')
# matching policy active uniqueness
if 'ux_matching_policy_one_active' not in sql: err('SQL_POLICY_ACTIVE','No single-active-policy unique index')

# Seed checks
for token in ['LAND_BOOK','AGRICULTURAL_CONCESSION','DOCUMENT_STATUS','0.2.0','OFFER_STALE','CONSENT_REVOKED','IDENTITY_CONSOLIDATED']:
    if token not in seed: err('SEED_MISSING',f'Missing seed token {token}')
# 16 communes count using C- codes in VALUES (plus no accidental duplicates)
communes=set(re.findall(r"\('?(C-[A-Z0-9-]+)'?,",seed))
metrics['seed_commune_codes']=len(communes)
if len(communes)<16: err('SEED_COMMUNES',f'Expected >=16 commune codes, found {len(communes)}')

# OpenAPI checks
if oas:
    metrics['openapi_version']=oas.get('openapi')
    paths=oas.get('paths',{}); schemas=oas.get('components',{}).get('schemas',{})
    methods={'get','post','put','patch','delete'}
    ops=[]; refs=[]
    def walk(x):
        if isinstance(x,dict):
            for k,v in x.items():
                if k=='$ref' and isinstance(v,str): refs.append(v)
                walk(v)
        elif isinstance(x,list):
            for v in x: walk(v)
    walk(oas)
    for r in refs:
        if not r.startswith('#/'): continue
        cur=oas
        try:
            for part in r[2:].split('/'):
                cur=cur[part.replace('~1','/').replace('~0','~')]
        except Exception: err('OAS_REF',f'Missing local ref {r}')
    for path,item in paths.items():
        for method,op in item.items():
            if method not in methods: continue
            oid=op.get('operationId')
            if not oid: err('OAS_OPERATION_ID',f'{method.upper()} {path} missing operationId')
            else: ops.append(oid)
            needed=set(re.findall(r'{([^}]+)}',path)); have=set()
            for par in op.get('parameters',[]):
                if '$ref' in par and par['$ref'].startswith('#/components/parameters/'):
                    pp=oas['components']['parameters'][par['$ref'].split('/')[-1]]
                    if pp.get('in')=='path': have.add(pp.get('name'))
                elif par.get('in')=='path': have.add(par.get('name'))
            if needed-have: err('OAS_PATH_PARAM',f'{method.upper()} {path} missing {sorted(needed-have)}')
            if method=='patch':
                try: body=op['requestBody']['content']['application/json']['schema']
                except Exception: body={}
                if body.get('additionalProperties') is True: err('OAS_GENERIC_PATCH',f'Generic PATCH body at {path}')
            if method=='post' and not path.startswith('/auth/') and not path.startswith('/webhooks/'):
                if not any(isinstance(x,dict) and x.get('$ref','').endswith('/IdempotencyKey') for x in op.get('parameters',[])):
                    err('OAS_IDEMPOTENCY',f'Mutating POST without Idempotency-Key: {path}')
            if method=='get' and 'CUSTOMER' in op.get('x-roles',[]) and not path.startswith('/me/'):
                err('OAS_CUSTOMER_BOLA',f'Customer GET outside /me namespace: {path}')
    if len(ops)!=len(set(ops)): err('OAS_OPERATION_DUP','Duplicate operationId values')
    metrics['openapi_paths']=len(paths); metrics['openapi_operations']=len(ops); metrics['openapi_schemas']=len(schemas); metrics['openapi_refs']=len(refs)

    # v0.2.3 preserves v0.2.2 D1/D2 contract checks
    ifm=oas.get('components',{}).get('parameters',{}).get('IfMatchVersion',{})
    if ifm.get('name')!='If-Match-Version': err('OAS_IF_MATCH_HEADER',f"IfMatchVersion wire name must be If-Match-Version, found {ifm.get('name')}")
    if ifm.get('schema',{}).get('type')!='integer' or ifm.get('schema',{}).get('minimum')!=1:
        err('OAS_IF_MATCH_SCHEMA','IfMatchVersion must be integer minimum 1')
    if re.search(r'(?m)^\s*name:\s*If-Match\s*$', OAS.read_text()):
        err('OAS_OLD_IF_MATCH','Old If-Match header declaration remains')
    for sn in ['Party','CustomerPartyView']:
        ss=schemas.get(sn,{})
        if 'version' not in ss.get('required',[]): err('OAS_PARTY_VERSION_REQUIRED',f'{sn}.version must be required')
        vp=ss.get('properties',{}).get('version',{})
        if vp.get('type')!='integer' or vp.get('minimum')!=1: err('OAS_PARTY_VERSION_SCHEMA',f'{sn}.version must be integer minimum 1')
    for sn in ['PartyCreate','PartyPatch']:
        if 'version' in schemas.get(sn,{}).get('properties',{}): err('OAS_PARTY_VERSION_INPUT',f'{sn} must not accept version')

    # Critical DTO checks
    pub=paths['/public/properties']['get']['responses']['200']['content']['application/json']['schema']
    if pub.get('items',{}).get('$ref')!='#/components/schemas/PublicPropertySummary': err('OAS_PUBLIC_DTO','Public properties not bound to PublicPropertySummary')
    if 'verification_level' in schemas.get('ClaimInput',{}).get('properties',{}): err('OAS_CLAIM_VERIFY','ClaimInput may self-upgrade verification')
    for needed in ['CustomerPropertyView','OperatorPropertyView','CustomerOpportunityView','InternalOpportunityView','ConsentBindingInput','TaskCompletionInput']:
        if needed not in schemas: err('OAS_SCHEMA_MISSING',f'Missing schema {needed}')
    if '/consents/{consent_id}/revoke' not in paths: err('OAS_CONSENT_REVOKE','Consent revoke command missing')
    for q in ['external-leads','requests','properties','matches','opportunities']:
        if f'/backoffice/queues/{q}' not in paths: err('OAS_QUEUE',f'Missing backoffice queue {q}')

# v0.2.3 D6 version-consistency checks
expected_version='0.2.3'
sm=re.search(r"\('schema_version','([^']+)'\)",sql)
schema_stamp=sm.group(1) if sm else None
if schema_stamp != expected_version:
    err('SCHEMA_VERSION_STAMP_MISMATCH',f'schema_metadata.schema_version={schema_stamp!r}, expected {expected_version!r}')
sh=re.search(r'^-- TURAB .* schema v(\d+\.\d+\.\d+)$',sql,re.M)
if not sh or sh.group(1)!=expected_version:
    err('VERSION_CLAIM_MISMATCH',f'schema header must declare {expected_version}')
seh=re.search(r'^-- TURAB .* seed v(\d+\.\d+\.\d+)$',seed,re.M)
if not seh or seh.group(1)!=expected_version:
    err('VERSION_CLAIM_MISMATCH',f'seed header must declare {expected_version}')
if oas and str(oas.get('info',{}).get('version'))!=expected_version:
    err('VERSION_CLAIM_MISMATCH',f"OpenAPI info.version={oas.get('info',{}).get('version')!r}, expected {expected_version!r}")
manifest_path=BASE/'HANDOFF_MANIFEST.json'
if manifest_path.exists():
    try:
        hm=json.loads(manifest_path.read_text())
        mt=re.search(r'v(\d+\.\d+\.\d+)',str(hm.get('technical_baseline','')))
        mv=mt.group(1) if mt else None
        if mv!=expected_version:
            err('VERSION_CLAIM_MISMATCH',f'HANDOFF_MANIFEST technical_baseline version={mv!r}, expected {expected_version!r}')
    except Exception as e:
        err('VERSION_MANIFEST_PARSE',str(e))
else:
    err('VERSION_MANIFEST_MISSING','HANDOFF_MANIFEST.json missing')

# File hashes for review reproducibility
file_map={'schema_v0.2.3.sql':SQL,'seed_master_data_v0.2.3.sql':SEED,'openapi_v0.2.3.yaml':OAS}
hashes={f:hashlib.sha256(path.read_bytes()).hexdigest() for f,path in file_map.items()}
result={'status':'PASS' if not errors else 'FAIL','metrics':metrics,'errors':errors,'warnings':warnings,'sha256':hashes}
(QA/'STATIC_AUDIT_RESULTS_v0.2.3.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False,indent=2))
sys.exit(0 if not errors else 1)
