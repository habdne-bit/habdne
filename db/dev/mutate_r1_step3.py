"""R-1 step 3, duty 5 and §5.1's classes and answers: which test refuses
which weakening.

    .venv/bin/python db/dev/mutate_r1_step3.py [D1 A1 ...] > /outside/the/tree.txt

Plan: `docs/gate/R1_RELAY_PLAN.md`, revision 7; step 3 authorized in the
review of `da3d778`. Each mutation weakens ONE rule:
- D: duty 5, the delivery to TURAB (R1-D2), the stop at the first element
  not completed, and the HTTP client's settings;
- A: §5.1's answers and R1-D3's alert; the counts;
- F: failing closed: no key, a refused key, no TURAB URL (R1-T4.4).

Not mutated, each with its reason:
- the 504 and 502 codes themselves: §5.1 asks only "not 200"; a mutation to
  another non-200 code is not a weakening;
- the content-type header: TURAB's route does not read it.

Only `tests/test_r1_step3.py` is run. Run in one part. See
`mutation_runner.py`.
"""
import sys

from mutation_runner import ROOT, run

FORWARD = "relay/turab_relay/forward.py"
TESTS = "tests/test_r1_step3.py"

MUTATIONS = [
 # --- D: duty 5 ---------------------------------------------------------------------------
 ("D1 an element not completed acknowledged 200", FORWARD,
  "            if outcome != COMPLETED:", "            if False:"),
 ("D2 the delivery goes on past an element not completed", FORWARD,
  "                break\n", "                continue\n"),
 ("D3 TURAB's 500 taken as completed", FORWARD,
  "    if response.status_code == 200:", "    if response.status_code in (200, 500):"),
 ("D4 no deadline per envelope", FORWARD,
  "        async with asyncio.timeout(timeout):", "        async with asyncio.timeout(None):"),
 ("D5 no answer taken as completed", FORWARD,
  "        return NO_ANSWER, None", "        return COMPLETED, None"),
 ("D6 a redirect followed", FORWARD,
  "                                 follow_redirects=False) as client:",
  "                                 follow_redirects=True) as client:"),
 ("D7 the environment's proxy used", FORWARD,
  "    async with httpx.AsyncClient(transport=transport, trust_env=False,",
  "    async with httpx.AsyncClient(transport=transport, trust_env=True,"),
 ("D8 the signature over other bytes", FORWARD,
  "                                            transform.sign(element.envelope, key), timeout)",
  "                                            transform.sign(element.envelope + b\" \", key), "
  "timeout)"),
 ("D9 the signature under another header", FORWARD,
  "                transform.SIGNATURE_HEADER: signature})",
  "                \"x-signature\": signature})"),
 # --- A: §5.1's answers, alerts and counts ------------------------------------------------
 ("A1 an ISOLATED element not alerted", FORWARD,
  "        if element.cls == transform.ISOLATED:", "        if False:"),
 ("A2 TURAB's refusal not alerted", FORWARD,
  "    alert(f\"TURAB_REFUSED {status}\", trace)", "    pass"),
 ("A3 TURAB's refusal taken as retryable", FORWARD,
  "    return REFUSED, response.status_code", "    return NOT_COMPLETED, response.status_code"),
 ("A4 a retryable answer alerted as a refusal", FORWARD,
  "    if response.status_code in RETRYABLE:", "    if False:"),
 ("A5 the elements not counted", FORWARD,
  "        counts[(element.cls, element.reason)] += 1", "        pass"),
 ("A6 the deliveries not counted", FORWARD,
  "            counts[(\"DELIVERY\", outcome)] += 1", "            pass"),
 # --- F: failing closed -------------------------------------------------------------------
 ("F1 the relay's key not checked", FORWARD,
  "        key = transform.signing_key()",
  "        key = (os.environ.get(transform.SIGNING_KEY_VARIABLE) or \"k\").encode()"),
 ("F2 no TURAB URL not refused before sending", FORWARD,
  "    if not url:\n        alert(\"TURAB_URL_NOT_CONFIGURED\", trace)",
  "    if url is None:\n        alert(\"TURAB_URL_NOT_CONFIGURED\", trace)"),
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
    survivors = run("TURAB — R-1 step 3: the delivery to TURAB, and the answer to Meta",
                    TESTS, MUTATIONS, tuple(sys.argv[1:]))
    sys.exit(1 if survivors else 0)
