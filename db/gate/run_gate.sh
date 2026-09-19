#!/usr/bin/env bash
# =============================================================================
# TURAB — PostgreSQL Execution Gate runner
# Ref: docs/handoff/04_DATABASE/POSTGRES_EXECUTION_GATE.md
#
# Rebuilds a clean database from zero, applies the schema, applies the seed
# TWICE (idempotency), then runs the database-level contract tests.
# A failure at any step is a release blocker.
#
# Usage: db/gate/run_gate.sh
# Env:   PGDATABASE (default turab_contract_test), plus standard PG* vars.
# =============================================================================
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DB_DIR="$REPO_ROOT/docs/handoff/04_DATABASE"
GATE_DIR="$REPO_ROOT/db/gate"
QA_DIR="$REPO_ROOT/docs/handoff/07_QA_ACCEPTANCE"
API_DIR="$REPO_ROOT/docs/handoff/05_API"
: "${PGDATABASE:=turab_contract_test}"
export PGDATABASE

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

step "0/6  Handoff package integrity"
( cd "$REPO_ROOT/docs/handoff" && python3 verify_handoff.py )

step "1/6  Static audit of the technical pack"
( cd "$QA_DIR" && python3 technical_pack_static_audit_v0.2.2.py )

step "2/6  Rebuild a clean database from zero"
dropdb --if-exists "$PGDATABASE"
createdb "$PGDATABASE"
psql -tAc 'SHOW server_version'

step "3/6  Apply schema_v0.2.2.sql"
psql -v ON_ERROR_STOP=1 -q -f "$DB_DIR/schema_v0.2.2.sql"

step "4/6  Apply seed_master_data_v0.2.2.sql twice (idempotency)"
psql -v ON_ERROR_STOP=1 -q -f "$DB_DIR/seed_master_data_v0.2.2.sql"
psql -v ON_ERROR_STOP=1 -q -f "$DB_DIR/seed_master_data_v0.2.2.sql"

step "5/6  Database-level contract tests"
psql -v ON_ERROR_STOP=1 -q -f "$GATE_DIR/postgres_execution_gate_tests.sql"

step "6/6  OpenAPI parse / lint"
python3 "$GATE_DIR/lint_openapi.py" "$API_DIR/openapi_v0.2.2.yaml"

printf '\n\033[1;32mPOSTGRES EXECUTION GATE: PASS\033[0m\n'
