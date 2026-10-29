"""R-1 step 1: Meta's GET (duty 1), Meta's signature and the inbound limit
(duty 2), and the mutual TLS of Meta's client certificate (§5.2).

Plan: `docs/gate/R1_RELAY_PLAN.md`, revision 3; step 1 authorized in the
review of `3d8b593`. Every test is synthetic: a test verify token, a test app
secret, and certificates generated here with `openssl`, a test CA standing
for Meta's. No Meta server, no real number, no real event.

Duties 1 and 2 are tested on the ASGI application with the client
certificate check turned off **explicitly** (`require_client_certificate=
False`); its default is on, and is tested so. The mTLS tests run the relay
behind a real uvicorn TLS server, with the relay's own server context and
TLS extension protocol.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import http.client
import json
import logging
import socket
import ssl
import subprocess
import threading
import time

import pytest
from fastapi.testclient import TestClient

from turab_relay import app as relay_app
from turab_relay import meta, tls

TOKEN = "test-verify-token-r1"
SECRET = "test-app-secret-r1"
PATH = relay_app.PATH
QUERY = {"hub.mode": "subscribe", "hub.challenge": "1158201444", "hub.verify_token": TOKEN}


@pytest.fixture(autouse=True)
def _secrets(monkeypatch):
    monkeypatch.setenv(meta.VERIFY_TOKEN_VARIABLE, TOKEN)
    monkeypatch.setenv(meta.APP_SECRET_VARIABLE, SECRET)


@pytest.fixture
def client():
    with TestClient(relay_app.create_app(require_client_certificate=False)) as c:
        yield c


def _sign(raw: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def _post(client, raw: bytes, signature: str | None = "auto", **headers):
    h = dict(headers)
    if signature == "auto":
        h["X-Hub-Signature-256"] = _sign(raw)
    elif signature is not None:
        h["X-Hub-Signature-256"] = signature
    return client.post(PATH, content=raw, headers=h)


def _reason(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == "turab_relay"]


BODY = json.dumps({"object": "whatsapp_business_account", "entry": []}).encode()


# --- duty 1: Meta's GET ------------------------------------------------------------------

def test_r1_t1_1_the_right_token_is_answered_200_with_the_challenge_exactly(client):
    r = client.get(PATH, params=QUERY)
    assert (r.status_code, r.content) == (200, b"1158201444")
    assert r.headers["content-type"].startswith("text/plain")
    assert r.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("token", ["test-verify-token-r2", "x", TOKEN + "-longer"])
def test_r1_t1_2_a_wrong_token_is_403_without_the_challenge(client, token):
    r = client.get(PATH, params={**QUERY, "hub.verify_token": token})
    assert r.status_code == 403 and b"1158201444" not in r.content


@pytest.mark.parametrize("params", [
    {k: v for k, v in QUERY.items() if k != "hub.verify_token"},
    {k: v for k, v in QUERY.items() if k != "hub.challenge"},
    {k: v for k, v in QUERY.items() if k != "hub.mode"},
    {**QUERY, "hub.mode": "unsubscribe"},
    {**QUERY, "hub.challenge": ""},
    {**QUERY, "hub.verify_token": ""},
])
def test_r1_t1_3_a_malformed_subscription_is_not_200(client, params):
    r = client.get(PATH, params=params)
    assert r.status_code == 400 and r.content == b""


def test_r1_t1_3_a_repeated_parameter_is_not_200(client):
    r = client.get(PATH + "?hub.mode=subscribe&hub.challenge=1&hub.verify_token=" + TOKEN
                   + "&hub.verify_token=" + TOKEN)
    assert r.status_code == 400


@pytest.mark.parametrize("value", [None, ""])
def test_r1_t1_4_no_configured_token_fails_closed(client, monkeypatch, value):
    if value is None:
        monkeypatch.delenv(meta.VERIFY_TOKEN_VARIABLE)
    else:
        monkeypatch.setenv(meta.VERIFY_TOKEN_VARIABLE, value)
    r = client.get(PATH, params={**QUERY, "hub.verify_token": value or ""})
    assert r.status_code == 503 and r.content == b""


class _Recorder:
    """Wraps the real `compare_digest`, recording its arguments."""

    def __init__(self):
        self.calls = []

    def __call__(self, a, b):
        self.calls.append((a, b))
        return hmac.compare_digest(a, b)


def test_r1_t1_5_the_token_goes_through_compare_digest_once_per_get_that_reaches_it(
        client, monkeypatch):
    """R1-T1.5 (revision 3): exactly once for each GET that reaches the
    comparison, on bytes; R1-T1.1 and R1-T1.2 stay the behavioural tests."""
    recorder = _Recorder()
    monkeypatch.setattr(meta, "compare_digest", recorder)
    assert client.get(PATH, params=QUERY).status_code == 200
    assert recorder.calls == [(TOKEN.encode(), TOKEN.encode())]
    recorder.calls.clear()
    assert client.get(PATH, params={**QUERY, "hub.verify_token": "other"}).status_code == 403
    assert recorder.calls == [(b"other", TOKEN.encode())]


@pytest.mark.parametrize("params", [
    {k: v for k, v in QUERY.items() if k != "hub.verify_token"},
    {**QUERY, "hub.mode": "unsubscribe"},
    {k: v for k, v in QUERY.items() if k != "hub.challenge"},
])
def test_r1_t1_5_a_get_refused_before_the_comparison_never_calls_it(client, monkeypatch,
                                                                    params):
    recorder = _Recorder()
    monkeypatch.setattr(meta, "compare_digest", recorder)
    assert client.get(PATH, params=params).status_code == 400
    assert recorder.calls == []


def test_r1_t1_5_no_configured_token_never_calls_the_comparison(client, monkeypatch):
    recorder = _Recorder()
    monkeypatch.setattr(meta, "compare_digest", recorder)
    monkeypatch.delenv(meta.VERIFY_TOKEN_VARIABLE)
    assert client.get(PATH, params=QUERY).status_code == 503
    assert recorder.calls == []


# --- duty 2: Meta's signature, and the inbound limit -------------------------------------

def test_r1_t2_1_a_verified_post_is_503_not_forwarding_never_200(client, caplog):
    """Step 1 builds no forwarding: a verified POST is not acknowledged."""
    caplog.set_level(logging.INFO, logger="turab_relay")
    r = _post(client, BODY)
    assert r.status_code == 503
    assert any("RELAY_NOT_FORWARDING" in m for m in _reason(caplog))


@pytest.mark.parametrize("signature", [
    None, "", "sha256=", "md5=" + "0" * 64, "sha256=" + "0" * 63,
    "sha256=" + "g" * 64, "SHA256=" + "0" * 64, " sha256=" + "0" * 64,
])
def test_r1_t2_2_a_missing_or_malformed_signature_is_401(client, signature):
    r = _post(client, b"{not json", signature=signature)
    assert r.status_code == 401


@pytest.mark.parametrize("wrap", [lambda h: h + "0", lambda h: "x" + h, lambda h: h + ",x",
                                  lambda h: h + " "])
def test_r1_t2_2_a_valid_digest_inside_a_longer_header_is_refused(client, wrap):
    """The header must be exactly `sha256=<64 hex>`: a valid digest found
    inside a longer value is not a valid header."""
    assert _post(client, BODY, signature=wrap(_sign(BODY))).status_code == 401


def test_r1_t2_2_an_uppercase_digest_is_refused(client):
    r = _post(client, BODY, signature=_sign(BODY).upper().replace("SHA256=", "sha256="))
    assert r.status_code == 401


def test_r1_t2_3_a_valid_signature_over_other_bytes_is_401(client):
    other = BODY[:-1] + b" "
    assert other != BODY
    assert _post(client, other, signature=_sign(BODY)).status_code == 401
    assert _post(client, BODY, signature=_sign(BODY, "another-secret")).status_code == 401


def test_r1_t2_4_the_same_json_reserialized_is_401(client):
    raw = b'{"object": "whatsapp_business_account", "entry": []}'
    again = json.dumps(json.loads(raw), separators=(",", ":")).encode()
    assert again != raw
    assert _post(client, again, signature=_sign(raw)).status_code == 401


@pytest.mark.parametrize("value", [None, ""])
def test_r1_t2_5_no_app_secret_fails_closed(client, monkeypatch, value):
    if value is None:
        monkeypatch.delenv(meta.APP_SECRET_VARIABLE)
    else:
        monkeypatch.setenv(meta.APP_SECRET_VARIABLE, value)
    assert _post(client, BODY, signature=_sign(BODY, value or "")).status_code == 503
    assert _post(client, BODY, signature=None).status_code == 503


def test_r1_t2_6_the_limit_is_3_mib_exactly(client):
    assert relay_app.INBOUND_LIMIT == 3 * 1024 * 1024
    at = b" " * relay_app.INBOUND_LIMIT
    assert _post(client, at).status_code == 503, "3 MiB is under the limit"
    over = b" " * (relay_app.INBOUND_LIMIT + 1)
    assert _post(client, over).status_code == 413


def _call(app, headers, chunks):
    """Drive the ASGI application directly; record how many chunks it read."""
    sent, read = [], []

    async def receive():
        if chunks:
            read.append(1)
            chunk = chunks.pop(0)
            return {"type": "http.request", "body": chunk, "more_body": bool(chunks)}
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": PATH, "query_string": b"",
             "headers": [(k.encode(), v.encode()) for k, v in headers.items()]}
    asyncio.run(app(scope, receive, send))
    return sent[0]["status"], len(read)


@pytest.mark.parametrize("declared", [
    str(relay_app.INBOUND_LIMIT + 1), "9" * 5000, "0" * 4000 + str(relay_app.INBOUND_LIMIT + 1),
])
def test_r1_t2_6_a_declared_length_over_the_limit_is_413_unread(declared):
    app = relay_app.create_app(require_client_certificate=False)
    status, read = _call(app, {"content-length": declared}, [b"x"])
    assert (status, read) == (413, 0)


def test_r1_t2_6_leading_zeros_alone_are_not_over_the_limit():
    assert not relay_app.declared_over_limit("0" * 4000 + "10")
    assert relay_app.declared_over_limit("0" * 4000 + str(relay_app.INBOUND_LIMIT + 1))


def test_r1_t2_6_the_body_is_counted_as_it_arrives_and_stops_past_the_limit():
    app = relay_app.create_app(require_client_certificate=False)
    chunk = b" " * (1024 * 1024)
    status, read = _call(app, {}, [chunk, chunk, chunk, b"  ", chunk, chunk])
    assert status == 413 and read == 4, "reading stops at the chunk that passes the limit"


def test_r1_t2_6_the_limit_comes_before_the_secret(client, monkeypatch):
    monkeypatch.delenv(meta.APP_SECRET_VARIABLE)
    assert _post(client, b" " * (relay_app.INBOUND_LIMIT + 1)).status_code == 413


def test_r1_t2_7_no_log_holds_the_body_a_header_the_token_or_the_challenge(client, caplog):
    """Every logger but the test's own HTTP client (`httpx`, `httpcore`), which
    logs the full URL it requests. A server logging the request line would
    record `hub.verify_token` the same way: the relay's server runs with
    uvicorn's access log off (`test_the_relay_server_runs_without_an_access_log`)."""
    caplog.set_level(logging.DEBUG)
    secret_body = b'{"text": {"body": "SECRET-BODY-r1"}}'
    _post(client, secret_body)
    _post(client, secret_body, signature="sha256=" + "a" * 64)
    _post(client, secret_body, signature=None)
    client.get(PATH, params={**QUERY, "hub.verify_token": "WRONG-TOKEN-r1",
                             "hub.challenge": "CHALLENGE-r1"})
    client.get(PATH, params={**QUERY, "hub.challenge": "CHALLENGE-r1"})
    text = "\n".join(r.getMessage() for r in caplog.records
                     if not r.name.startswith(("httpx", "httpcore")))
    for needle in ("SECRET-BODY-r1", "a" * 64, _sign(secret_body)[7:], "WRONG-TOKEN-r1",
                   "CHALLENGE-r1", TOKEN, SECRET):
        assert needle not in text
    assert "SIGNATURE_NOT_VALID" in text and "VERIFY_TOKEN_MISMATCH" in text


