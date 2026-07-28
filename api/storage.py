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
from pathlib import Path

log = logging.getLogger("sing_khmer.storage")

ROOT = Path(__file__).resolve().parents[1]

DB_ENV_VARS = (
    "DATABASE_URL",
    "POSTGRES_URL",
    "DATABASE_URL_UNPOOLED",
    "POSTGRES_URL_NON_POOLING",
    "NEON_DATABASE_URL",
)

DATABASE_URL = os.environ.get("DATABASE_URL", "")
# Anchored to the repo root, not the working directory, so the dev database doesn't move
# depending on where uvicorn was started from. It used to live in /tmp, which made it
# invisible ("I sent a word and see nothing") and wiped it on reboot. Gitignored.
SQLITE_PATH = os.environ.get("SQLITE_PATH", str(ROOT / "local.db"))
# Vercel sets VERCEL=1. Its disk is wiped on every deploy, so falling back to SQLite there
# would silently throw away everything — refuse instead of pretending to store data.
IS_SERVERLESS = bool(os.environ.get("VERCEL"))
RAW_TEXT_TTL_DAYS = int(os.environ.get("RAW_TEXT_TTL_DAYS", "90"))

CONSENT_VERSION = "2026-07-1"


def get_db_env() -> tuple[str, str | None]:
    """Return (db_url, var_name) for the first non-empty database env var found."""
    for var_name in DB_ENV_VARS:
        val = os.environ.get(var_name, "").strip()
        if val:
            return val, var_name
    if DATABASE_URL:
        return DATABASE_URL, "DATABASE_URL"
    return "", None


def mode() -> str:
    """'postgres' | 'sqlite' | 'disabled'."""
    url, _ = get_db_env()
    if url:
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

        url, _ = get_db_env()
        conn = psycopg.connect(url)
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


def redact_error(msg: str) -> str:
    """Sanitize error messages so connection strings, passwords, and hosts are never leaked."""
    if not msg:
        return ""
    msg = re.sub(r"postgres(?:ql)?://[^\s'\"]+", "[redacted-db-url]", msg, flags=re.IGNORECASE)
    msg = re.sub(r'at "[^"]+"', 'at "[redacted-host]"', msg)
    msg = re.sub(r"host=\S+", "host=[redacted]", msg, flags=re.IGNORECASE)
    msg = re.sub(r"password=\S+", "password=[redacted]", msg, flags=re.IGNORECASE)
    msg = re.sub(r"user=\S+", "user=[redacted]", msg, flags=re.IGNORECASE)
    return msg


def location() -> str:
    """Where the data actually is, in words — for humans looking for their rows.

    Never the connection string: for Postgres this names the *environment variable*, so it
    can be printed in a terminal or rendered on /admin without leaking credentials.
    """
    m = mode()
    if m == "sqlite":
        return f"sqlite file: {SQLITE_PATH}"
    if m == "postgres":
        _, env_var = get_db_env()
        return f"postgres (from ${env_var})"
    return "disabled — nothing is being stored"


