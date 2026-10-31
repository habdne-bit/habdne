"""TURAB — Slice 8, plan revision 4: the draft of 0009 through Alembic; the clock; Q-B1.

Authorized in the review of 0a78e91: the draft gains its revision metadata
and is tested "through Alembic on a temporary database, the downgrade
refused with data included"; the clock rule bounded precisely; the case of
a CONVERTED lead measured before "links may become NULL" is restricted. No
implementation code; nothing written under db/migrations/. Kept beside its
output (`SLICE8-PLAN-MEASUREMENTS-R4.txt`), under docs/, outside the
fingerprinted trees.

    PGHOST=127.0.0.1 PGUSER=turab PGPASSWORD=turab \
      .venv/bin/python docs/gate/evidence/SLICE8-PLAN-MEASUREMENTS-R4.py

What it does, and only this:
- M12: rebuilds the scratch database `turab_s8_probe` (db/dev/reset_db.sh
  --fixtures: the baseline stamped, 0002-0008 applied by Alembic), then runs
  Alembic itself, with `version_locations` = db/migrations/versions plus a
  temporary directory holding ONLY the draft, copied as
  `0009_external_lead_workflow.py`. Upgrade to head; the downgrade refused
  with an attempt recorded; then a fresh database: upgrade, downgrade, upgrade.
- M13: the clock rule, an explicit `recorded_at` in an INSERT.
- M14: a CONVERTED lead's links; what a party's deletion leaves of a lead.
The scratch database is dropped at the end; the temporary directory is
removed by the context manager.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[3]
DRAFT = ROOT / "docs/gate/drafts/0009_external_lead_workflow.DRAFT.py"
DB = "turab_s8_probe"
HOST = os.environ.get("PGHOST", "127.0.0.1")
USER = os.environ.get("PGUSER", "turab")
PASSWORD = os.environ.get("PGPASSWORD", "turab")
URL = f"postgresql+psycopg://{USER}:{PASSWORD}@{HOST}:5432/{DB}"
OPERATOR = "f3000000-0000-4000-8000-000000000002"   # tests/conftest.py, dev fixtures
OBJECTS = ("SELECT to_regclass('turab.external_lead_contact_attempts')::text, "
           "(SELECT count(*) FROM turab.reason_codes WHERE code LIKE 'LEAD\\_%'), "
           "(SELECT count(*) FROM pg_trigger WHERE tgname IN ('trg_external_lead_transition', "
           "'trg_lead_attempt_insert', 'trg_lead_attempt_immutable', "
           "'audit_external_lead_contact_attempts'))")


def out(line: str = "") -> None:
    print(line, flush=True)


def env() -> dict:
    e = {**os.environ, "PGDATABASE": DB, "PGHOST": HOST, "PGUSER": USER, "PGPASSWORD": PASSWORD,
         "TURAB_DATABASE_URL": URL}
    e.pop("PGHOSTADDR", None)
    return e


def rebuild() -> None:
    built = subprocess.run([str(ROOT / "db/dev/reset_db.sh"), "--fixtures"], env=env(),
                           capture_output=True, text=True)
    if built.returncode:
        raise SystemExit(built.stdout[-2000:] + built.stderr[-2000:])


def connect() -> psycopg.Connection:
    conn = psycopg.connect(f"host={HOST} hostaddr='' port=5432 user={USER} "
                           f"password={PASSWORD} dbname={DB}", autocommit=True)
    conn.execute("SET search_path TO turab, public")
    return conn


def version(conn) -> str:
    return conn.execute("SELECT version_num FROM public.alembic_version").fetchone()[0]


def alembic(extra: str):
    from alembic.config import Config

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "db/migrations"))
    cfg.set_main_option("version_locations",
                        f"{ROOT / 'db/migrations/versions'}{os.pathsep}{extra}")
    return cfg


def run(label, fn) -> str:
    try:
        fn()
        return "DONE"
    except Exception as exc:  # the database's refusal, as Alembic raises it
        cause = getattr(exc, "orig", None) or exc
        diag = getattr(cause, "diag", None)
        message = (diag.message_primary if diag else str(cause)).strip().splitlines()[0]
        return f"REFUSED: {message}"


def m12() -> None:
    from alembic import command
    from alembic.script import ScriptDirectory

    os.environ["TURAB_DATABASE_URL"] = URL
    out("M12 The draft as an Alembic revision, in the real chain")
    with tempfile.TemporaryDirectory() as extra:
        shutil.copy(DRAFT, Path(extra) / "0009_external_lead_workflow.py")
        cfg = alembic(extra)
        script = ScriptDirectory.from_config(cfg)
        heads = script.get_heads()
        rev = script.get_revision("0009_external_lead_workflow")
        out(f"    heads: {heads}; 0009's down_revision: {rev.down_revision}")
        rebuild()
        conn = connect()
        out(f"    the scratch database before: {version(conn)}")
        out(f"    alembic upgrade head: {run('up', lambda: command.upgrade(cfg, 'head'))}; "
            f"now {version(conn)}")
        source = conn.execute("INSERT INTO sources (kind) VALUES ('OTHER') RETURNING source_id"
                              ).fetchone()[0]
        lead = conn.execute("INSERT INTO external_leads (lead_kind, source_id) VALUES "
                            "('REQUEST', %s) RETURNING external_lead_id", (source,)).fetchone()[0]
        conn.execute("INSERT INTO external_lead_contact_attempts (external_lead_id, channel, "
                     "outcome_code, occurred_at, operator_account_id) VALUES "
                     "(%s, 'PHONE', 'LEAD_NO_ANSWER', now(), %s)", (lead, OPERATOR))
        out("    one attempt recorded; alembic downgrade -1: "
            f"{run('down', lambda: command.downgrade(cfg, '-1'))}; now {version(conn)}")
        out(f"    after the refused downgrade: {conn.execute(OBJECTS).fetchone()}")
        conn.close()
        rebuild()
        conn = connect()
        out(f"    a fresh database: {version(conn)}")
        out(f"    alembic upgrade head: {run('up', lambda: command.upgrade(cfg, 'head'))}; "
            f"now {version(conn)}; objects {conn.execute(OBJECTS).fetchone()}")
        out(f"    alembic downgrade -1: {run('down', lambda: command.downgrade(cfg, '-1'))}; "
            f"now {version(conn)}; objects {conn.execute(OBJECTS).fetchone()}")
        out(f"    alembic upgrade head: {run('up', lambda: command.upgrade(cfg, 'head'))}; "
            f"now {version(conn)}; objects {conn.execute(OBJECTS).fetchone()}")
        conn.close()
    out()


def m13(conn) -> None:
    out("M13 The clock rule: recorded_at assigned by the server")
    with conn.transaction(force_rollback=True):
        source = conn.execute("INSERT INTO sources (kind) VALUES ('OTHER') RETURNING source_id"
                              ).fetchone()[0]
        lead = conn.execute("INSERT INTO external_leads (lead_kind, source_id) VALUES "
                            "('REQUEST', %s) RETURNING external_lead_id", (source,)).fetchone()[0]
        ins = ("INSERT INTO external_lead_contact_attempts (external_lead_id, channel, "
               "outcome_code, occurred_at, operator_account_id, recorded_at) VALUES "
               "(%s, 'PHONE', 'LEAD_NO_ANSWER', {}, %s, {}) RETURNING recorded_at")
        try:
            with conn.transaction():
                conn.execute(ins.format("now() + interval '1 day'", "'2099-01-01'"),
                             (lead, OPERATOR))
            out("    occurred_at tomorrow, recorded_at given as 2099-01-01: ACCEPTED")
        except psycopg.Error as exc:
            out("    occurred_at tomorrow, recorded_at given as 2099-01-01: REFUSED "
                f"{exc.sqlstate}: {(exc.diag.message_primary or '').strip()}")
        stored = conn.execute(ins.format("now()", "'2000-01-01'"), (lead, OPERATOR)).fetchone()[0]
        out(f"    occurred_at now(), recorded_at given as 2000-01-01: ACCEPTED; recorded_at "
            f"stored is the server's clock: {stored.year != 2000}")
    out("    (rolled back)")
    out()


def m14(conn) -> None:
    out("M14 A CONVERTED lead's links; what a party's deletion leaves")
    with conn.transaction(force_rollback=True):
        party = conn.execute("INSERT INTO parties (kind) VALUES ('PERSON') RETURNING party_id"
                             ).fetchone()[0]
        request = conn.execute("INSERT INTO requests (party_id, management_mode, claim_status) "
                               "VALUES (%s, 'ASSISTED', 'UNCLAIMED') RETURNING request_id",
                               (party,)).fetchone()[0]
        source = conn.execute("INSERT INTO sources (kind, raw_text) VALUES ('OTHER', "
                              "'synthetic raw text M14') RETURNING source_id").fetchone()[0]
        lead = conn.execute(
            "INSERT INTO external_leads (lead_kind, source_id, status, party_id, "
            "converted_request_id, raw_payload) VALUES ('REQUEST', %s, 'CONVERTED', %s, %s, "
            "'{\"m\": \"synthetic payload M14\"}') RETURNING external_lead_id",
            (source, party, request)).fetchone()[0]

        def attempt(label, sql, params):
            try:
                with conn.transaction():
                    conn.execute(sql, params)
                out(f"    {label}: ACCEPTED")
            except psycopg.Error as exc:
                constraint = exc.diag.constraint_name
                out(f"    {label}: REFUSED {exc.sqlstate}"
                    + (f" constraint={constraint}" if constraint else "")
                    + f": {(exc.diag.message_primary or '').strip()}")

        attempt("the CONVERTED lead's converted_request_id set to NULL",
                "UPDATE external_leads SET converted_request_id = NULL "
                "WHERE external_lead_id = %s", (lead,))
        attempt("DELETE of its converted request", "DELETE FROM requests WHERE request_id = %s",
                (request,))
        attempt("DELETE of its party (the converted request's party too)",
                "DELETE FROM parties WHERE party_id = %s", (party,))
        other = conn.execute("INSERT INTO parties (kind) VALUES ('PERSON') RETURNING party_id"
                             ).fetchone()[0]
        declined = conn.execute(
            "INSERT INTO external_leads (lead_kind, source_id, status, party_id, "
            "close_reason_code, raw_payload) VALUES ('REQUEST', %s, 'DECLINED', %s, "
            "'LEAD_DUPLICATE', '{\"m\": \"synthetic payload M14\"}') RETURNING external_lead_id",
            (source, other)).fetchone()[0]
        attempt("DELETE of a DECLINED lead's party", "DELETE FROM parties WHERE party_id = %s",
                (other,))
        row = conn.execute("SELECT party_id, raw_payload->>'m' FROM external_leads "
                           "WHERE external_lead_id = %s", (declined,)).fetchone()
        text = conn.execute("SELECT raw_text FROM sources WHERE source_id = %s",
                            (source,)).fetchone()[0]
        out(f"    after it: the lead's party_id {'NULL' if row[0] is None else 'kept'}; its "
            f"raw_payload kept: {row[1] == 'synthetic payload M14'}; its source's raw_text "
            f"kept: {text == 'synthetic raw text M14'}")
    out("    (rolled back)")
    out()


def main() -> int:
    logging.disable(logging.CRITICAL)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                          text=True).stdout.strip()
    clean = not subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True,
                               text=True).stdout.strip()
    out(f"Tree    : {head}; working tree {'CLEAN' if clean else 'NOT CLEAN'} at the start")
    out(f"Draft   : {DRAFT.relative_to(ROOT)}")
    out()
    try:
        m12()
        conn = connect()
        out(f"Database: {DB} at {version(conn)}, after M12's last upgrade; PostgreSQL "
            f"{conn.execute('SHOW server_version').fetchone()[0]}")
        out()
        m13(conn)
        m14(conn)
        conn.close()
    finally:
        subprocess.run(["dropdb", "--if-exists", DB], env=env(), check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
