#!/usr/bin/env python3
from pathlib import Path
import re, json, yaml, sys, hashlib
BASE=Path(__file__).resolve().parents[1]
QA=BASE/'07_QA_ACCEPTANCE'
SQL=BASE/'04_DATABASE'/'schema_v0.2.1.sql'
SEED=BASE/'04_DATABASE'/'seed_master_data_v0.2.sql'
OAS=BASE/'05_API'/'openapi_v0.2.yaml'
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
funcs=set(found['functions'])
for m in re.finditer(r'CREATE TRIGGER\s+(\w+).*?ON\s+(\w+).*?EXECUTE FUNCTION\s+(\w+)\s*\(',sql,re.S):
    tr,table,fn=m.groups()
    if table not in blocks: err('SQL_TRIGGER_TABLE',f'{tr} targets missing table {table}')
    if fn not in funcs: err('SQL_TRIGGER_FUNCTION',f'{tr} calls missing function {fn}')

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
    # Critical DTO checks
    pub=paths['/public/properties']['get']['responses']['200']['content']['application/json']['schema']
    if pub.get('items',{}).get('$ref')!='#/components/schemas/PublicPropertySummary': err('OAS_PUBLIC_DTO','Public properties not bound to PublicPropertySummary')
    if 'verification_level' in schemas.get('ClaimInput',{}).get('properties',{}): err('OAS_CLAIM_VERIFY','ClaimInput may self-upgrade verification')
    for needed in ['CustomerPropertyView','OperatorPropertyView','CustomerOpportunityView','InternalOpportunityView','ConsentBindingInput','TaskCompletionInput']:
        if needed not in schemas: err('OAS_SCHEMA_MISSING',f'Missing schema {needed}')
    if '/consents/{consent_id}/revoke' not in paths: err('OAS_CONSENT_REVOKE','Consent revoke command missing')
    for q in ['external-leads','requests','properties','matches','opportunities']:
        if f'/backoffice/queues/{q}' not in paths: err('OAS_QUEUE',f'Missing backoffice queue {q}')

# File hashes for review reproducibility
file_map={'schema_v0.2.1.sql':SQL,'seed_master_data_v0.2.sql':SEED,'openapi_v0.2.yaml':OAS}
hashes={f:hashlib.sha256(path.read_bytes()).hexdigest() for f,path in file_map.items()}
result={'status':'PASS' if not errors else 'FAIL','metrics':metrics,'errors':errors,'warnings':warnings,'sha256':hashes}
(QA/'STATIC_AUDIT_RESULTS_v0.2.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False,indent=2))
sys.exit(0 if not errors else 1)