def diagnose() -> dict:
    """Diagnose storage connectivity, table existence, and row counts."""
    url, env_var = get_db_env()
    m = mode()

    result = {
        "storage": m,
        "location": location(),
        "env_var": env_var,
        "checked_env_vars": list(DB_ENV_VARS) if env_var is None else None,
        "connected": False,
        "error_type": None,
        "error": None,
        "tables_exist": False,
        "tables": {},
    }

    if m == "disabled":
        result["error_type"] = "RuntimeError"
        result["error"] = (
            "No database environment variable set in a serverless deployment — "
            "refusing to write to temporary disk."
        )
        return result

    try:
        with connect() as (conn, ph):
            cur = conn.cursor()
            cur.execute("SELECT 1")

        migrate()

        counts = {}
        with connect() as (conn, ph):
            cur = conn.cursor()
            for tbl in ("sessions", "conversions", "corrections"):
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                    row = cur.fetchone()
                    counts[tbl] = row[0] if row and row[0] is not None else 0
                except Exception:
                    counts[tbl] = 0

        result["connected"] = True
        result["tables_exist"] = True
        result["tables"] = counts
    except Exception as e:
        result["connected"] = False
        result["error_type"] = type(e).__name__
        result["error"] = redact_error(str(e))

    return result


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
    pk = "BIGSERIAL PRIMARY KEY" if mode() == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
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
            # Admin review actions — tracks accept/reject decisions per reviewer.
            f"CREATE TABLE IF NOT EXISTS review_actions (id {pk},"
            " reviewer_name TEXT NOT NULL, session_id TEXT NOT NULL,"
            " spelling TEXT NOT NULL, khmer TEXT NOT NULL,"
            " action TEXT NOT NULL, ts TIMESTAMP NOT NULL,"
            " status TEXT DEFAULT 'pending',"
            " reverted_at TIMESTAMP, reverted_by TEXT)",
            "CREATE INDEX IF NOT EXISTS conversions_expiry ON conversions (expires_at)",
            "CREATE INDEX IF NOT EXISTS corrections_pair ON corrections (spelling, expected_khmer)",
            "CREATE INDEX IF NOT EXISTS review_actions_status ON review_actions (spelling, khmer, status)",
            "CREATE INDEX IF NOT EXISTS review_actions_ts ON review_actions (ts DESC)",
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


def record_correction(session_id: str, spelling: str, expected_khmer: str, source: str) -> bool:
    """Store a user correction, unless the quality filter rejects it.

    Returns True if stored, False if rejected by the quality filter.
    Score-3 submissions are silently dropped. Score-2 submissions are stored
    with status='flagged' so the admin reviews them with a warning.
    """
    if not available():
        return False
    from api.filters import filter_submission

    score, reason = filter_submission(spelling, expected_khmer)
    if score >= 3:
        log.info("filter_rejected: %r → %r  (%s)", spelling, expected_khmer, reason)
        return False

    status = "flagged" if score >= 2 else "new"
    if status == "flagged":
        log.info("filter_flagged: %r → %r  (%s)", spelling, expected_khmer, reason)

    migrate()
    with connect() as (conn, ph):
        cur = conn.cursor()
        touch_session(cur, ph, session_id)
        cur.execute(
            f"INSERT INTO corrections (session_id, ts, spelling, expected_khmer, source, status)"
            f" VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})",
            (session_id, datetime.now(timezone.utc), spelling, expected_khmer, source, status),
        )
    return True


# The three views worth reviewing, strongest evidence first. Lives here rather than in the
# export script because both the /admin download and scripts/export_feedback.py serve it —
# two copies of this SQL would drift, and then the spreadsheet and the download would
# disagree about what the data says.
EXPORTS = {
    "overrides": (
        ["they typed", "engine put first", "they chose", "people", "times", "used"],
        "SELECT spelling, engine_top, chosen,"
        " COUNT(DISTINCT session_id) AS people, COUNT(*) AS times,"
        " SUM(CASE WHEN copied THEN 1 ELSE 0 END) AS used"
        " FROM word_choices GROUP BY spelling, engine_top, chosen"
        " ORDER BY people DESC, used DESC, times DESC LIMIT {limit}",
    ),
    "corrections": (
        ["they typed", "they say it means", "people", "times", "how"],
        "SELECT spelling, expected_khmer, COUNT(DISTINCT session_id) AS people,"
        " COUNT(*) AS times, MIN(source) AS source FROM corrections"
        " WHERE status = 'new' GROUP BY spelling, expected_khmer"
        " ORDER BY people DESC, times DESC LIMIT {limit}",
    ),
    "missing": (
        ["they typed", "people", "times"],
        "SELECT spelling, session_count, total_count FROM unknown_words"
        " WHERE status = 'new' ORDER BY session_count DESC, total_count DESC LIMIT {limit}",
    ),
}


