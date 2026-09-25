#!/usr/bin/env python3
"""Bind a saved JUnit report to the source tree that produced it, and check
that binding before the report is presented as evidence for a tree.

Why: a JUnit report says when IT was produced, not which tree produced it,
and nothing ties it afterwards to the numbers quoted about it. A review of
d0d58c3 showed both gaps. A failing case appended to the saved report was
still described as "1280, zero failures", copied from the provenance file.
A source change (`FOR SHARE` -> `FOR KEY SHARE`) left the report described as
evidence for a tree it never ran on.

The record (`TEST-RUN-PROVENANCE.txt`) is written by `record_test_run.py`
and holds:
- the commit;
- the source fingerprint (`db/dev/source_fingerprint.py`);
- the report's sha256;
- the cases COUNTED in the report, one per `<testcase>`.

`check()` refuses the report when:
1. the record lacks a field;
2. the report's sha256 differs from the recorded one;
3. the cases counted in the report differ from the recorded counts;
4. the report's own `<testsuite>` totals disagree with its cases;
5. any case failed or errored;
6. the CURRENT tree's source fingerprint differs from the recorded one.

A report that fails any of these is not evidence for the current tree,
whatever else it says.
"""
from __future__ import annotations

import hashlib
import pathlib
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parents[2]
REPORT = pathlib.Path("docs/gate/evidence/junit-run.xml")
PROVENANCE = pathlib.Path("docs/gate/evidence/TEST-RUN-PROVENANCE.txt")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "dev"))
from source_fingerprint import fingerprint  # noqa: E402


@dataclass(frozen=True)
class Counts:
    tests: int
    failures: int
    errors: int
    skipped: int

    def __str__(self) -> str:
        return (f"tests={self.tests} failures={self.failures} errors={self.errors} "
                f"skipped={self.skipped}")


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def counted(report: pathlib.Path) -> Counts:
    """One outcome per `<testcase>`: error, else failure, else skipped, else
    passed."""
    tests = failures = errors = skipped = 0
    for case in ET.parse(report).getroot().iter("testcase"):
        tests += 1
        tags = {child.tag for child in case}
        if "error" in tags:
            errors += 1
        elif "failure" in tags:
            failures += 1
        elif "skipped" in tags:
            skipped += 1
    return Counts(tests, failures, errors, skipped)


def declared(report: pathlib.Path) -> Counts:
    """The totals the report's `<testsuite>` elements state about themselves."""
    suites = list(ET.parse(report).getroot().iter("testsuite"))
    return Counts(*(sum(int(s.get(k, 0)) for s in suites)
                    for k in ("tests", "failures", "errors", "skipped")))


def suite_stamp(report: pathlib.Path) -> tuple[str, str]:
    suite = next(ET.parse(report).getroot().iter("testsuite"))
    return suite.get("timestamp", ""), suite.get("time", "")


INTRO = """\
TURAB — test run provenance
===========================
Written by db/gate/record_test_run.py, which runs the suite. Checked by
db/gate/run_binding.py, through `db/gate/stop_gate_c_evidence.py --check`.
A saved JUnit report says when IT was produced, not which tree produced it.
This record binds the report to that tree, and to its own digest and counts.
"""

LIMITS = """\
WHAT THIS DOES AND DOES NOT SAY
  * It says: these tests were run, at this time, against a tree whose source
    fingerprint is the value above, with nothing uncommitted when the suite
    started and nothing changed when it ended.
  * The check refuses the report in any of these cases:
      - its sha256 differs from the value above;
      - its counted cases differ from the counts above;
      - its own totals disagree with its cases;
      - any case failed or errored;
      - the CURRENT tree's source fingerprint differs from the value above.
  * It does not say the reviewer's environment would produce the same result.
    Nobody but us has re-run this suite; every result we report is ours.
  * The fingerprint covers src/, tests/, db/ and alembic.ini, not docs/. A
    later commit that touches only documentation leaves it unchanged, which is
    why the fingerprint, not the commit id, is what binds a report to the code
    it exercised.
"""


