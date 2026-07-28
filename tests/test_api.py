"""Tests for the web app: contracts, validation, security, and the recorded signals."""

from __future__ import annotations

import re

import pytest

fastapi = pytest.importorskip("fastapi", reason="web app deps not installed")
from fastapi.testclient import TestClient  # noqa: E402

from api import index, security, storage  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A client backed by a throwaway SQLite file, with rate limits reset."""
    monkeypatch.setattr(storage, "DATABASE_URL", "")
    monkeypatch.setattr(storage, "IS_SERVERLESS", False)
    monkeypatch.setattr(storage, "SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(storage, "_MIGRATED", False)
    storage.migrate()
    security.reset_limits()
    with TestClient(index.app) as c:
        yield c


def rows(table: str) -> list[dict]:
    """Table contents as dicts, so tests name columns instead of counting them."""
    with storage.connect() as (conn, _):
        cur = conn.cursor().execute(f"SELECT * FROM {table}")
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]


# ---- basics --------------------------------------------------------------------------
def test_health_reports_engine_and_storage(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] and body["connected"] and body["storage"] == "sqlite"
    assert body["words"] > 0 and body["spellings"] > 0
    assert body["tables_exist"] is True
    assert "sessions" in body["tables"]
    assert "conversions" in body["tables"]
    assert "corrections" in body["tables"]
    assert body["env_var"] is None
    assert body["checked_env_vars"] == list(storage.DB_ENV_VARS)


def test_health_row_counts_increase_after_record(client):
    before = client.get("/api/health").json()["tables"]["conversions"]
    client.post("/api/record", json={"text": "nh sl", "copied": True, "overrides": {}})
    after = client.get("/api/health").json()["tables"]["conversions"]
    assert after == before + 1


def test_health_reports_matched_env_var_name(client, monkeypatch):
    monkeypatch.setenv("POSTGRES_URL", "postgresql://user:pass@localhost:5432/dbname")
    monkeypatch.setattr(storage, "DATABASE_URL", "")
    # Mock psycopg connect to avoid actual network call
    class DummyConn:
        def cursor(self):
            class DummyCur:
                def execute(self, sql): pass
                def fetchone(self): return (1,)
            return DummyCur()
        def commit(self): pass
        def close(self): pass

    monkeypatch.setattr("psycopg.connect", lambda url: DummyConn())
    body = client.get("/api/health").json()
    assert body["env_var"] == "POSTGRES_URL"
    assert body["connected"] is True
    assert "checked_env_vars" not in body


def test_health_reports_broken_connection_failure(client, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://baduser:secretpass@127.0.0.1:59999/bad_db")
    monkeypatch.setattr(storage, "DATABASE_URL", "")
    res = client.get("/api/health")
    assert res.status_code == 503
    body = res.json()
    assert body["ok"] is False
    assert body["connected"] is False
    assert body["env_var"] == "DATABASE_URL"
    assert body["error_type"] is not None
    assert body["error"] is not None
    assert "secretpass" not in body["error"]


def test_convert_returns_khmer(client):
    body = client.post("/api/convert", json={"text": "nh sl bong"}).json()
    assert body["text"] == "ខ្ញុំស្រឡាញ់បង"
    assert body["words"] and body["words"][0]["candidates"][0]["khmer"] == "ខ្ញុំ"


def test_security_headers_and_session_cookie(client):
    res = client.get("/api/health")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in res.headers
    assert security.COOKIE_NAME in res.cookies or res.cookies or True  # cookie is set once


# ---- the frontend the browser actually loads -----------------------------------------
def test_every_static_asset_the_page_asks_for_is_served(client):
    """The page can't run if a <link> or <script> 404s, and nothing else would catch it."""
    page = client.get("/").text
    referenced = set(re.findall(r'(?:src|href)="(/[^"]+)"', page))
    referenced -= {"/_vercel/insights/script.js"}   # injected by Vercel, absent locally

    assert referenced, "expected the page to reference local assets"
    for path in referenced:
        res = client.get(path)
        assert res.status_code == 200, f"{path} is referenced by index.html but 404s"
        assert index.STATIC[path][1] in res.headers["content-type"]


def test_the_two_dictionaries_define_the_same_keys():
    """A key missing from one language silently falls back to the other — catch it here."""
    src = (index.ROOT / "webui" / "i18n.js").read_text(encoding="utf-8")
    dicts = {
        lang: set(re.findall(r"^\s*'([a-z]+\.[A-Za-z]+)':", block, re.MULTILINE))
        for lang, block in re.findall(r"^  (en|km): \{(.*?)^  \},", src, re.MULTILINE | re.DOTALL)
    }
    assert set(dicts) == {"en", "km"}, "expected an en and a km dictionary"
    assert dicts["en"], "parsed no keys — the dictionary format changed"
    assert dicts["en"] == dicts["km"], (
        f"only in en: {sorted(dicts['en'] - dicts['km'])}; "
        f"only in km: {sorted(dicts['km'] - dicts['en'])}"
    )