def export_data(name: str, limit: int = 300) -> tuple[list[str], list[tuple]]:
    """(headers, rows) for one of the EXPORTS views."""
    headers, sql = EXPORTS[name]
    migrate()
    with connect() as (conn, _):
        cur = conn.cursor()
        cur.execute(sql.format(limit=int(limit)))
        return headers, cur.fetchall()


def stats() -> dict:
    """Aggregates only — never raw messages. Powers /admin."""
    if not available():
        return {"storage": mode(), "location": location()}
    migrate()
    out: dict = {"storage": mode(), "location": location()}
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
        out["recent_corrections"] = recent_corrections(cur, 50)
    return out


def recent_corrections(cur, limit: int = 50) -> list[dict]:
    """What people typed into "Missing a word?", newest first.

    Grouped by (spelling, khmer) so the same answer from five people is one row with
    `people = 5` — agreement is the whole signal — rather than five rows to read past.
    """
    cur.execute(
        "SELECT spelling, expected_khmer, COUNT(DISTINCT session_id) AS people,"
        " COUNT(*) AS times, MIN(source) AS source, MAX(ts) AS last_seen"
        " FROM corrections GROUP BY spelling, expected_khmer"
        f" ORDER BY last_seen DESC LIMIT {int(limit)}"
    )
    return [
        {
            "spelling": r[0],
            "khmer": r[1],
            "people": r[2],
            "times": r[3],
            "source": r[4],
            "last_seen": str(r[5])[:19],
        }
        for r in cur.fetchall()
    ]


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


# ---- admin review ------------------------------------------------------------------
def _latest_action(cur, ph: str, spelling: str, khmer: str) -> dict | None:
    """Most recent non-reverted action for a (spelling, khmer) pair, or None."""
    cur.execute(
        f"SELECT id, action, reviewer_name, status, ts FROM review_actions"
        f" WHERE spelling = {ph} AND khmer = {ph} AND status != 'reverted'"
        f" ORDER BY ts DESC, id DESC LIMIT 1",
        (spelling, khmer),
    )
    row = cur.fetchone()
    return (
        {"id": row[0], "action": row[1], "reviewer": row[2], "status": row[3], "ts": str(row[4])[:19]}
        if row else None
    )


def admin_queue() -> list[dict]:
    """All correction pairs with their review status, newest first.

    Returns a list where each item has spelling, khmer, people (distinct submitters),
    times (total submissions), source, last_seen, and review (action dict or None).
    """
    if not available():
        return []
    migrate()
    with connect() as (conn, ph):
        cur = conn.cursor()
        cur.execute(
            "SELECT c.spelling, c.expected_khmer, COUNT(DISTINCT c.session_id) AS people,"
            " COUNT(*) AS times, MIN(c.source) AS source, MAX(c.ts) AS last_seen,"
            " MIN(c.status) AS item_status"
            " FROM corrections c WHERE c.status IN ('new', 'flagged')"
            " GROUP BY c.spelling, c.expected_khmer"
            " ORDER BY CASE WHEN MIN(c.status) = 'flagged' THEN 1 ELSE 0 END, last_seen DESC"
        )
        rows = cur.fetchall()
        out: list[dict] = []
        for r in rows:
            spelling, khmer = r[0], r[1]
            item = {
                "spelling": spelling, "khmer": khmer,
                "people": r[2], "times": r[3],
                "source": r[4], "last_seen": str(r[5])[:19],
                "review": _latest_action(cur, ph, spelling, khmer),
                "flagged": r[6] == "flagged",
            }
            out.append(item)
        return out


