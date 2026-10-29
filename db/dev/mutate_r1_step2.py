"""R-1 step 2, the transformation, the relay's signature and `thread_ref`:
which test refuses which weakening.

    .venv/bin/python db/dev/mutate_r1_step2.py [X1 I1 ...] > /outside/the/tree.txt

Plan: `docs/gate/R1_RELAY_PLAN.md`, revision 6; step 2 authorized in the
review of `e9fac51`; X18 and X19 added after the review of `ced7df7`
(document order inside one `value`). Each mutation weakens ONE rule:
- X: duty 3, the transformation and §5.3's table, §5.1's checks by kind;
- I: duty 6, `thread_ref`, R1-D8 and R1-D7;
- K: duty 4, the relay's signature and its key.

Not mutated, each with its reason:
- the refusal of a status value Meta does not document (`STATUS_NOT_KNOWN`):
  removing it makes the next line raise a `KeyError`, a crash rather than a
  weakening; the forwarded envelope would also be refused by TURAB's own
  parser (its six statuses);
- the `business is None` part of the required-field checks: without it, a
  missing business number fails the scoping check that follows
  (`IDENTIFIER_NOT_SCOPABLE`), still ISOLATED; the two are equivalent for the
  element's class.

Only `tests/test_r1_step2.py` is run. Run in one part. See
`mutation_runner.py`.
"""
import sys

from mutation_runner import ROOT, run

TRANSFORM = "relay/turab_relay/transform.py"
TESTS = "tests/test_r1_step2.py"

