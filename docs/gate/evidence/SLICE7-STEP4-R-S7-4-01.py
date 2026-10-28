#!/usr/bin/env python3
"""R-S7-4-01 (review of a659587): two concurrent backfills, under each
isolation level a connection may default to.

    TURAB_DATABASE_URL=postgresql+psycopg://.../<scratch db at head> \\
        .venv/bin/python docs/gate/evidence/SLICE7-STEP4-R-S7-4-01.py

For each default (`read committed`, `repeatable read`), on its own engine
whose connections take it as `default_transaction_isolation`:
1. a thread and N messages with no interaction (a pre-step-4 database);
2. backfill A starts, writes its first interaction, and is held there (a
   barrier inside `write`), holding the advisory lock;
3. backfill B starts its transaction and blocks on the lock (witness:
   `pg_blocking_pids`);
4. A is released and commits; B proceeds.
It prints, per default: the isolation level each backfill actually ran
under (read inside it), what each wrote, and how many of the N messages end
with more than one interaction. Prints counts and levels only.
"""
from __future__ import annotations

import os
import pathlib
import sys
import threading
import time
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from turab.services import message_interactions as mi  # noqa: E402

N = 5
URL = os.environ["TURAB_DATABASE_URL"]


def measure(default: str) -> dict:
    engine = create_engine(URL, connect_args={
        # libpq's `options`: a space inside a value is escaped by a backslash.
        "options": "-c default_transaction_isolation=" + default.replace(" ", "\\ ")})
    with engine.begin() as c:
        party = c.execute(text("INSERT INTO turab.parties (kind) VALUES ('PERSON') "
                               "RETURNING party_id")).scalar_one()
        thread = c.execute(text("INSERT INTO turab.communication_threads (channel, party_id) "
                                "VALUES ('PHONE', :p) RETURNING thread_id"),
                           {"p": party}).scalar_one()
        messages = [c.execute(text("""
            INSERT INTO turab.communication_messages (thread_id, direction, occurred_at)
            VALUES (:t, 'OUTBOUND', now()) RETURNING message_id"""), {"t": thread}).scalar_one()
                    for _ in range(N)]
    real = mi.write
    held, release = threading.Event(), threading.Event()
    seen: dict = {}

    def write(session, message_id):
        name = threading.current_thread().name
        seen.setdefault(name, session.execute(
            text("SELECT current_setting('transaction_isolation')")).scalar_one())
        if name == "A" and not held.is_set():
            seen["pid_A"] = session.execute(text("SELECT pg_backend_pid()")).scalar_one()
            held.set()
            release.wait(30)
        return real(session, message_id)

    mi.write = write
    out: dict = {}

    def run(name):
        with Session(bind=engine) as s:
            try:
                out[name] = mi.backfill(s, f"measure-{name}")
            except Exception as exc:  # recorded by type, as the result
                out[name] = f"refused: {type(exc).__name__}"

    a = threading.Thread(target=run, args=("A",), name="A")
    a.start()
    held.wait(30)
    b = threading.Thread(target=run, args=("B",), name="B")
    b.start()
    blocked = False
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not blocked:
        with engine.connect() as c:
            blocked = bool(c.execute(text("""
                SELECT 1 FROM pg_stat_activity
                 WHERE :a = ANY(pg_blocking_pids(pid))"""), {"a": seen["pid_A"]}).first())
        time.sleep(0.05)
    release.set()
    a.join(30)
    b.join(30)
    mi.write = real
    with engine.connect() as c:
        dup = c.execute(text("""
            SELECT count(*) FROM (
              SELECT metadata->>'message_id' FROM turab.interactions
               WHERE metadata->>'message_id' = ANY(:ids)
               GROUP BY 1 HAVING count(*) > 1) d"""),
                        {"ids": [str(m) for m in messages]}).scalar_one()
        total = c.execute(text("""
            SELECT count(*) FROM turab.interactions
             WHERE metadata->>'message_id' = ANY(:ids)"""),
                          {"ids": [str(m) for m in messages]}).scalar_one()
    engine.dispose()
    return {"default": default, "level_A": seen.get("A"), "level_B": seen.get("B"),
            "B_waited_for_A": blocked, "A_wrote": out.get("A"), "B_wrote": out.get("B"),
            "messages": N, "interactions_for_them": total, "messages_with_two_or_more": dup}


if __name__ == "__main__":
    print(f"run {uuid.uuid4().hex[:8]}")
    for default in ("read committed", "repeatable read"):
        r = measure(default)
        print(f"default_transaction_isolation = {r.pop('default')}")
        for key, value in r.items():
            print(f"  {key:26}: {value}")
