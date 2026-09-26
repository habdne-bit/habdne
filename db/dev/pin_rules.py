#!/usr/bin/env python3
"""Pin new rule versions in `src/turab/matching/rule_pins.py` (G4-2).

    .venv/bin/python db/dev/pin_rules.py           # add pins for new versions
    .venv/bin/python db/dev/pin_rules.py --check   # report, change nothing

It only ADDS a pin for a (rule_id, rule_version) pair that has none. It
REFUSES, and writes nothing, when:
- a pinned pair's source changed. That is a new version, not a new pin;
- a pinned pair is no longer implemented. Replay of the matches citing it
  would be lost.

Changing an existing pin is therefore a hand edit of the pin file, and
review will see it.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from turab.matching import registry as reg  # noqa: E402


def main(argv: list[str]) -> int:
    pins = reg.load_pins()
    problems = [p for p in reg.REGISTRY.verify_pins(pins) if "not pinned" not in p]
    if problems:
        for p in problems:
            print("REFUSED:", p, file=sys.stderr)
        return 1
    new = {r.key: r.source_sha256() for r in reg.REGISTRY.rules() if r.key not in pins}
    if "--check" in argv:
        print(f"{len(pins)} pinned, {len(new)} to add: {sorted(new)}")
        return 1 if new else 0
    if new:
        pins.update(new)
        reg.PINS_PATH.write_text(reg.render_pins(pins), encoding="utf-8")
    print(f"pinned {len(new)} new version(s); {len(pins)} in total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
