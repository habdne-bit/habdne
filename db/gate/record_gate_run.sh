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
# tree was at, what was uncommitted, and the source fingerprint. The body below
# the header is the gate's unmodified output.
#
# Two defects in earlier versions of this header, both found in review:
#
#   * It counted the uncommitted paths BEFORE creating the output file and
#     listed them AFTER, so the count and the list disagreed — "2 paths" above
#     a list of three. There is now ONE snapshot, taken before anything is
#     written, and both the count and the list come from it.
#   * It marked every non-source path "[doc] cannot affect what ran", which is
#     false: the gate READS docs/handoff and docs/api. The labels below say
#     what is actually true of each path.
set -euo pipefail
cd "$(dirname "$0")/.."/..

OUT="${1:-docs/gate/evidence/gate-run.txt}"
PY="${PY:-.venv/bin/python}"

COMMIT="$(git rev-parse HEAD)"
FINGERPRINT="$($PY db/dev/source_fingerprint.py .)"

# ONE snapshot, taken before this script writes anything, so the count and the
# list below can never disagree. $OUT is written afterwards and is therefore
# not in it — stated in the header rather than left for a reader to work out.
SNAPSHOT="$(git status --porcelain || true)"
DIRTY="$(printf '%s' "$SNAPSHOT" | grep -c . || true)"

# Paths the gate actually READS, from run_gate.sh itself: the frozen handoff
# package, the effective contract, and its own scripts. A change under one of
# these can change the gate's result; `check_gate_inputs_are_current` in the
# test suite fails if this list drifts from what the script references.
classify() {
  case "$1" in
    docs/handoff/*|docs/api/*|db/gate/*) echo "gate-input" ;;
    src/*|tests/*|db/*|alembic.ini)      echo "source" ;;
    *)                                    echo "other" ;;
  esac
}

{
  echo "TURAB — PostgreSQL execution gate, recorded AT RUN TIME"
  echo "======================================================="
  echo "Recorded    : $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
  echo "Commit      : ${COMMIT}"
  if [ "$DIRTY" -eq 0 ]; then
    echo "Working tree: clean when this run started"
  else
    echo "Working tree: ${DIRTY} uncommitted path(s) when this run started."
    echo "              This log therefore describes the WORKING TREE, not the"
    echo "              commit above. Labels:"
    echo "                [gate-input] the gate READS it — a change here can"
    echo "                             change the result below"
    echo "                [source]     the source fingerprint covers it"
    echo "                [other]      neither; it cannot affect this run"
    printf '%s\n' "$SNAPSHOT" | while read -r _ path rest; do
      [ -n "${path:-}" ] || continue
      printf '                [%s] %s\n' "$(classify "$path")" "$path"
    done
    echo "              (the output file this run writes, ${OUT}, is not in"
    echo "              the snapshot: it is created after it was taken)"
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