def test_r1_t2_8_the_signature_goes_through_compare_digest_on_bytes(client, monkeypatch):
    recorder = _Recorder()
    monkeypatch.setattr(meta, "compare_digest", recorder)
    assert _post(client, BODY).status_code == 503
    expected = _sign(BODY)[7:].encode()
    assert recorder.calls == [(expected, expected)]
    recorder.calls.clear()
    assert _post(client, BODY, signature="sha256=" + "0" * 64).status_code == 401
    assert recorder.calls == [(expected, b"0" * 64)]
    recorder.calls.clear()
    assert _post(client, BODY, signature="sha256=short").status_code == 401
    assert recorder.calls == [], "a malformed header is refused before the comparison"


def test_another_path_or_method_is_refused(client):
    assert client.get("/other", params=QUERY).status_code == 404
    assert client.put(PATH, content=BODY).status_code == 405


# --- §5.2: the client certificate, required by default -----------------------------------

def test_the_client_certificate_is_required_by_default():
    with TestClient(relay_app.create_app()) as c:
        r = c.get(PATH, params=QUERY)
    assert r.status_code == 403 and r.content == b""


def test_r1_t10_7_a_header_naming_metas_cn_counts_for_nothing():
    with TestClient(relay_app.create_app()) as c:
        r = c.get(PATH, params=QUERY, headers={
            "X-Client-Cert-CN": tls.META_CLIENT_CN,
            "X-Amzn-Mtls-Clientcert-Subject": "CN=" + tls.META_CLIENT_CN,
            "X-SSL-Client-S-DN": "CN=" + tls.META_CLIENT_CN})
    assert r.status_code == 403


