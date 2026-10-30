"""TURAB — Slice 8, plan revision 3: the draft of 0009 measured on PostgreSQL.

Authorized in the review of b39ad10 (plan revision 2): a planning revision 3
with "0009's text, its downgrade and the tests of its consequences", and the
consequence for a party's deletion "measured before the text is approved".
No implementation code; no migration applied to the repository. Kept beside
its output (`SLICE8-PLAN-MEASUREMENTS-R3.txt`), under docs/, outside the
fingerprinted trees.

    PGHOST=127.0.0.1 PGUSER=turab PGPASSWORD=turab \
      .venv/bin/python docs/gate/evidence/SLICE8-PLAN-MEASUREMENTS-R3.py

What it does, and only this:
- rebuilds the scratch database `turab_s8_probe` with `db/dev/reset_db.sh
  --fixtures` and drops it at the end;
- reads `UPGRADE`, `DOWNGRADE` and `TRANSITIONS` from the draft
  `docs/gate/drafts/0009_external_lead_workflow.DRAFT.py`: the statements
  measured are the draft's own text;
- M7: the existing rows before the draft (the test's DECLINED row without a
  reason), then the draft applied, the row unchanged;
- M8: every (from, to) pair of the ten statuses against the draft's table;
- M9: the guards one by one; a party's deletion under the draft, under a
  strict variant without the NULL exception, and with no 0009;
- M10: the attempts table: the clock rule, the outcome's category,
  append-only, the audit row;
- M11: the downgrade refused with data, then run on a database without data,
  and the upgrade applied again.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[3]
DRAFT = ROOT / "docs/gate/drafts/0009_external_lead_workflow.DRAFT.py"
DB = "turab_s8_probe"
HOST = os.environ.get("PGHOST", "127.0.0.1")
USER = os.environ.get("PGUSER", "turab")
PASSWORD = os.environ.get("PGPASSWORD", "turab")
OPERATOR = "f3000000-0000-4000-8000-000000000002"   # tests/conftest.py, dev fixtures
STATUSES = ("DISCOVERED", "CONTACT_ATTEMPTED", "CONTACTED", "CONSENT_PENDING", "CONSENTED",
            "PENDING_INFO", "CONVERTED", "DECLINED", "UNREACHABLE", "CLOSED")


def load_draft():
    spec = importlib.util.spec_from_file_location("draft_0009", DRAFT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def out(line: str = "") -> None:
    print(line, flush=True)


def connect() -> psycopg.Connection:
    conn = psycopg.connect(f"host={HOST} hostaddr='' port=5432 user={USER} "
                           f"password={PASSWORD} dbname={DB}")
    conn.execute("SET search_path TO turab, public")
    return conn


def error(exc: psycopg.Error) -> str:
    return f"REFUSED {exc.sqlstate}: {(exc.diag.message_primary or '').strip()}"


def attempt(conn, sql, params=None) -> str:
    try:
        with conn.transaction():
            conn.execute(sql, params or {})
        return "ACCEPTED"
    except psycopg.Error as exc:
        return error(exc)


def apply(conn, statements) -> str:
    try:
        with conn.transaction():
            for statement in statements:
                conn.execute(statement)
        return "APPLIED"
    except psycopg.Error as exc:
        return error(exc)


def source(conn) -> str:
    return str(conn.execute("INSERT INTO sources (kind) VALUES ('OTHER') RETURNING source_id"
                            ).fetchone()[0])


def party(conn) -> str:
    return str(conn.execute("INSERT INTO parties (kind) VALUES ('PERSON') RETURNING party_id"
                            ).fetchone()[0])


def request(conn, party_id) -> str:
    return str(conn.execute("INSERT INTO requests (party_id, management_mode, claim_status) "
                            "VALUES (%s, 'ASSISTED', 'UNCLAIMED') RETURNING request_id",
                            (party_id,)).fetchone()[0])


def lead(conn, status, *, party_id=None, reason=None, request_id=None) -> str:
    """A lead INSERTED directly in `status`: INSERT is not guarded."""
    return str(conn.execute(
        "INSERT INTO external_leads (lead_kind, source_id, status, party_id, close_reason_code, "
        "converted_request_id) VALUES ('REQUEST', %s, %s, %s, %s, %s) RETURNING external_lead_id",
        (source(conn), status, party_id, reason, request_id)).fetchone()[0])


def columns_for(conn, target, party_id, request_id):
    """The columns a move to `target` needs under the draft's guards."""
    sets = {"status": target}
    if target in ("CONSENTED", "PENDING_INFO", "CONVERTED"):
        sets["party_id"] = party_id
    if target in ("DECLINED", "CLOSED"):
        sets["close_reason_code"] = "LEAD_DUPLICATE"
    if target == "CONVERTED":
        sets["converted_request_id"] = request_id
    return sets


