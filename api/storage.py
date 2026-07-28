"""Storage for the Sing Khmer web app — separates durable *signal* from disposable *text*.

The central idea: informal romanization has no ground truth, so the app never asks users
whether it was right — it records **what they did**, ranked by how much that action proves:

  1. override -> copy : engine's top pick was A, the user chose B and then copied it.
     Revealed preference: B is right and the ranking of A above B is wrong.
  2. copy, no edits    : the whole output was accepted as typed. Those mappings are confirmed.
  3. inline answer     : the user told us the Khmer for a word we failed on.
  4. generic form      : weakest — anyone can type anything.

Agreement across *distinct sessions* is what turns any of these into confidence, so every
aggregate tracks how many different people produced it.

Raw messages live only in `conversions` and carry an `expires_at`; every useful signal is
derived at write time into tables that never expire. That means deleting people's text later
costs nothing (see `scripts/purge.py`).

All signals are derived **server-side** from the submitted input by re-running the engine —
the browser cannot claim "the engine said X".
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

log = logging.getLogger("sing_khmer.storage")

DATABASE_URL = os.environ.get("DATABASE_URL", "")
SQLITE_PATH = os.environ.get("SQLITE_PATH", "/tmp/sing_khmer.db")
# Vercel sets VERCEL=1. Its disk is wiped on every deploy, so falling back to SQLite there
# would silently throw away everything — refuse instead of pretending to store data.
IS_SERVERLESS = bool(os.environ.get("VERCEL"))
RAW_TEXT_TTL_DAYS = int(os.environ.get("RAW_TEXT_TTL_DAYS", "90"))

CONSENT_VERSION = "2026-07-1"


def mode() -> str:
    """'postgres' | 'sqlite' | 'disabled'."""
    if DATABASE_URL:
        return "postgres"
    if IS_SERVERLESS:
        return "disabled"          # never silently write to a disk that gets wiped
    return "sqlite"


def available() -> bool:
    return mode() != "disabled"


@contextmanager
def connect():
    """Yield (connection, placeholder). Raises RuntimeError when storage is disabled."""
    m = mode()
    if m == "disabled":
        raise RuntimeError(
            "No DATABASE_URL set in a serverless deployment — refusing to write to a "
            "temporary disk. Attach Postgres (see DEPLOY.md)."
        )
    if m == "postgres":
        import psycopg

        conn = psycopg.connect(DATABASE_URL)
        try:
            yield conn, "%s"
            conn.commit()
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(SQLITE_PATH)
        try:
            yield conn, "?"
            conn.commit()
        finally:
            conn.close()


# ---- privacy: strip the things people most regret typing ---------------------------
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_URL = re.compile(r"https?://\S+|www\.\S+")
_LONG_DIGITS = re.compile(r"\d{7,}")          # phone numbers, account numbers


def redact(text: str) -> str:
    """Remove emails, links and long digit runs before anything is stored."""
    text = _EMAIL.sub("[email]", text)
    text = _URL.sub("[link]", text)
    return _LONG_DIGITS.sub("[number]", text)


# ---- schema -------------------------------------------------------------------------
_MIGRATED = False


def migrate() -> None:
    """Create tables once per process (not on every request)."""
    global _MIGRATED
    if _MIGRATED or not available():
        return
    pk = "BIGSERIAL PRIMARY KEY" if DATABASE_URL else "INTEGER PRIMARY KEY AUTOINCREMENT"
    with connect() as (conn, _):
        cur = conn.cursor()
        for ddl in (
            "CREATE TABLE IF NOT EXISTS sessions ("
            " id TEXT PRIMARY KEY, created_at TIMESTAMP, last_seen TIMESTAMP,"
            " consent_version TEXT, trusted BOOLEAN DEFAULT FALSE, flagged BOOLEAN DEFAULT FALSE)",
            # The ONLY table holding raw messages. Everything below is derived and permanent.
            f"CREATE TABLE IF NOT EXISTS conversions (id {pk}, session_id TEXT, ts TIMESTAMP,"
            " input_text TEXT, output_text TEXT, token_count INTEGER, unknown_count INTEGER,"
            " overrode BOOLEAN, copied BOOLEAN, expires_at TIMESTAMP)",
            # Signal 1 — the strongest: the engine ranked the wrong candidate first.
            f"CREATE TABLE IF NOT EXISTS word_choices (id {pk}, session_id TEXT, ts TIMESTAMP,"
            " spelling TEXT, engine_top TEXT, chosen TEXT, copied BOOLEAN)",
            # Signal 2 — coverage gap. Aggregated, never expires.
            "CREATE TABLE IF NOT EXISTS unknown_words ("
            " spelling TEXT PRIMARY KEY, total_count INTEGER DEFAULT 0,"
            " session_count INTEGER DEFAULT 0, first_seen TIMESTAMP, last_seen TIMESTAMP,"
            " status TEXT DEFAULT 'new')",
            "CREATE TABLE IF NOT EXISTS unknown_word_sessions ("
            " spelling TEXT, session_id TEXT, PRIMARY KEY (spelling, session_id))",
            # Signal 3 — accepted as-is (copied without editing).
            "CREATE TABLE IF NOT EXISTS confirmations ("
            " spelling TEXT, khmer TEXT, total_count INTEGER DEFAULT 0,"
            " session_count INTEGER DEFAULT 0, PRIMARY KEY (spelling, khmer))",
            "CREATE TABLE IF NOT EXISTS confirmation_sessions ("
            " spelling TEXT, khmer TEXT, session_id TEXT,"
            " PRIMARY KEY (spelling, khmer, session_id))",
            # Signal 4 — what people explicitly told us.
            f"CREATE TABLE IF NOT EXISTS corrections (id {pk}, session_id TEXT, ts TIMESTAMP,"
            " spelling TEXT, expected_khmer TEXT, source TEXT, status TEXT DEFAULT 'new')",
            "CREATE INDEX IF NOT EXISTS conversions_expiry ON conversions (expires_at)",
            "CREATE INDEX IF NOT EXISTS corrections_pair ON corrections (spelling, expected_khmer)",
        ):
            cur.execute(ddl)
    _MIGRATED = True


def touch_session(cur, ph: str, session_id: str) -> None:
    now = datetime.now(timezone.utc)
    cur.execute(f"SELECT 1 FROM sessions WHERE id = {ph}", (session_id,))
    if cur.fetchone() is None:
        cur.execute(
            f"INSERT INTO sessions (id, created_at, last_seen, consent_version)"
            f" VALUES ({ph}, {ph}, {ph}, {ph})",
            (session_id, now, now, CONSENT_VERSION),
        )
    else:
        cur.execute(f"UPDATE sessions SET last_seen = {ph} WHERE id = {ph}", (now, session_id))


def _bump_unknown(cur, ph: str, session_id: str, spelling: str) -> None:
    now = datetime.now(timezone.utc)
    cur.execute(
        f"INSERT INTO unknown_words (spelling, total_count, session_count, first_seen, last_seen)"
        f" VALUES ({ph}, 1, 0, {ph}, {ph})"
        f" ON CONFLICT (spelling) DO UPDATE SET"
        f" total_count = unknown_words.total_count + 1, last_seen = {ph}",
        (spelling, now, now, now),
    )
    cur.execute(
        f"INSERT INTO unknown_word_sessions (spelling, session_id) VALUES ({ph}, {ph})"
        f" ON CONFLICT DO NOTHING",
        (spelling, session_id),
    )
    if cur.rowcount:                      # first time THIS person hit this word
        cur.execute(
            f"UPDATE unknown_words SET session_count = session_count + 1 WHERE spelling = {ph}",
            (spelling,),
        )


def _bump_confirmation(cur, ph: str, session_id: str, spelling: str, khmer: str) -> None:
    cur.execute(
        f"INSERT INTO confirmations (spelling, khmer, total_count, session_count)"
        f" VALUES ({ph}, {ph}, 1, 0)"
        f" ON CONFLICT (spelling, khmer) DO UPDATE SET"
        f" total_count = confirmations.total_count + 1",
        (spelling, khmer),
    )
    cur.execute(
        f"INSERT INTO confirmation_sessions (spelling, khmer, session_id)"
        f" VALUES ({ph}, {ph}, {ph}) ON CONFLICT DO NOTHING",
        (spelling, khmer, session_id),
    )
    if cur.rowcount:
        cur.execute(
            f"UPDATE confirmations SET session_count = session_count + 1"
            f" WHERE spelling = {ph} AND khmer = {ph}",
            (spelling, khmer),
        )


def record_conversion(
    session_id: str,
    *,
    input_text: str,
    output_text: str,
    token_count: int,
    unknown: list[str],
    choices: list[dict],
    confirmations: list[dict],
    copied: bool,
) -> None:
    """Store one conversion plus every signal derived from it (all server-computed)."""
    if not available():
        return
    migrate()
    now = datetime.now(timezone.utc)
    with connect() as (conn, ph):
        cur = conn.cursor()
        touch_session(cur, ph, session_id)
        cur.execute(
            f"INSERT INTO conversions (session_id, ts, input_text, output_text, token_count,"
            f" unknown_count, overrode, copied, expires_at)"
            f" VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})",
            (session_id, now, redact(input_text), redact(output_text), token_count,
             len(unknown), bool(choices), copied,
             now + timedelta(days=RAW_TEXT_TTL_DAYS)),
        )
        for c in choices:
            cur.execute(
                f"INSERT INTO word_choices (session_id, ts, spelling, engine_top, chosen, copied)"
                f" VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})",
                (session_id, now, c["spelling"], c["engine_top"], c["chosen"], copied),
            )
        for spelling in unknown:
            _bump_unknown(cur, ph, session_id, spelling)
        if copied:                       # only a copy proves acceptance
            for c in confirmations:
                _bump_confirmation(cur, ph, session_id, c["spelling"], c["khmer"])


def record_correction(session_id: str, spelling: str, expected_khmer: str, source: str) -> None:
    if not available():
        return
    migrate()
    with connect() as (conn, ph):
        cur = conn.cursor()
        touch_session(cur, ph, session_id)
        cur.execute(
            f"INSERT INTO corrections (session_id, ts, spelling, expected_khmer, source)"
            f" VALUES ({ph}, {ph}, {ph}, {ph}, {ph})",
            (session_id, datetime.now(timezone.utc), spelling, expected_khmer, source),
        )


def stats() -> dict:
    """Aggregates only — never raw messages. Powers /admin."""
    if not available():
        return {"storage": mode()}
    migrate()
    out: dict = {"storage": mode()}
    with connect() as (conn, ph):
        cur = conn.cursor()

        def one(sql, default=0):
            cur.execute(sql)
            row = cur.fetchone()
            return (row[0] if row and row[0] is not None else default)

        out["sessions"] = one("SELECT COUNT(*) FROM sessions")
        out["conversions"] = one("SELECT COUNT(*) FROM conversions")
        tokens = one("SELECT COALESCE(SUM(token_count),0) FROM conversions")
        unknown = one("SELECT COALESCE(SUM(unknown_count),0) FROM conversions")
        out["tokens"] = tokens
        # THE number: how often the engine had no idea what a word was.
        out["unknown_rate"] = round(100.0 * unknown / tokens, 1) if tokens else 0.0
        copied = one("SELECT COUNT(*) FROM conversions WHERE copied")
        out["copy_rate"] = round(100.0 * copied / out["conversions"], 1) if out["conversions"] else 0.0
        out["corrections"] = one("SELECT COUNT(*) FROM corrections")

        cur.execute(
            "SELECT spelling, total_count, session_count FROM unknown_words"
            " WHERE status = 'new' ORDER BY session_count DESC, total_count DESC LIMIT 25"
        )
        out["top_missing"] = [
            {"spelling": r[0], "times": r[1], "people": r[2]} for r in cur.fetchall()
        ]
        cur.execute(
            "SELECT spelling, engine_top, chosen, COUNT(DISTINCT session_id) AS people,"
            " COUNT(*) AS times FROM word_choices GROUP BY spelling, engine_top, chosen"
            " ORDER BY people DESC, times DESC LIMIT 25"
        )
        out["top_overrides"] = [
            {"spelling": r[0], "engine_top": r[1], "chosen": r[2], "people": r[3], "times": r[4]}
            for r in cur.fetchall()
        ]
    return out


def purge_expired(now: datetime | None = None) -> int:
    """Delete raw message text past its TTL. Derived signals are untouched."""
    if not available():
        return 0
    migrate()
    now = now or datetime.now(timezone.utc)
    with connect() as (conn, ph):
        cur = conn.cursor()
        cur.execute(f"DELETE FROM conversions WHERE expires_at < {ph}", (now,))
        return cur.rowcount or 0
