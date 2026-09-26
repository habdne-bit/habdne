"""Rule source pins (G4-2). Written by `db/dev/pin_rules.py`, which only adds.

A Python file rather than JSON, so the source fingerprint
(`db/dev/source_fingerprint.py`, which covers .py files) binds every test run
to the exact pins it ran with.
"""

FORMAT = 1

PINS: dict[str, str] = {
}
