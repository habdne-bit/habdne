"""R-1 step 5, the run entry point: which test refuses which weakening.

    .venv/bin/python db/dev/mutate_r1_step5.py [A1 T1 ...] > /outside/the/tree.txt

Plan: `docs/gate/R1_RELAY_PLAN.md`, revision 12: §5.5, §5.2, §5.7 (R1-Q4);
step 5 authorized in the review of `63a3e95`. Each mutation weakens ONE rule
of `relay/turab_relay/__main__.py`:
- A: §5.5, what the process writes: the access log off, the configured
  logging, `httpx` held at WARNING;
- T: §5.2 through the process: TLS, the relay's TLS extension protocol, the
  client certificate required, Meta's CA the anchor;
- R: refusing to start: no argument, every setting set and not empty, the
  port a port number, the TLS files loadable, exit status 2, no value named.

Not mutated, each with its reason:
- `lifespan="on"`: operational lines, not a rule of §5.2 or §5.5;
- the root level INFO: lowering it only writes less. A1 is killed because
  INFO is written: the access log's lines are INFO (a first trial, with the
  root at WARNING, let A1 survive: the level hid the access log, and
  `access_log=False` was not what kept it out);
- a refusal written to stderr rather than stdout: the tests read both
  together, as an operator's log collector would.

Only `tests/test_r1_step5.py` is run. Run in one part. See
`mutation_runner.py`.
"""
import sys

from mutation_runner import ROOT, run

MAIN = "relay/turab_relay/__main__.py"
TESTS = "tests/test_r1_step5.py"

MUTATIONS = [
 # --- A: what the process writes (§5.5) ----------------------------------------------------
 ("A1 the access log on", MAIN,
  "access_log=False, log_config=LOG_CONFIG,", "access_log=True, log_config=LOG_CONFIG,"),
 ("A2 uvicorn's default logging configuration", MAIN,
  "access_log=False, log_config=LOG_CONFIG,", "access_log=False,"),
 ("A3 httpx at INFO", MAIN,
  "\"httpx\": {\"level\": \"WARNING\"}", "\"httpx\": {\"level\": \"INFO\"}"),
 # --- T: mTLS through the process (§5.2) ---------------------------------------------------
 ("T1 no TLS", MAIN,
  "                            ssl_context_factory=lambda config, default: context)",
  "                            )"),
 ("T2 uvicorn's own protocol, without the TLS extension", MAIN,
  "http=tls.TLSExtensionH11Protocol,", "http=\"h11\","),
 ("T3 the client certificate not required", MAIN,
  "uvicorn.Config(relay_app.create_app(),",
  "uvicorn.Config(relay_app.create_app(require_client_certificate=False),"),
 ("T4 the server's certificate as the client's anchor", MAIN,
  "                                     os.environ[META_CA_FILE])",
  "                                     os.environ[CERTFILE])"),
 # --- R: refusing to start -----------------------------------------------------------------
 ("R1 a command-line argument accepted", MAIN, "    if argv:\n", "    if False:\n"),
 ("R2 a missing setting not refused", MAIN,
  "    if missing:\n", "    if False:\n"),
 ("R3 an empty setting accepted", MAIN,
  "if not os.environ.get(name)]", "if name not in os.environ]"),
 ("R4 a port above 65535 accepted", MAIN,
  "    if _PORT.fullmatch(port) is None or int(port) > 65535:",
  "    if _PORT.fullmatch(port) is None:"),
 ("R5 a signed port accepted", MAIN,
  "_PORT = re.compile(r\"[0-9]{1,5}\")", "_PORT = re.compile(r\"-?[0-9]{1,5}\")"),
 ("R6 a TLS file that cannot be loaded not caught", MAIN,
  "    except OSError:\n", "    except KeyError:\n"),
 ("R7 a refusal exits 1", MAIN,
  "    print(f\"refused: {reason}\", file=sys.stderr)\n    return 2",
  "    print(f\"refused: {reason}\", file=sys.stderr)\n    return 1"),
 ("R8 a refusal names the value", MAIN,
  "f\"{BIND_PORT} is not a port number\"", "f\"{BIND_PORT}={port} is not a port number\""),
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
    survivors = run("TURAB — R-1 step 5: the run entry point, python -m turab_relay", TESTS,
                    MUTATIONS, tuple(sys.argv[1:]))
    sys.exit(1 if survivors else 0)
