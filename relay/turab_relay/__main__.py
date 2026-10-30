"""The relay's run entry point (R-1 step 5).

    python -m turab_relay

Plan: `docs/gate/R1_RELAY_PLAN.md`, revision 12: §5.5 (the access log), §5.2
(mTLS), §5.7 (R1-Q4); step 5 authorized in the review of `63a3e95`.

**Configured by its environment only.** It takes no command-line argument:
a process's arguments are visible to every user of its host.
- `TURAB_RELAY_BIND_HOST`, `TURAB_RELAY_BIND_PORT`: where it listens;
- `TURAB_RELAY_TLS_CERTFILE`, `TURAB_RELAY_TLS_KEYFILE`: the relay's own
  certificate and key;
- `TURAB_RELAY_META_CA_FILE`: Meta's outbound API CA certificate, the only
  anchor for the client's (§5.2, `tls.server_context`).

The verify token, the app secret, the relay's key and TURAB's URL are read by
the application at each request, as in steps 1 to 3; a missing or refused one
fails closed there.

**It refuses to start**, with exit status 2, before listening, when a setting
is missing or empty, the port is not a port number, or the TLS files cannot be
loaded as one certificate, its key and a CA. It names the variables, never a
value.

**There is no other way to serve:** no plain HTTP, and no option to drop the
client certificate. The application is `create_app()`, which requires Meta's
identity on the validated certificate; uvicorn serves it with the relay's own
server context and TLS extension protocol (`tls.py`).

**What it writes**, to stderr, one line each: `time level logger message`,
every logger at INFO and above, except:
- **uvicorn's access log, off** (`access_log=False`): no request line, so
  no query, is ever written (§5.5). It is the only thing keeping it out: the
  access log's lines are INFO, which this configuration writes;
- `httpx`, held at WARNING: its INFO line names TURAB's URL for every
  request. (`httpcore` logs at DEBUG only, below INFO.)
What remains: uvicorn's own logger, `uvicorn.error` (its start, its stop,
fixed warnings), and the relay's refusals and alerts (a fixed reason and a
trace id).

**Not covered** (§5.7): the logs of any layer in front of the relay, examined
in the deployment environment.
"""
from __future__ import annotations

import os
import re
import sys

import uvicorn

from turab_relay import app as relay_app
from turab_relay import tls

BIND_HOST = "TURAB_RELAY_BIND_HOST"
BIND_PORT = "TURAB_RELAY_BIND_PORT"
CERTFILE = "TURAB_RELAY_TLS_CERTFILE"
KEYFILE = "TURAB_RELAY_TLS_KEYFILE"
META_CA_FILE = "TURAB_RELAY_META_CA_FILE"
SETTINGS = (BIND_HOST, BIND_PORT, CERTFILE, KEYFILE, META_CA_FILE)
_PORT = re.compile(r"[0-9]{1,5}")

LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"line": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"stderr": {"class": "logging.StreamHandler", "formatter": "line",
                            "stream": "ext://sys.stderr"}},
    "root": {"handlers": ["stderr"], "level": "INFO"},
    "loggers": {"httpx": {"level": "WARNING"}},
}


def _refuse(reason: str) -> int:
    print(f"refused: {reason}", file=sys.stderr)
    return 2


def main(argv: list[str]) -> int:
    if argv:
        return _refuse("python -m turab_relay takes no argument; it is configured by "
                       "its environment")
    missing = [name for name in SETTINGS if not os.environ.get(name)]
    if missing:
        return _refuse(f"not set: {', '.join(missing)}")
    port = os.environ[BIND_PORT]
    if _PORT.fullmatch(port) is None or int(port) > 65535:
        return _refuse(f"{BIND_PORT} is not a port number")
    try:
        context = tls.server_context(os.environ[CERTFILE], os.environ[KEYFILE],
                                     os.environ[META_CA_FILE])
    except OSError:
        return _refuse(f"the TLS files could not be loaded: {CERTFILE}, {KEYFILE}, "
                       f"{META_CA_FILE}")
    config = uvicorn.Config(relay_app.create_app(), host=os.environ[BIND_HOST],
                            port=int(port), http=tls.TLSExtensionH11Protocol, lifespan="on",
                            access_log=False, log_config=LOG_CONFIG,
                            ssl_context_factory=lambda config, default: context)
    uvicorn.Server(config).run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
