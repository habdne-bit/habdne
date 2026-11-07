"""M16 (review of 5054bd0): how a body is parsed today, and the schema's own numbers.

    .venv/bin/python docs/gate/evidence/SLICE8-BODY-PARSING-MEASUREMENTS.py

Two measurements, the basis of `src/turab/api/exact_json.py`'s choices:
1. The existing conversion route (`postExternalLeadsLeadIdConvert`, FastAPI's
   own body parsing) with raw bodies at the parsing limits, on an unknown
   lead: a body that parses reaches the handler and is answered 404 (Slice 3);
   one that does not is answered by the parsing layer. Against the suite's
   test database (turab_authz_test, as left by the last suite run); it writes
   at most a recorded denial.
2. The frozen contract's numbers in const, enum, minimum, maximum,
   exclusiveMinimum, exclusiveMaximum, default and multipleOf: any float, and
   any non-integral one.
"""
import sys
import uuid

sys.path.insert(0, "src")
import warnings  # noqa: E402
warnings.filterwarnings("ignore")
from fastapi.testclient import TestClient  # noqa: E402
from turab.app import create_app  # noqa: E402
from turab.auth import contract as C  # noqa: E402
from turab.db.session import create_app_engine  # noqa: E402

OPERATOR = "f3000000-0000-4000-8000-000000000002"


def body(payload: str) -> bytes:
    return ('{"party_id": "f1000000-0000-4000-8000-000000000001", "consent_id": '
            '"f8000000-0000-4000-8000-000000000001", "target": "REQUEST", "payload": '
            + payload + '}').encode()


CASES = [("a valid body", body('{"intent": "EXPLORING"}')),
         ("NaN", body('{"budget_max_dzd": NaN}')),
         ("1e400", body('{"budget_max_dzd": 1e400}')),
         ("1e-400", body('{"budget_max_dzd": 1e-400}')),
         ("nested 100000 deep", body("[" * 100000 + "]" * 100000)),
         ("not JSON", b"{"),
         ("not UTF-8", b'{"a": "\xff"}')]

print("M16.1 The conversion route today, raw bodies, an unknown lead")
engine = create_app_engine("postgresql+psycopg://turab:turab@127.0.0.1/turab_authz_test")
with TestClient(create_app(engine=engine), raise_server_exceptions=False) as client:
    for name, raw in CASES:
        r = client.post(f"/external-leads/{uuid.uuid4()}/convert", content=raw,
                        headers={"Authorization": f"Bearer {OPERATOR}",
                                 "Idempotency-Key": str(uuid.uuid4()),
                                 "Content-Type": "application/json"})
        j = r.json()
        fields = [e.get("field") for e in j.get("field_errors") or []]
        print(f"  {name:20} {r.status_code} {j.get('code')} fields={fields}")
engine.dispose()

print()
print("M16.2 Numbers in the frozen contract's numeric keywords")
KEYS = ("const", "enum", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
        "default", "multipleOf")
floats, inexact = [], []


def walk(node, where):
    if isinstance(node, dict):
        for k, v in node.items():
            if k in KEYS:
                for x in (v if isinstance(v, list) else [v]):
                    if isinstance(x, float):
                        floats.append((where, k))
                        if not x.is_integer():
                            inexact.append((where, k))
            walk(v, f"{where}.{k}")
    elif isinstance(node, list):
        for i, x in enumerate(node):
            walk(x, f"{where}[{i}]")


frozen = C.load_contract()
walk(frozen["components"], "components")
walk(frozen["paths"], "paths")
print(f"  floats: {len(floats)}; non-integral: {len(inexact)}")

print()
print("M16.3 The production route POST /requests today (FastAPI's parsing, RequestCreate):")
print("      the budget sent, the answer, and the value the bigint column holds")
from sqlalchemy import text  # noqa: E402

engine = create_app_engine("postgresql+psycopg://turab:turab@127.0.0.1/turab_authz_test")
with TestClient(create_app(engine=engine), raise_server_exceptions=False) as client:
    for literal in ("1e-400", "9007199254740993.0", "9223372036854775807.0",
                    "9007199254740993", "1.0"):
        raw = ('{"party_id": "f1000000-0000-4000-8000-000000000001", '
               '"transaction_intent": "BUY", "intent": "EXPLORING", '
               '"management_mode": "ASSISTED", "claim_status": "UNCLAIMED", '
               '"budget_max_dzd": %s}' % literal).encode()
        r = client.post("/requests", content=raw,
                        headers={"Authorization": f"Bearer {OPERATOR}",
                                 "Idempotency-Key": str(uuid.uuid4()),
                                 "Content-Type": "application/json"})
        held = None
        if r.status_code == 201:
            with engine.connect() as c:
                held = c.execute(text("SELECT budget_max_dzd FROM turab.requests "
                                      "WHERE request_id = :r"),
                                 {"r": r.json()["request_id"]}).scalar_one()
        print(f"  {literal:24} {r.status_code} {r.json().get('code', '')!s:18} held={held}")
engine.dispose()
