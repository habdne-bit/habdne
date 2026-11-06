"""M15 (review of f77f8aa): what a JSON number becomes before the judge sees it.

    .venv/bin/python docs/gate/evidence/SLICE8-NUMBER-PARSING-MEASUREMENTS.py

The question: CORRECTION-009's budget fields are `integer` with `minimum: 0`
and no maximum. JSON Schema 2020-12 judges the NUMBER the text denotes
(Validation 6.1.1, 6.2.4); the judge (`contract.body_violations`) judges the
Python value the parser made of it. Where the two differ, the verdicts can.

Three columns, for {"type": "integer", "minimum": 0}:
- SPEC: the specification's verdict, computed exactly from the text with
  decimal.Decimal (a decimal literal is exact in Decimal);
- TODAY: json.loads(text), then contract.body_violations, unchanged;
- PARSE-EXACT: a PROTOTYPE, written in this script only, not in the code:
  json.loads(text, parse_float=Decimal, parse_constant=<refuse>), and the
  judge with a number test that admits a finite Decimal. It shows what the
  "preserve the value at parsing" option would change; contract.py is not
  changed.
Nothing here touches a database or the repository's code.
"""
import decimal
import json
import sys

sys.path.insert(0, "src")
from turab.auth import contract as C  # noqa: E402

SCHEMA = {"type": "integer", "minimum": 0}
FROZEN = C.load_contract()


def spec(text):
    try:
        d = decimal.Decimal(text)
    except decimal.InvalidOperation:
        return "not JSON"
    if not d.is_finite():
        return "not JSON"
    if d != d.to_integral_value(rounding=decimal.ROUND_FLOOR):
        return "refused: not an integer"
    return "accepted" if d >= 0 else "refused: below 0"


def verdict(violations):
    return "accepted" if not violations else "refused: " + "; ".join(
        v.split(": ", 1)[1] for v in violations)


def today(text):
    try:
        value = json.loads(text)
    except ValueError as e:
        return f"parser error: {type(e).__name__}"
    return f"{verdict(C.body_violations(SCHEMA, value, FROZEN))}  (parsed {value!r})"


def _refuse(name):
    raise ValueError(f"{name} is not JSON")


def exact(text):
    try:
        value = json.loads(text, parse_float=decimal.Decimal, parse_constant=_refuse)
    except ValueError as e:
        return f"parser error: {type(e).__name__}: {e}"[:70]
    original = C._type_holds

    def holds(kind, v):  # the prototype's only change: a finite Decimal is a number
        if isinstance(v, decimal.Decimal):
            if kind == "number":
                return v.is_finite()
            if kind == "integer":
                return v.is_finite() and v == v.to_integral_value()
            return False
        return original(kind, v)

    C._type_holds = holds
    try:
        return verdict(C.body_violations(SCHEMA, value, FROZEN))
    finally:
        C._type_holds = original


TEXTS = ["0", "1", "1.0", "1e0", "1E+2", "1.5", "-1", "-0.0",
         "1e400", "1e-400", "1.0000000000000001", "0.99999999999999999",
         "9007199254740993.0", "NaN", "Infinity"]

print("M15 What a JSON number becomes before the judge; schema", json.dumps(SCHEMA))
print(f"Python {sys.version.split()[0]}; sys.int_max_str_digits = {sys.get_int_max_str_digits()}")
print()
print(f"{'text':24} {'SPEC':26} | TODAY")
disagree_today = disagree_exact = 0
for t in TEXTS:
    s, d, e = spec(t), today(t), exact(t)
    td = s.split(":")[0] != d.split(":")[0].split("  ")[0] and s != "not JSON"
    ed = s.split(":")[0] != e.split(":")[0] and s != "not JSON"
    disagree_today += td
    disagree_exact += ed
    print(f"{t:24} {s:26} | {d}{'   <-- DIFFERS' if td else ''}")
    print(f"{'':24} {'':26} | PARSE-EXACT: {e}{'   <-- DIFFERS' if ed else ''}")
print()
print(f"disagreements with SPEC (JSON texts): TODAY {disagree_today}, PARSE-EXACT {disagree_exact}")
print()
print("A long integer literal (the parser's own bound, both columns):")
for n in (4300, 4301):
    try:
        json.loads("1" * n)
        print(f"  {n} digits: parsed")
    except ValueError as e:
        print(f"  {n} digits: ValueError ({str(e)[:60]}...)")
