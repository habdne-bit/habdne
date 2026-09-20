"""Independent control-flow probes. No PostgreSQL server is used.
Run: python followup_probes.py /path/to/source
HTTP probes use real route/model/service code and explicit I/O stubs.
The criterion IntegrityError is injected, not produced by a real database.
"""
import sys, json, uuid
from pathlib import Path
from datetime import datetime, UTC
from types import SimpleNamespace
from unittest.mock import patch
root=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(root/'src'))
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from turab.api.routes import requests as routes
from turab.services import requests as service

def outcome(r):
    """Record a response without assuming it carries a JSON body.

    The reviewer's own script called r.json() unconditionally. A response
    with no content (204) has an empty body, so that call raises before any
    result is written. This helper records what actually came back.
    """
    recorded = {'status': r.status_code, 'content_length': len(r.content)}
    if r.content:
        try:
            recorded['body'] = r.json()
        except ValueError:
            recorded['body_text'] = r.text
    else:
        recorded['body'] = None
    return recorded

rid=uuid.UUID(int=1); cid=uuid.UUID(int=2)
results=[]
SLOT_CONSTRAINT = 'request_criteria_request_id_criterion_code_sort_order_key'


class Rows:
    """A result that returns exactly the rows it was given, and no more.

    The first version of this stub returned ONE non-empty row for EVERY
    query, including the slot pre-check. The service therefore raised
    `DuplicateCriterionSlot` at the pre-check and never reached the write,
    so the run proved the pre-check and not the SAVEPOINT — while the result
    was recorded as though it had proved the SAVEPOINT (acceptance review
    E-01). The stub now answers each query separately, so "the write was
    reached" is something the probe establishes rather than assumes.
    """

    def __init__(self, rows): self._rows = list(rows)
    def scalar_one(self): return self._rows[0] if self._rows else None
    def scalars(self): return self
    def all(self): return list(self._rows)
    def mappings(self): return self
    def first(self): return self._rows[0] if self._rows else None
    def one(self): return self._rows[0]


CRITERION_ROW = {'request_criterion_id': cid, 'criterion_code': 'ROOMS_MIN',
                 'importance': 'REQUIRED', 'operator': 'GTE', 'value': 3,
                 'unit': None, 'blocking_if_unknown': False, 'sort_order': 200,
                 'created_at': datetime(2026, 9, 19, tzinfo=UTC)}


class Savepoint:
    """Records that the service really opened a SAVEPOINT, and how it ended."""

    def __init__(self, log): self._log = log; log.append('SAVEPOINT begin')
    def commit(self): self._log.append('SAVEPOINT commit')
    def rollback(self): self._log.append('SAVEPOINT rollback')


class Session:
    """`slot_taken` decides what the PRE-CHECK sees; `violate` decides which
    constraint the WRITE trips. The two are independent, which is the whole
    point: with `slot_taken=False` the pre-check passes and the write is the
    only thing that can produce a refusal."""

    def __init__(self, *, slot_taken=False, violate=None):
        self.queries = []
        self.transaction_log = []
        self.slot_taken = slot_taken
        self.violate = violate

    def begin_nested(self):
        return Savepoint(self.transaction_log)

    def execute(self, stmt, params=None):
        sql = ' '.join(str(stmt).split())
        self.queries.append(sql)
        if 'FROM turab.criterion_definitions' in sql:
            return Rows(['ROOMS_MIN'])
        if 'SELECT 1 FROM turab.request_criteria' in sql:      # the pre-check
            return Rows([(1,)] if self.slot_taken else [])
        if 'FOR UPDATE' in sql and 'request_criterion_id = :cid' in sql:
            return Rows([CRITERION_ROW])                        # the row being changed
        if ('UPDATE turab.request_criteria' in sql
                or 'INSERT INTO turab.request_criteria' in sql):
            self.transaction_log.append('WRITE reached')
            if self.violate:
                orig = Exception('injected unique violation')
                orig.diag = SimpleNamespace(constraint_name=self.violate)
                raise IntegrityError(sql, params, orig)
            return Rows([CRITERION_ROW])
        if 'INSERT INTO turab.observations' in sql or 'INSERT INTO turab.claims' in sql:
            return Rows([])
        return Rows([datetime(2026, 9, 19, tzinfo=UTC)])