MUTATIONS = [
 # --- X: duty 3 ---------------------------------------------------------------------------
 ("X1 a text's body not carried", TRANSFORM,
  "    if carries == \"text\" and isinstance(body.get(\"body\"), str):", "    if False:"),
 ("X2 a caption carried for every media type", TRANSFORM,
  "    if carries == \"media+caption\" and isinstance(body.get(\"caption\"), str):",
  "    if carries in (\"media\", \"media+caption\") and isinstance(body.get(\"caption\"), str):"),
 ("X3 a media id not carried", TRANSFORM,
  "    if carries in (\"media\", \"media+caption\") and _text(body.get(\"id\")):",
  "    if False:"),
 ("X4 an unlisted type passed through", TRANSFORM,
  "    stored, carries = TYPES.get(meta_type, (OTHER, None))",
  "    stored, carries = TYPES.get(meta_type, (meta_type.upper(), None))"),
 ("X5 an unlisted type carries content", TRANSFORM,
  "    stored, carries = TYPES.get(meta_type, (OTHER, None))",
  "    stored, carries = TYPES.get(meta_type, (OTHER, \"text\"))"),
 ("X6 an image's caption dropped", TRANSFORM,
  "    \"image\": (\"IMAGE\", \"media+caption\"),", "    \"image\": (\"IMAGE\", \"media\"),"),
 ("X7 a message's event id without its prefix", TRANSFORM,
  "    event_id = f\"message:{wamid}\"", "    event_id = f\"{wamid}\""),
 ("X8 a status's event id without its timestamp", TRANSFORM,
  "    event_id = f\"status:{wamid}:{value}:{timestamp}\"",
  "    event_id = f\"status:{wamid}:{value}\""),
 ("X9 delivered mapped to READ", TRANSFORM,
  "\"delivered\": \"DELIVERED\"", "\"delivered\": \"READ\""),
 ("X10 played not dropped", TRANSFORM,
  "    if value == PLAYED:\n        return Element(\"status\", DROPPED, \"STATUS_PLAYED\")",
  "    if False:\n        return Element(\"status\", DROPPED, \"STATUS_PLAYED\")"),
 ("X11 the instant without its zone", TRANSFORM,
  "    return moment.strftime(\"%Y-%m-%dT%H:%M:%SZ\")",
  "    return moment.strftime(\"%Y-%m-%dT%H:%M:%S\")"),
 ("X12 a timestamp not checked as decimal digits", TRANSFORM,
  "    if not (isinstance(timestamp, str) and timestamp.isascii() and timestamp.isdigit()):",
  "    if not isinstance(timestamp, str):"),
 ("X13 non-ASCII digits accepted", TRANSFORM,
  "timestamp.isascii() and timestamp.isdigit()", "timestamp.isdigit()"),
 ("X14 any object accepted", TRANSFORM,
  "    if not isinstance(doc, dict) or doc.get(\"object\") != OBJECT:",
  "    if not isinstance(doc, dict):"),
 ("X15 any field accepted", TRANSFORM,
  "            if not isinstance(change, dict) or change.get(\"field\") != \"messages\":",
  "            if not isinstance(change, dict):"),
 ("X16 value.errors not counted", TRANSFORM,
  "                out.append(Element(\"change\", DROPPED, \"VALUE_ERRORS\"))",
  "                pass"),
 ("X17 a missing timestamp not a missing field", TRANSFORM,
  "            and _text(message.get(\"timestamp\"))) or business is None:",
  "            ) or business is None:"),
 ("X18 the fixed order of kinds restored", TRANSFORM,
  "            for key, items in value.items():",
  "            for key, items in sorted(value.items(), key=lambda kv: (\"errors\", \"messages\", "
  "\"statuses\").index(kv[0]) if kv[0] in (\"errors\", \"messages\", \"statuses\") else -1):"),
 ("X19 contacts read as a stream", TRANSFORM,
  "            for key, items in value.items():",
  "            contacts = None\n            for key, items in value.items():\n"
  "                contacts = items if key == \"contacts\" else contacts"),
 # --- I: duty 6 ---------------------------------------------------------------------------
 ("I1 a message's thread_ref reversed", TRANSFORM,
  "                            \"thread_ref\": f\"{business}:{sender}\",",
  "                            \"thread_ref\": f\"{sender}:{business}\","),
 ("I2 a status's thread_ref reversed", TRANSFORM,
  "                            \"thread_ref\": f\"{business}:{recipient}\",",
  "                            \"thread_ref\": f\"{recipient}:{business}\","),
 ("I3 a message's identifiers not scoped", TRANSFORM,
  "    if not (_scoped(sender) and _scoped(business)):", "    if False:"),
 ("I4 a status's identifiers not scoped", TRANSFORM,
  "    if not (_scoped(recipient) and _scoped(business)):", "    if False:"),
 ("I5 a colon accepted in an identifier", TRANSFORM,
  "    return isinstance(value, str) and value != \"\" and \":\" not in value",
  "    return isinstance(value, str) and value != \"\""),
 ("I6 contacts not checked", TRANSFORM,
  "        if wa_ids and sender not in wa_ids:", "        if False:"),
 ("I7 a message without a wa_id isolated", TRANSFORM,
  "        if wa_ids and sender not in wa_ids:", "        if sender not in wa_ids:"),
 ("I8 a group message forwarded", TRANSFORM,
  "    if \"group_id\" in message:", "    if False:"),
 ("I9 a group status forwarded", TRANSFORM,
  "    if status.get(\"recipient_type\") == \"group\":", "    if False:"),
 # --- K: duty 4 ---------------------------------------------------------------------------
 ("K1 the signature over other bytes", TRANSFORM,
  "    return \"sha256=\" + hmac.new(key, envelope, hashlib.sha256).hexdigest()",
  "    return \"sha256=\" + hmac.new(key, envelope + b\"\\n\", hashlib.sha256).hexdigest()"),
 ("K2 a key equal to Meta's app secret accepted", TRANSFORM,
  "    if app_secret and hmac.compare_digest(key.encode(\"utf-8\"), app_secret.encode(\"utf-8\")):",
  "    if False:"),
 ("K3 an empty key accepted", TRANSFORM,
  "    if not key:\n        raise RelayKeyRefused", "    if key is None:\n        raise RelayKeyRefused"),
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
    survivors = run("TURAB — R-1 step 2: the transformation, the relay's signature, "
                    "thread_ref", TESTS, MUTATIONS, tuple(sys.argv[1:]))
    sys.exit(1 if survivors else 0)