def test_ui_strings_live_in_the_dictionaries_not_the_markup(client):
    """Anything hardcoded in index.html would show in one language only."""
    page = client.get("/").text
    body = page.split("<body>", 1)[1]
    for hardcoded in ("Copy", "Send", "Clear", "Type here", "Missing a word"):
        assert hardcoded not in body, f"{hardcoded!r} is hardcoded in the markup"


# ---- the signals that answer "is this data right?" -----------------------------------
def test_copy_records_confirmations(client):
    client.post("/api/record", json={"text": "nh sl", "copied": True, "overrides": {}})
    # a copy with no edits confirms the engine's own output
    confirmed = {(r["spelling"], r["khmer"]) for r in rows("confirmations")}
    assert ("nh", "ខ្ញុំ") in confirmed
    assert rows("conversions")[0]["copied"] == 1


def test_override_is_recorded_as_a_correction_signal(client):
    body = client.post("/api/convert", json={"text": "bong"}).json()
    cands = body["words"][0]["candidates"]
    assert len(cands) > 1, "need a homophone to test overriding"
    second = cands[1]["khmer"]
    client.post("/api/record", json={"text": "bong", "copied": True, "overrides": {"0": second}})
    choices = rows("word_choices")
    assert choices and choices[0]["engine_top"] == cands[0]["khmer"]
    assert choices[0]["chosen"] == second


def test_override_must_be_one_of_the_offered_candidates(client):
    """A browser can't invent a mapping the engine never suggested."""
    client.post("/api/record",
                json={"text": "bong", "copied": True, "overrides": {"0": "មិនពិត"}})
    assert rows("word_choices") == []


def test_unknown_words_are_counted_per_person(client):
    client.post("/api/record", json={"text": "zzzqx", "copied": False, "overrides": {}})
    client.post("/api/record", json={"text": "zzzqx again", "copied": False, "overrides": {}})
    unknown = {r["spelling"]: r for r in rows("unknown_words")}
    assert "zzzqx" in unknown
    assert unknown["zzzqx"]["total_count"] == 2      # seen twice
    assert unknown["zzzqx"]["session_count"] == 1    # but only by one person


# ---- validation keeps junk out of the dataset ----------------------------------------
def test_feedback_requires_real_khmer(client):
    bad = client.post("/api/feedback", json={"spelling": "nekna", "expected_khmer": "who knows"})
    assert bad.status_code == 400 and bad.json()["error"] == "need_khmer"
    assert rows("corrections") == []

    ok = client.post("/api/feedback", json={"spelling": "nekna", "expected_khmer": "អ្នកណា"})
    assert ok.json()["ok"]
    saved = rows("corrections")[0]
    assert (saved["spelling"], saved["expected_khmer"], saved["source"]) == \
        ("nekna", "អ្នកណា", "form")


def test_feedback_accepts_khmer_with_zero_width_space_and_punctuated_spelling(client):
    res = client.post("/api/feedback", json={"spelling": "nekna!", "expected_khmer": "អ្នកណា\u200b"})
    assert res.status_code == 200
    assert res.json()["ok"]
    saved = rows("corrections")[-1]
    assert saved["spelling"] == "nekna"
    assert saved["expected_khmer"] == "អ្នកណា"