class Command:
    subject=SimpleNamespace(account_id=uuid.UUID(int=3))
    is_staff=True
    def __init__(self): self.session=Session()
    def authorize(self,*args): return SimpleNamespace(allowed=True)
    def authorize_request_scope(self,*args): return SimpleNamespace(allowed=True)
    def run(self,handler,**kwargs):
        status,body=handler(self.session)
        return SimpleNamespace(status=status,body=body)
cmd=Command();app=FastAPI()
@app.patch('/probe')
def patch_route(request:Request, body:routes.RequestPatch):
    return routes.update_request(request,rid,body,cmd,'1')
@app.post('/reconfirm')
def reconfirm_route(request:Request, body:routes.StateReconfirm):
    return routes.reconfirm_request(request,rid,body,cmd)
@app.post('/criteria')
def criterion_route(request:Request, body:routes.RequestCriterionInput):
    return routes.add_criterion(request,rid,body,cmd)
client=TestClient(app,raise_server_exceptions=False)
# --- probe 1, re-instrumented -------------------------------------------
# The reviewer's script called r.json() on this response unconditionally and
# recorded only a status. Run unchanged against the CORRECTED source it raises
# JSONDecodeError, because the response now has an empty body: the stub
# `Command` has no `read_current`, so that 500 is the harness, not the route.
#
# That failure is itself the measurement. The sentinel gate is the first thing
# `update_request` does after `model_dump`; `read_current` is called only AFTER
# it. So WHERE execution stops says whether the gate fired:
#   * stopped at the gate -> a coded 422 response, `read_current` never called
#   * passed the gate     -> AttributeError at `read_current`
def reached(payload):
    try:
        r = strict.patch('/probe', json=payload)
    except AttributeError as exc:
        if 'read_current' not in str(exc):
            raise
        return {'reached': 'access_free_budget_check (past the sentinel gate)',
                'harness_limit': f'{type(exc).__name__}: {exc}'}
    return {'reached': 'returned before access_free_budget_check', **outcome(r)}

strict = TestClient(app, raise_server_exceptions=True)
allowed = reached({'local_location_detail': ''})
non_nullable = reached({'intent': ''})
try:
    routes.RequestPatch.model_validate({'intent': ''})
    model_admits_empty_intent = True
except Exception as exc:
    model_admits_empty_intent = False
    model_refusal = type(exc).__name__
results.append({'probe':'empty_location_detail',
    'payload':{'local_location_detail':''},
    'empty_string_on_a_nullable_free_text_field':allowed,
    'empty_string_on_a_non_nullable_field':non_nullable,
    'model_admits_empty_intent':model_admits_empty_intent,
    'expected_by_reviewer':422,
    'note':("the reviewer asserted 422, which WAS the defect: the generic check "
            "equated an empty string with null for EVERY field. The corrected gate "
            "is scoped to intent/payment/budget_flexibility, and the free-text "
            "field now passes it. Read the second row precisely: that 422 is "
            "raised by the MODEL's pattern on `intent`, not by the route gate. "
            "Since all three non-nullable fields carry a pattern that an empty "
            "string fails, the scoped gate cannot be reached through the HTTP "
            "surface at all; it is a residual assertion, not a filter, and the "
            "source says so at the call site. This DB-free probe can only show "
            "the gate was passed; that the PATCH then returns 200 and stores the "
            "empty string is proven on PostgreSQL by "
            "tests/test_slice2_http.py::test_an_empty_free_text_field_is_accepted"),
    'scope':'real model and route; authorization and all I/O stubbed; DB not reached'})

try:
    body=routes.StateReconfirm.model_validate({'confirmed_at':'2026-01-01T12:00:00'})
    model_accepts=True; model_error=None
except Exception as exc:
    body=None; model_accepts=False; model_error=f'{type(exc).__name__}'
