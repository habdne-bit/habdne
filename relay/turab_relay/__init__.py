"""The relay between Meta's WhatsApp webhooks and TURAB's webhook (R-1).

Plan: `docs/gate/R1_RELAY_PLAN.md` (revision 7). Step 1 (closed): Meta's GET
verification, the verification of Meta's signature, the inbound limit, and
the mutual TLS of Meta's client certificate. Step 2 (closed): the
transformation, the relay's signature, `thread_ref`. Step 3: the delivery to
TURAB and the answer to Meta (`forward.py`).

R-1 is UNMET. This component is not deployed, holds no secret, and receives
no real event.
"""
