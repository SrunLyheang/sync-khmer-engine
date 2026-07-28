"""Reviewer accounts — so "who accepted this word" is a fact rather than a claim.

The review dashboard originally shared one `ADMIN_TOKEN` between everyone and took the
reviewer's name from an `X-Reviewer-Name` header the browser sets itself. That makes the
attribution decorative: anyone holding the token can record actions under anyone's name, and
losing one helper means rotating the single secret for all of them.

This gives each person a real account:

* **Invites, not open sign-up.** The owner generates a single-use link that expires. Only the
  *hash* of the invite is stored, so a database dump never yields a working invite.
* **Passwords hashed with `hashlib.scrypt`** — stdlib, so no new dependency, matching the rest
  of this repo. Per-user random salt, constant-time comparison.
* **Sessions are signed server-side**, exactly like `security.issue_session`, and carry only an
  account id. A tampered cookie fails its signature; a disabled account fails on the next
  request because status is read from the database every time, not baked into the cookie.
* **The first account bootstraps from `ADMIN_TOKEN`** and becomes the owner, so there's no
  chicken-and-egg on a fresh deployment.

Roles are deliberately thin: `owner` can invite people and push to GitHub, `reviewer` can only
judge words. A write-capable GitHub token shouldn't be wielded by everyone who can review.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone

from api import security, storage

COOKIE_NAME = "sk_reviewer"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30
INVITE_DAYS = 7

# scrypt parameters. n=2**14 costs ~50ms per verify here — slow enough to make guessing
# expensive, fast enough for a login on a serverless cold start.
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}

_NAME_OK = re.compile(r"^[\w .'-]{2,40}$", re.UNICODE)
MIN_PASSWORD = 8


# ---- passwords ----------------------------------------------------------------------
def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Return (hash_hex, salt_hex). A fresh salt is generated when none is given."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **_SCRYPT)
    return digest.hex(), salt


def verify_password(password: str, hash_hex: str, salt_hex: str) -> bool:
    try:
        candidate, _ = hash_password(password, salt_hex)
    except ValueError:
        return False
    return hmac.compare_digest(candidate, hash_hex)


# ---- sessions -----------------------------------------------------------------------
def issue_cookie(reviewer_id: int) -> str:
    """A signed `id.signature` pair. Reuses the app's existing signing secret."""
    return f"{reviewer_id}.{security._sign(str(reviewer_id))}"


def parse_cookie(token: str | None) -> int | None:
    """Return the account id if the cookie is present and its signature checks out."""
    if not token or "." not in token:
        return None
    rid, _, sig = token.partition(".")
    if not rid.isdigit():
        return None
    return int(rid) if hmac.compare_digest(sig, security._sign(rid)) else None


# ---- queries ------------------------------------------------------------------------
_FIELDS = "id, name, role, status, created_at, last_seen"


def _row_to_reviewer(row) -> dict:
    return {
        "id": row[0], "name": row[1], "role": row[2], "status": row[3],
        "created_at": str(row[4])[:19], "last_seen": str(row[5])[:19] if row[5] else None,
    }


def get(reviewer_id: int) -> dict | None:
    """Load an account. Status is read here, never trusted from the cookie."""
    if not storage.available():
        return None
    storage.migrate()
    with storage.connect() as (conn, ph):
        cur = conn.cursor()
        cur.execute(f"SELECT {_FIELDS} FROM reviewers WHERE id = {ph}", (reviewer_id,))
        row = cur.fetchone()
        return _row_to_reviewer(row) if row else None


def list_all() -> list[dict]:
    if not storage.available():
        return []
    storage.migrate()
    with storage.connect() as (conn, _):
        cur = conn.cursor()
        cur.execute(f"SELECT {_FIELDS} FROM reviewers ORDER BY created_at")
        return [_row_to_reviewer(r) for r in cur.fetchall()]


def count() -> int:
    if not storage.available():
        return 0
    storage.migrate()
    with storage.connect() as (conn, _):
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM reviewers")
        return (cur.fetchone() or [0])[0]


def set_status(reviewer_id: int, status: str) -> bool:
    """Disable or re-enable an account. Takes effect on that person's next request."""
    if status not in ("active", "disabled") or not storage.available():
        return False
    storage.migrate()
    with storage.connect() as (conn, ph):
        cur = conn.cursor()
        cur.execute(
            f"UPDATE reviewers SET status = {ph} WHERE id = {ph}", (status, reviewer_id)
        )
        return bool(cur.rowcount)


def touch(reviewer_id: int) -> None:
    with storage.connect() as (conn, ph):
        conn.cursor().execute(
            f"UPDATE reviewers SET last_seen = {ph} WHERE id = {ph}",
            (datetime.now(timezone.utc), reviewer_id),
        )


# ---- creating accounts ---------------------------------------------------------------
def _insert_reviewer(cur, ph: str, name: str, password: str, role: str) -> int:
    """Insert and return the new id.

    Uses lastrowid on SQLite rather than RETURNING, which needs SQLite 3.35+ (2021) and
    would break local dev on an older interpreter.
    """
    pw_hash, salt = hash_password(password)
    sql = (
        f"INSERT INTO reviewers (name, password_hash, salt, role, status, created_at)"
        f" VALUES ({ph}, {ph}, {ph}, {ph}, 'active', {ph})"
    )
    params = (name, pw_hash, salt, role, datetime.now(timezone.utc))
    if ph == "%s":                       # postgres
        cur.execute(sql + " RETURNING id", params)
        return cur.fetchone()[0]
    cur.execute(sql, params)
    return cur.lastrowid


