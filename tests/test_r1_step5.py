"""R-1 step 5: the run entry point, `python -m turab_relay`, tested through
an actual process.

Plan: `docs/gate/R1_RELAY_PLAN.md`, revision 12: §5.5 (the access log), §5.2
(mTLS), §5.7 (R1-Q4), §6 step 5; authorized in the review of `63a3e95`.

Each test starts the entry point as an operating-system process of its own,
as an operator would: `python -m turab_relay`, configured by its environment
only, from a directory outside the repository. Every line the process writes,
to stdout and to stderr, is read.

**Not proven here** (§5.7): the logs of any layer in front of the relay (a
load balancer, a proxy, a TLS terminator). Each is examined in the
deployment environment before condition 11 is met.
"""
from __future__ import annotations

import hashlib
import hmac
import http.client
import http.server
import os
import pathlib
import re
import signal
import socket
import ssl
import subprocess
import sys
import threading
import time

import pytest

from tests.test_r1_step1 import pki  # noqa: F401  (the synthetic PKI fixture)
from tests.test_r1_step2 import CONTENT, _message, _notification
from turab_relay import tls

ROOT = pathlib.Path(__file__).resolve().parents[1]
PATH = "/whatsapp/webhook"
TOKEN = "verify-token-r1-step5"
CHALLENGE = "challenge-r1-step5-7731"
APP_SECRET = "meta-app-secret-r1-step5"
KEY = "relay-key-r1-step5"
TURAB_BODY = b"TURAB-ANSWER-BODY-r1s5"
STARTED = re.compile(r"Uvicorn running on https://127\.0\.0\.1:([0-9]+) ")
LINE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:,]+ (INFO|WARNING|ERROR|CRITICAL) (\S+) .*")
CONFIG_VARIABLES = ("TURAB_RELAY_BIND_HOST", "TURAB_RELAY_BIND_PORT", "TURAB_RELAY_TLS_CERTFILE",
                    "TURAB_RELAY_TLS_KEYFILE", "TURAB_RELAY_META_CA_FILE")


class Turab:
    """A test double of TURAB's webhook on loopback: answers 200 and keeps
    the bodies it received."""

    def __init__(self):
        received = self.received = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                received.append(self.rfile.read(int(self.headers["Content-Length"])))
                self.send_response(200)
                self.send_header("Content-Length", str(len(TURAB_BODY)))
                self.end_headers()
                self.wfile.write(TURAB_BODY)

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/webhooks/whatsapp"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def turab():
    double = Turab()
    yield double
    double.close()


def _environment(pki, turab_url, **overrides):  # noqa: F811
    """The process's whole environment: nothing inherited but `PATH`, so no
    variable of the test run reaches it."""
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT / "relay"),
           "TURAB_RELAY_BIND_HOST": "127.0.0.1", "TURAB_RELAY_BIND_PORT": "0",
           "TURAB_RELAY_TLS_CERTFILE": str(pki / "server.pem"),
           "TURAB_RELAY_TLS_KEYFILE": str(pki / "server.key"),
           "TURAB_RELAY_META_CA_FILE": str(pki / "meta-ca.pem"),
           "TURAB_RELAY_META_VERIFY_TOKEN": TOKEN, "TURAB_RELAY_META_APP_SECRET": APP_SECRET,
           "TURAB_RELAY_SIGNING_SECRET": KEY, "TURAB_RELAY_TURAB_WEBHOOK_URL": turab_url}
    for name, value in overrides.items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    return env