def m7(conn, draft) -> None:
    out("M7  Existing rows, then the draft applied")
    with conn.transaction():
        row = lead(conn, "DECLINED")   # as the queue test leaves one: no reason code
    out(f"    a DECLINED lead without a reason code exists: {row is not None}")
    out(f"    the draft's UPGRADE: {apply(conn, draft.UPGRADE)}")
    status, reason = conn.execute("SELECT status::text, close_reason_code FROM external_leads "
                                  "WHERE external_lead_id = %s", (row,)).fetchone()
    out(f"    that row after the upgrade: status {status}, reason {reason} (unchanged)")
    out("    the queue test's own statement on a new DISCOVERED lead, after the upgrade:")
    with conn.transaction(force_rollback=True):
        fresh = lead(conn, "DISCOVERED")
        out("      UPDATE ... SET status = 'DECLINED' (no reason): "
            + attempt(conn, "UPDATE external_leads SET status = 'DECLINED' "
                            "WHERE external_lead_id = %s", (fresh,)))
        out("      the same with close_reason_code = 'LEAD_DUPLICATE': "
            + attempt(conn, "UPDATE external_leads SET status = 'DECLINED', "
                            "close_reason_code = 'LEAD_DUPLICATE' WHERE external_lead_id = %s",
                      (fresh,)))
    out("      (rolled back)")
    out()


def m8(conn, draft) -> None:
    out("M8  Every (from, to) pair of the ten statuses, against the draft's table")
    allowed = {(a, b) for a, targets in draft.TRANSITIONS.items() for b in targets}
    mismatches, accepted = [], 0
    with conn.transaction(force_rollback=True):
        party_id = party(conn)
        request_id = request(conn, party_id)
        for source_status in STATUSES:
            for target in STATUSES:
                if source_status == target:
                    continue
                kw = {}
                if source_status in ("CONSENTED", "PENDING_INFO"):
                    kw["party_id"] = party_id
                if source_status in ("DECLINED", "CLOSED"):
                    kw["reason"] = "LEAD_DUPLICATE"
                if source_status == "CONVERTED":
                    kw.update(party_id=party_id, request_id=request(conn, party_id))
                with conn.transaction():
                    row = lead(conn, source_status, **kw)
                sets = columns_for(conn, target, party_id,
                                   request(conn, party_id) if target == "CONVERTED" else None)
                sql = ("UPDATE external_leads SET "
                       + ", ".join(f"{k} = %({k})s" for k in sets)
                       + " WHERE external_lead_id = %(id)s")
                result = attempt(conn, sql, {**sets, "id": row})
                ok = result == "ACCEPTED"
                accepted += ok
                if ok != ((source_status, target) in allowed):
                    mismatches.append(f"{source_status} -> {target}: {result}")
    out(f"    pairs tried: {len(STATUSES) * (len(STATUSES) - 1)}; accepted: {accepted}; "
        f"allowed by the draft's table: {len(allowed)}")
    out(f"    mismatches with the table: {mismatches or 'none'}")
    out("    (rolled back)")
    out()


