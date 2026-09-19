#!/usr/bin/env python3
from pathlib import Path
import json, re, sys, yaml

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / '07_QA_ACCEPTANCE'
MANIFEST = ROOT / 'HANDOFF_MANIFEST.json'

FILES = {
    'schema filename': ROOT / '04_DATABASE' / 'schema_v0.2.3.sql',
    'seed filename': ROOT / '04_DATABASE' / 'seed_master_data_v0.2.3.sql',
    'openapi filename': ROOT / '05_API' / 'openapi_v0.2.3.yaml',
    'static audit script filename': QA / 'technical_pack_static_audit_v0.2.3.py',
    'static audit results filename': QA / 'STATIC_AUDIT_RESULTS_v0.2.3.json',
    'technical pack manifest filename': QA / 'TECHNICAL_PACK_MANIFEST_SHA256_v0.2.3.txt',
}

def filename_version(path: Path):
    m = re.search(r'v(\d+\.\d+\.\d+)', path.name)
    return m.group(1) if m else None

claims = []
errors = []
for label, path in FILES.items():
    if not path.exists():
        errors.append(f'{label}: missing {path.name}')
        continue
    claims.append((label, filename_version(path)))

schema = FILES['schema filename'].read_text(encoding='utf-8') if FILES['schema filename'].exists() else ''
seed = FILES['seed filename'].read_text(encoding='utf-8') if FILES['seed filename'].exists() else ''
oas = yaml.safe_load(FILES['openapi filename'].read_text(encoding='utf-8')) if FILES['openapi filename'].exists() else {}
manifest = json.loads(MANIFEST.read_text(encoding='utf-8')) if MANIFEST.exists() else {}

m = re.search(r'^-- TURAB .* schema v(\d+\.\d+\.\d+)$', schema, re.M)
claims.append(('schema header', m.group(1) if m else None))
m = re.search(r"\('schema_version','([^']+)'\)", schema)
claims.append(('schema_metadata.schema_version', m.group(1) if m else None))
m = re.search(r'^-- TURAB .* seed v(\d+\.\d+\.\d+)$', seed, re.M)
claims.append(('seed header', m.group(1) if m else None))
claims.append(('openapi info.version', str(oas.get('info',{}).get('version')) if oas else None))
tech = str(manifest.get('technical_baseline',''))
m = re.search(r'v(\d+\.\d+\.\d+)', tech)
claims.append(('HANDOFF_MANIFEST.technical_baseline', m.group(1) if m else None))

versions = [v for _,v in claims if v]
expected = versions[0] if versions else None
for label, value in claims:
    if value is None:
        errors.append(f'{label}: version claim missing/unparseable')
    elif expected is not None and value != expected:
        errors.append(f'{label}: {value} != {expected}')

for label, value in claims:
    print(f'{label:<40} {value}')

if errors:
    print('\nVERSION CONSISTENCY: FAIL')
    for e in errors:
        print('-', e)
    sys.exit(1)
print(f'\nVERSION CONSISTENCY: PASS ({expected})')
