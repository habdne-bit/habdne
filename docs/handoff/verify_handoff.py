#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, sys
root=Path(__file__).resolve().parent
manifest=json.loads((root/'HANDOFF_MANIFEST.json').read_text(encoding='utf-8'))
errors=[]
for entry in manifest['files']:
    p=root/entry['path']
    if not p.exists():
        errors.append(f"MISSING: {entry['path']}")
        continue
    h=hashlib.sha256(p.read_bytes()).hexdigest()
    if h != entry['sha256']:
        errors.append(f"HASH MISMATCH: {entry['path']} expected={entry['sha256']} actual={h}")
if errors:
    print('FAIL')
    for e in errors: print(e)
    sys.exit(1)
print(f"PASS: verified {len(manifest['files'])} handoff files")
