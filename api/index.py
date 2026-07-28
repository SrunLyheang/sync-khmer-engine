"""Sing Khmer web app — the real engine behind a small HTTP API.

This is the deployable counterpart to `scripts/serve.py` (which stays as the
zero-dependency local tester). It wraps `sing_khmer_engine.lookup.Engine` in FastAPI so
one engine serves the browser, and records how people actually type so the vocabulary can
grow from real usage instead of hand-curated batches.

Endpoints:
    GET  /              — the web app
    POST /api/convert   — {text} -> {words[], readings[]}   (same shape as serve.py)
    POST /api/log       — batched usage events (settled text, copies)
    POST /api/feedback  — an explicit "this is wrong / here's the spelling" report
    GET  /api/health    — engine + storage status

Storage: Postgres when DATABASE_URL is set (Vercel/Neon), otherwise a local SQLite file
so the app runs on a laptop with no setup. Run locally with:

    uvicorn api.index:app --reload
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sing_khmer_engine.lookup import Engine  # noqa: E402

# Built once per cold start and reused by every warm request (~0.5s to build, 6ms/50 conversions).
ENGINE = Engine()

DATABASE_URL = os.environ.get("DATABASE_URL", "")
# Vercel's filesystem is read-only except /tmp, so the SQLite fallback lives there.
SQLITE_PATH = os.environ.get("SQLITE_PATH", "/tmp/sing_khmer.db")
MAX_TEXT = 2000          # ignore absurdly long payloads

app = FastAPI(title="Sing Khmer")


# ---- storage -----------------------------------------------------------------------
@contextmanager
def _connect():
    """Yield (connection, paramstyle) for Postgres or SQLite."""
    if DATABASE_URL:
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


def init_db() -> None:
    """Create the tables if they don't exist (safe to call repeatedly)."""
    serial = "BIGSERIAL PRIMARY KEY" if DATABASE_URL else "INTEGER PRIMARY KEY AUTOINCREMENT"
    with _connect() as (conn, _):
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS sessions ("
            " id TEXT PRIMARY KEY, created_at TIMESTAMP, consent BOOLEAN)"
        )
        cur.execute(
            f"CREATE TABLE IF NOT EXISTS events (id {serial}, session_id TEXT, ts TIMESTAMP,"
            " kind TEXT, input_text TEXT, output_text TEXT)"
        )
        cur.execute(
            f"CREATE TABLE IF NOT EXISTS feedback (id {serial}, session_id TEXT, ts TIMESTAMP,"
            " spelling TEXT, expected_khmer TEXT, note TEXT)"
        )


def _ensure_session(cur, ph: str, session_id: str) -> None:
    cur.execute(f"SELECT 1 FROM sessions WHERE id = {ph}", (session_id,))
    if cur.fetchone() is None:
        cur.execute(
            f"INSERT INTO sessions (id, created_at, consent) VALUES ({ph}, {ph}, {ph})",
            (session_id, datetime.now(timezone.utc), True),
        )


# ---- request models ----------------------------------------------------------------
class ConvertIn(BaseModel):
    text: str = Field(default="", max_length=MAX_TEXT)


class LogEvent(BaseModel):
    kind: str = "typed"                     # "typed" | "copied"
    input_text: str = Field(default="", max_length=MAX_TEXT)
    output_text: str = Field(default="", max_length=MAX_TEXT)


class LogIn(BaseModel):
    session_id: str = ""
    events: list[LogEvent] = []


class FeedbackIn(BaseModel):
    session_id: str = ""
    spelling: str = Field(default="", max_length=200)
    expected_khmer: str = Field(default="", max_length=200)
    note: str = Field(default="", max_length=500)


# ---- endpoints ---------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    # Deliberately NOT named public/ — Vercel auto-serves that folder statically, which
    # would shadow this route.
    return HTMLResponse((ROOT / "webui" / "index.html").read_text(encoding="utf-8"))


@app.post("/api/convert")
def convert(body: ConvertIn) -> JSONResponse:
    """Romanized input -> Khmer segments + whole-message alternative readings."""
    text = body.text[:MAX_TEXT]
    words = [
        {
            "token": f"{w.lead}{w.surface}{w.trail}", "core": w.surface,
            "lead": w.lead, "trail": w.trail, "space": w.space, "display": w.display,
            "candidates": [
                {"khmer": c.khmer, "score": c.score, "source": c.source} for c in w.candidates
            ],
        }
        for w in ENGINE.decode(text)
    ]
    return JSONResponse({
        "words": words,
        "readings": ENGINE.readings(text),
        "text": ENGINE.convert_sentence_text(text),
    })


@app.post("/api/log")
def log(body: LogIn) -> JSONResponse:
    """Record settled text (not keystrokes). Silently no-ops if storage is unavailable."""
    if not body.events:
        return JSONResponse({"ok": True, "stored": 0})
    session_id = body.session_id or str(uuid.uuid4())
    try:
        with _connect() as (conn, ph):
            cur = conn.cursor()
            _ensure_session(cur, ph, session_id)
            now = datetime.now(timezone.utc)
            for e in body.events:
                cur.execute(
                    f"INSERT INTO events (session_id, ts, kind, input_text, output_text)"
                    f" VALUES ({ph}, {ph}, {ph}, {ph}, {ph})",
                    (session_id, now, e.kind, e.input_text[:MAX_TEXT], e.output_text[:MAX_TEXT]),
                )
        return JSONResponse({"ok": True, "stored": len(body.events)})
    except Exception as exc:                      # logging must never break the app
        return JSONResponse({"ok": False, "error": type(exc).__name__}, status_code=200)


@app.post("/api/feedback")
def feedback(body: FeedbackIn) -> JSONResponse:
    """An explicit correction — the highest-value signal for growing the vocabulary."""
    if not body.spelling.strip():
        return JSONResponse({"ok": False, "error": "empty"}, status_code=400)
    session_id = body.session_id or str(uuid.uuid4())
    try:
        with _connect() as (conn, ph):
            cur = conn.cursor()
            _ensure_session(cur, ph, session_id)
            cur.execute(
                f"INSERT INTO feedback (session_id, ts, spelling, expected_khmer, note)"
                f" VALUES ({ph}, {ph}, {ph}, {ph}, {ph})",
                (session_id, datetime.now(timezone.utc), body.spelling.strip(),
                 body.expected_khmer.strip(), body.note.strip()),
            )
        return JSONResponse({"ok": True})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": type(exc).__name__}, status_code=200)


@app.get("/api/health")
def health() -> JSONResponse:
    try:
        with _connect() as (conn, _):
            conn.cursor().execute("SELECT 1")
        storage = "postgres" if DATABASE_URL else "sqlite"
    except Exception as exc:
        storage = f"unavailable ({type(exc).__name__})"
    return JSONResponse({
        "ok": True,
        "words": len(ENGINE.vocab),
        "spellings": len(ENGINE.index),
        "storage": storage,
    })


try:                                              # best-effort at import; never block startup
    init_db()
except Exception:
    pass


if __name__ == "__main__":                        # local convenience: python api/index.py
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
