#!/usr/bin/env python3
from pathlib import Path
import re, sys, yaml
ROOT=Path(__file__).resolve().parents[1]
SQL=ROOT/'04_DATABASE/schema_v0.2.2.sql'
OAS=ROOT/'05_API/openapi_v0.2.2.yaml'
errors=[]
def fail(msg): errors.append(msg)
if not SQL.exists(): fail('missing schema_v0.2.2.sql')
if not OAS.exists(): fail('missing openapi_v0.2.2.yaml')
if not errors:
    sql=SQL.read_text(encoding='utf-8')
    oas=yaml.safe_load(OAS.read_text(encoding='utf-8'))
    # D1
    p=oas.get('components',{}).get('parameters',{}).get('IfMatchVersion',{})
    if p.get('name')!='If-Match-Version': fail(f"D1: header is named {p.get('name')!r}, expected 'If-Match-Version'")
    if p.get('schema',{}).get('type')!='integer' or p.get('schema',{}).get('minimum')!=1: fail('D1: IfMatchVersion schema must be integer minimum 1')
    if re.search(r'(?m)^\s*name:\s*If-Match\s*$', OAS.read_text(encoding='utf-8')): fail('D1: old If-Match header declaration remains')
    # D2 SQL
    m=re.search(r'CREATE TABLE\s+parties\s*\((.*?)\n\);',sql,re.S|re.I)
    block=m.group(1) if m else ''
    if not re.search(r'\bversion\s+integer\s+NOT NULL\s+DEFAULT 1\s+CHECK\s*\(version > 0\)',block,re.I): fail('D2: parties must gain version integer NOT NULL DEFAULT 1 CHECK (version > 0)')
    party_trigs=[x.groups() for x in re.finditer(r'CREATE TRIGGER\s+(\w+).*?ON\s+parties\s+.*?EXECUTE FUNCTION\s+(\w+)\s*\(',sql,re.S|re.I)]
    if not any(fn.lower()=='bump_version_and_timestamp' for _,fn in party_trigs): fail('D2: parties must use bump_version_and_timestamp()')
    if any(fn.lower()=='set_updated_at' for _,fn in party_trigs): fail(f'D2: timestamp-only PARTY trigger remains: {party_trigs}')
    # D2 OAS
    schemas=oas.get('components',{}).get('schemas',{})
    for sn in ('Party','CustomerPartyView'):
        s=schemas.get(sn,{})
        if 'version' not in s.get('required',[]): fail(f'D2: {sn} must require version')
        v=s.get('properties',{}).get('version',{})
        if v.get('type')!='integer' or v.get('minimum')!=1: fail(f'D2: {sn}.version must be integer minimum 1')
    for sn in ('PartyCreate','PartyPatch'):
        if 'version' in schemas.get(sn,{}).get('properties',{}): fail(f'D2: {sn} must not accept version')
    # preserve v0.2.1 FK repairs and expected count
    if len(re.findall(r'REFERENCES\s+\w+\s*\(\w+\)',sql))!=131: fail('Regression: FK reference count must remain 131')
    if sql.count('CONSTRAINT fk_consent_evidence_observation')!=1: fail('Regression: fk_consent_evidence_observation must occur exactly once')
    if sql.count('CONSTRAINT fk_property_attribute_resolved_claim')!=1: fail('Regression: fk_property_attribute_resolved_claim must occur exactly once')
if errors:
    print('FAIL')
    for e in errors: print('-',e)
    sys.exit(1)
print('PASS: v0.2.2 D1/D2 acceptance checks satisfied; prior FK remediations preserved')
