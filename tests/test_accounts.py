"""Reviewer accounts: invites, sign-in, roles, and the filter that must never delete a word."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi", reason="web app deps not installed")
from fastapi.testclient import TestClient  # noqa: E402

from api import accounts, index, security, storage  # noqa: E402
from api.admin_routes import _get_repo  # noqa: E402

ADMIN = "test-admin-token"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATABASE_URL", "")
    monkeypatch.setattr(storage, "IS_SERVERLESS", False)
    monkeypatch.setattr(storage, "SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(storage, "_MIGRATED", False)
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN)
    storage.migrate()
    security.reset_limits()
    with TestClient(index.app) as c:
        yield c


def owner(client, name="Lyheang", password="a-good-password"):
    res = client.post("/admin/api/bootstrap",
                      json={"admin_token": ADMIN, "name": name, "password": password})
    assert res.status_code == 200, res.text
    return res.json()


def invited(client, name="Dara", password="another-password"):
    """Owner issues an invite; a *separate* client redeems it into a reviewer account."""
    url = client.post("/admin/api/invite", json={}).json()["url"]
    token = url.split("invite=")[1]
    helper = TestClient(index.app)
    res = helper.post("/admin/api/join",
                      json={"invite": token, "name": name, "password": password})
    assert res.status_code == 200, res.text
    return helper, res.json()


# ---- upgrading a database that already holds data ---------------------------------------
def test_an_older_database_gains_the_new_columns(tmp_path, monkeypatch):
    """The exact failure from the deployed site: /review loaded but showed nothing.

    `CREATE TABLE IF NOT EXISTS` does nothing when the table already exists, so `flag_reason`
    was never added to a `corrections` table created by an earlier version — and the review
    queue answered 500 ("column does not exist") while working fine against a fresh database.
    """
    import sqlite3

    db = tmp_path / "old.db"
    old = sqlite3.connect(db)
    old.execute(                                    # the schema as it was before this branch
        "CREATE TABLE corrections (id INTEGER PRIMARY KEY, session_id TEXT, ts TIMESTAMP,"
        " spelling TEXT, expected_khmer TEXT, source TEXT, status TEXT DEFAULT 'new')"
    )
    old.execute(
        "INSERT INTO corrections (session_id, ts, spelling, expected_khmer, source, status)"
        " VALUES ('s1', '2026-07-28', 'nekna', 'អ្នកណា', 'form', 'new')"
    )
    old.commit()
    old.close()

    monkeypatch.setattr(storage, "DATABASE_URL", "")
    monkeypatch.setattr(storage, "IS_SERVERLESS", False)
    monkeypatch.setattr(storage, "SQLITE_PATH", str(db))
    monkeypatch.setattr(storage, "_MIGRATED", False)
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN)
    storage.migrate()

    with storage.connect() as (conn, _):
        cols = {r[1] for r in conn.cursor().execute("PRAGMA table_info(corrections)")}
    assert "flag_reason" in cols, "migrate() must add columns to tables that already exist"

    # And the endpoint that was returning 500 now works, with the pre-existing row intact.
    security.reset_limits()
    with TestClient(index.app) as c:
        owner(c)
        res = c.get("/admin/api/queue")
        assert res.status_code == 200, res.text
        assert [i["spelling"] for i in res.json()["items"]] == ["nekna"]


def test_adding_columns_is_idempotent(client):
    """migrate() runs on every cold start; the second run must be a no-op, not an error."""
    with storage.connect() as (conn, _):
        cur = conn.cursor()
        assert storage._add_missing_columns(cur) == []


# ---- passwords ------------------------------------------------------------------------
def test_passwords_are_salted_and_never_stored_in_the_clear():
    h1, s1 = accounts.hash_password("hunter2000")
    h2, s2 = accounts.hash_password("hunter2000")
    assert s1 != s2 and h1 != h2, "the same password must not produce the same hash twice"
    assert "hunter2000" not in h1
    assert accounts.verify_password("hunter2000", h1, s1)
    assert not accounts.verify_password("hunter2001", h1, s1)


# ---- bootstrap ------------------------------------------------------------------------
def test_first_account_is_the_owner_and_bootstrap_then_closes(client):
    assert client.get("/admin/api/me").json() == {"signed_in": False, "needs_bootstrap": True}
    who = owner(client)
    assert who["role"] == "owner"
    assert client.get("/admin/api/me").json()["role"] == "owner"

    # The back door shuts behind it: ADMIN_TOKEN can't mint a second account.
    again = TestClient(index.app).post(
        "/admin/api/bootstrap",
        json={"admin_token": ADMIN, "name": "Sneaky", "password": "a-good-password"},
    )
    assert again.status_code == 400 and again.json()["error"] == "already_bootstrapped"


def test_bootstrap_needs_the_admin_token(client):
    res = client.post("/admin/api/bootstrap",
                      json={"admin_token": "wrong", "name": "X", "password": "a-good-password"})
    assert res.status_code == 404
    assert accounts.count() == 0


# ---- invites --------------------------------------------------------------------------
def test_an_invite_creates_an_account_and_cannot_be_used_twice(client):
    owner(client)
    url = client.post("/admin/api/invite", json={}).json()["url"]
    token = url.split("invite=")[1]

    first = TestClient(index.app).post(
        "/admin/api/join", json={"invite": token, "name": "Dara", "password": "another-password"})
    assert first.status_code == 200 and first.json()["role"] == "reviewer"

    second = TestClient(index.app).post(
        "/admin/api/join", json={"invite": token, "name": "Bora", "password": "another-password"})
    assert second.status_code == 400 and second.json()["error"] == "invite_used"


def test_the_raw_invite_is_never_stored(client):
    owner(client)
    token = client.post("/admin/api/invite", json={}).json()["url"].split("invite=")[1]
    with storage.connect() as (conn, _):
        stored = " ".join(
            str(v) for row in conn.cursor().execute("SELECT * FROM invites") for v in row
        )
    assert token not in stored, "a database dump must not yield a usable invite"


def test_an_expired_invite_is_refused(client):
    from datetime import datetime, timedelta, timezone

    who = owner(client)
    raw = accounts.create_invite(who["id"], days=7)
    with storage.connect() as (conn, ph):
        conn.cursor().execute(
            f"UPDATE invites SET expires_at = {ph}",
            (datetime.now(timezone.utc) - timedelta(days=1),),
        )
    out = accounts.redeem_invite(raw, "Late", "another-password")
    assert out == {"ok": False, "error": "invite_expired"}


def test_a_made_up_invite_is_refused(client):
    owner(client)
    res = TestClient(index.app).post(
        "/admin/api/join",
        json={"invite": "not-a-real-invite", "name": "Nope", "password": "another-password"})
    assert res.status_code == 400 and res.json()["error"] == "bad_invite"


def test_only_the_owner_can_invite(client):
    owner(client)
    helper, _ = invited(client)
    assert helper.post("/admin/api/invite", json={}).status_code == 403
    assert TestClient(index.app).post("/admin/api/invite", json={}).status_code == 404


# ---- sessions -------------------------------------------------------------------------
def test_a_tampered_session_cookie_is_refused(client):
    owner(client)
    forged = TestClient(index.app)
    forged.cookies.set(accounts.COOKIE_NAME, "1.notarealsignature")
    assert forged.get("/admin/api/me").json()["signed_in"] is False
    assert forged.get("/admin/api/queue").status_code == 404


def test_signing_in_requires_the_right_password(client):
    owner(client, name="Lyheang", password="a-good-password")
    fresh = TestClient(index.app)
    assert fresh.post("/admin/api/login",
                      json={"name": "Lyheang", "password": "wrong"}).status_code == 401
    assert fresh.post("/admin/api/login",
                      json={"name": "Lyheang", "password": "a-good-password"}).status_code == 200
    assert fresh.get("/admin/api/me").json()["signed_in"] is True


def test_disabling_a_reviewer_locks_them_out_immediately(client):
    owner(client)
    helper, who = invited(client)
    assert helper.get("/admin/api/queue").status_code == 200

    assert client.post("/admin/api/reviewer-status",
                       json={"id": who["id"], "status": "disabled"}).json()["ok"]
    # Same cookie, still correctly signed — but status is read from the database each time.
    assert helper.get("/admin/api/queue").status_code == 404


def test_the_owner_cannot_lock_themselves_out(client):
    who = owner(client)
    res = client.post("/admin/api/reviewer-status", json={"id": who["id"], "status": "disabled"})
    assert res.status_code == 400 and res.json()["error"] == "cannot_disable_self"


# ---- what the reviewer can and can't do ------------------------------------------------
def test_actions_are_attributed_to_the_account_not_a_header(client):
    """The old dashboard took the reviewer's name from a header the browser sets itself."""
    owner(client)
    helper, who = invited(client, name="Dara")
    client.post("/api/feedback", json={"spelling": "nekna", "expected_khmer": "អ្នកណា"})

    res = helper.post(
        "/admin/api/act",
        json={"spelling": "nekna", "khmer": "អ្នកណា", "action": "accept"},
        headers={"x-reviewer-name": "Lyheang"},      # a lie the server must ignore
    )
    assert res.status_code == 200
    action = client.get("/admin/api/history").json()["actions"][0]
    assert action["reviewer"] == "Dara"
    assert action["reviewer_id"] == who["id"]


