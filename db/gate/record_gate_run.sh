#!/usr/bin/env bash
# Run the execution gate and bind its output to the tree it ran against.
#
# The gate's own output carries no timestamp and no commit: it is a
# deterministic function of the frozen package, so two runs of an unchanged
# package produce byte-identical logs. That is a virtue for reproducibility and
# a defect for evidence — a reviewer found that a gate log shipped as proof for
# one commit was byte-identical to the previous bundle's, and could therefore
# not show it had been run at all for that commit.
#
# This wrapper writes a header naming WHEN it ran, WHICH commit the working
# tree was at, whether that tree was clean, and the source fingerprint. The
# body below the header is the gate's unmodified output.
set -euo pipefail
cd "$(dirname "$0")/.."/..

OUT="${1:-docs/gate/evidence/gate-run.txt}"
PY="${PY:-.venv/bin/python}"

COMMIT="$(git rev-parse HEAD)"
DIRTY="$(git status --porcelain | wc -l)"
FINGERPRINT="$($PY db/dev/source_fingerprint.py .)"

{
  echo "TURAB — PostgreSQL execution gate, recorded AT RUN TIME"
  echo "======================================================="
  echo "Recorded    : $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
  echo "Commit      : ${COMMIT}"
  if [ "$DIRTY" -eq 0 ]; then
    echo "Working tree: clean"
  else
    # A bare count is not reviewable: "3 uncommitted changes" leaves a reader
    # unable to tell a stray source edit from the evidence file this very run
    # is writing. The paths are listed, and each is marked according to whether
    # the source fingerprint covers it — because only those can change what the
    # gate actually exercised.
    echo "Working tree: ${DIRTY} uncommitted path(s); [src] means the source"
    echo "              fingerprint covers it, [doc] means it cannot affect"
    echo "              what ran:"
    git status --porcelain | while read -r _ path; do
      case "$path" in
        src/*|tests/*|db/*|alembic.ini) echo "                [src] $path" ;;
        *)                              echo "                [doc] $path" ;;
      esac
    done
  fi
  echo "Source fingerprint (db/dev/source_fingerprint.py):"
  echo "              ${FINGERPRINT}"
  echo "Server      : $(PGPASSWORD=${PGPASSWORD:-turab} psql -h "${PGHOST:-127.0.0.1}" \
                        -U "${PGUSER:-turab}" -tAc 'SHOW server_version' postgres 2>/dev/null \
                        | sed 's/^ *//;s/ *$//')"
  echo
  echo "The gate output below is deterministic: it is a function of the frozen"
  echo "package, so an unchanged package yields an identical body. The header"
  echo "is what binds this run to a tree; compare the fingerprint, not the body."
  echo "-------------------------------------------------------"
  echo
} > "$OUT"

db/gate/run_gate.sh >> "$OUT" 2>&1
STATUS=$?
echo "" >> "$OUT"
echo "gate exit status: ${STATUS}" >> "$OUT"
exit $STATUS
