"""Mutual TLS with Meta's client certificate (R1-D10, plan §5.2).

Meta's documentation (`R1-META-SOURCES.txt`): trust Meta's outbound API CA
certificate (E53), verify the client certificate against it (E54), and
verify its common name, `client.webhooks.fbclientcerts.com` (E55).

**What is verified, and where:**
1. **The chain, to Meta's CA as the only anchor, and the validity period:**
   by the TLS handshake, under `server_context`. The context requires a
   client certificate, trusts the one CA file it is given and nothing else
   (`PROTOCOL_TLS_SERVER` loads no default roots, and none are added), and
   refuses TLS below 1.2. A certificate that fails is refused before any
   request reaches the application.
2. **The identity:** by `meta_identity`, on the subject of the certificate
   the handshake validated. The server puts that subject in the ASGI scope's
   TLS extension (`TLSExtensionH11Protocol`), from the connection's own TLS
   object; nothing a client sends can set it. A header naming the right CN
   counts for nothing.

**Not covered here:** the rotation of Meta's CA certificate, an operational
change (§5.2); the deployment, which step 1 does not authorize.
"""
from __future__ import annotations

import ssl

from uvicorn.protocols.http.h11_impl import H11Protocol

META_CLIENT_CN = "client.webhooks.fbclientcerts.com"


def server_context(certfile: str, keyfile: str, client_ca_file: str) -> ssl.SSLContext:
    """The relay's server context: its own certificate, and Meta's CA as the
    only anchor for the client's."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile, keyfile)
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cafile=client_ca_file)
    return context


def meta_identity(scope) -> bool:
    """Whether the validated client certificate in the scope is Meta's: its
    subject holds exactly one common name, and it is `META_CLIENT_CN`."""
    tls = (scope.get("extensions") or {}).get("tls") or {}
    subject = tls.get("client_cert_subject")
    if not subject:
        return False
    names = [value for rdn in subject for key, value in rdn if key == "commonName"]
    return names == [META_CLIENT_CN]


class TLSExtensionH11Protocol(H11Protocol):
    """uvicorn's h11 protocol, adding to each request's scope the subject of
    the client certificate this connection's handshake validated."""

    def connection_made(self, transport) -> None:  # type: ignore[override]
        super().connection_made(transport)
        ssl_object = transport.get_extra_info("ssl_object")
        certificate = ssl_object.getpeercert() if ssl_object is not None else None
        if not certificate:
            return
        subject = certificate.get("subject", ())
        inner = self.app

        async def app(scope, receive, send):
            extensions = dict(scope.get("extensions") or {})
            extensions["tls"] = {"client_cert_subject": subject}
            scope["extensions"] = extensions
            await inner(scope, receive, send)

        self.app = app
