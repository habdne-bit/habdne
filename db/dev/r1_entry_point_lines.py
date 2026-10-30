"""R-1 step 5: every line `python -m turab_relay` writes, recorded.

    .venv/bin/python db/dev/r1_entry_point_lines.py > docs/gate/evidence/R1-STEP5-PROCESS-LINES.txt

Runs `tests/test_r1_step5.py::test_no_line_the_process_writes_holds_a_request_line_a_query_a_secret_or_content`,
which starts the entry point as a process, sends it the requests its
docstring lists, stops it, checks every line, and, with `R1_STEP5_LINES` set,
writes those lines. This script prints them with the time, the port, the
process id and the trace ids replaced, so the same tree writes the same record.
"""
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEST = ("tests/test_r1_step5.py::"
        "test_no_line_the_process_writes_holds_a_request_line_a_query_a_secret_or_content")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        out = pathlib.Path(tmp) / "lines.txt"
        done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                               TEST], cwd=ROOT, env={**os.environ, "R1_STEP5_LINES": str(out)},
                              capture_output=True, text=True)
        if done.returncode != 0 or not out.exists():
            print(done.stdout[-2000:], file=sys.stderr)
            return 1
        lines = out.read_text().splitlines()
    print("TURAB — R-1 step 5: every line `python -m turab_relay` wrote, through an actual process")
    print(f"Written by db/dev/r1_entry_point_lines.py, from {TEST}")
    print("(which passed: no request line, query, secret, signature, content, TURAB URL or answer).")
    print("Replaced: the time (T), the port (PORT), the process id (PID), trace ids (X).")
    print("The requests, in order: Meta's GET (200); a wrong token (403); a query holding %ff,")
    print("a percent-escape that is not UTF-8 (400, parameters missing); another path with the")
    print("token in its query (404); a signed POST delivered")
    print("to TURAB's double (200); a wrong signature (401); a certificate of the test CA with")
    print("another CN (403); no certificate, and another CA's (refused at the handshake); a")
    print("clear-text request to the TLS port; then SIGTERM.")
    print("-" * 72)
    for line in lines:
        line = re.sub(r"^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:,]+", "T", line)
        line = re.sub(r"127\.0\.0\.1:[0-9]+", "127.0.0.1:PORT", line)
        line = re.sub(r"\[[0-9]+\]", "[PID]", line)
        line = re.sub(r"trace=[0-9a-f]+", "trace=X", line)
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