def test_a_reviewer_can_undo_their_own_decision(client):
    owner(client)
    helper, _ = invited(client)
    client.post("/api/feedback", json={"spelling": "nekna", "expected_khmer": "អ្នកណា"})

    acted = helper.post("/admin/api/act",
                        json={"spelling": "nekna", "khmer": "អ្នកណា", "action": "accept"}).json()
    assert helper.post("/admin/api/undo", json={"id": acted["id"]}).json()["ok"]


def test_the_owner_can_overturn_a_reviewers_decision(client):
    """Having the last word on what reaches the dictionary is the point of being the owner."""
    owner(client)
    helper, _ = invited(client, name="Dara")
    client.post("/api/feedback", json={"spelling": "nekna", "expected_khmer": "អ្នកណា"})

    accepted = helper.post("/admin/api/act",
                           json={"spelling": "nekna", "khmer": "អ្នកណា",
                                 "action": "accept"}).json()
    undone = client.post("/admin/api/undo", json={"id": accepted["id"]}).json()
    assert undone["ok"] and undone["reverted_by"] == "Lyheang"

    # And the other direction: a reject the owner disagrees with.
    rejected = helper.post("/admin/api/act",
                           json={"spelling": "nekna", "khmer": "អ្នកណា",
                                 "action": "reject"}).json()
    assert client.post("/admin/api/undo", json={"id": rejected["id"]}).json()["ok"]


