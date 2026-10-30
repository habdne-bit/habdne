"""R-1 step 4, duty 7 and OVERSIZE: which test refuses which weakening.

    .venv/bin/python db/dev/mutate_r1_step4.py [Z1 Z2 ...] > /outside/the/tree.txt

Plan: `docs/gate/R1_RELAY_PLAN.md`, revision 10; step 4 authorized in the
review of `79c232b`. Each mutation weakens ONE rule:
- Z: duty 7, the limit and where it is measured;
- O: OVERSIZE (R1-Q1 (a), §5.4): not sent, not shortened, alerted, the
  others delivered, the answer not 200;
- E: a string UTF-8 cannot encode, ISOLATED;
- C: the count check of §4 (R1-D14 (a)): read-only, the databases named.

Not mutated, each with its reason:
- the 503 code of `ENVELOPE_OVERSIZE`: §5.1 asks only "not 200";
- the OVERSIZE element's event id: it is not content, and nothing reads it
  but the counts.

Only `tests/test_r1_step4.py` is run. Run in one part. See
`mutation_runner.py`.
"""
import sys

from mutation_runner import ROOT, run

TRANSFORM = "relay/turab_relay/transform.py"
FORWARD = "relay/turab_relay/forward.py"
COUNTS = "db/ops/count_webhook_events.py"
TESTS = "tests/test_r1_step4.py"

MUTATIONS = [
 # --- Z: the limit ------------------------------------------------------------------------
 ("Z1 the limit one byte larger", TRANSFORM,
  "ENVELOPE_LIMIT = 64 * 1024\n", "ENVELOPE_LIMIT = 64 * 1024 + 1\n"),
 ("Z2 the limit one byte smaller", TRANSFORM,
  "ENVELOPE_LIMIT = 64 * 1024\n", "ENVELOPE_LIMIT = 64 * 1024 - 1\n"),
 ("Z3 the size measured in characters", TRANSFORM,
  "    if len(data) > ENVELOPE_LIMIT:", "    if len(data.decode(\"utf-8\")) > ENVELOPE_LIMIT:"),
 ("Z4 the limit not checked", TRANSFORM,
  "    if len(data) > ENVELOPE_LIMIT:", "    if False:"),
 # --- O: OVERSIZE --------------------------------------------------------------------------
 ("O1 an oversize envelope shortened and sent", TRANSFORM,
  "        return Element(kind, OVERSIZE, \"ENVELOPE_OVER_LIMIT\", event_id)",
  "        return Element(kind, FORWARD, \"FORWARDED\", event_id, data[:ENVELOPE_LIMIT])"),
 ("O2 the oversize answer 200", FORWARD,
  "    if failed is None and oversize:", "    if False:"),
 ("O3 OVERSIZE not alerted", FORWARD,
  "            alert(f\"OVERSIZE {element.kind}\", trace)", "            pass"),
 ("O4 OVERSIZE stops the delivery", FORWARD,
  "            if element.cls != transform.FORWARD:\n                continue",
  "            if element.cls == transform.OVERSIZE:\n                break\n"
  "            if element.cls != transform.FORWARD:\n                continue"),
 ("O5 the oversize envelope kept in the element", TRANSFORM,
  "        return Element(kind, OVERSIZE, \"ENVELOPE_OVER_LIMIT\", event_id)",
  "        return Element(kind, OVERSIZE, \"ENVELOPE_OVER_LIMIT\", event_id, data)"),
 # --- E: encoding --------------------------------------------------------------------------
 ("E1 a string UTF-8 cannot encode not caught", TRANSFORM,
  "    except UnicodeEncodeError:\n        return Element(kind, ISOLATED, \"NOT_UTF8_ENCODABLE\")",
  "    except KeyError:\n        return Element(kind, ISOLATED, \"NOT_UTF8_ENCODABLE\")"),
 # --- C: the count check -------------------------------------------------------------------
 ("C1 the count not read-only", COUNTS,
  "        conn.execute(\"SET TRANSACTION READ ONLY\")", "        conn.execute(\"SELECT 1\")"),
 ("C2 PGDATABASE accepted", COUNTS,
  "    for variable in (\"PGSERVICE\", \"PGDATABASE\"):", "    for variable in (\"PGSERVICE\",):"),
 ("C3 PGSERVICE accepted", COUNTS,
  "    for variable in (\"PGSERVICE\", \"PGDATABASE\"):", "    for variable in (\"PGDATABASE\",):"),
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
    survivors = run("TURAB — R-1 step 4: duty 7, the serialized size, OVERSIZE", TESTS,
                    MUTATIONS, tuple(sys.argv[1:]))
    sys.exit(1 if survivors else 0)
