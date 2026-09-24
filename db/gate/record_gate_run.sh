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
#     false: the gate READS docs/handoff and docs/api.
#   * Replacing that with a hand-written prefix list did not go far enough. The
#     list was taken from the paths written literally in run_gate.sh, so it
#     could not see what the scripts run_gate.sh INVOKES read: step 7 calls
#     generate_effective_contract.py, which reads
#     docs/contract/CONTRACT_CORRECTIONS.yaml. That file was labelled "[other]
#     cannot affect this run" while a comment-only edit to it flipped the
#     contract check from PASS to FAIL. Classification is now DERIVED by
#     walking the call chain (db/gate/gate_inputs.py), so this script no longer
#     makes a claim about other scripts that can drift from them.
#   * Even the derived label overclaimed. "[other] ... cannot affect this run"
#     is a guarantee the derivation cannot give: it is a TEXTUAL scan, and a
#     path assembled at run time (joined from parts, read from an environment
#     variable) is invisible to it. [other] now says only what is known — not
#     found by the scan — and says that this is not a proof.
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

# Derived, not declared: gate_inputs.py follows run_gate.sh into the scripts it
# invokes and reports what any of them reads. Nothing here to keep in sync.
classify() {
  $PY db/gate/gate_inputs.py --classify "$1"
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
    echo "                [other]      NOT FOUND by the textual scan of the"
    echo "                             gate's call chain. This is not a proof"
    echo "                             that the gate does not read it: a path"
    echo "                             assembled at run time is invisible to"
    echo "                             the scan (gate_inputs.py, 'Limits')"
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
  echo "The gate output below is deterministic, but not of the frozen package"
  echo "alone: it is a function of every file the gate reads — the frozen"
  echo "package, the corrections and approved addenda under docs/contract, the"
  echo "Contract Deltas under docs/gate each addendum is bound to by sha256, and"
  echo "the policy code under src/turab/auth that step 7 compares against. Those"
  echo "inputs unchanged, the body is identical. The header is what binds this"
  echo "run to a tree; compare the fingerprint and the labels above, not the body."
  echo
  echo "Gate inputs, as derived by db/gate/gate_inputs.py from the call chain:"
  $PY db/gate/gate_inputs.py | sed 's/^/                /'
  echo "-------------------------------------------------------"
  echo
} > "$OUT"

db/gate/run_gate.sh >> "$OUT" 2>&1
STATUS=$?
echo "" >> "$OUT"
echo "gate exit status: ${STATUS}" >> "$OUT"
exit $STATUS
