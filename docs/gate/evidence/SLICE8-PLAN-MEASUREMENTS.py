"""TURAB — Slice 8: the plan's facts measured on PostgreSQL, before any code.

Authorized in the review of 3922850 (plan revision 1): §6.5's three
measurements, plus the race between revoking an ASSISTED_ENTRY grant and a
conversion, and the rows that exist before any new constraint. No
implementation code; no migration applied. Kept beside its output
(`SLICE8-PLAN-MEASUREMENTS.txt`); placed under docs/, outside the trees the
source fingerprint covers (src/, tests/, db/, relay/), so it changes no
binding.

    PGHOST=127.0.0.1 PGUSER=turab PGPASSWORD=turab \
      .venv/bin/python docs/gate/evidence/SLICE8-PLAN-MEASUREMENTS.py

What it does, and only this:
- rebuilds the scratch database `turab_s8_probe` with `db/dev/reset_db.sh
  --fixtures` (the frozen schema, the seed, the migrations, the dev fixtures),
  and drops it at the end;
- M1: reads the application's statements that write `external_leads`, and the
  scratch database's leads by status;
- M2: two concurrent `interests` inserts for one (party, property);
- M3: `enforce_consent_binding()` on a REQUEST binding of an ASSISTED_ENTRY
  grant, the request's party's, another party's, and a revoked one (rolled
  back);
- M4: a revocation racing a conversion's binding, four ways (committed rows,
  in the scratch database only);
- M5: the rows that exist before any new constraint: the scratch database,
  and the server's other TURAB databases READ ONLY, counts only;
- M6: keyset paging of the leads queue by (discovered_at, id) while a lead
  inserted earlier commits later.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[3]
DB = "turab_s8_probe"
HOST = os.environ.get("PGHOST", "127.0.0.1")
USER = os.environ.get("PGUSER", "turab")
PASSWORD = os.environ.get("PGPASSWORD", "turab")
PAUSE = 1.0


def dsn(db: str = DB) -> str:
    return f"host={HOST} hostaddr='' port=5432 user={USER} password={PASSWORD} dbname={db}"


def out(line: str = "") -> None:
    print(line, flush=True)


def connect(autocommit: bool = False, db: str = DB) -> psycopg.Connection:
    conn = psycopg.connect(dsn(db), autocommit=autocommit)
    conn.execute("SET search_path TO turab, public")
    return conn


def error(exc: psycopg.Error) -> str:
    message = (exc.diag.message_primary or "").strip()
    constraint = f" constraint={exc.diag.constraint_name}" if exc.diag.constraint_name else ""
    return f"REFUSED {exc.sqlstate} {type(exc).__name__}{constraint}: {message}"


def attempt(conn, sql, params=None) -> str:
    try:
        with conn.transaction():
            conn.execute(sql, params or {})
        return "ACCEPTED"
    except psycopg.Error as exc:
        return error(exc)


def new_party(conn) -> str:
    return str(conn.execute("INSERT INTO parties (kind) VALUES ('PERSON') RETURNING party_id")
               .fetchone()[0])


def new_grant(conn, party_id: str, scope: str = "ASSISTED_ENTRY") -> str:
    return str(conn.execute(
        "INSERT INTO consent_grants (party_id, scope, channel, consent_version, granted_at) "
        "VALUES (%s, %s, 'PHONE_CONFIRMED', 'v1', now() - interval '1 minute') "
        "RETURNING consent_id", (party_id, scope)).fetchone()[0])


def new_request(conn, party_id: str) -> str:
    return str(conn.execute(
        "INSERT INTO requests (party_id, management_mode, claim_status) "
        "VALUES (%s, 'ASSISTED', 'UNCLAIMED') RETURNING request_id", (party_id,)).fetchone()[0])


BIND = ("INSERT INTO resource_consent_bindings (consent_id, purpose, request_id) "
        "VALUES (%s, 'ASSISTED_ENTRY', %s)")
REVOKE = ("UPDATE consent_grants SET status = 'REVOKED', "
          "revoked_at = GREATEST(clock_timestamp(), granted_at) WHERE consent_id = %s")


# --- M1 ---------------------------------------------------------------------------------------

def m1(conn) -> None:
    out("M1  Which application statements write external_leads, and the leads by status")
    found = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        text = path.read_text()
        for match in re.finditer(r"(INSERT INTO|UPDATE|DELETE FROM)\s+(turab\.)?external_leads\b",
                                 text):
            line = text[:match.start()].count("\n") + 1
            found.append(f"{path.relative_to(ROOT)}:{line} {match.group(1)}")
    for item in found or ["(none)"]:
        out(f"    {item}")
    rows = conn.execute("SELECT status::text, count(*) FROM external_leads GROUP BY 1 ORDER BY 1"
                        ).fetchall()
    out(f"    scratch database, leads by status: {rows or 'none'}")
    out()


# --- M2 ---------------------------------------------------------------------------------------

def m2() -> None:
    out("M2  Two concurrent ACTIVE interests for one (party, property)")
    setup = connect(autocommit=True)
    party = new_party(setup)
    prop = setup.execute("SELECT property_id FROM properties ORDER BY property_id LIMIT 1"
                         ).fetchone()[0]
    a, b = connect(), connect()
    a.execute("INSERT INTO interests (party_id, property_id) VALUES (%s, %s)", (party, prop))
    result = {}

    def second():
        start = time.monotonic()
        try:
            b.execute("INSERT INTO interests (party_id, property_id) VALUES (%s, %s)",
                      (party, prop))
            b.commit()
            result["b"] = "ACCEPTED"
        except psycopg.Error as exc:
            b.rollback()
            result["b"] = error(exc)
        result["waited"] = time.monotonic() - start

    thread = threading.Thread(target=second)
    thread.start()
    time.sleep(PAUSE)
    out(f"    second insert still waiting while the first is uncommitted: {thread.is_alive()}")
    a.commit()
    thread.join(10)
    out(f"    first: committed; second: {result['b']}")
    out(f"    the second waited for the first's commit: {result['waited'] >= PAUSE}")
    count = setup.execute("SELECT count(*) FROM interests WHERE party_id = %s AND status = 'ACTIVE'",
                          (party,)).fetchone()[0]
    out(f"    ACTIVE rows for the pair: {count}")
    for c in (a, b, setup):
        c.close()
    out()


# --- M3 ---------------------------------------------------------------------------------------

def m3(conn) -> None:
    out("M3  enforce_consent_binding() on a REQUEST binding of an ASSISTED_ENTRY grant")
    with conn.transaction(force_rollback=True):
        party, other = new_party(conn), new_party(conn)
        own, foreign = new_grant(conn, party), new_grant(conn, other)
        revoked = new_grant(conn, party)
        conn.execute(REVOKE, (revoked,))
        request = new_request(conn, party)
        out(f"    the request's party's grant : {attempt(conn, BIND, (own, request))}")
        out(f"    another party's grant       : {attempt(conn, BIND, (foreign, request))}")
        out(f"    a revoked grant             : {attempt(conn, BIND, (revoked, request))}")
        purpose = ("INSERT INTO resource_consent_bindings (consent_id, purpose, request_id) "
                   "VALUES (%s, 'PUBLIC_LISTING_ALLOWED', %s)")
        out(f"    a purpose not the grant's   : {attempt(conn, purpose, (own, request))}")
    out("    (rolled back)")
    out()


# --- M4 ---------------------------------------------------------------------------------------

def _race(label: str, lock: str | None, revoke_first: bool) -> None:
    setup = connect(autocommit=True)
    party = new_party(setup)
    grant = new_grant(setup, party)
    conversion, revocation = connect(), connect()
    result = {}

    def revoke():
        start = time.monotonic()
        revocation.execute(REVOKE, (grant,))
        result["revoke_waited"] = time.monotonic() - start
        if not revoke_first:
            revocation.commit()
            result.setdefault("order", []).append("revocation")

    def convert():
        start = time.monotonic()
        try:
            if lock:
                row = conversion.execute(
                    f"SELECT 1 FROM consent_grants WHERE consent_id = %s AND status = 'GRANTED' "
                    f"{lock}", (grant,)).fetchone()
                if row is None:
                    conversion.rollback()
                    result["conversion"] = "REFUSED by the service: no GRANTED grant after the lock"
                    result["convert_waited"] = time.monotonic() - start
                    return
            request = new_request(conversion, party)
            conversion.execute(BIND, (grant, request))
            result["convert_waited"] = time.monotonic() - start
            if not revoke_first:
                time.sleep(PAUSE)
            conversion.commit()
            result.setdefault("order", []).append("conversion")
            result["conversion"] = "COMMITTED"
        except psycopg.Error as exc:
            conversion.rollback()
            result["conversion"] = error(exc)
            result["convert_waited"] = time.monotonic() - start

    if revoke_first:
        revoke()
        worker = threading.Thread(target=convert)
        worker.start()
        time.sleep(PAUSE)
        out(f"    [{label}] conversion still waiting on the uncommitted revocation: "
            f"{worker.is_alive()}")
        revocation.commit()
        result.setdefault("order", []).append("revocation")
        worker.join(10)
    else:
        worker = threading.Thread(target=convert)
        worker.start()
        time.sleep(PAUSE / 4)
        revoker = threading.Thread(target=revoke)
        revoker.start()
        worker.join(10)
        revoker.join(10)
        out(f"    [{label}] revocation waited for the conversion's commit: "
            f"{result['revoke_waited'] >= PAUSE / 2}")
    status = setup.execute("SELECT status::text FROM consent_grants WHERE consent_id = %s",
                           (grant,)).fetchone()[0]
    bindings = setup.execute(
        "SELECT count(*) FROM resource_consent_bindings WHERE consent_id = %s AND revoked_at IS NULL",
        (grant,)).fetchone()[0]
    out(f"    [{label}] conversion: {result['conversion']}; grant now {status}; "
        f"unrevoked bindings to it: {bindings}")
    out(f"    [{label}] commit order: {' then '.join(result.get('order', []))}")
    for c in (conversion, revocation, setup):
        c.close()


def m4() -> None:
    out("M4  A revocation of ASSISTED_ENTRY racing a conversion's binding (READ COMMITTED)")
    out("    The conversion inserts a request and its binding, then waits before committing;")
    out("    the revocation runs meanwhile, as consent.revoke_consent does.")
    _race("a, no lock", None, revoke_first=False)
    _race("b, FOR KEY SHARE", "FOR KEY SHARE", revoke_first=False)
    _race("c, FOR SHARE", "FOR SHARE", revoke_first=False)
    out("    The revocation first, uncommitted; then the conversion:")
    _race("d, FOR SHARE, revocation first", "FOR SHARE", revoke_first=True)
    out()


# --- M5 ---------------------------------------------------------------------------------------

def _counts(conn) -> list[str]:
    lines = []
    for sql, label in [
        ("SELECT status::text, count(*) FROM external_leads GROUP BY 1 ORDER BY 1", "leads by status"),
        ("SELECT count(*) FROM external_leads WHERE party_id IS NOT NULL "
         "OR converted_request_id IS NOT NULL OR converted_property_id IS NOT NULL "
         "OR last_contact_at IS NOT NULL OR close_reason_code IS NOT NULL",
         "leads with any workflow column set"),
        ("SELECT status::text, count(*) FROM interests GROUP BY 1 ORDER BY 1", "interests by status"),
        ("SELECT count(*) FROM (SELECT party_id, property_id FROM interests "
         "WHERE status = 'ACTIVE' GROUP BY 1, 2 HAVING count(*) > 1) d",
         "ACTIVE interest pairs held twice"),
        ("SELECT count(*) FROM reason_codes WHERE code LIKE 'LEAD\\_%'", "reason codes named LEAD_*"),
        ("SELECT to_regclass('turab.external_lead_contact_attempts')::text",
         "table external_lead_contact_attempts"),
    ]:
        rows = conn.execute(sql).fetchall()
        value = rows[0][0] if len(rows) == 1 and len(rows[0]) == 1 else rows
        lines.append(f"{label}: {value if value not in ([], None) else 'none'}")
    return lines


def m5(conn) -> None:
    out("M5  The rows that exist before any new constraint")
    out("    scratch database (frozen schema, seed, migrations, dev fixtures):")
    for line in _counts(conn):
        out(f"      {line}")
    cats = conn.execute("SELECT category, count(*) FROM reason_codes GROUP BY 1 ORDER BY 1"
                        ).fetchall()
    out(f"      reason code categories: {cats}")
    admin = connect(autocommit=True, db="postgres")
    names = [r[0] for r in admin.execute(
        "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname <> %s "
        "ORDER BY 1", (DB,)).fetchall()]
    admin.close()
    for name in names:
        try:
            other = psycopg.connect(dsn(name))
            other.execute("SET TRANSACTION READ ONLY")
            if other.execute("SELECT to_regclass('turab.external_leads')").fetchone()[0] is None:
                out(f"    {name}: no turab.external_leads (read only)")
                other.close()
                continue
            other.execute("SET search_path TO turab, public")
            out(f"    {name} (read only, counts only):")
            for line in _counts(other):
                out(f"      {line}")
            other.rollback()
            other.close()
        except psycopg.Error as exc:
            out(f"    {name}: {error(exc)}")
    out()


# --- M6 ---------------------------------------------------------------------------------------

def m6() -> None:
    out("M6  Keyset paging of the leads queue by (discovered_at, id), a late commit")
    setup = connect(autocommit=True)
    source = setup.execute("INSERT INTO sources (kind) VALUES ('OTHER') RETURNING source_id"
                           ).fetchone()[0]
    marker = f"m6-{uuid.uuid4()}"
    lead = ("INSERT INTO external_leads (lead_kind, source_id, raw_payload) "
            "VALUES ('REQUEST', %s, jsonb_build_object('m', %s::text)) RETURNING external_lead_id")
    late = connect()
    late_id = late.execute(lead, (source, marker)).fetchone()[0]
    time.sleep(PAUSE)
    setup.execute(lead, (source, marker))
    page = ("SELECT external_lead_id, discovered_at FROM external_leads "
            "WHERE raw_payload->>'m' = %s {after} ORDER BY discovered_at, external_lead_id")
    first = setup.execute(page.format(after=""), (marker,)).fetchall()
    out(f"    page 1 (the earlier transaction not yet committed): {len(first)} lead(s)")
    cursor_at, cursor_id = first[-1][1], first[-1][0]
    late.commit()
    second = setup.execute(page.format(
        after="AND (discovered_at, external_lead_id) > (%s, %s)"),
        (marker, cursor_at, cursor_id)).fetchall()
    every = setup.execute(page.format(after=""), (marker,)).fetchall()
    order = ["late-committed" if r[0] == late_id else "committed first" for r in every]
    out(f"    page 2 after the cursor: {len(second)} lead(s)")
    out(f"    all leads, in the queue's order: {order}")
    out(f"    the late-committed lead sorts before the cursor, so paging never returns it: "
        f"{late_id not in [r[0] for r in first + second]}")
    out("    (discovered_at defaults to now(): the inserting TRANSACTION's start)")
    late.close()
    setup.close()
    out()


def main() -> int:
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
    identity = conn.execute("SELECT system_identifier FROM pg_control_system()").fetchone()[0]
    out(f"Tree    : {head}; working tree {'CLEAN' if clean else 'NOT CLEAN'} at the start")
    out(f"Database: {DB}, rebuilt by db/dev/reset_db.sh --fixtures; PostgreSQL {server}; "
        f"system_identifier {identity}")
    out()
    try:
        m1(conn)
        conn.commit()
        m2()
        m3(conn)
        m4()
        m5(conn)
        conn.rollback()
        m6()
    finally:
        conn.close()
        subprocess.run(["dropdb", "--if-exists", DB], env=env, check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
