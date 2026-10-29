"""R-1 step 1, Meta's GET, Meta's signature, the inbound limit and mutual TLS:
which test refuses which weakening.

    .venv/bin/python db/dev/mutate_r1_step1.py [G1 S1 ...] > /outside/the/tree.txt

Plan: `docs/gate/R1_RELAY_PLAN.md`, revision 3; step 1 authorized in the
review of `3d8b593`. Each mutation weakens ONE rule:
- G: duty 1, Meta's GET (R1-T1.1 to R1-T1.5);
- S: duty 2, Meta's signature (R1-T2.1 to R1-T2.5, R1-T2.8);
- L: the inbound limit (R1-T2.6);
- T: mutual TLS (§5.2, R1-T10).

G1 and S5 are R1-T1.5's and R1-T2.8's own mutations: the comparison made
`==`. They are killed by the call-path tests, not by an accept or refuse
test, since `==` and `compare_digest` give the same results.

Not mutated, each with its reason:
- the limit's place before the secret: moving it is a reordering, not a
  one-site weakening; `test_r1_t2_6_the_limit_comes_before_the_secret` pins
  the order;
- the 404 and 405 answers: they guard no rule of the plan.

Part 2, F (review of 8c64c64): the source fingerprint covers `relay/` and
pytest's configuration files, killed by `tests/test_evidence_binding.py`.

Run in two parts, one per test file; each prints its own header. See
`mutation_runner.py`.
"""
import sys

from mutation_runner import ROOT, run

META = "relay/turab_relay/meta.py"
APP = "relay/turab_relay/app.py"
TLS = "relay/turab_relay/tls.py"
TESTS = "tests/test_r1_step1.py"
FINGERPRINT = "db/dev/source_fingerprint.py"
BINDING_TESTS = "tests/test_evidence_binding.py"

MUTATIONS = [
 # --- G: duty 1, Meta's GET ---------------------------------------------------------------
 ("G1 the token compared with ==", META,
  "    if not compare_digest(token.encode(\"utf-8\"), stored):",
  "    if not token.encode(\"utf-8\") == stored:"),
 ("G2 the token not compared", META,
  "    if not compare_digest(token.encode(\"utf-8\"), stored):", "    if False:"),
 ("G3 no configured token fails open", META,
  "    if stored is None:\n        return Answer(503, \"VERIFY_TOKEN_NOT_CONFIGURED\")",
  "    if False:\n        return Answer(503, \"VERIFY_TOKEN_NOT_CONFIGURED\")"),
 ("G4 any mode accepted", META,
  "    if mode != \"subscribe\":", "    if False:"),
 ("G5 a repeated parameter accepted", META,
  "    if any(len(v) != 1 for v in values.values()):",
  "    if any(len(v) == 0 for v in values.values()):"),
 ("G6 an empty challenge or token accepted", META,
  "    if not challenge or not token:", "    if False:"),
 ("G7 the challenge not echoed", META,
  "    return Answer(200, \"SUBSCRIPTION_VERIFIED\", challenge.encode(\"utf-8\"))",
  "    return Answer(200, \"SUBSCRIPTION_VERIFIED\", b\"ok\")"),
 # --- S: duty 2, Meta's signature ---------------------------------------------------------
 ("S1 a digest found inside the header accepted", META,
  "    match = _SIGNATURE.fullmatch(header or \"\")",
  "    match = _SIGNATURE.search(header or \"\")"),
 ("S2 any well-formed signature accepted", META,
  "    return compare_digest(expected.encode(\"ascii\"), match.group(1).encode(\"ascii\"))",
  "    return True"),
 ("S3 the HMAC over a re-serialized body", META,
  "    expected = hmac.new(secret, raw, hashlib.sha256).hexdigest()",
  "    expected = hmac.new(secret, __import__(\"json\").dumps(__import__(\"json\")"
  ".loads(raw)).encode(), hashlib.sha256).hexdigest()"),
 ("S4 no app secret fails open", APP,
  "    if not secret:\n        return meta.Answer(503, \"APP_SECRET_NOT_CONFIGURED\")",
  "    if False:\n        return meta.Answer(503, \"APP_SECRET_NOT_CONFIGURED\")"),
 ("S5 the signature compared with ==", META,
  "    return compare_digest(expected.encode(\"ascii\"), match.group(1).encode(\"ascii\"))",
  "    return expected.encode(\"ascii\") == match.group(1).encode(\"ascii\")"),
 ("S6 a verified POST acknowledged 200", APP,
  "    return await deliver(raw, trace)",
  "    return meta.Answer(200, \"DELIVERED\")"),
 # --- L: the inbound limit ----------------------------------------------------------------
 ("L1 the limit one byte larger", APP,
  "INBOUND_LIMIT = 3 * 1024 * 1024\n", "INBOUND_LIMIT = 3 * 1024 * 1024 + 1\n"),
 ("L2 the declared length not checked", APP,
  "    if declared_over_limit(_header(scope, b\"content-length\")):", "    if False:"),
 ("L3 the body not counted as it arrives", APP,
  "        if size > INBOUND_LIMIT:", "        if False:"),
 ("L4 leading zeros counted as significant", APP,
  "    significant = declared.lstrip(\"0\")", "    significant = declared"),
 ("L5 a long value converted whole", APP,
  "    if len(significant) > len(str(INBOUND_LIMIT)):\n        return True",
  "    if False:\n        return True"),
 # --- T: mutual TLS -----------------------------------------------------------------------
 ("T1 a client certificate optional", TLS,
  "    context.verify_mode = ssl.CERT_REQUIRED", "    context.verify_mode = ssl.CERT_OPTIONAL"),
 ("T2 the system's roots trusted too", TLS,
  "    context.load_verify_locations(cafile=client_ca_file)",
  "    context.load_verify_locations(cafile=client_ca_file)\n    context.load_default_certs()"),
 ("T3 no minimum TLS version", TLS,
  "    context.minimum_version = ssl.TLSVersion.TLSv1_2\n", ""),
 ("T4 any identity accepted", TLS,
  "    return names == [META_CLIENT_CN]", "    return True"),
 ("T5 Meta's CN among others accepted", TLS,
  "    return names == [META_CLIENT_CN]", "    return META_CLIENT_CN in names"),
 ("T6 the certificate not required by default", APP,
  "def create_app(*, require_client_certificate: bool = True,",
  "def create_app(*, require_client_certificate: bool = False,"),
 ("T7 the validated subject not passed to the application", TLS,
  "            extensions[\"tls\"] = {\"client_cert_subject\": subject}",
  "            extensions[\"tls\"] = {}"),
]