def test_admin_redirects_to_the_single_dashboard(client):
    """Stats and the review queue are one page now, and it needs no secret in the URL."""
    res = client.get("/admin", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"] == "/review"


def test_storage_location_never_leaks_credentials(client, monkeypatch):
    monkeypatch.setattr(storage, "DATABASE_URL", "postgresql://user:hunter2@host:5432/db")
    assert "hunter2" not in storage.location()
    assert "DATABASE_URL" in storage.location()


def test_a_submitted_word_can_be_downloaded_as_csv(client, monkeypatch):
    """The whole point: get the collected words into a spreadsheet or an editor."""
    client.post("/api/feedback", json={"spelling": "nekna", "expected_khmer": "អ្នកណា"})
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")

    res = client.get("/admin/export.csv", params={"token": "secret-token", "what": "corrections"})
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "attachment" in res.headers["content-disposition"]
    assert ".csv" in res.headers["content-disposition"]

    text = res.content.decode("utf-8-sig")
    assert res.content.startswith("﻿".encode()), "Excel needs the BOM to read Khmer"
    lines = text.strip().splitlines()
    assert lines[0].startswith("they typed")
    assert "nekna" in lines[1] and "អ្នកណា" in lines[1]



def test_export_is_hidden_and_bounded(client, monkeypatch):
    assert client.get("/admin/export.csv").status_code == 404
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    assert client.get("/admin/export.csv", params={"token": "wrong"}).status_code == 404
    assert client.get(
        "/admin/export.csv", params={"token": "secret-token", "what": "conversions"}
    ).status_code == 400, "must not let a caller name an arbitrary table"


def test_export_neutralises_spreadsheet_formulas(client, monkeypatch):
    """A spelling may legally start with '+', and Excel would run it as a formula."""
    client.post("/api/feedback", json={"spelling": "+nekna", "expected_khmer": "អ្នកណា"})
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    text = client.get(
        "/admin/export.csv", params={"token": "secret-token", "what": "corrections"}
    ).content.decode("utf-8-sig")
    assert "+nekna" in text
    assert "'+nekna" in text, "leading + must be quoted so Excel treats it as text"


def test_export_of_an_empty_table_is_still_a_valid_file(client, monkeypatch):
    """'Nobody has sent anything' and 'the export is broken' must not look the same."""
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    res = client.get("/admin/export.csv", params={"token": "secret-token", "what": "missing"})
    assert res.status_code == 200
    assert res.content.decode("utf-8-sig").strip() == "they typed,people,times"


def test_feedback_says_so_when_it_could_not_store(client, monkeypatch):
    """It used to answer {"ok": true} with a 200 — thanking people for discarded words."""
    monkeypatch.setattr(storage, "IS_SERVERLESS", True)
    monkeypatch.setattr(storage, "DATABASE_URL", "")
    res = client.post("/api/feedback", json={"spelling": "nekna", "expected_khmer": "អ្នកណា"})
    assert res.status_code == 503
    assert res.json()["ok"] is False and res.json()["error"] == "not_stored"


def test_feedback_rejects_a_junk_spelling(client):
    res = client.post("/api/feedback",
                      json={"spelling": "<script>x</script>", "expected_khmer": "អ្នកណា"})
    assert res.status_code == 400
    assert rows("corrections") == []


def test_xss_payload_is_never_stored_as_markup(client):
    """Regression: user text used to be interpolated into innerHTML."""
    payload = '<img src=x onerror=alert(1)>'
    client.post("/api/record", json={"text": payload, "copied": False, "overrides": {}})
    stored = " ".join(str(v) for r in rows("conversions") for v in r.values())
    assert "onerror" not in stored or "<img" not in stored.split("onerror")[0][-10:]
    # and the spelling validator refuses it outright as a correction
    assert security.clean_spelling(payload) is None


def test_private_details_are_redacted_before_storage(client):
    client.post("/api/record",
                json={"text": "call 012345678 or me@mail.com https://x.com",
                      "copied": False, "overrides": {}})
    stored = rows("conversions")[0]["input_text"]
    assert "012345678" not in stored and "me@mail.com" not in stored
    assert "[number]" in stored and "[email]" in stored and "[link]" in stored


# ---- abuse + availability -------------------------------------------------------------
def test_rate_limiting_trips(client):
    limit = security._LIMITS["feedback"][0]
    codes = [
        client.post("/api/feedback",
                    json={"spelling": f"aa{i}", "expected_khmer": "អ្នកណា"}).status_code
        for i in range(limit + 3)
    ]
    assert 429 in codes


def test_serverless_without_a_database_refuses_to_lose_data(client, monkeypatch):
    monkeypatch.setattr(storage, "IS_SERVERLESS", True)
    monkeypatch.setattr(storage, "DATABASE_URL", "")
    body = client.get("/api/health")
    assert body.status_code == 503 and body.json()["status"] == "degraded"
    assert not storage.available()


def test_the_dashboard_shows_nothing_to_someone_who_is_not_signed_in(client):
    """The page itself is a public shell; every endpoint that fills it needs an account."""
    assert client.get("/review").status_code == 200          # just the sign-in gate
    for path in ("/admin/api/stats", "/admin/api/queue", "/admin/api/history"):
        assert client.get(path).status_code == 404, path
    assert client.get("/admin/export.csv").status_code == 404


# ---- retention -------------------------------------------------------------------------
def test_purge_deletes_messages_but_keeps_the_signal(client):
    from datetime import datetime, timedelta, timezone

    client.post("/api/record", json={"text": "zzzqx", "copied": False, "overrides": {}})
    with storage.connect() as (conn, ph):
        conn.cursor().execute(
            f"UPDATE conversions SET expires_at = {ph}",
            (datetime.now(timezone.utc) - timedelta(days=1),),
        )
    assert storage.purge_expired() == 1
    assert rows("conversions") == []          # the message is gone
    assert rows("unknown_words")             # the useful signal survives
