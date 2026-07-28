"""Security helpers: sessions, rate limiting, input validation, response headers.

Design notes worth knowing:

* **Sessions are issued by the server**, signed with `SECRET_KEY`, and delivered in an
  HttpOnly cookie. The browser can no longer invent an id or write into someone else's
  session — which also means the collected data can be trusted to be per-person.
* **IPs are never stored.** Rate limiting keys on a daily-rotated salted hash, so it can
  count requests without retaining anything that identifies a visitor.
* **Rate limiting is in-process**, so on serverless each instance keeps its own counters —
  it blunts accidental floods and casual abuse, but it is not a hard guarantee. A shared
  store (Redis/Postgres) would be the upgrade if this ever goes properly public.
* **Validation rejects junk at the door**: a Khmer correction must actually contain Khmer,
  a spelling must actually look like a spelling. Bad data never reaches the dataset.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import time
import unicodedata
import uuid
from collections import defaultdict, deque

SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    # Ephemeral fallback: sessions simply don't survive a restart. Set SECRET_KEY in
    # production (see DEPLOY.md) so returning visitors keep the same id.
    SECRET_KEY = secrets.token_hex(32)

COOKIE_NAME = "sk_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 180


# ---- sessions ----------------------------------------------------------------------
def _sign(value: str) -> str:
    return hmac.new(SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()[:32]


def issue_session() -> str:
    sid = uuid.uuid4().hex
    return f"{sid}.{_sign(sid)}"


def parse_session(token: str | None) -> str | None:
    """Return the session id if the cookie is present and its signature checks out."""
    if not token or "." not in token:
        return None
    sid, _, sig = token.partition(".")
    if not re.fullmatch(r"[0-9a-f]{32}", sid):
        return None
    return sid if hmac.compare_digest(sig, _sign(sid)) else None


# ---- client key (for rate limiting only; never stored) ------------------------------
def client_key(ip: str | None) -> str:
    """A salted, daily-rotating hash of the IP. Not reversible, not persisted."""
    day = int(time.time() // 86400)
    return hashlib.sha256(f"{SECRET_KEY}:{day}:{ip or ''}".encode()).hexdigest()[:16]


# ---- rate limiting ------------------------------------------------------------------
_hits: dict[str, deque[float]] = defaultdict(deque)
_LIMITS = {                      # endpoint -> (max requests, window seconds)
    "convert": (120, 60),
    "log": (60, 60),
    "feedback": (20, 300),
    "login": (10, 300),          # a scrypt verify costs ~50ms; this caps guessing regardless
}


def allow(bucket: str, key: str) -> bool:
    limit, window = _LIMITS.get(bucket, (60, 60))
    now = time.time()
    q = _hits[f"{bucket}:{key}"]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    if len(_hits) > 10_000:      # bound memory on a long-lived process
        for k in [k for k, v in list(_hits.items())[:2000] if not v]:
            _hits.pop(k, None)
    return True


def reset_limits() -> None:
    _hits.clear()


# ---- validation ---------------------------------------------------------------------
_KHMER = re.compile(r"[ក-៿]")
_SPELLING_OK = re.compile(r"^[a-z0-9'+ -]{1,60}$")


def clean_spelling(text: str) -> str | None:
    """A romanized spelling: latin letters and the few marks people actually type."""
    t = " ".join((text or "").strip().lower().split())
    t = re.sub(r"^[^\w+]+|[^\w+]+$", "", t)
    return t if t and _SPELLING_OK.fullmatch(t) else None


def clean_khmer(text: str) -> str | None:
    """Must genuinely contain Khmer script — blocks junk and accidental latin answers."""
    # Normalize unicode (NFC) & strip zero-width and invisible control characters commonly inserted by Khmer IMEs
    t = unicodedata.normalize("NFC", text or "")
    t = re.sub(r"[\u200b\u200c\u200d\ufeff\u200e\u200f]", "", t)
    t = " ".join(t.strip().split())
    if not t or len(t) > 80 or not _KHMER.search(t):
        return None
    if "<" in t or ">" in t:
        return None
    return t


# ---- response headers ---------------------------------------------------------------
# Allow Google Fonts (css from fonts.googleapis.com, font files from fonts.gstatic.com)
CSP = (
    "default-src 'none'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "connect-src 'self'; "
    "img-src 'self' data:; "
    "font-src 'self' https://fonts.gstatic.com; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-ancestors 'none'"
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), interest-cohort=()",
}


def admin_ok(token: str | None) -> bool:
    """Constant-time check of the admin token. No token configured = admin disabled."""
    expected = os.environ.get("ADMIN_TOKEN", "")
    return bool(expected) and bool(token) and hmac.compare_digest(token, expected)