@pytest.mark.parametrize("subject, ok", [
    ((((("commonName", tls.META_CLIENT_CN),),)), True),
    (((("commonName", tls.META_CLIENT_CN + ".evil"),),), False),
    (((("commonName", "evil." + tls.META_CLIENT_CN),),), False),
    (((("commonName", tls.META_CLIENT_CN),), (("commonName", "second"),)), False),
    (((("organizationName", tls.META_CLIENT_CN),),), False),
    ((), False),
])
def test_meta_identity_is_exactly_one_common_name(subject, ok):
    scope = {"extensions": {"tls": {"client_cert_subject": subject}}}
    assert tls.meta_identity(scope) is ok


# --- §5.2: mutual TLS, end to end ------------------------------------------------------

def _openssl(*args, cwd):
    done = subprocess.run(["openssl", *args], cwd=cwd, capture_output=True, text=True)
    assert done.returncode == 0, f"openssl {args[0]}: {done.stderr}"


@pytest.fixture(scope="module")
def pki(tmp_path_factory):
    """Synthetic certificates: the relay's server certificate, a test CA
    standing for Meta's, and the client certificates of R1-T10.1 to 10.6."""
    d = tmp_path_factory.mktemp("r1-pki")
    (d / "client.ext").write_text("basicConstraints=CA:FALSE\nextendedKeyUsage=clientAuth\n")
    (d / "server.ext").write_text("basicConstraints=CA:FALSE\nextendedKeyUsage=serverAuth\n"
                                  "subjectAltName=IP:127.0.0.1\n")

    def ca(name, cn):
        _openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", f"{name}.key",
                 "-out", f"{name}.pem", "-days", "2", "-subj", f"/CN={cn}", cwd=d)

    def leaf(name, subject, issuer, ext="client.ext"):
        _openssl("req", "-newkey", "rsa:2048", "-nodes", "-keyout", f"{name}.key", "-out",
                 f"{name}.csr", "-subj", subject, cwd=d)
        _openssl("x509", "-req", "-in", f"{name}.csr", "-CA", f"{issuer}.pem", "-CAkey",
                 f"{issuer}.key", "-CAcreateserial", "-out", f"{name}.pem", "-days", "2",
                 "-extfile", ext, cwd=d)

    def dated(name, subject, start, end):
        if not (d / "db").exists():
            (d / "db").mkdir()
            (d / "db" / "index.txt").touch()
            (d / "db" / "serial").write_text("1000\n")
        (d / "ca.cnf").write_text(
            "[ca]\ndefault_ca=c\n[c]\ndir=db\ndatabase=db/index.txt\nnew_certs_dir=db\n"
            "serial=db/serial\ndefault_md=sha256\npolicy=p\nunique_subject=no\n"
            "x509_extensions=x\n[p]\ncommonName=supplied\n"
            "[x]\nbasicConstraints=CA:FALSE\nextendedKeyUsage=clientAuth\n")
        _openssl("req", "-newkey", "rsa:2048", "-nodes", "-keyout", f"{name}.key", "-out",
                 f"{name}.csr", "-subj", subject, cwd=d)
        _openssl("ca", "-batch", "-config", "ca.cnf", "-cert", "meta-ca.pem", "-keyfile",
                 "meta-ca.key", "-in", f"{name}.csr", "-out", f"{name}.pem", "-startdate",
                 start, "-enddate", end, "-notext", cwd=d)

    ca("server-ca", "r1-test-server-ca")
    leaf("server", "/CN=127.0.0.1", "server-ca", "server.ext")
    ca("meta-ca", "r1-test-meta-ca")
    ca("other-ca", "r1-test-other-ca")
    leaf("good", f"/CN={tls.META_CLIENT_CN}", "meta-ca")
    leaf("wrong-cn", "/CN=client.webhooks.example.com", "meta-ca")
    leaf("two-cn", f"/CN={tls.META_CLIENT_CN}/CN=second", "meta-ca")
    leaf("other", f"/CN={tls.META_CLIENT_CN}", "other-ca")
    ca("self", tls.META_CLIENT_CN)
    dated("expired", f"/CN={tls.META_CLIENT_CN}", "20200101000000Z", "20200102000000Z")
    dated("future", f"/CN={tls.META_CLIENT_CN}", "20990101000000Z", "20990102000000Z")
    return d


