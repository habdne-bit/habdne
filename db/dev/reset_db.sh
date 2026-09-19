#!/usr/bin/env bash
# =============================================================================
# TURAB — development database reset
# Ref: IMPLEMENTATION_SLICES_v0.2.md, Slice -1 ("migration reset script for
#      development").
#
# Drops and rebuilds the development database from the FROZEN baseline, then
# optionally loads developer fixtures. Never use against a shared database.
#
# Usage:
#   db/dev/reset_db.sh              # schema + master seed
#   db/dev/reset_db.sh --fixtures   # schema + master seed + dev fixtures
# Env:
#   PGDATABASE (default turab_dev), plus standard PG* variables.
# =============================================================================
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DB_DIR="$REPO_ROOT/docs/handoff/04_DATABASE"
: "${PGDATABASE:=turab_dev}"
export PGDATABASE

WITH_FIXTURES=0
[[ "${1:-}" == "--fixtures" ]] && WITH_FIXTURES=1

case "$PGDATABASE" in
  *prod*|*production*|*staging*)
    echo "refusing to reset '$PGDATABASE': name looks non-development" >&2
    exit 2 ;;
esac

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

step "Dropping and recreating $PGDATABASE"
dropdb --if-exists "$PGDATABASE"
createdb "$PGDATABASE"

step "Applying frozen baseline"
psql -v ON_ERROR_STOP=1 -q -f "$DB_DIR/schema_v0.2.3.sql"
psql -v ON_ERROR_STOP=1 -q -f "$DB_DIR/seed_master_data_v0.2.3.sql"

# R14.4: the frozen schema IS the initial migration, so the database is
# STAMPED at that revision rather than migrated up to it. Without this the
# database carries no alembic_version, and the next `alembic upgrade head`
# would try to apply the baseline again on top of itself and fail.
step "Stamping the initial Alembic revision"
if [[ -x "$REPO_ROOT/.venv/bin/alembic" ]]; then
  ALEMBIC="$REPO_ROOT/.venv/bin/alembic"
else
  ALEMBIC="alembic"
fi
# Built from the same PG* variables psql just used, so the stamp cannot land
# on a different database than the schema did. PGPORT is included: omitting it
# would let a non-default port succeed for psql and silently fail here.
STAMP_URL="${TURAB_DATABASE_URL:-postgresql+psycopg://${PGUSER:-$USER}@${PGHOST:-/var/run/postgresql}:${PGPORT:-5432}/$PGDATABASE}"
( cd "$REPO_ROOT" && TURAB_DATABASE_URL="$STAMP_URL" "$ALEMBIC" stamp head )

if [[ $WITH_FIXTURES -eq 1 ]]; then
  step "Loading development fixtures"
  psql -v ON_ERROR_STOP=1 -q -f "$REPO_ROOT/db/fixtures/dev_fixtures.sql"
fi

step "Ready"
psql -tAc "SELECT 'schema_version=' || value FROM turab.schema_metadata WHERE key='schema_version'"
psql -tAc "SELECT 'locations=' || count(*) FROM turab.locations"
[[ $WITH_FIXTURES -eq 1 ]] && psql -tAc "SELECT 'parties=' || count(*) FROM turab.parties"
printf '\n\033[1;32m%s reset from the frozen baseline\033[0m\n' "$PGDATABASE"