r=client.post('/reconfirm',json={'confirmed_at':'2026-01-01T12:00:00'})
results.append({'probe':'timezone_missing','model_accepts':model_accepts,'model_error':model_error,'actual':outcome(r),'expected_by_reviewer':500,'note':'the reviewer asserted 500; a 422 field error is the fix','scope':'real model, route and date comparison; DB clock and command plumbing stubbed'})
# --- probe 3, re-instrumented (acceptance review E-01) -------------------
# Four runs over the same code, differing only in what the stub answers:
#   a. the pre-check SEES the slot taken  -> refused before any write
#   b. CHANGE branch, pre-check clear, the UPDATE trips the slot constraint
#   c. ADD branch,    pre-check clear, the INSERT trips the slot constraint
#   d. the write trips a DIFFERENT constraint -> must NOT become a 409
# Only (b) and (c) exercise the SAVEPOINT. Each run reports the queries it
# actually issued and the savepoint transitions it actually made, so the
# attribution can be checked rather than taken on trust.
def criterion_run(*, slot_taken, violate, change):
    probe_cmd = Command()
    probe_cmd.session = Session(slot_taken=slot_taken, violate=violate)
    probe_app = FastAPI()

    @probe_app.post('/criteria')
    def route(request: Request, body: routes.RequestCriterionInput):
        return routes.add_criterion(request, rid, body, probe_cmd)

    payload = {'criterion_code': 'ROOMS_MIN', 'importance': 'REQUIRED',
               'operator': 'GTE', 'value': 4, 'sort_order': 100}
    if change:
        payload['request_criterion_id'] = str(cid)
    with patch.object(service, '_row', return_value={'party_id': uuid.UUID(int=4)}):
        r = TestClient(probe_app, raise_server_exceptions=False).post('/criteria', json=payload)
    log = probe_cmd.session.transaction_log
    return {**outcome(r),
            'branch': 'CHANGE' if change else 'ADD',
            'write_reached': 'WRITE reached' in log,
            'savepoint_opened': 'SAVEPOINT begin' in log,
            'savepoint_rolled_back': 'SAVEPOINT rollback' in log,
            'transaction_log': log,
            'queries': probe_cmd.session.queries}

results.append({'probe':'criterion_slot_collision',
    'a_refused_by_the_pre_check':
        criterion_run(slot_taken=True, violate=None, change=False),
    'b_change_branch_constraint_at_the_write':
        criterion_run(slot_taken=False, violate=SLOT_CONSTRAINT, change=True),
    'c_add_branch_constraint_at_the_write':
        criterion_run(slot_taken=False, violate=SLOT_CONSTRAINT, change=False),
    'd_a_different_constraint_is_not_mapped':
        criterion_run(slot_taken=False, violate='request_criteria_request_id_fkey',
                      change=True),
    'expected_by_reviewer':500,
    'note':("(a) is the pre-check and reaches no write; (b) and (c) reach the "
            "write, open a SAVEPOINT, roll it back and return a typed 409 in "
            "BOTH branches; (d) trips a different constraint at the same point "
            "and is NOT turned into a 409, so the mapping is specific rather "
            "than a catch-all. The earlier version of this probe answered every "
            "query with one non-empty row, so it was refused at the pre-check "
            "and never reached the SAVEPOINT it was recorded as proving "
            "(acceptance review E-01)."),
    'scope':("control flow only: the constraint violation is INJECTED by name. "
             "This says nothing about PostgreSQL isolation, and does not prove "
             "the unique index fires — the two-connection tests in "
             "tests/test_slice2_concurrency.py do that on a real server.")})
state={'status':'PAUSED','last_confirmed_at':datetime(2020,1,1,tzinfo=UTC)}
with patch.object(service,'_row',return_value=state),patch.object(service.freshness,'request_threshold_days',return_value=(30,'probe-policy')):
    try: service.transition(Session(),request_id=rid,target_status='ACTIVE')
    except service.ReactivationNeedsConfirmation as exc:
        results.append({'probe':'stale_reactivation','result':'rejected','error':str(exc),'scope':'actual freshness evaluator; policy and row I/O stubbed'})
    else: raise AssertionError('stale reactivation accepted')
print(json.dumps({'source':str(root),'database_integration':False,'results':results},indent=2,ensure_ascii=False))