#: Part 2 (review of 8c64c64): the fingerprint covers the relay and pytest's
#: configuration, killed by `tests/test_evidence_binding.py`.
BINDING_MUTATIONS = [
 ("F1 pytest's configuration files not in the recipe", FINGERPRINT,
  "EXTRA = (\"alembic.ini\", \"pyproject.toml\", \"pytest.toml\", \".pytest.toml\", "
  "\"pytest.ini\",\n         \".pytest.ini\", \"tox.ini\", \"setup.cfg\", \"conftest.py\")",
  "EXTRA = (\"alembic.ini\",)"),
 ("F2 relay/ not in the recipe", FINGERPRINT,
  "TREES = (\"src\", \"tests\", \"db\", \"relay\")", "TREES = (\"src\", \"tests\", \"db\")"),
 ("F3 pyproject.toml alone not in the recipe", FINGERPRINT,
  "EXTRA = (\"alembic.ini\", \"pyproject.toml\", ", "EXTRA = (\"alembic.ini\", "),
]


def _check_anchors() -> None:
    """Each anchor names ONE site: the runner replaces every occurrence. Run
    before a run, never on import."""
    for name, rel, old, _new in MUTATIONS + BINDING_MUTATIONS:
        count = (ROOT / rel).read_text().count(old)
        assert count == 1, (name, count)
    labels = [m[0].split()[0] for m in MUTATIONS + BINDING_MUTATIONS]
    assert len(set(labels)) == len(labels)


if __name__ == "__main__":
    _check_anchors()
    only = tuple(sys.argv[1:])
    survivors = run("TURAB — R-1 step 1: Meta's GET, Meta's signature, the inbound limit, "
                    "mutual TLS", TESTS, MUTATIONS, only)
    print()
    survivors += run("TURAB — R-1 step 1: the fingerprint covers the relay and pytest's "
                     "configuration (review of 8c64c64)", BINDING_TESTS, BINDING_MUTATIONS, only)
    sys.exit(1 if survivors else 0)