def provenance_text(*, recorded: str, commit: str, source_fingerprint: str,
                    report: pathlib.Path, report_name: str) -> str:
    stamp, took = suite_stamp(report)
    return (INTRO + "\n"
            f"Recorded    : {recorded}\n"
            f"Commit      : {commit}\n"
            "Working tree: clean when the suite started; unchanged when it ended\n"
            "Source fingerprint (db/dev/source_fingerprint.py):\n"
            f"              {source_fingerprint}\n"
            f"Report      : {report_name}\n"
            "Report sha256:\n"
            f"              {sha256(report)}\n"
            "Cases counted in the report, one per <testcase>:\n"
            f"              {counted(report)}\n"
            "JUnit timestamp / time:\n"
            f"              timestamp={stamp} time={took}s\n\n" + LIMITS)


_FIELDS = {
    "commit": r"^Commit      : (\S+)$",
    "fingerprint": r"^Source fingerprint \(db/dev/source_fingerprint\.py\):\n\s+([0-9a-f]{64})$",
    "report_sha256": r"^Report sha256:\n\s+([0-9a-f]{64})$",
    "counts": (r"^Cases counted in the report, one per <testcase>:\n"
               r"\s+tests=(\d+) failures=(\d+) errors=(\d+) skipped=(\d+)$"),
}


def read_provenance(text: str) -> dict:
    """The recorded fields; a field that is absent is absent from the result."""
    found: dict = {}
    for key, pattern in _FIELDS.items():
        m = re.search(pattern, text, re.M)
        if m:
            found[key] = Counts(*map(int, m.groups())) if key == "counts" else m.group(1)
    return found


def check(root: pathlib.Path = ROOT, report: pathlib.Path | None = None,
          provenance: pathlib.Path | None = None) -> tuple[dict, list[str]]:
    """(recorded fields, problems). No problems = the report is bound to the
    current tree."""
    report = report or root / REPORT
    provenance = provenance or root / PROVENANCE
    recorded = read_provenance(provenance.read_text())
    missing = [k for k in _FIELDS if k not in recorded]
    if missing:
        return recorded, [f"{provenance.name} lacks {', '.join(missing)}"]
    problems = []
    digest = sha256(report)
    if digest != recorded["report_sha256"]:
        problems.append(f"the report's sha256 is {digest}; the run recorded "
                        f"{recorded['report_sha256']}: this is not the report of that run")
    cases = counted(report)
    if cases != recorded["counts"]:
        problems.append(f"the report holds {cases}; the run recorded {recorded['counts']}")
    own = declared(report)
    if own != cases:
        problems.append(f"the report's totals say {own} but its cases are {cases}")
    if cases.failures or cases.errors:
        problems.append(f"the report has {cases.failures} failed and {cases.errors} "
                        "errored cases")
    current = fingerprint(root)
    if current != recorded["fingerprint"]:
        problems.append(f"the current tree's source fingerprint is {current}; the run "
                        f"was on {recorded['fingerprint']}: the report is not evidence "
                        "for this tree")
    return recorded, problems


def recorded_fingerprint_problems(record: pathlib.Path, root: pathlib.Path = ROOT) -> list[str]:
    """For any other run record that states a source fingerprint (gate-run.txt)."""
    m = re.search(_FIELDS["fingerprint"], record.read_text(), re.M)
    if not m:
        return [f"{record.name} states no source fingerprint"]
    current = fingerprint(root)
    if m.group(1) != current:
        return [f"{record.name} was recorded on source fingerprint {m.group(1)}; the "
                f"current tree's is {current}"]
    return []


if __name__ == "__main__":
    fields, found = check()
    for p in found:
        print("PROBLEM:", p, file=sys.stderr)
    print("bound" if not found else "NOT BOUND")
    sys.exit(1 if found else 0)
