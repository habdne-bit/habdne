"""The relay between Meta's WhatsApp webhooks and TURAB's webhook (R-1).

Plan: `docs/gate/R1_RELAY_PLAN.md` (revision 3). Step 1 only: Meta's GET
verification, the verification of Meta's signature, the inbound limit, and
the mutual TLS of Meta's client certificate. **Nothing is forwarded to
TURAB yet:** a POST whose signature verifies is answered 503, never 200, so
no delivery is acknowledged to Meta (steps 2 and 3 build the forwarding).

R-1 is UNMET. This component is not deployed, holds no secret, and receives
no real event.
"""