@pytest.fixture(scope="module")
def relay_server(pki):
    """The relay behind a real uvicorn TLS server, with the relay's own server
    context and TLS extension protocol. `reached` counts requests that got
    past the TLS layer to the application."""
    import uvicorn

    reached = []
    inner = relay_app.create_app()

    async def counted(scope, receive, send):
        if scope["type"] == "http":
            reached.append(scope["path"])
        await inner(scope, receive, send)

    context = tls.server_context(str(pki / "server.pem"), str(pki / "server.key"),
                                 str(pki / "meta-ca.pem"))
    config = uvicorn.Config(counted, http=tls.TLSExtensionH11Protocol, lifespan="off",
                            log_level="critical", access_log=False,
                            ssl_context_factory=lambda cfg, default: context)
    server = uvicorn.Server(config)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started
    yield port, reached, context, config
    server.should_exit = True
    thread.join(10)


def _https_get(pki, port, cert=None):
    context = ssl.create_default_context(cafile=str(pki / "server-ca.pem"))
    if cert:
        context.load_cert_chain(str(pki / f"{cert}.pem"), str(pki / f"{cert}.key"))
    query = "&".join(f"{k}={v}" for k, v in QUERY.items())
    conn = http.client.HTTPSConnection("127.0.0.1", port, context=context, timeout=10)
    try:
        conn.request("GET", f"{PATH}?{query}")
        r = conn.getresponse()
        return r.status, r.read()
    finally:
        conn.close()


