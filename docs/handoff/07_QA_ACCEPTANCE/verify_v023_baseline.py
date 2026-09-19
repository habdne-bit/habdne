#!/usr/bin/env python3
from pathlib import Path
import json, re, subprocess, sys, yaml

ROOT=Path(__file__).resolve().parents[1]
SQL=ROOT/'04_DATABASE/schema_v0.2.3.sql'
SEED=ROOT/'04_DATABASE/seed_master_data_v0.2.3.sql'
OAS=ROOT/'05_API/openapi_v0.2.3.yaml'
errors=[]
def fail(msg): errors.append(msg)
for p in (SQL,SEED,OAS):
    if not p.exists(): fail(f'missing {p.name}')
if not errors:
    sql=SQL.read_text(encoding='utf-8')
    seed=SEED.read_text(encoding='utf-8')
    oas_text=OAS.read_text(encoding='utf-8')
    oas=yaml.safe_load(oas_text)
    # D6 version stamp
    if not re.search(r"\('schema_version','0\.2\.3'\)",sql): fail('D6: schema_metadata.schema_version must be 0.2.3')
    if not re.search(r'^-- TURAB .* schema v0\.2\.3$',sql,re.M): fail('D6: schema header must declare v0.2.3')
    if not re.search(r'^-- TURAB .* seed v0\.2\.3$',seed,re.M): fail('D6: seed header must declare v0.2.3')
    if str(oas.get('info',{}).get('version'))!='0.2.3': fail('D6: OpenAPI info.version must be 0.2.3')
    # Preserve D1
    p=oas.get('components',{}).get('parameters',{}).get('IfMatchVersion',{})
    if p.get('name')!='If-Match-Version': fail('Regression D1: canonical header must remain If-Match-Version')
    if p.get('schema',{}).get('type')!='integer' or p.get('schema',{}).get('minimum')!=1: fail('Regression D1: IfMatchVersion must remain integer minimum 1')
    if re.search(r'(?m)^\s*name:\s*If-Match\s*$',oas_text): fail('Regression D1: old If-Match header declaration returned')
    # Preserve D2 SQL
    m=re.search(r'CREATE TABLE\s+parties\s*\((.*?)\n\);',sql,re.S|re.I)
    block=m.group(1) if m else ''
    if not re.search(r'\bversion\s+integer\s+NOT NULL\s+DEFAULT 1\s+CHECK\s*\(version > 0\)',block,re.I): fail('Regression D2: parties.version missing')
    party_trigs=[x.groups() for x in re.finditer(r'CREATE TRIGGER\s+(\w+).*?ON\s+parties\s+.*?EXECUTE FUNCTION\s+(\w+)\s*\(',sql,re.S|re.I)]
    if not any(fn.lower()=='bump_version_and_timestamp' for _,fn in party_trigs): fail('Regression D2: parties must use bump_version_and_timestamp()')
    if any(fn.lower()=='set_updated_at' for _,fn in party_trigs): fail('Regression D2: timestamp-only PARTY trigger returned')
    schemas=oas.get('components',{}).get('schemas',{})
    for sn in ('Party','CustomerPartyView'):
        s=schemas.get(sn,{})
        if 'version' not in s.get('required',[]): fail(f'Regression D2: {sn} must require version')
        v=s.get('properties',{}).get('version',{})
        if v.get('type')!='integer' or v.get('minimum')!=1: fail(f'Regression D2: {sn}.version must be integer minimum 1')
    for sn in ('PartyCreate','PartyPatch'):
        if 'version' in schemas.get(sn,{}).get('properties',{}): fail(f'Regression D2: {sn} must not accept version')
    # Preserve FK repairs
    if len(re.findall(r'REFERENCES\s+\w+\s*\(\w+\)',sql))!=131: fail('Regression: FK reference count must remain 131')
    if sql.count('CONSTRAINT fk_consent_evidence_observation')!=1: fail('Regression: fk_consent_evidence_observation must occur exactly once')
    if sql.count('CONSTRAINT fk_property_attribute_resolved_claim')!=1: fail('Regression: fk_property_attribute_resolved_claim must occur exactly once')

# version-consistency invariant
vc=ROOT/'07_QA_ACCEPTANCE/verify_version_consistency.py'
if vc.exists():
    cp=subprocess.run([sys.executable,str(vc)],capture_output=True,text=True)
    if cp.returncode!=0: fail('D6: version-consistency invariant failed: '+(cp.stdout+cp.stderr).strip().replace('\n',' | '))
else:
    fail('missing verify_version_consistency.py')

if errors:
    print('FAIL')
    for e in errors: print('-',e)
    sys.exit(1)
print('PASS: v0.2.3 D6 correction accepted; D1/D2 and prior FK remediations preserved')
