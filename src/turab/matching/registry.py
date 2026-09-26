"""The rule registry: every rule the engine may cite, by id AND version
(decision G4-2).

Ref: `docs/gate/SLICE_4_PLAN.md` G4-2, decided in the review of aad9f34,
option (a), with a condition; Developer Spec §30 (a rule change goes through a
versioned record, "not silently in code").

## Keyed by (rule_id, rule_version), and old versions stay

A criterion result records the `rule_id` and `rule_version` that produced
it (`match_criterion_results`). Replaying an old match means running THAT
version, so the condition attached to G4-2 holds:

> every version that any stored match cites stays implemented and
> replayable. Raising a rule's version and deleting the previous
> implementation does not achieve replay.

A new version is therefore REGISTERED BESIDE the old one, never in its place.
`register` refuses a second implementation of an existing
(rule_id, rule_version) pair.

## The pins: a code change without a version bump fails

`rule_pins.py`, next to this file (Python, so the source fingerprint binds
it), maps `"<rule_id>@<rule_version>"` to
the sha256 of that rule's source text. `verify_pins` reports three kinds of
problem:
- a registered rule whose source no longer matches its pin: it was changed
  without a version bump;
- a registered rule that is not pinned;
- a pin whose rule is no longer implemented: replay of every match that
  cites it is gone;

Pins are written by `db/dev/pin_rules.py`, which only ADDS a pin for a new
pair. It refuses to change an existing one, so moving a pin to match new
code is a deliberate edit that review will see.

**Scope of the source digest.** It covers the rule function's own source
text (`inspect.getsource`). A helper the rule calls is not covered unless it
is itself a registered rule, or the rule is written without such helpers.
The rules of step 4 are written to that constraint, and it is restated
there.

## The digest in the input hash

`RuleRegistry.digest()` is sha256 over the sorted lines
`rule_id \\t rule_version \\t source_sha256`, one per registered pair. It is an
input of the match hash (G4-13), so a run under a different rule set is a
different input.

The production registry, `REGISTRY`, is EMPTY in step 2. The criterion rules
are step 4, and wait on G4-3 to G4-7.
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import pathlib
from dataclasses import dataclass
from typing import Any, Callable

PINS_PATH = pathlib.Path(__file__).with_name("rule_pins.py")


class RegistryError(RuntimeError):
    """The registry was asked to hold two implementations of one version."""


class UnknownRuleVersion(LookupError):
    """No implementation is registered for this (rule_id, rule_version)."""


@dataclass(frozen=True, slots=True)
class Rule:
    rule_id: str
    rule_version: str
    evaluate: Callable[..., Any]

    @property
    def key(self) -> str:
        return f"{self.rule_id}@{self.rule_version}"

    def source_sha256(self) -> str:
        return hashlib.sha256(inspect.getsource(self.evaluate).encode("utf-8")).hexdigest()


def _valid_name(value: str) -> bool:
    return bool(value) and value == value.strip() and "@" not in value and "\t" not in value


class RuleRegistry:
    def __init__(self) -> None:
        self._rules: dict[tuple[str, str], Rule] = {}

    def register(self, rule_id: str, rule_version: str):
        """Decorator: register `fn` as `rule_id` at `rule_version`."""
        if not (_valid_name(rule_id) and _valid_name(rule_version)):
            raise RegistryError(f"invalid rule id or version: {rule_id!r} {rule_version!r}")

        def add(fn: Callable[..., Any]) -> Callable[..., Any]:
            key = (rule_id, rule_version)
            if key in self._rules:
                raise RegistryError(
                    f"{rule_id}@{rule_version} is already registered. A changed rule is "
                    "a NEW version, registered beside the old one (G4-2)")
            self._rules[key] = Rule(rule_id, rule_version, fn)
            return fn
        return add

    def resolve(self, rule_id: str, rule_version: str) -> Rule:
        try:
            return self._rules[(rule_id, rule_version)]
        except KeyError:
            raise UnknownRuleVersion(f"{rule_id}@{rule_version} is not implemented") from None

    def versions(self, rule_id: str) -> tuple[str, ...]:
        return tuple(sorted(v for (i, v) in self._rules if i == rule_id))

    def rules(self) -> tuple[Rule, ...]:
        return tuple(self._rules[k] for k in sorted(self._rules))

    def digest(self) -> str:
        lines = "".join(f"{r.rule_id}\t{r.rule_version}\t{r.source_sha256()}\n"
                        for r in self.rules())
        return hashlib.sha256(lines.encode("utf-8")).hexdigest()

    def verify_pins(self, pins: dict[str, str]) -> list[str]:
        """Every problem between this registry and `pins`; empty means they agree."""
        problems = []
        registered = {r.key: r for r in self.rules()}
        for key, rule in registered.items():
            if key not in pins:
                problems.append(f"{key} is registered but not pinned; pin it with "
                                "db/dev/pin_rules.py")
            elif pins[key] != rule.source_sha256():
                problems.append(f"{key} changed without a version bump: its source no "
                                "longer matches its pin. Register a new version instead")
        for key in sorted(set(pins) - set(registered)):
            problems.append(f"{key} is pinned but no longer implemented: every match "
                            "citing it can no longer be replayed")
        return problems


def load_pins(path: pathlib.Path | None = None) -> dict[str, str]:
    """Read `FORMAT` and `PINS` as literals: the file is data, never executed.

    The default path is resolved at CALL time, not bound as a default
    argument, so a caller that points `PINS_PATH` elsewhere is honoured."""
    path = path or PINS_PATH
    values = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            target = node.targets[0] if isinstance(node, ast.Assign) else node.target
            if isinstance(target, ast.Name):
                values[target.id] = ast.literal_eval(node.value)
    pins = values.get("PINS")
    if values.get("FORMAT") != 1 or not isinstance(pins, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in pins.items()):
        raise RegistryError(f"{path.name}: not a rule pin file (format 1)")
    return dict(pins)


def render_pins(pins: dict[str, str]) -> str:
    """The pin file's text, sorted, for `db/dev/pin_rules.py`."""
    body = "".join(f"    {k!r}: {v!r},\n" for k, v in sorted(pins.items()))
    return ('"""Rule source pins (G4-2). Written by `db/dev/pin_rules.py`, which only adds.\n\n'
            "A Python file rather than JSON, so the source fingerprint\n"
            "(`db/dev/source_fingerprint.py`, which covers .py files) binds every test run\n"
            'to the exact pins it ran with.\n"""\n\nFORMAT = 1\n\nPINS: dict[str, str] = {\n'
            + body + "}\n")


#: The production registry. Empty in step 2: the criterion rules are step 4.
REGISTRY = RuleRegistry()