class Process:
    """`python -m turab_relay`, as an operator starts it. `lines` holds every
    line it wrote, stdout and stderr together, as they arrive."""

    def __init__(self, env, tmp_path, args=()):
        self.lines: list[str] = []
        self.proc = subprocess.Popen([sys.executable, "-m", "turab_relay", *args], env=env,
                                     cwd=tmp_path, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        for raw in self.proc.stdout:
            self.lines.append(raw.decode("utf-8", "backslashreplace").rstrip("\n"))

    def port(self, timeout=20.0) -> int:
        deadline = time.time() + timeout
        while time.time() < deadline:
            for line in self.lines:
                found = STARTED.search(line)
                if found:
                    return int(found.group(1))
            assert self.proc.poll() is None, f"the process exited: {self.lines}"
            time.sleep(0.05)
        raise AssertionError(f"not started: {self.lines}")

    def stop(self) -> list[str]:
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
        self.proc.wait(20)
        self.reader.join(10)
        return self.lines

    def finished(self, timeout=20.0) -> tuple[int, list[str]]:
        code = self.proc.wait(timeout)
        self.reader.join(10)
        return code, self.lines


@pytest.fixture
def start(tmp_path):
    started = []

    def run(env, args=()):
        process = Process(env, tmp_path, args)
        started.append(process)
        return process

    yield run
    for process in started:
        if process.proc.poll() is None:
            process.proc.kill()
            process.proc.wait(10)


def _request(pki, port, method, target, *, cert="good", body=b"", headers=None):  # noqa: F811
    context = ssl.create_default_context(cafile=str(pki / "server-ca.pem"))
    if cert:
        context.load_cert_chain(str(pki / f"{cert}.pem"), str(pki / f"{cert}.key"))
    conn = http.client.HTTPSConnection("127.0.0.1", port, context=context, timeout=15)
    try:
        conn.request(method, target, body=body, headers=headers or {})
        r = conn.getresponse()
        return r.status, r.read()
    finally:
        conn.close()


def _subscription(token=TOKEN, challenge=CHALLENGE):
    return f"{PATH}?hub.mode=subscribe&hub.challenge={challenge}&hub.verify_token={token}"


def _signed(raw: bytes) -> dict:
    return {"X-Hub-Signature-256":
            "sha256=" + hmac.new(APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()}


# --- the entry point serves, over mutual TLS -------------------------------------------------

def test_the_entry_point_answers_metas_get_over_mutual_tls(pki, turab, start):  # noqa: F811
    process = start(_environment(pki, turab.url))
    port = process.port()
    assert _request(pki, port, "GET", _subscription()) == (200, CHALLENGE.encode())


def test_the_entry_point_delivers_a_signed_notification_to_turab(pki, turab, start):  # noqa: F811
    process = start(_environment(pki, turab.url))
    port = process.port()
    raw = _notification(messages=[_message(wamid="w5")])
    assert _request(pki, port, "POST", PATH, body=raw, headers=_signed(raw)) == (200, b"")
    assert len(turab.received) == 1 and CONTENT.encode() in turab.received[0]


# --- §5.5: every line the process writes ------------------------------------------------------

def _plain_http(port, target):
    """A request in clear text to the TLS port, its query included."""
    with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
        sock.sendall(f"GET {target} HTTP/1.1\r\nHost: relay\r\n\r\n".encode())
        try:
            while sock.recv(4096):
                pass
        except OSError:
            pass


def test_no_line_the_process_writes_holds_a_request_line_a_query_a_secret_or_content(
        pki, turab, start):  # noqa: F811
    """Through the process: Meta's GET, right and wrong; a query holding a
    percent-escape that is not UTF-8 (`%ff`); another path with the token in
    its query; a signed POST delivered
    to TURAB; a POST with a wrong signature; clients refused by mTLS; a
    clear-text request to the TLS port. Then every line is read."""
    process = start(_environment(pki, turab.url))
    port = process.port()
    raw = _notification(messages=[_message(wamid="w6")])
    signature = _signed(raw)["X-Hub-Signature-256"]
    assert _request(pki, port, "GET", _subscription()) == (200, CHALLENGE.encode())
    assert _request(pki, port, "GET", _subscription(token="wrong-" + TOKEN))[0] == 403
    assert _request(pki, port, "GET", f"{PATH}?hub.verify_token={TOKEN}&x=%ff")[0] == 400
    assert _request(pki, port, "GET", f"/other?hub.verify_token={TOKEN}")[0] == 404
    assert _request(pki, port, "POST", PATH, body=raw, headers=_signed(raw)) == (200, b"")
    assert _request(pki, port, "POST", PATH, body=raw,
                    headers={"X-Hub-Signature-256": "sha256=" + "0" * 64})[0] == 401
    assert _request(pki, port, "GET", _subscription(), cert="wrong-cn")[0] == 403
    for cert in (None, "other"):
        with pytest.raises((ssl.SSLError, OSError, http.client.HTTPException)):
            _request(pki, port, "GET", _subscription(), cert=cert)
    _plain_http(port, _subscription())
    lines = process.stop()
    assert len(turab.received) == 1
    text = "\n".join(lines)
    for needle in [TOKEN, CHALLENGE, "hub.", "verify_token", "?", "%ff", CONTENT, APP_SECRET,
                   KEY, signature[7:], turab.url, "/webhooks/whatsapp", TURAB_BODY.decode(),
                   turab.received[0].decode(), "Traceback"]:
        assert needle not in text, needle
    assert not re.search(r"\b(GET|POST) /|HTTP/1\.[01]", text), "a request line"
    loggers = set()
    for line in lines:
        match = LINE.fullmatch(line)
        assert match, f"a line not written by the configured logging: {line!r}"
        loggers.add(match.group(2))
    assert "uvicorn.access" not in loggers
    assert {"uvicorn.error", "turab_relay"} <= loggers
    if os.environ.get("R1_STEP5_LINES"):  # db/dev/r1_entry_point_lines.py: the record
        pathlib.Path(os.environ["R1_STEP5_LINES"]).write_text("\n".join(lines) + "\n")


# --- §5.2: mTLS, through the process ----------------------------------------------------------

@pytest.mark.parametrize("cert", [None, "self", "other", "expired", "future"])
def test_an_absent_untrusted_or_invalid_certificate_is_refused_by_the_process(
        pki, turab, start, cert):  # noqa: F811
    """R1-T10.2 none; 10.3 self-signed with Meta's CN; 10.4 another CA with
    Meta's CN; 10.6 expired, and not yet valid: refused at the handshake."""
    process = start(_environment(pki, turab.url))
    port = process.port()
    with pytest.raises((ssl.SSLError, OSError, http.client.HTTPException)):
        _request(pki, port, "GET", _subscription(), cert=cert)


@pytest.mark.parametrize("cert", ["wrong-cn", "two-cn"])
def test_a_certificate_of_metas_ca_with_another_identity_is_403_from_the_process(
        pki, turab, start, cert):  # noqa: F811
    process = start(_environment(pki, turab.url))
    port = process.port()
    assert _request(pki, port, "GET", _subscription(), cert=cert) == (403, b"")


def test_a_header_naming_metas_cn_does_not_replace_the_certificate(pki, turab, start):  # noqa: F811
    """R1-T10.7, through the process: a certificate of Meta's CA with another
    identity, and headers naming Meta's CN."""
    process = start(_environment(pki, turab.url))
    port = process.port()
    headers = {"X-SSL-Client-S-DN": f"CN={tls.META_CLIENT_CN}",
               "X-Client-Cert-CN": tls.META_CLIENT_CN}
    assert _request(pki, port, "GET", _subscription(), cert="wrong-cn",
                    headers=headers) == (403, b"")


# --- it refuses to start without its configuration --------------------------------------------

@pytest.mark.parametrize("variable", CONFIG_VARIABLES)
@pytest.mark.parametrize("value", [None, ""])
def test_it_refuses_to_start_without_each_of_its_settings(pki, turab, start, variable,
                                                          value):  # noqa: F811
    code, lines = start(_environment(pki, turab.url, **{variable: value})).finished()
    assert code == 2
    assert not any(STARTED.search(line) for line in lines)
    assert any(variable in line for line in lines)


@pytest.mark.parametrize("variable, value", [
    ("TURAB_RELAY_BIND_PORT", "https"), ("TURAB_RELAY_BIND_PORT", "65536"),
    ("TURAB_RELAY_BIND_PORT", "-1"), ("TURAB_RELAY_META_CA_FILE", "/nonexistent/meta-ca.pem"),
    ("TURAB_RELAY_TLS_CERTFILE", "/nonexistent/server.pem")])
def test_it_refuses_to_start_with_a_setting_it_cannot_use(pki, turab, start, variable,
                                                         value):  # noqa: F811
    code, lines = start(_environment(pki, turab.url, **{variable: value})).finished()
    assert code == 2
    assert not any(STARTED.search(line) for line in lines)
    assert any(variable in line for line in lines)
    assert not any("Traceback" in line for line in lines)


def test_a_key_that_is_not_the_certificates_is_refused_at_start(pki, turab, start):  # noqa: F811
    env = _environment(pki, turab.url, TURAB_RELAY_TLS_KEYFILE=str(pki / "good.key"))
    code, lines = start(env).finished()
    assert code == 2
    assert not any(STARTED.search(line) for line in lines)


def test_it_takes_no_command_line_argument(pki, turab, start):  # noqa: F811
    """A process's arguments are visible to every user of its host: nothing
    is configured there."""
    code, lines = start(_environment(pki, turab.url), args=["--port", "8443"]).finished()
    assert code == 2
    assert not any(STARTED.search(line) for line in lines)


def test_a_refusal_to_start_names_no_value(pki, turab, start):  # noqa: F811
    """The variables are named, never their values: the secrets stay set
    while the configuration is refused."""
    env = _environment(pki, turab.url, TURAB_RELAY_BIND_PORT="not-a-port-r1s5")
    code, lines = start(env).finished()
    text = "\n".join(lines)
    assert code == 2
    for needle in ["not-a-port-r1s5", TOKEN, APP_SECRET, KEY, turab.url]:
        assert needle not in text