def m9(conn, draft) -> None:
    out("M9  The guards, one by one; a party's deletion")
    with conn.transaction(force_rollback=True):
        p, other = party(conn), party(conn)
        rows = {s: lead(conn, s) for s in ("DISCOVERED", "CONTACTED")}
        upd = "UPDATE external_leads SET {} WHERE external_lead_id = %s"
        out("    DISCOVERED -> DECLINED, a MATCH-category reason code: "
            + attempt(conn, upd.format("status = 'DECLINED', close_reason_code = "
                                       "(SELECT code FROM reason_codes WHERE category = 'MATCH' "
                                       "ORDER BY code LIMIT 1)"), (rows["DISCOVERED"],)))
        out("    a reason code on an open lead: "
            + attempt(conn, upd.format("close_reason_code = 'LEAD_DUPLICATE'"),
                      (rows["DISCOVERED"],)))
        out("    CONTACTED -> CONSENTED without party_id: "
            + attempt(conn, upd.format("status = 'CONSENTED'"), (rows["CONTACTED"],)))
        closed = lead(conn, "DECLINED", party_id=p, reason="LEAD_DUPLICATE")
        out("    a DECLINED lead's reason changed: "
            + attempt(conn, upd.format("close_reason_code = 'LEAD_STALE'"), (closed,)))
        out("    a DECLINED lead's party_id re-pointed to another party: "
            + attempt(conn, upd.format("party_id = %s"), (other, closed)))
        out("    a DECLINED lead's party_id set to NULL by hand: "
            + attempt(conn, upd.format("party_id = NULL"), (closed,)))
    out("    (rolled back)")

    out("    A party's deletion (the frozen key: external_leads.party_id ON DELETE SET NULL):")
    for label in ("the draft (a link may only become NULL)", "a strict variant (no exception)"):
        with conn.transaction(force_rollback=True):
            if label.startswith("a strict"):
                lenient = ("(NEW.party_id IS NOT NULL\n           AND NEW.party_id IS DISTINCT "
                           "FROM OLD.party_id)")
                assert draft.UPGRADE[-2].count(lenient) == 1, "the draft's text changed"
                conn.execute(draft.UPGRADE[-2].replace(
                    "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION").replace(
                    lenient, "NEW.party_id IS DISTINCT FROM OLD.party_id"))
            for status in ("DECLINED", "CONTACTED"):
                p = party(conn)
                row = lead(conn, status, party_id=p,
                           reason="LEAD_DUPLICATE" if status == "DECLINED" else None)
                result = attempt(conn, "DELETE FROM parties WHERE party_id = %s", (p,))
                left = conn.execute("SELECT party_id FROM external_leads WHERE "
                                    "external_lead_id = %s", (row,)).fetchone()[0]
                out(f"      {label}, a {status} lead: delete {result}; "
                    f"lead's party_id now {'NULL' if left is None else 'unchanged'}")
    out()


def m10(conn) -> None:
    out("M10 The attempts table")
    with conn.transaction(force_rollback=True):
        row = lead(conn, "DISCOVERED")
        ins = ("INSERT INTO external_lead_contact_attempts (external_lead_id, channel, "
               "outcome_code, occurred_at, operator_account_id) VALUES (%s, 'PHONE', %s, {}, %s)")
        out("    occurred_at now(): "
            + attempt(conn, ins.format("now()"), (row, "LEAD_NO_ANSWER", OPERATOR)))
        out("    occurred_at one second after the insert's clock: "
            + attempt(conn, ins.format("clock_timestamp() + interval '1 second'"),
                      (row, "LEAD_NO_ANSWER", OPERATOR)))
        out("    outcome LEAD_DUPLICATE (a LEAD_CLOSURE code): "
            + attempt(conn, ins.format("now()"), (row, "LEAD_DUPLICATE", OPERATOR)))
        out("    UPDATE of an attempt: "
            + attempt(conn, "UPDATE external_lead_contact_attempts SET channel = 'SMS'"))
        out("    DELETE of an attempt: "
            + attempt(conn, "DELETE FROM external_lead_contact_attempts"))
        audited = conn.execute(
            "SELECT action, new_row ? 'outcome_code', new_row ? 'operator_account_id' "
            "FROM audit_log WHERE entity_table = 'external_lead_contact_attempts'").fetchall()
        out(f"    audit_log rows for the attempts table: {audited}")
        columns = [r[0] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'turab' "
            "AND table_name = 'external_lead_contact_attempts' ORDER BY ordinal_position")]
        out(f"    its columns (no free text): {columns}")
    out("    (rolled back)")
    out()


