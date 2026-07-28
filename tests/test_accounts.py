"""Reviewer accounts: invites, sign-in, roles, and the filter that must never delete a word."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi", reason="web app deps not installed")
from fastapi.testclient import TestClient  # noqa: E402

from api import accounts, index, security, storage  # noqa: E402

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


def test_only_the_owner_can_push_to_github(client, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-token")
    owner(client)
    helper, _ = invited(client)
    assert helper.post("/admin/api/submit", json={}).status_code == 403
    assert TestClient(index.app).post("/admin/api/submit", json={}).status_code == 404


def test_the_queue_is_hidden_from_strangers(client):
    owner(client)
    stranger = TestClient(index.app)
    for path in ("/admin/api/queue", "/admin/api/history", "/admin/api/reviewers"):
        assert stranger.get(path).status_code == 404, path


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
