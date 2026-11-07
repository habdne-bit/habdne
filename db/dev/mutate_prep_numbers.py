"""The preparatory step for exact numbers (Slice 8 plan Q-C1 (a)): which test refuses which weakening.

    .venv/bin/python db/dev/mutate_prep_numbers.py [X1 X2 ...] > /outside/the/tree.txt

Authorized in the review of `5054bd0`: "parse the body from its bytes before
its numbers become float, update the judge and its comparison for exact
values", every refusal at the parsing limit classified, no idempotency key
consumed. Each mutation weakens ONE rule:
- P: `api/exact_json.py`, the parser and the dependency;
- E: `auth/contract.py`, the judge's exact number and the schema's exact
  numbers.

Not mutated, each with its reason:
- the refusals' message texts: fixed strings naming no part of the body;
  the tests assert the status and the code, not the words;
- `BodyNotParsed.__init__`: plumbing every refusal test goes through.

Only `tests/test_exact_numbers.py` is run. See `mutation_runner.py`.
"""
import sys

from mutation_runner import ROOT, run

PARSER = "src/turab/api/exact_json.py"
CONTRACT = "src/turab/auth/contract.py"
TESTS = "tests/test_exact_numbers.py"

MUTATIONS = [
 # --- P: the parser and the dependency -------------------------------------------------------
 ("P1 a non-integer number parsed as a float", PARSER,
  "json.loads(text_, parse_float=decimal.Decimal, parse_int=_integer,",
  "json.loads(text_, parse_int=_integer,"),
 ("P2 an integer beyond 4300 digits refused", PARSER,
  "    except ValueError:\n        # Beyond sys.int_max_str_digits: kept exactly, not refused.\n"
  "        return decimal.Decimal(literal)",
  "    except ValueError:\n        # Beyond sys.int_max_str_digits: kept exactly, not refused.\n"
  "        raise"),
 ("P3 NaN and Infinity accepted", PARSER,
  "                          parse_constant=_constant)",
  "                          )"),
 ("P4 a body not UTF-8 decoded anyway", PARSER,
  '        text_ = raw.decode("utf-8")', '        text_ = raw.decode("utf-8", "replace")'),
 ("P5 a body nested too deeply not classified", PARSER,
  "    except RecursionError:\n"
  '        raise BodyNotParsed(400, "the body nests too deeply to be parsed") from None\n', ""),
 ("P6 a 400 refusal answered as a 422", PARSER,
  "        if refused.status == 400:", "        if False:"),
 ("P7 a 422 refusal raised as a general exception", PARSER,
  "        raise RequestValidationError([", "        raise ValueError(["),
 ("P8 an invalid body not classified", PARSER,
  "    except ValueError:  # json.JSONDecodeError is a ValueError\n"
  '        raise BodyNotParsed(422, "the body is not JSON") from None\n', ""),
 # --- E: the judge's exact number; the schema's exact numbers --------------------------------
 ("E1 a Decimal not a number", CONTRACT,
  "        or (isinstance(value, decimal.Decimal) and value.is_finite())",
  "        or False"),
 ("E2 a non-finite Decimal a number", CONTRACT,
  "        or (isinstance(value, decimal.Decimal) and value.is_finite())",
  "        or isinstance(value, decimal.Decimal)"),
 ("E3 a Decimal integral only with a non-negative exponent", CONTRACT,
  "    return exponent >= 0 or not any(digits[max(len(digits) + exponent, 0):])",
  "    return exponent >= 0"),
 ("E4 every Decimal integral", CONTRACT,
  "    return exponent >= 0 or not any(digits[max(len(digits) + exponent, 0):])",
  "    return True"),
 ("E5 the fractional digits read one short", CONTRACT,
  "    return exponent >= 0 or not any(digits[max(len(digits) + exponent, 0):])",
  "    return exponent >= 0 or not any(digits[max(len(digits) + exponent + 1, 0):])"),
 ("E6 the schema's inexact numbers admitted", CONTRACT,
  "        if key in node and _inexact(node[key]):", "        if False:"),
 ("E7 minimum not checked for exactness", CONTRACT,
  '    for key in ("const", "enum", "default", "minimum"):',
  '    for key in ("const", "enum", "default"):'),
 ("E8 a list's numbers not checked", CONTRACT,
  "        return any(_inexact(v) for v in value)\n", "        return False\n"),
 ("E9 an object's numbers not checked", CONTRACT,
  "        return any(_inexact(v) for v in value.values())", "        return False"),
 ("E10 an integral float taken for inexact", CONTRACT,
  "        return not value.is_integer()\n    if isinstance(value, list):",
  "        return True\n    if isinstance(value, list):"),
]


def _check_anchors() -> None:
    """Each anchor names ONE site: the runner replaces every occurrence. Run
    before a run, never on import."""
    for name, rel, old, _new in MUTATIONS:
        count = (ROOT / rel).read_text().count(old)
        assert count == 1, (name, count)
    labels = [m[0].split()[0] for m in MUTATIONS]
    assert len(set(labels)) == len(labels)


if __name__ == "__main__":
    _check_anchors()
    survivors = run("TURAB — preparatory step: exact numbers (Slice 8 plan Q-C1 (a))", TESTS,
                    MUTATIONS, tuple(sys.argv[1:]))
    sys.exit(1 if survivors else 0)