def m11(conn, draft) -> None:
    out("M11 The downgrade")
    with conn.transaction(force_rollback=True):
        row = lead(conn, "DISCOVERED")
        conn.execute("INSERT INTO external_lead_contact_attempts (external_lead_id, channel, "
                     "outcome_code, occurred_at, operator_account_id) VALUES "
                     "(%s, 'PHONE', 'LEAD_NO_ANSWER', now(), %s)", (row, OPERATOR))
        out(f"    with one attempt recorded: {apply(conn, draft.DOWNGRADE)}")
    with conn.transaction(force_rollback=True):
        lead(conn, "CLOSED", reason="LEAD_STALE")
        out(f"    with one lead CLOSED by a LEAD_* reason: {apply(conn, draft.DOWNGRADE)}")
    out(f"    with neither: {apply(conn, draft.DOWNGRADE)}")
    left = conn.execute(
        "SELECT to_regclass('turab.external_lead_contact_attempts')::text, "
        "(SELECT count(*) FROM reason_codes WHERE code LIKE 'LEAD\\_%'), "
        "(SELECT count(*) FROM pg_trigger WHERE tgname IN ('trg_external_lead_transition', "
        "'trg_lead_attempt_outcome', 'trg_lead_attempt_immutable', "
        "'audit_external_lead_contact_attempts'))").fetchone()
    out(f"    after it: table {left[0] or 'none'}; LEAD_* codes {left[1]}; triggers {left[2]}")
    out(f"    the upgrade again: {apply(conn, draft.UPGRADE)}")
    out()


def main() -> int:
    draft = load_draft()
    env = {**os.environ, "PGDATABASE": DB, "PGHOST": HOST, "PGUSER": USER,
           "PGPASSWORD": PASSWORD}
    env.pop("PGHOSTADDR", None)
    built = subprocess.run([str(ROOT / "db/dev/reset_db.sh"), "--fixtures"], env=env,
                           capture_output=True, text=True)
    if built.returncode:
        print(built.stdout[-2000:], built.stderr[-2000:], file=sys.stderr)
        return 1
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                          text=True).stdout.strip()
    clean = not subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True,
                               text=True).stdout.strip()
    conn = connect()
    server = conn.execute("SHOW server_version").fetchone()[0]
    out(f"Tree    : {head}; working tree {'CLEAN' if clean else 'NOT CLEAN'} at the start")
    out(f"Database: {DB}, rebuilt by db/dev/reset_db.sh --fixtures; PostgreSQL {server}")
    out(f"Draft   : {DRAFT.relative_to(ROOT)}; {len(draft.UPGRADE)} upgrade and "
        f"{len(draft.DOWNGRADE)} downgrade statements")
    out()
    try:
        out("M9a A party's deletion with no 0009 (the frozen schema alone):")
        with conn.transaction(force_rollback=True):
            p = party(conn)
            row = lead(conn, "DECLINED", party_id=p)
            result = attempt(conn, "DELETE FROM parties WHERE party_id = %s", (p,))
            left = conn.execute("SELECT party_id FROM external_leads WHERE external_lead_id = %s",
                                (row,)).fetchone()[0]
            out(f"    a DECLINED lead: delete {result}; lead's party_id now "
                f"{'NULL' if left is None else 'unchanged'}")
        out()
        m7(conn, draft)
        m8(conn, draft)
        m9(conn, draft)
        m10(conn)
        m11(conn, draft)
    finally:
        conn.close()
        subprocess.run(["dropdb", "--if-exists", DB], env=env, check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
