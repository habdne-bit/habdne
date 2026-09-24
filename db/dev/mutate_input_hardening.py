"""Step 5 input hardening: which mechanism refuses which hostile input.

Applies each mutation below to the PRODUCTION code, one at a time, runs the
shipped `tests/test_input_hardening.py`, records the failing tests and the
CAUSE each failure reports (the test client raises server exceptions, so a
500 surfaces as its exception), restores the file, and checks its sha256 is
identical to what it was.

    .venv/bin/python db/dev/mutate_input_hardening.py [M1 M2 ...] > evidence.txt

Needs the test database, as pytest does (`TURAB_TEST_DB`, `PGHOST`, `PGUSER`,
`PGPASSWORD`; tests/conftest.py). Run it on
a clean tree: the header binds the output to the commit and the source
fingerprint it ran on.
"""
import datetime, hashlib, pathlib, re, shutil, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
M = [
 ("M1 unknown attribute_code echoed", "src/turab/services/truth.py",
  'raise Invalid("attribute_code is not a registered attribute")',
  'raise Invalid(f"attribute_code {attribute_code!r} is not a registered attribute")'),
 ("M2 ENUM value echoed", "src/turab/services/truth.py",
  'raise Invalid("the value is not a registered, active option of "',
  'raise Invalid(f"{value!r} is not a registered, active option of "'),
 ("M3 resolution reason echoed", "src/turab/services/truth.py",
  'raise Invalid("resolution_reason_code is not a known reason code")',
  'raise Invalid(f"{resolution_reason_code!r} is not a known reason code")'),
 ("M4 offer reason echoed", "src/turab/services/offers.py",
  '"reason_code is not an active reason code",', 'f"{code!r} is not an active reason code",'),
 ("M5 relation reason echoed", "src/turab/services/relations.py",
  '"reason_code is not an active reason code")', 'f"{code!r} is not an active reason code")'),
 ("M6 criterion code echoed", "src/turab/services/requests.py",
  '"criterion_code is not a criterion in the master registry; "',
  'f"{code!r} is not a criterion in the master registry; "'),
 ("M7 closure reason echoed", "src/turab/services/requests.py",
  '"close_reason_code is not a REQUEST_CLOSURE reason; the adopted codes are "',
  'f"{code!r} is not a REQUEST_CLOSURE reason; the adopted codes are "'),
 ("M8 JsonNumber finite check removed", "src/turab/api/json_types.py",
  'if isinstance(value, float) and not math.isfinite(value):\n        raise ValueError("must be a finite JSON number")',
  'if False:\n        pass'),
 ("M9 FiniteJson walk removed", "src/turab/api/json_types.py",
  '    pending = [value]\n', '    return value\n    pending = [value]\n'),
 ("M10 offer bigint bound removed", "src/turab/api/routes/offers.py",
  'le=BIGINT_MAX', 'le=None'),
 ("M11 request bigint bound removed", "src/turab/api/routes/requests.py",
  'ge=0, le=BIGINT_MAX', 'ge=0'),
 ("M12 sort_order smallint bound removed", "src/turab/api/routes/requests.py",
  'Field(default=100, ge=SMALLINT_MIN, le=SMALLINT_MAX)', 'Field(default=100)'),
 ("M13 area upper end back to le=9999999999.99 (review of 3010cb9)", "src/turab/api/json_types.py",
  '_AREA_LOWEST <= as_bound_to_numeric(value) < _AREA_BEYOND',
  '_AREA_LOWEST <= as_bound_to_numeric(value) <= Decimal("9999999999.99")'),
 ("M14 area upper end widened past the column", "src/turab/api/json_types.py",
  '_AREA_BEYOND = Decimal("9999999999.995")', '_AREA_BEYOND = Decimal("10000000000.005")'),
 ("M15 area lower end back to gt=0", "src/turab/api/json_types.py",
  '_AREA_LOWEST <= as_bound_to_numeric(value)', 'Decimal(0) < as_bound_to_numeric(value)'),
 ("M16 area rule reads repr() instead of 15 significant digits", "src/turab/api/json_types.py",
  'format(value, ".15g")', 'repr(value)'),
]
only = sys.argv[1:]


def _run(*argv):
    return subprocess.run(argv, cwd=ROOT, capture_output=True, text=True).stdout.strip()


dirty = _run("git", "status", "--porcelain")
print("TURAB — step 5: which mechanism refuses which hostile input")
print("=" * 60)
print("Base commit       :", _run("git", "rev-parse", "HEAD"))
print("Source fingerprint:", _run(str(ROOT / ".venv/bin/python"), "db/dev/source_fingerprint.py", "."))
print("Working tree      :", "CLEAN" if not dirty else "DIRTY\n" + dirty)
print("Recorded          :", datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
print()
base = subprocess.run([str(ROOT/".venv/bin/python"), "-m", "pytest", "tests/test_input_hardening.py",
                       "-q", "-p", "no:cacheprovider"], cwd=ROOT, capture_output=True, text=True)
print("=== baseline (no mutation) ===\n   " + base.stdout.strip().splitlines()[-1])
for name, rel, old, new in M:
    if only and name.split()[0] not in only: continue
    path = ROOT / rel; backup = path.with_suffix(".py.orig")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    shutil.copy2(path, backup)
    s = path.read_text(); n = s.count(old)
    assert n >= 1, (name, "anchor not found")
    path.write_text(s.replace(old, new))
    try:
        r = subprocess.run([str(ROOT/".venv/bin/python"), "-m", "pytest",
                            "tests/test_input_hardening.py", "-q", "-p", "no:cacheprovider",
                            "--tb=line", "-rf"], cwd=ROOT, capture_output=True, text=True)
    finally:
        shutil.copy2(backup, path); backup.unlink()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, "not restored"
    out = r.stdout
    failed = sorted(set(re.findall(r"^FAILED tests/test_input_hardening.py::(\S+)", out, re.M)))
    def _cause(line):
        # A refused body carries a per-request trace_id; its field message is
        # the cause, so that is what is kept.
        field = re.search(r'"status":(\d+).*?"message":"([^"]+)"', line)
        if field:
            return f"HTTP {field.group(1)} field error: {field.group(2)}"
        return re.sub(r"^/\S+:\d+: ", "", line)[:170]

    causes = sorted(set(_cause(l) for l in out.splitlines()
                        if re.match(r"^/.*:\d+: ", l) or l.startswith("E   ")))
    summary = out.strip().splitlines()[-1]
    print(f"== {name} [{rel}, {n} site(s)]  restored: sha256 {digest[:16]} identical\n   {summary}")
    for f in failed: print("   FAILED", f)
    for c in causes[:6]: print("   cause:", c)
    sys.stdout.flush()