def validate_signup(name: str, password: str) -> str | None:
    """Return an error code, or None when the details are acceptable."""
    if not name or not _NAME_OK.match(name.strip()):
        return "bad_name"
    if len(password or "") < MIN_PASSWORD:
        return "weak_password"
    return None


def bootstrap_owner(name: str, password: str) -> dict:
    """Create the very first account, as owner. Refuses once any account exists.

    The caller must already have checked ADMIN_TOKEN — this only enforces that bootstrap
    can't be used to add a second back-door account later.
    """
    if not storage.available():
        return {"ok": False, "error": "storage_unavailable"}
    err = validate_signup(name, password)
    if err:
        return {"ok": False, "error": err}
    storage.migrate()
    with storage.connect() as (conn, ph):
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM reviewers")
        if (cur.fetchone() or [0])[0]:
            return {"ok": False, "error": "already_bootstrapped"}
        rid = _insert_reviewer(cur, ph, name.strip(), password, "owner")
    return {"ok": True, "id": rid, "name": name.strip(), "role": "owner"}


def authenticate(name: str, password: str) -> dict | None:
    """Return the account on a correct name+password, else None."""
    if not storage.available():
        return None
    storage.migrate()
    with storage.connect() as (conn, ph):
        cur = conn.cursor()
        cur.execute(
            f"SELECT id, password_hash, salt, status FROM reviewers WHERE name = {ph}",
            ((name or "").strip(),),
        )
        row = cur.fetchone()
    if not row:
        # Spend the same work as a real verify so a wrong *name* and a wrong *password*
        # don't take visibly different amounts of time.
        hash_password(password or "", secrets.token_hex(16))
        return None
    if not verify_password(password or "", row[1], row[2]):
        return None
    if row[3] != "active":
        return None
    return get(row[0])


# ---- invites --------------------------------------------------------------------------
def _invite_hash(raw: str) -> str:
    return hashlib.sha256(f"{security.SECRET_KEY}:{raw}".encode()).hexdigest()


def create_invite(created_by: int, days: int = INVITE_DAYS) -> str:
    """Generate a single-use invite and return the raw token — shown once, never stored."""
    raw = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    storage.migrate()
    with storage.connect() as (conn, ph):
        conn.cursor().execute(
            f"INSERT INTO invites (token_hash, created_by, created_at, expires_at)"
            f" VALUES ({ph}, {ph}, {ph}, {ph})",
            (_invite_hash(raw), created_by, now, now + timedelta(days=days)),
        )
    return raw


def list_invites() -> list[dict]:
    """Outstanding and spent invites — never the tokens themselves, which aren't stored."""
    if not storage.available():
        return []
    storage.migrate()
    with storage.connect() as (conn, _):
        cur = conn.cursor()
        cur.execute(
            "SELECT created_by, created_at, expires_at, used_at, used_by FROM invites"
            " ORDER BY created_at DESC LIMIT 50"
        )
        return [
            {"created_by": r[0], "created_at": str(r[1])[:19], "expires_at": str(r[2])[:19],
             "used_at": str(r[3])[:19] if r[3] else None, "used_by": r[4]}
            for r in cur.fetchall()
        ]


def redeem_invite(raw: str, name: str, password: str) -> dict:
    """Turn an invite into an account. Single use, and expired invites are refused."""
    if not storage.available():
        return {"ok": False, "error": "storage_unavailable"}
    err = validate_signup(name, password)
    if err:
        return {"ok": False, "error": err}
    storage.migrate()
    now = datetime.now(timezone.utc)
    token_hash = _invite_hash(raw or "")
    with storage.connect() as (conn, ph):
        cur = conn.cursor()
        cur.execute(
            f"SELECT expires_at, used_at FROM invites WHERE token_hash = {ph}", (token_hash,)
        )
        row = cur.fetchone()
        if not row:
            return {"ok": False, "error": "bad_invite"}
        if row[1] is not None:
            return {"ok": False, "error": "invite_used"}
        if _as_utc(row[0]) < now:
            return {"ok": False, "error": "invite_expired"}

        cur.execute(f"SELECT 1 FROM reviewers WHERE name = {ph}", (name.strip(),))
        if cur.fetchone():
            return {"ok": False, "error": "name_taken"}

        rid = _insert_reviewer(cur, ph, name.strip(), password, "reviewer")
        # Spend the invite in the same transaction that creates the account, so a crash
        # can't leave an account created with the invite still usable.
        cur.execute(
            f"UPDATE invites SET used_at = {ph}, used_by = {ph}"
            f" WHERE token_hash = {ph} AND used_at IS NULL",
            (now, rid, token_hash),
        )
        if not cur.rowcount:
            raise RuntimeError("invite was consumed concurrently")
    return {"ok": True, "id": rid, "name": name.strip(), "role": "reviewer"}


def _as_utc(value) -> datetime:
    """SQLite hands back strings where Postgres hands back datetimes."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value)).replace(tzinfo=timezone.utc)


# ---- request helper --------------------------------------------------------------------
def current(request) -> dict | None:
    """The signed-in account for a request, or None. Disabled accounts return None."""
    rid = parse_cookie(request.cookies.get(COOKIE_NAME))
    if rid is None:
        return None
    who = get(rid)
    return who if who and who["status"] == "active" else None
