"""Shared machinery for the mutation evidence scripts in db/dev/.

`run(title, test_file, mutations, only)`:
1. prints a header binding the output to the commit, the source fingerprint
   and whether the tree was clean;
2. runs the baseline;
3. for each mutation `(name, relative path, anchor, replacement)`, applies it
   to the production file, runs the shipped test file, restores the file, and
   checks its sha256 is unchanged;
4. prints the failing tests and the CAUSE each failure reports.

Write the output OUTSIDE the tree (a redirect into the tree dirties it before
the header is taken), then copy it in.
"""
from __future__ import annotations

import datetime
import hashlib
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PYTHON = str(ROOT / ".venv/bin/python")


def _out(*argv):
    return subprocess.run(argv, cwd=ROOT, capture_output=True, text=True).stdout.strip()


def _pytest(test_file):
    return subprocess.run([PYTHON, "-m", "pytest", test_file, "-q", "-p", "no:cacheprovider",
                           "--tb=line", "-rf"], cwd=ROOT, capture_output=True, text=True).stdout


def _cause(line):
    # A refused body carries a per-request trace_id; its field message is the
    # cause, so that is what is kept.
    field = re.search(r'"status":(\d+).*?"message":"([^"]+)"', line)
    if field:
        return f"HTTP {field.group(1)} field error: {field.group(2)}"
    return re.sub(r"^/\S+:\d+: ", "", line)[:170]


def run(title, test_file, mutations, only=()):
    dirty = _out("git", "status", "--porcelain")
    print(title)
    print("=" * 60)
    print("Base commit       :", _out("git", "rev-parse", "HEAD"))
    print("Source fingerprint:", _out(PYTHON, "db/dev/source_fingerprint.py", "."))
    print("Working tree      :", "CLEAN" if not dirty else "DIRTY\n" + dirty)
    print("Recorded          :",
          datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
    print("Test file         :", test_file)
    print()
    print("=== baseline (no mutation) ===\n   " + _pytest(test_file).strip().splitlines()[-1])
    survivors = []
    for name, rel, old, new in mutations:
        if only and name.split()[0] not in only:
            continue
        path = ROOT / rel
        source = path.read_text()
        sites = source.count(old)
        # Checked BEFORE the backup is made: a missing anchor must not leave a
        # stray .orig behind (it did, once, during the review of 1935dc1).
        assert sites >= 1, (name, "anchor not found")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        backup = path.with_suffix(path.suffix + ".orig")
        shutil.copy2(path, backup)
        path.write_text(source.replace(old, new))
        try:
            out = _pytest(test_file)
        finally:
            shutil.copy2(backup, path)
            backup.unlink()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, "not restored"
        failed = sorted(set(re.findall(r"^FAILED \S+::(\S+)", out, re.M)))
        causes = sorted(set(_cause(l) for l in out.splitlines()
                            if re.match(r"^/.*:\d+: ", l) or l.startswith("E   ")))
        print(f"== {name} [{rel}, {sites} site(s)]  restored: sha256 {digest[:16]} identical")
        print("   " + out.strip().splitlines()[-1])
        for f in failed:
            print("   FAILED", f)
        for c in causes[:6]:
            print("   cause:", c)
        if not failed:
            survivors.append(name)
        sys.stdout.flush()
    print()
    print("SURVIVING MUTATIONS:", ", ".join(survivors) if survivors else "none")
    return survivors
