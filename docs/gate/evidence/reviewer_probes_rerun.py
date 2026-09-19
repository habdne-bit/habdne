"""Re-run of the reviewer's probes against the CORRECTED source.

The probes are the reviewer's, unchanged in intent. Three adaptations, each
forced by a fix and each noted in the output:

  * the `_row` stub accepts `**kwargs`, because `_row` now takes `for_update`
    (R-S2-02);
  * probes that the corrected code makes RAISE are recorded as raising, with
    the exception, instead of aborting the script;
  * the reactivation probe's `request_threshold_days` stub is kept exactly as
    the reviewer wrote it — `AssertionError('policy lookup should be
    observed')` — so the fix is demonstrated by THEIR assertion firing.
"""
import sys, json, uuid, inspect
from datetime import datetime, UTC
from unittest.mock import patch
from pathlib import Path

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / 'src'))
from turab.api.routes.requests import RequestPatch, RequestCreate, RequestCriterionInput
from turab.services import requests as service, concurrency
from pydantic import ValidationError

rid = uuid.uuid4(); party = uuid.uuid4(); actor = uuid.uuid4()
results = []
def emit(name, **data): results.append({'probe': name, **data})

for name, model, payload in [
 ('declared_criterion_id', RequestCriterionInput, {'request_criterion_id': str(rid), 'criterion_code': 'ROOMS_MIN', 'importance': 'REQUIRED', 'operator': 'GTE', 'value': 3}),
 ('patch_null_intent', RequestPatch, {'intent': None}),
 ('patch_unknown_property_type', RequestPatch, {'desired_property_type': 'NOT_A_PROPERTY_TYPE'}),
 ('create_inconsistent_budgets', RequestCreate, {'party_id': str(party), 'transaction_intent': 'BUY', 'intent': 'ACTIVE_SEARCH', 'management_mode': 'SELF_MANAGED', 'claim_status': 'CLAIMED', 'budget_target_dzd': 200, 'budget_max_dzd': 100}),
]:
    try:
        model.model_validate(payload); emit(name, accepted=True, payload=payload)
    except ValidationError:
        emit(name, accepted=False, payload=payload)

class ScalarResult:
    def scalar_one_or_none(self): return 7
class VersionSession:
    def __init__(self): self.sql = []
    def execute(self, stmt, params=None): self.sql.append(str(stmt)); return ScalarResult()
s = VersionSession(); concurrency.check(s, 'requests', rid, 7)
emit('actual_version_guard_sql', sql=s.sql,
     uses_row_lock=any('FOR UPDATE' in x.upper() for x in s.sql))

class Writer:
    def __init__(self, state): self.state = state; self.sql = []
    def execute(self, stmt, params=None):
        q = str(stmt); self.sql.append(q)
        if 'UPDATE turab.requests' in q:
            if 'CAST(:status AS' in q: self.state['status'] = params['status']
            if "SET status = 'ACTIVE'" in q: self.state['status'] = 'ACTIVE'
            if 'SET last_confirmed_at' in q:
                self.state['last_confirmed_at'] = params['at'] or datetime.now(UTC)
        return None
    def scalar_one(self): return datetime.now(UTC)

class ClockWriter(Writer):
    """`reconfirm` now asks the database for the time to reject a future
    confirmation, so the stub answers that one query."""
    def execute(self, stmt, params=None):
        q = str(stmt)
        if 'clock_timestamp()' in q and 'UPDATE' not in q:
            self.sql.append(q)
            class R:
                def scalar_one(self_inner): return datetime.now(UTC)
            return R()
        return super().execute(stmt, params)

state = {'request_id': rid, 'party_id': party, 'status': 'PAUSED',
         'last_confirmed_at': datetime(2020, 1, 1, tzinfo=UTC)}
s = Writer(state)
try:
    with patch.object(service, '_row', side_effect=lambda *_, **__: dict(state)), \
         patch.object(service, 'record_provenance', return_value=uuid.uuid4()), \
         patch.object(service.freshness, 'request_threshold_days',
                      side_effect=AssertionError('policy lookup should be observed')):
        row = service.transition(s, request_id=rid, target_status='ACTIVE',
                                 recorded_by_account_id=actor)
    emit('stale_paused_request_reactivation_control_flow', status=row['status'],
         last_confirmed_at=row['last_confirmed_at'].isoformat(),
         policy_reader_called=False, io_stubbed=True)
except AssertionError as exc:
    emit('stale_paused_request_reactivation_control_flow',
         policy_reader_called=True, raised=f'AssertionError: {exc}',
         note="the reviewer's own stub fired: the policy IS now consulted",
         io_stubbed=True)

state = {'request_id': rid, 'party_id': party, 'status': 'NEEDS_CONFIRMATION',
         'last_confirmed_at': datetime(2020, 1, 1, tzinfo=UTC)}
s = ClockWriter(state)
try:
    with patch.object(service, '_row', side_effect=lambda *_, **__: dict(state)), \
         patch.object(service, 'record_provenance', return_value=uuid.uuid4()):
        row = service.reconfirm(s, request_id=rid,
                                confirmed_at=datetime(2099, 1, 1, tzinfo=UTC),
                                recorded_by_account_id=actor)
    emit('future_confirmation_control_flow', accepted=True, status=row['status'],
         last_confirmed_at=row['last_confirmed_at'].isoformat(), io_stubbed=True)
except Exception as exc:
    emit('future_confirmation_control_flow', accepted=False,
         raised=f'{type(exc).__name__}: {exc}', io_stubbed=True)

emit('criterion_mutation_source', source=inspect.getsource(service.add_criterion))
emit('freshness_pass_source',
     source=inspect.getsource(service.mark_stale_as_needing_confirmation))
print(json.dumps({'source_root': str(root),
                  'scope': "reviewer's probes re-run against the corrected source",
                  'results': results}, ensure_ascii=False, indent=2))