def test_a_reviewer_cannot_undo_someone_elses_decision(client):
    """The dashboard only *hid* the button, so this ran backwards: any reviewer could revert
    the owner's decisions through the endpoint, while the owner couldn't fix a helper's."""
    owner(client)
    helper, _ = invited(client, name="Dara")
    other, _ = invited(client, name="Bora")
    client.post("/api/feedback", json={"spelling": "nekna", "expected_khmer": "អ្នកណា"})

    acted = helper.post("/admin/api/act",
                        json={"spelling": "nekna", "khmer": "អ្នកណា", "action": "accept"}).json()
    res = other.post("/admin/api/undo", json={"id": acted["id"]})
    assert res.status_code == 409 and res.json()["error"] == "not_yours"


def test_only_the_owner_can_push_to_github(client, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-token")
    owner(client)
    helper, _ = invited(client)
    assert helper.post("/admin/api/submit", json={}).status_code == 403
    assert TestClient(index.app).post("/admin/api/submit", json={}).status_code == 404


@pytest.mark.parametrize("value", [
    "SrunLyheang/sing-khmer-engine-2",
    "https://github.com/SrunLyheang/sing-khmer-engine-2",
    "https://github.com/SrunLyheang/sing-khmer-engine-2.git",
    "git@github.com:SrunLyheang/sing-khmer-engine-2.git",
])
def test_github_repo_accepts_common_formats(monkeypatch, value):
    monkeypatch.setenv("GITHUB_REPO", value)
    assert _get_repo() == ("SrunLyheang", "sing-khmer-engine-2")


def test_bad_github_repo_format_is_a_client_error(client, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-token")
    monkeypatch.setenv("GITHUB_REPO", "github.com/SrunLyheang/sing-khmer-engine-2/tree/main")
    owner(client)

    res = client.post("/admin/api/submit", json={})

    assert res.status_code == 400
    body = res.json()
    assert body["error"] == "GitHub repo is not configured correctly."
    assert "GITHUB_REPO" in body["hint"]


def test_the_queue_is_hidden_from_strangers(client):
    owner(client)
    stranger = TestClient(index.app)
    for path in ("/admin/api/queue", "/admin/api/history", "/admin/api/reviewers"):
        assert stranger.get(path).status_code == 404, path


# ---- the merged page --------------------------------------------------------------------
def test_reviewers_see_the_numbers_but_not_the_downloads(client):
    """Stats motivate a helper; the CSVs export what users typed, so they stay with the owner."""
    owner(client)
    helper, _ = invited(client)

    mine = client.get("/admin/api/stats").json()
    theirs = helper.get("/admin/api/stats").json()
    assert mine["can_download"] is True
    assert theirs["can_download"] is False
    assert "unknown_rate" in theirs and "copy_rate" in theirs

    assert client.get("/admin/export.csv", params={"what": "corrections"}).status_code == 200
    assert helper.get("/admin/export.csv", params={"what": "corrections"}).status_code == 404


def test_the_owner_downloads_with_a_session_not_a_url_secret(client):
    """The dashboard link carries no token — the cookie is the proof."""
    client.post("/api/feedback", json={"spelling": "nekna", "expected_khmer": "អ្នកណា"})
    owner(client)
    res = client.get("/admin/export.csv", params={"what": "corrections"})
    assert res.status_code == 200 and "nekna" in res.content.decode("utf-8-sig")


# ---- recovering the owner account --------------------------------------------------------
def test_admin_token_can_reset_a_lost_owner_password_but_not_create_accounts(client):
    owner(client, name="Lyheang", password="a-good-password")

    locked = TestClient(index.app)
    assert locked.post("/admin/api/login",
                       json={"name": "Lyheang", "password": "forgotten"}).status_code == 401

    res = locked.post("/admin/api/reset-owner",
                      json={"admin_token": ADMIN, "password": "a-new-password"})
    assert res.status_code == 200 and res.json()["role"] == "owner"
    assert locked.get("/admin/api/me").json()["name"] == "Lyheang"

    # It resets; it does not mint. Still exactly one account.
    assert accounts.count() == 1
    assert TestClient(index.app).post(
        "/admin/api/reset-owner", json={"admin_token": "wrong", "password": "x" * 10}
    ).status_code == 404


# ---- the filter must never destroy a word ----------------------------------------------
@pytest.mark.parametrize("spelling,khmer", [
    ("porn", "ពាន់"),      # thousand
    ("sex", "សុិច"),
    ("die", "ដៃ"),          # hand
])
def test_real_khmer_words_that_look_like_profanity_are_kept(client, spelling, khmer):
    """These are in data/vocabulary.csv. A wordlist used to delete them on arrival.

    Romanization is phonetic, so ordinary words collide with English profanity by accident.
    Losing ពាន់ ("thousand") to a regex is far worse than a human skimming a rude row.
    """
    res = client.post("/api/feedback", json={"spelling": spelling, "expected_khmer": khmer})
    assert res.status_code == 200 and res.json()["stored"] is True

    owner(client)
    queued = {(i["spelling"], i["khmer"]) for i in client.get("/admin/api/queue").json()["items"]}
    assert (spelling, khmer) in queued


def test_obvious_junk_is_flagged_but_still_kept(client):
    """Nothing is discarded — suspicious rows just sort last, with a reason attached."""
    client.post("/api/feedback", json={"spelling": "asdfgh", "expected_khmer": "អ្នកណា"})
    owner(client)
    items = client.get("/admin/api/queue").json()["items"]
    junk = [i for i in items if i["spelling"] == "asdfgh"]
    assert junk, "junk must still be stored, just flagged"
    assert junk[0]["flagged"] is True
    assert junk[0]["flag_reason"]