def test_the_relay_server_runs_without_an_access_log(relay_server):
    """Meta sends the verify token in the GET's query (E1): an access log of
    the request line would record it."""
    *_, config = relay_server
    assert config.access_log is False


def test_r1_t10_the_server_trusts_the_configured_ca_only(relay_server):
    _, _, context, _ = relay_server
    anchors = context.get_ca_certs()
    assert [dict(x[0] for x in c["subject"])["commonName"] for c in anchors] == [
        "r1-test-meta-ca"]
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.minimum_version == ssl.TLSVersion.TLSv1_2


def test_r1_t10_1_metas_certificate_from_the_ca_is_accepted(pki, relay_server):
    port, reached, _, _ = relay_server
    before = len(reached)
    assert _https_get(pki, port, "good") == (200, b"1158201444")
    assert len(reached) == before + 1


@pytest.mark.parametrize("cert", [None, "self", "other", "expired", "future"])
def test_r1_t10_2_to_6_an_absent_untrusted_or_invalid_certificate_never_reaches_the_relay(
        pki, relay_server, cert):
    """R1-T10.2 none; 10.3 self-signed with the right CN; 10.4 another CA with
    the right CN; 10.6 expired, and not yet valid."""
    port, reached, _, _ = relay_server
    before = len(reached)
    with pytest.raises((ssl.SSLError, OSError, http.client.HTTPException)):
        _https_get(pki, port, cert)
    assert len(reached) == before, "refused at the TLS layer"


@pytest.mark.parametrize("cert", ["wrong-cn", "two-cn"])
def test_r1_t10_5_a_valid_certificate_with_another_identity_is_403(pki, relay_server, cert):
    """R1-T10.5: the chain is Meta's CA's, but the identity is not Meta's."""
    port, _, _, _ = relay_server
    assert _https_get(pki, port, cert) == (403, b"")
