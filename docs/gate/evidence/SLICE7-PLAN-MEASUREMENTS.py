"""TURAB — Slice 7 step 0: the plan's facts measured on PostgreSQL, before any code.

Authorized in the review of dcebe46 (plan revision 1): M1-M7, plus M8, on a
TEMPORARY database, with transactions rolled back where possible, and no
implementation code. Kept beside its output (`SLICE7-PLAN-MEASUREMENTS.txt`)
so the run can be repeated. It is placed under docs/, outside the trees the
source fingerprint covers (src/, tests/, db/), so it changes no binding.

    PGHOST=127.0.0.1 PGUSER=turab PGPASSWORD=turab \
      .venv/bin/python docs/gate/evidence/SLICE7-PLAN-MEASUREMENTS.py

What it does, and only this:
- rebuilds the scratch database `turab_s7_probe` with `db/dev/reset_db.sh
  --fixtures` (the frozen schema, the seed, migrations 0002-0007, the dev
  fixtures), and drops it at the end;
- writes rows by plain SQL, to observe what the SCHEMA permits. M1-M3, M5 and
  M8 are rolled back. M4 commits, because concurrency needs committed rows.
  M7 commits one observation through the delivered route;
- M6 runs the delivered STOP GATE E generator in a COPY of the tree, in a
  temporary directory.
The candidate triggers of M8 exist only inside rolled-back transactions; they
are not a proposal's text.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

import psycopg
from psycopg import errors

ROOT = Path(__file__).resolve().parents[3]
DB = "turab_s7_probe"
HOST = os.environ.get("PGHOST", "127.0.0.1")
USER = os.environ.get("PGUSER", "turab")
PASSWORD = os.environ.get("PGPASSWORD", "turab")
DSN = f"host={HOST} user={USER} password={PASSWORD} dbname={DB}"
OPERATOR = "f3000000-0000-4000-8000-000000000002"   # tests/conftest.py, dev fixtures


def out(line: str = "") -> None:
    print(line, flush=True)


def connect(autocommit: bool = False) -> psycopg.Connection:
    conn = psycopg.connect(DSN, autocommit=autocommit)
    conn.execute("SET search_path TO turab, public")
    return conn


def attempt(conn, sql, params=None, label=""):
    """Run one statement under a savepoint; report accepted or the error."""
    try:
        with conn.transaction():
            cur = conn.execute(sql, params or {})
            rows = cur.rowcount
        return f"ACCEPTED (rows {rows})"
    except psycopg.Error as exc:
        diag = exc.diag
        return (f"REFUSED {exc.sqlstate} {type(exc).__name__}"
                + (f" constraint={diag.constraint_name}" if diag.constraint_name else "")
                + f": {(diag.message_primary or '').strip()}")


def party(conn) -> str:
    return conn.execute("INSERT INTO parties (kind) VALUES ('PERSON') RETURNING party_id::text"
                        ).fetchone()[0]


def thread(conn, party_id=None, channel="WHATSAPP", ref=None) -> str:
    return conn.execute(
        "INSERT INTO communication_threads (channel, party_id, external_thread_ref) "
        "VALUES (%s, %s, %s) RETURNING thread_id::text", (channel, party_id, ref)).fetchone()[0]


def message(conn, thread_id, provider, ref):
    return conn.execute(
        "INSERT INTO communication_messages (thread_id, provider, external_message_ref, "
        "direction, occurred_at) VALUES (%s, %s, %s, 'INBOUND', now())",
        (thread_id, provider, ref))


# ---------------------------------------------------------------------------------------
def m1_m2(conn) -> None:
    out("M1  Two messages, provider NULL, the same external_message_ref, two threads")
    with conn.transaction(force_rollback=True):
        a, b = thread(conn), thread(conn)
        out(f"    thread A: {attempt(conn, 'INSERT INTO communication_messages (thread_id, provider, external_message_ref, direction, occurred_at) VALUES (%(t)s, NULL, %(r)s, %(d)s, now())', {'t': a, 'r': 'wamid.SAME', 'd': 'INBOUND'})}")
        out(f"    thread B: {attempt(conn, 'INSERT INTO communication_messages (thread_id, provider, external_message_ref, direction, occurred_at) VALUES (%(t)s, NULL, %(r)s, %(d)s, now())', {'t': b, 'r': 'wamid.SAME', 'd': 'INBOUND'})}")
        n = conn.execute("SELECT count(*) FROM communication_messages "
                         "WHERE external_message_ref = 'wamid.SAME'").fetchone()[0]
        out(f"    rows with that reference: {n}")
    out("    (rolled back)")
    out()
    out("M2  The same (provider, external_message_ref) in a second thread")
    with conn.transaction(force_rollback=True):
        a, b = thread(conn), thread(conn)
        sql = ("INSERT INTO communication_messages (thread_id, provider, external_message_ref, "
               "direction, occurred_at) VALUES (%(t)s, 'whatsapp', 'wamid.G', 'INBOUND', now())")
        out(f"    thread A: {attempt(conn, sql, {'t': a})}")
        out(f"    thread B: {attempt(conn, sql, {'t': b})}")
        out(f"    thread A again: {attempt(conn, sql, {'t': a})}")
    out("    (rolled back)")
    out()


def m3(conn) -> None:
    role = conn.execute("SELECT current_user, rolsuper FROM pg_roles WHERE rolname = current_user"
                        ).fetchone()
    out(f"M3  UPDATE and DELETE as the connecting role ({role[0]}, superuser={role[1]})")
    with conn.transaction(force_rollback=True):
        p, p2 = party(conn), party(conn)
        t = thread(conn, p)
        message(conn, t, "whatsapp", "wamid.M3")
        conn.execute("INSERT INTO webhook_events (provider, provider_event_id, event_type, payload) "
                      "VALUES ('whatsapp', 'evt.M3', 'message', '{}')")
        for label, sql in (
                ("message body_text UPDATE", "UPDATE communication_messages SET body_text = 'changed' WHERE external_message_ref = 'wamid.M3'"),
                ("message delivery_status backwards (READ then SENT)", "UPDATE communication_messages SET delivery_status = 'READ' WHERE external_message_ref = 'wamid.M3'"),
                ("", "UPDATE communication_messages SET delivery_status = 'SENT' WHERE external_message_ref = 'wamid.M3'"),
                ("webhook_events payload UPDATE", "UPDATE webhook_events SET payload = '{\"x\": 1}' WHERE provider_event_id = 'evt.M3'"),
                ("webhook_events status back to RECEIVED", "UPDATE webhook_events SET processing_status = 'PROCESSED' WHERE provider_event_id = 'evt.M3'"),
                ("", "UPDATE webhook_events SET processing_status = 'RECEIVED' WHERE provider_event_id = 'evt.M3'"),
                ("thread party_id UPDATE", f"UPDATE communication_threads SET party_id = '{p2}' WHERE thread_id = '{t}'"),
                ("thread channel UPDATE", f"UPDATE communication_threads SET channel = 'SMS' WHERE thread_id = '{t}'"),
                ("thread DELETE while it has a message", f"DELETE FROM communication_threads WHERE thread_id = '{t}'"),
                ("message DELETE", "DELETE FROM communication_messages WHERE external_message_ref = 'wamid.M3'"),
                ("webhook_events DELETE", "DELETE FROM webhook_events WHERE provider_event_id = 'evt.M3'"),
                ("thread DELETE once empty", f"DELETE FROM communication_threads WHERE thread_id = '{t}'")):
            result = attempt(conn, sql)
            out(f"    {label or '  then'}: {result}")
        trig = conn.execute("""
            SELECT c.relname, count(t.tgname) FILTER (WHERE NOT t.tgisinternal)
              FROM pg_class c LEFT JOIN pg_trigger t ON t.tgrelid = c.oid
             WHERE c.relnamespace = 'turab'::regnamespace
               AND c.relname IN ('communication_threads', 'communication_messages',
                                 'webhook_events', 'interactions')
             GROUP BY c.relname ORDER BY c.relname""").fetchall()
        out("    user triggers per table: " + ", ".join(f"{n}={k}" for n, k in trig))
    out("    (rolled back)")
    out()


def m4() -> None:
    out("M4  Two concurrent inserts of one (provider, provider_event_id)")
    sql = ("INSERT INTO webhook_events (provider, provider_event_id, event_type, payload) "
           "VALUES ('whatsapp', %s, 'message', '{}') ON CONFLICT (provider, provider_event_id) "
           "DO NOTHING RETURNING webhook_event_id")
    for ending in ("COMMIT", "ROLLBACK"):
        event = f"evt.M4.{ending}"
        a, b = connect(), connect()
        pid_b = b.execute("SELECT pg_backend_pid()").fetchone()[0]
        a.execute(sql, (event,))
        result = {}

        def second():
            try:
                result["rows"] = len(b.execute(sql, (event,)).fetchall())
                b.commit()
            except psycopg.Error as exc:
                result["error"] = exc.sqlstate
        worker = threading.Thread(target=second)
        worker.start()
        blocked_by, deadline = [], time.time() + 10
        watch = connect(autocommit=True)
        while time.time() < deadline and not blocked_by:
            blocked_by = watch.execute("SELECT pg_blocking_pids(%s)", (pid_b,)).fetchone()[0]
            time.sleep(0.05)
        pid_a = a.execute("SELECT pg_backend_pid()").fetchone()[0]
        still = worker.is_alive()
        getattr(a, ending.lower())()
        worker.join(10)
        rows = watch.execute("SELECT count(*), min(processing_status::text) FROM webhook_events "
                             "WHERE provider_event_id = %s", (event,)).fetchone()
        out(f"    first transaction ends by {ending}: the second waited on the first "
            f"(pg_blocking_pids holds its pid: {pid_a in blocked_by}; still waiting before "
            f"the end: {still}); the second inserted {result.get('rows')} row(s) "
            f"{'(error ' + result['error'] + ')' if 'error' in result else ''}; rows stored: "
            f"{rows[0]}, status {rows[1]}")
        for c in (a, b, watch):
            c.close()
    out()
    out("M4b A RECEIVED row: what a replay can see, and whether an in-flight claim is visible")
    setup = connect(autocommit=True)
    setup.execute("INSERT INTO webhook_events (provider, provider_event_id, event_type, payload) "
                  "VALUES ('whatsapp', 'evt.M4b', 'message', '{}')")
    seen = setup.execute(
        "INSERT INTO webhook_events (provider, provider_event_id, event_type, payload) "
        "VALUES ('whatsapp', 'evt.M4b', 'message', '{}') ON CONFLICT (provider, provider_event_id) "
        "DO NOTHING RETURNING webhook_event_id").fetchall()
    status = setup.execute("SELECT processing_status::text FROM webhook_events "
                           "WHERE provider_event_id = 'evt.M4b'").fetchone()[0]
    out(f"    a replay with ON CONFLICT DO NOTHING returns {len(seen)} row(s); the stored "
        f"status, read separately, is {status}")
    holder, other = connect(), connect()
    holder.execute("SELECT 1 FROM webhook_events WHERE provider_event_id = 'evt.M4b' FOR UPDATE")
    out(f"    while a processor holds the row FOR UPDATE, a second claim with NOWAIT: "
        f"{attempt(other, 'SELECT 1 FROM webhook_events WHERE provider_event_id = %(e)s FOR UPDATE NOWAIT', {'e': 'evt.M4b'})}")
    out(f"    the same claim with SKIP LOCKED returns "
        f"{len(other.execute('SELECT 1 FROM webhook_events WHERE provider_event_id = %s FOR UPDATE SKIP LOCKED', ('evt.M4b',)).fetchall())} row(s)")
    other.rollback()
    holder.rollback()
    out(f"    once the holder ends (no status change): a claim with NOWAIT "
        f"{attempt(other, 'SELECT 1 FROM webhook_events WHERE provider_event_id = %(e)s FOR UPDATE NOWAIT', {'e': 'evt.M4b'})}")
    other.rollback()
    for c in (holder, other, setup):
        c.close()
    out()


def m5(conn) -> None:
    out("M5  A COMMUNICATION_ARCHIVE binding to a thread")
    with conn.transaction(force_rollback=True):
        p, q = party(conn), party(conn)
        grant = conn.execute(
            "INSERT INTO consent_grants (party_id, scope, channel, consent_version, granted_at) "
            "VALUES (%s, 'COMMUNICATION_ARCHIVE', 'PHONE_CONFIRMED', 'v1', now() - interval '1 day') "
            "RETURNING consent_id::text", (p,)).fetchone()[0]
        sql = ("INSERT INTO resource_consent_bindings (consent_id, purpose, thread_id) "
               "VALUES (%(g)s, 'COMMUNICATION_ARCHIVE', %(t)s)")
        for label, owner in (("thread with party NULL", None), ("thread of another party", q),
                             ("thread of the grant's party", p)):
            out(f"    {label}: {attempt(conn, sql, {'g': grant, 't': thread(conn, owner)})}")
    out("    (rolled back)")
    out()


def m6() -> None:
    out("M6  STOP GATE E's generator with a second writer of `interactions`, in a copy of the tree")
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "tree"
        archive = subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, capture_output=True,
                                 check=True).stdout
        copy.mkdir()
        subprocess.run(["tar", "-x", "-C", str(copy)], input=archive, check=True)
        before = subprocess.run([sys.executable, "db/gate/stop_gate_e_evidence.py", "--check"],
                                cwd=copy, capture_output=True, text=True)
        (copy / "src/turab/services/probe_writer.py").write_text(
            'SQL = "INSERT INTO turab.interactions (interaction_type, occurred_at) VALUES (NULL, NULL)"\n')
        after = subprocess.run([sys.executable, "db/gate/stop_gate_e_evidence.py", "--check"],
                               cwd=copy, capture_output=True, text=True)

    def problems(run):
        return [line for line in run.stderr.splitlines() if line.startswith("PROBLEM")]
    out(f"    the copy as committed: exit {before.returncode}")
    for line in problems(before):
        out(f"      {line}")
    out(f"    with src/turab/services/probe_writer.py added: exit {after.returncode}")
    for line in problems(after):
        out(f"      {line}")
    out()


def m7(conn) -> None:
    out("M7  Payload sizes of SYNTHETIC SAMPLES (عينة اصطناعية), and the app's body limit today")
    out("    Both envelopes below are synthetic samples written for this measurement: no")
    out("    provider produced them, and the envelope's producer is undecided (G7-2).")
    text_body = "رسالة تجريبية " * 20
    turab = {"provider_event_id": "evt.synthetic.1", "event_type": "message",
             "payload": {"external_message_ref": "wamid.synthetic.1", "thread_ref": "213770000000",
                         "occurred_at": "2026-10-23T10:00:00Z", "message_type": "TEXT",
                         "body_text": text_body}}
    meta_shaped = {"object": "whatsapp_business_account", "entry": [{"id": "0", "changes": [{
        "field": "messages", "value": {"messaging_product": "whatsapp",
                                       "metadata": {"phone_number_id": "0"},
                                       "messages": [{"from": "213770000000", "id": "wamid.synthetic.1",
                                                     "timestamp": "0", "type": "text",
                                                     "text": {"body": text_body}}]}}]}]}
    with conn.transaction(force_rollback=True):
        for label, doc in (("TURAB envelope, synthetic", turab),
                           ("Meta-shaped notification, synthetic", meta_shaped)):
            raw = json.dumps(doc, ensure_ascii=False).encode()
            stored = conn.execute(
                "INSERT INTO webhook_events (provider, provider_event_id, event_type, payload) "
                "VALUES ('whatsapp', %s, 'message', %s::jsonb) "
                "RETURNING pg_column_size(payload), payload::text LIKE %s",
                (str(uuid.uuid4()), json.dumps(doc, ensure_ascii=False), f"%{text_body[:20]}%")
            ).fetchone()
            out(f"    {label}: {len(raw)} bytes as JSON; stored jsonb column {stored[0]} bytes; "
                f"the message text is inside the stored payload: {stored[1]}")
    out("    (rolled back)")
    sys.path.insert(0, str(ROOT / "src"))
    os.environ["TURAB_DATABASE_URL"] = (f"postgresql+psycopg://{USER}:{PASSWORD}@{HOST}/{DB}")
    from fastapi.testclient import TestClient
    from turab.app import create_app
    from turab.db.session import create_app_engine
    engine = create_app_engine(os.environ["TURAB_DATABASE_URL"])
    with TestClient(create_app(engine=engine), raise_server_exceptions=False) as client:
        for size in (1 << 20, 8 << 20):
            r = client.post("/observations", json={"kind": "TEXT", "raw_text": "x" * size},
                            headers={"Authorization": f"Bearer {OPERATOR}",
                                     "Idempotency-Key": str(uuid.uuid4())})
            out(f"    POST /observations with a {size >> 20} MiB raw_text: HTTP {r.status_code}")
    engine.dispose()
    out()


def m8(conn) -> None:
    out("M8  ON DELETE SET NULL against a candidate guard that freezes a thread's links")
    out("    Parents with a delete guard (prevent_core_delete): requests, properties,")
    out("    property_offers, opportunities (and claims, resolved_values). parties and")
    out("    user_accounts have none, so a thread's party_id can reach SET NULL.")
    variants = {
        "strict (any change of a link refused)": """
            IF NEW.party_id IS DISTINCT FROM OLD.party_id
               OR NEW.request_id IS DISTINCT FROM OLD.request_id
               OR NEW.property_id IS DISTINCT FROM OLD.property_id
               OR NEW.opportunity_id IS DISTINCT FROM OLD.opportunity_id
               OR NEW.channel IS DISTINCT FROM OLD.channel THEN
              RAISE EXCEPTION 'candidate: thread links are frozen';
            END IF;""",
        "permissive (a link may only become NULL)": """
            IF (NEW.party_id IS DISTINCT FROM OLD.party_id AND NEW.party_id IS NOT NULL)
               OR (NEW.request_id IS DISTINCT FROM OLD.request_id AND NEW.request_id IS NOT NULL)
               OR (NEW.property_id IS DISTINCT FROM OLD.property_id AND NEW.property_id IS NOT NULL)
               OR (NEW.opportunity_id IS DISTINCT FROM OLD.opportunity_id AND NEW.opportunity_id IS NOT NULL)
               OR NEW.channel IS DISTINCT FROM OLD.channel THEN
              RAISE EXCEPTION 'candidate: thread links are frozen';
            END IF;"""}
    for label, body in variants.items():
        with conn.transaction(force_rollback=True):
            conn.execute(f"""
                CREATE FUNCTION pg_temp.m8_guard() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                  RAISE NOTICE 'm8 depth=%', pg_trigger_depth();
                  {body}
                  RETURN NEW;
                END $$""")
            conn.execute("CREATE TRIGGER m8_guard BEFORE UPDATE ON communication_threads "
                         "FOR EACH ROW EXECUTE FUNCTION pg_temp.m8_guard()")
            notices = []
            conn.add_notice_handler(lambda d: notices.append(d.message_primary))
            p, p2 = party(conn), party(conn)
            t = thread(conn, p)
            direct = attempt(conn, "UPDATE communication_threads SET party_id = %(p)s "
                                   "WHERE thread_id = %(t)s", {"p": p2, "t": t})
            t2 = thread(conn, p2)
            to_null = attempt(conn, "UPDATE communication_threads SET party_id = NULL "
                                    "WHERE thread_id = %(t)s", {"t": t2})
            delete = attempt(conn, "DELETE FROM parties WHERE party_id = %(p)s", {"p": p})
            left = conn.execute("SELECT party_id IS NULL FROM communication_threads "
                                "WHERE thread_id = %s", (t,)).fetchone()[0]
            out(f"    {label}:")
            out(f"      a direct UPDATE of party_id to another party: {direct}")
            out(f"      a direct UPDATE of party_id to NULL (no delete): {to_null}")
            out(f"      DELETE of the thread's party (FK ON DELETE SET NULL): {delete}")
            out(f"      the thread's party_id is now NULL: {left}; "
                f"pg_trigger_depth seen by the guard: {sorted(set(notices))}")
    out("    (rolled back; the candidate triggers existed only inside these transactions)")
    out()


def main() -> int:
    env = {**os.environ, "PGDATABASE": DB, "PGHOST": HOST, "PGUSER": USER, "PGPASSWORD": PASSWORD}
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
    out()
    try:
        m1_m2(conn)
        m3(conn)
        m4()
        m5(conn)
        m6()
        m7(conn)
        m8(conn)
    finally:
        conn.close()
        subprocess.run(["dropdb", "--if-exists", DB], env=env, check=False)
    out(f"Database {DB} dropped at the end.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