def admin_act(reviewer_name: str, session_id: str, spelling: str, khmer: str,
              action: str) -> dict:
    """Accept or reject a correction pair. Returns the created action record."""
    if action not in ("accept", "reject"):
        raise ValueError(f"action must be 'accept' or 'reject', got {action!r}")
    if not available():
        return {"ok": False, "error": "storage_unavailable"}
    migrate()
    now = datetime.now(timezone.utc)
    with connect() as (conn, ph):
        cur = conn.cursor()
        # Only allow if there's no existing non-reverted action for this pair
        existing = _latest_action(cur, ph, spelling, khmer)
        if existing and existing["status"] != "reverted":
            return {"ok": False, "error": "already_reviewed", "existing": existing}
        cur.execute(
            f"INSERT INTO review_actions (reviewer_name, session_id, spelling, khmer,"
            f" action, ts, status) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, 'pending')"
            f" RETURNING id",
            (reviewer_name, session_id, spelling, khmer, action, now),
        )
        row_id = (cur.fetchone() or [None])[0]
        return {"ok": True, "id": row_id, "action": action, "spelling": spelling,
                "khmer": khmer, "reviewer": reviewer_name, "ts": str(now)[:19]}


def admin_undo(action_id: int, reviewer_name: str) -> dict:
    """Revert a review action — marks it as reverted."""
    if not available():
        return {"ok": False, "error": "storage_unavailable"}
    migrate()
    now = datetime.now(timezone.utc)
    with connect() as (conn, ph):
        cur = conn.cursor()
        cur.execute(
            f"SELECT id, action, spelling, khmer, status FROM review_actions WHERE id = {ph}",
            (action_id,),
        )
        row = cur.fetchone()
        if not row:
            return {"ok": False, "error": "not_found"}
        if row[4] == "submitted":
            return {"ok": False, "error": "already_submitted"}
        if row[4] == "reverted":
            return {"ok": False, "error": "already_reverted"}
        cur.execute(
            f"UPDATE review_actions SET status = 'reverted', reverted_at = {ph},"
            f" reverted_by = {ph} WHERE id = {ph}",
            (now, reviewer_name, action_id),
        )
        return {"ok": True, "id": action_id, "spelling": row[2], "khmer": row[3],
                "action": row[1], "reverted_by": reviewer_name}


def admin_history(limit: int = 100) -> list[dict]:
    """Recent review actions, newest first."""
    if not available():
        return []
    migrate()
    with connect() as (conn, ph):
        cur = conn.cursor()
        cur.execute(
            f"SELECT id, reviewer_name, spelling, khmer, action, ts, status,"
            f" reverted_at, reverted_by FROM review_actions"
            f" ORDER BY ts DESC, id DESC LIMIT {int(limit)}"
        )
        return [
            {"id": r[0], "reviewer": r[1], "spelling": r[2], "khmer": r[3],
             "action": r[4], "ts": str(r[5])[:19], "status": r[6],
             "reverted_at": str(r[7])[:19] if r[7] else None,
             "reverted_by": r[8]}
            for r in cur.fetchall()
        ]


def admin_accepted_for_submit() -> list[dict]:
    """Accepted items that haven't been submitted yet."""
    if not available():
        return []
    migrate()
    with connect() as (conn, ph):
        cur = conn.cursor()
        cur.execute(
            f"SELECT spelling, khmer, COUNT(DISTINCT reviewer_name) AS reviewers"
            f" FROM review_actions WHERE action = 'accept' AND status = 'pending'"
            f" GROUP BY spelling, khmer ORDER BY reviewers DESC"
        )
        return [
            {"spelling": r[0], "khmer": r[1], "reviewers": r[2]}
            for r in cur.fetchall()
        ]


def admin_mark_submitted(spelling: str, khmer: str) -> None:
    """Mark all pending accept actions for a pair as submitted."""
    if not available():
        return
    migrate()
    with connect() as (conn, ph):
        cur = conn.cursor()
        cur.execute(
            f"UPDATE review_actions SET status = 'submitted'"
            f" WHERE spelling = {ph} AND khmer = {ph} AND action = 'accept'"
            f" AND status = 'pending'",
            (spelling, khmer),
        )
