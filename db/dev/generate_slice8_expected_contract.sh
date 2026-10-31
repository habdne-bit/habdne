#!/usr/bin/env bash
# Regenerate docs/gate/drafts/SLICE8_EFFECTIVE_CONTRACT_EXPECTED.txt on a temporary git worktree of
# COMMIT, never on the repository's tree. DRAFT EVIDENCE: the addendum and CORRECTION-009 are
# installed in the worktree only, then the gate's generators run there.
#
#     db/dev/generate_slice8_expected_contract.sh COMMIT /outside/the/tree.txt
set -euo pipefail
REV=${1:?commit}; OUT=${2:?output file}; REPO=$(git rev-parse --show-toplevel); WT=$(mktemp -d)/wt
git -C $REPO worktree add -q --detach $WT $REV
trap 'git -C $REPO worktree remove --force $WT' EXIT
cd $WT
D=docs/gate/drafts/CONTRACT_DELTA_SLICE8_external_lead_workflow.DRAFT.md
SHA=$(sha256sum $D | cut -d' ' -f1)
sed "s/^  delta_sha256: 0\{64\}$/  delta_sha256: $SHA/" docs/gate/drafts/ADD-SLICE8_external_lead_workflow.DRAFT.yaml > docs/contract/addenda/ADD-SLICE8_external_lead_workflow.yaml
grep -q "delta_sha256: $SHA" docs/contract/addenda/ADD-SLICE8_external_lead_workflow.yaml
$REPO/.venv/bin/python - <<'PY'
import re, yaml, pathlib
md = pathlib.Path('docs/gate/drafts/CORRECTION-009-lead-conversion-payload.DRAFT.md').read_text()
block = re.search(r"## 3\. The entry, literally.*?```yaml\n(.*?)```", md, re.S).group(1)
p = pathlib.Path('docs/contract/CONTRACT_CORRECTIONS.yaml')
lines = p.read_text().split('\n')
# after the last entry of request_body_narrowings: the last line that is neither
# blank nor a comment before the top-level key that follows it
end = lines.index('response_additions:')
at = max(i for i in range(end) if lines[i].strip() and not lines[i].lstrip().startswith('#')) + 1
lines[at:at] = block.rstrip('\n').split('\n')
text = '\n'.join(lines)
p.write_text(text)
doc = yaml.safe_load(text)
assert doc['request_body_narrowings'][-1]['id'] == 'CORRECTION-009', 'not appended to request_body_narrowings'
PY
PYTHONPATH=src $REPO/.venv/bin/python db/gate/generate_effective_contract.py >/dev/null
PYTHONPATH=src $REPO/.venv/bin/python db/gate/generate_api_inventory.py docs/api/openapi_effective_v0.2.3.yaml -o docs/api/API_INVENTORY_GENERATED.md >/dev/null
P0=$(PYTHONPATH=src $REPO/.venv/bin/python - <<'PY'
import uuid, yaml
from turab.auth import contract as C
frozen = C.load_contract()
eff = C.effective_request_body('postExternalLeadsLeadIdConvert')
gen = yaml.safe_load(open('docs/api/openapi_effective_v0.2.3.yaml'))
g = gen['paths']['/external-leads/{lead_id}/convert']['post']['requestBody']['content']['application/json']['schema']
print('the generated body equals the runtime\'s effective body:', g == eff)
P, K = str(uuid.uuid4()), str(uuid.uuid4())
GOOD = {'intent': 'EXPLORING', 'transaction_intent': 'BUY'}
cases = [
 ('REQUEST, minimal payload', {'party_id': P, 'consent_id': K, 'target': 'REQUEST', 'payload': GOOD}),
 ('REQUEST, RENT', {'party_id': P, 'consent_id': K, 'target': 'REQUEST', 'payload': {**GOOD, 'transaction_intent': 'RENT'}}),
 ('payload carries party_id', {'party_id': P, 'consent_id': K, 'target': 'REQUEST', 'payload': {**GOOD, 'party_id': P}}),
 ('payload carries claim_status', {'party_id': P, 'consent_id': K, 'target': 'REQUEST', 'payload': {**GOOD, 'claim_status': 'UNCLAIMED'}}),
 ('payload without transaction_intent', {'party_id': P, 'consent_id': K, 'target': 'REQUEST', 'payload': {'intent': 'EXPLORING'}}),
 ('target absent', {'party_id': P, 'consent_id': K, 'payload': GOOD}),
 ('PROPERTY, any payload (refused 409 by decision, not by schema)', {'party_id': P, 'consent_id': K, 'target': 'PROPERTY', 'payload': {'anything': 1}}),
]
for label, body in cases:
    v = C.body_violations(eff, body, frozen)
    print(f"  {label}: " + ('accepted' if not v else 'refused: ' + '; '.join(v)))
PY
)
{
cat <<HDR
TURAB — Slice 8: the effective contract the drafts produce (CORRECTION-009 complete)
=====================================================================================
DRAFT EVIDENCE. Nothing below is in force. Regenerated on the tree of the
preparatory step's addendum (review of a7a4fe9), whose loader checks the
structure of each keyword's value; the previous version was generated at
0c54875.

How it was produced (the gate's own generators, on a temporary git worktree of
$(git rev-parse --short HEAD), never on the repository's tree, by the script
db/dev/generate_slice8_expected_contract.sh as committed with this file):
- docs/contract/addenda/ADD-SLICE8_external_lead_workflow.yaml = the draft
  docs/gate/drafts/ADD-SLICE8_external_lead_workflow.DRAFT.yaml, its delta_sha256
  set to the sha256 of the Delta draft as committed at $(git rev-parse --short HEAD)
  ($SHA);
- docs/contract/CONTRACT_CORRECTIONS.yaml + CORRECTION-009, appended to
  request_body_narrowings, LITERALLY as
  docs/gate/drafts/CORRECTION-009-lead-conversion-payload.DRAFT.md §3 carries
  it: require [target, payload] AND add_all_of (the payload schema), the whole
  entry generated, nothing hand-written;
- then db/gate/generate_effective_contract.py and
  db/gate/generate_api_inventory.py docs/api/openapi_effective_v0.2.3.yaml
  -o docs/api/API_INVENTORY_GENERATED.md.
The worktree was removed afterwards.

0. The runtime's judgement of the generated body (contract.body_violations, on
   contract.effective_request_body, in the same worktree)
------------------------------------------------------------------------------
$P0

1. git diff docs/api/API_INVENTORY_GENERATED.md
-----------------------------------------------
HDR
git diff docs/api/API_INVENTORY_GENERATED.md
echo
echo "2. git diff docs/api/openapi_effective_v0.2.3.yaml"
echo "--------------------------------------------------"
git diff docs/api/openapi_effective_v0.2.3.yaml
} > $OUT
