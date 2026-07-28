"""Sing Khmer web app — the real engine behind a small, hardened HTTP API.

The one and only UI: a single engine serves the browser, and real usage is recorded so the
vocabulary grows from how people actually type. (This replaced two earlier testers that each
carried a hand-synced JavaScript copy of the decoder.)

    GET  /              the web app
    POST /api/convert   {text} -> {words[], readings[], text}
    POST /api/record    a finished conversion; the server re-runs the engine and derives
                        every signal itself, so the browser cannot misreport what happened
    POST /api/feedback  "this spelling should be this Khmer word"
    GET  /api/health    engine + storage status
    GET  /review        stats + the correction review queue, behind a reviewer account
    GET  /admin         redirects to /review

Run locally:  PYTHONPATH=src uvicorn api.index:app --reload
"""

from __future__ import annotations

import csv
import io
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import (HTMLResponse, JSONResponse, PlainTextResponse,
                               RedirectResponse)
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from api import security, storage  # noqa: E402
from api.admin_routes import router as admin_router  # noqa: E402
from sing_khmer_engine.lookup import Engine  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sing_khmer.api")

# Built once per cold start, reused by every warm request (~0.5s build, ms per conversion).
ENGINE = Engine()

MAX_TEXT = 2000
app = FastAPI(title="Sing Khmer", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(admin_router)


# ---- middleware ---------------------------------------------------------------------
@app.middleware("http")
async def add_session_and_headers(request: Request, call_next):
    """Attach a signed server-issued session, and harden every response."""
    sid = security.parse_session(request.cookies.get(security.COOKIE_NAME))
    issue = None
    if sid is None:
        issue = security.issue_session()
        sid = security.parse_session(issue)
    request.state.session_id = sid

    response = await call_next(request)
    for key, value in security.SECURITY_HEADERS.items():
        response.headers[key] = value
    if issue:
        response.set_cookie(
            security.COOKIE_NAME, issue, max_age=security.COOKIE_MAX_AGE,
            httponly=True, samesite="lax", secure=request.url.scheme == "https", path="/",
        )
    return response


def _limited(request: Request, bucket: str) -> bool:
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
        request.client.host if request.client else ""
    )
    key = f"{request.state.session_id}:{security.client_key(ip)}"
    return not security.allow(bucket, key)


# ---- request models -----------------------------------------------------------------
class ConvertIn(BaseModel):
    text: str = Field(default="", max_length=MAX_TEXT)


class RecordIn(BaseModel):
    text: str = Field(default="", max_length=MAX_TEXT)
    copied: bool = False
    # {word index -> the Khmer the user picked instead of the engine's first choice}
    overrides: dict[str, str] = Field(default_factory=dict)


class FeedbackIn(BaseModel):
    spelling: str = Field(default="", max_length=60)
    expected_khmer: str = Field(default="", max_length=80)
    source: str = Field(default="form", max_length=10)


# ---- conversion ---------------------------------------------------------------------
def _decode(text: str) -> list[dict]:
    return [
        {
            "token": f"{w.lead}{w.surface}{w.trail}", "core": w.surface,
            "lead": w.lead, "trail": w.trail, "space": w.space, "display": w.display,
            "candidates": [
                {"khmer": c.khmer, "score": c.score, "source": c.source} for c in w.candidates
            ],
        }
        for w in ENGINE.decode(text)
    ]


@app.post("/api/convert")
def convert(body: ConvertIn, request: Request) -> JSONResponse:
    if _limited(request, "convert"):
        return JSONResponse({"error": "slow_down"}, status_code=429)
    text = body.text[:MAX_TEXT]
    return JSONResponse({
        "words": _decode(text),
        "readings": ENGINE.readings(text),
        "text": ENGINE.convert_sentence_text(text),
    })


@app.post("/api/record")
def record(body: RecordIn, request: Request) -> JSONResponse:
    """Record a finished conversion.

    The browser sends only what it cannot lie about usefully — the text, whether the user
    copied, and which words they overrode. Everything else (what the engine originally
    chose, which words failed, what counts as confirmed) is recomputed here.
    """
    if _limited(request, "log"):
        return JSONResponse({"ok": False, "error": "slow_down"}, status_code=429)
    text = body.text[:MAX_TEXT].strip()
    if not text or not storage.available():
        return JSONResponse({"ok": True, "stored": False})

    words = _decode(text)
    unknown: list[str] = []
    choices: list[dict] = []
    confirmed: list[dict] = []
    token_count = 0

    for i, w in enumerate(words):
        if w["space"] or not w["core"].strip():
            continue
        token_count += 1
        spelling = (w["core"] or "").strip().lower()
        if not w["candidates"]:
            if security.clean_spelling(spelling):
                unknown.append(spelling)
            continue
        engine_top = w["candidates"][0]["khmer"]
        picked = body.overrides.get(str(i))
        if picked and picked != engine_top:
            # Only trust an override that is one of the options we actually offered.
            if any(c["khmer"] == picked for c in w["candidates"]):
                choices.append(
                    {"spelling": spelling, "engine_top": engine_top, "chosen": picked}
                )
                confirmed.append({"spelling": spelling, "khmer": picked})
                continue
        confirmed.append({"spelling": spelling, "khmer": engine_top})

    try:
        storage.record_conversion(
            request.state.session_id,
            input_text=text,
            output_text=ENGINE.convert_sentence_text(text),
            token_count=token_count,
            unknown=unknown,
            choices=choices,
            confirmations=confirmed,
            copied=bool(body.copied),
        )
    except Exception:
        log.exception("record_conversion failed")     # logged server-side, quiet to client
        return JSONResponse({"ok": False}, status_code=200)
    return JSONResponse({"ok": True, "stored": True})


@app.post("/api/feedback")
def feedback(body: FeedbackIn, request: Request) -> JSONResponse:
    """An explicit correction. Junk is rejected before it can pollute the dataset."""
    if _limited(request, "feedback"):
        return JSONResponse({"ok": False, "error": "slow_down"}, status_code=429)
    spelling = security.clean_spelling(body.spelling)
    khmer = security.clean_khmer(body.expected_khmer)
    if not spelling:
        return JSONResponse({"ok": False, "error": "bad_spelling"}, status_code=400)
    if not khmer:
        return JSONResponse({"ok": False, "error": "need_khmer"}, status_code=400)
    # Say so, rather than thanking someone for a word that went nowhere. This used to answer
    # {"ok": true, "stored": false} with a 200, so a degraded deployment looked like it was
    # collecting data when nothing was being written.
    if not storage.available():
        return JSONResponse({"ok": False, "error": "not_stored"}, status_code=503)
    source = "inline" if body.source == "inline" else "form"
    try:
        storage.record_correction(request.state.session_id, spelling, khmer, source)
    except Exception:
        log.exception("record_correction failed")
        return JSONResponse({"ok": False, "error": "not_stored"}, status_code=500)
    return JSONResponse({"ok": True, "stored": True})


# ---- pages --------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    # Named webui/ deliberately: Vercel serves a public/ folder statically, which would
    # shadow this route.
    return HTMLResponse((ROOT / "webui" / "index.html").read_text(encoding="utf-8"))


# A fixed table, not a path parameter: the browser never gets to name a file, so there is
# no traversal surface. Adding an asset means adding a line here.
STATIC = {
    "/app.js": ("app.js", "application/javascript"),
    "/i18n.js": ("i18n.js", "application/javascript"),
    "/speed-insights.js": ("speed-insights.js", "application/javascript"),
    "/styles.css": ("styles.css", "text/css"),
    "/admin.js": ("admin.js", "application/javascript"),
}


def _serve_static(filename: str, media_type: str):
    def handler() -> Response:
        return Response(
            (ROOT / "webui" / filename).read_text(encoding="utf-8"),
            media_type=media_type,
        )

    return handler


for _route, (_filename, _media_type) in STATIC.items():
    app.get(_route)(_serve_static(_filename, _media_type))


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots() -> str:
    return "User-agent: *\nDisallow: /admin\n"


@app.get("/api/health")
def health() -> JSONResponse:
    diag = storage.diagnose()
    m = diag["storage"]
    is_ok = diag["connected"]

    detail = ""
    if m == "disabled":
        detail = (
            "No database environment variable set — data would be lost on redeploy, "
            "so writes are refused."
        )
    elif not is_ok:
        detail = diag.get("error") or "Database connection failed."

    res = {
        "ok": is_ok,
        "status": "ok" if is_ok else "degraded",
        "detail": detail,
        "words": len(ENGINE.vocab),
        "spellings": len(ENGINE.index),
        "storage": m,
        "location": diag["location"],   # where to go looking for the rows
        # Unset on serverless means every instance signs with its own key: random sign-outs
        # and invite links that can't be redeemed. Surface it rather than leaving it to be
        # discovered as flakiness.
        "secret_key_set": not security.SECRET_KEY_IS_EPHEMERAL,
        "connected": is_ok,
        "env_var": diag["env_var"],
        "tables": diag["tables"],
        "tables_exist": diag["tables_exist"],
    }
    if diag["env_var"] is None:
        res["checked_env_vars"] = diag["checked_env_vars"]
    if not is_ok:
        res["error_type"] = diag["error_type"]
        res["error"] = diag["error"]

    return JSONResponse(res, status_code=200 if is_ok else 503)


def _csv_safe(value) -> str:
    """Neutralise spreadsheet formulas before a cell reaches Excel.

    Cells come from whatever visitors typed, and `security.clean_spelling` allows `+` and `-`,
    so a spelling like `=cmd|'/c calc'!A1` would otherwise *execute* when this download is
    opened. A leading apostrophe makes Excel treat it as text.
    """
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@app.get("/admin/export.csv")
def admin_export(request: Request, token: str = "", what: str = "corrections") -> Response:
    """Download one view as CSV — the way to get this data into a spreadsheet or an editor.

    Owner only, by either route: the signed-in session (how the dashboard's link works) or
    ADMIN_TOKEN as a header (so `scripts/` and any automation keep working). These export
    what users actually typed, so an invited reviewer doesn't get them.

    A caller who is neither gets a 404, so the route doesn't announce that it exists.
    """
    from api import accounts

    if not (accounts.is_owner(request)
            or security.admin_ok(token or request.headers.get("x-admin-token"))):
        return PlainTextResponse("404", status_code=404)
    if what not in storage.EXPORTS:
        return PlainTextResponse("unknown export", status_code=400)
    if not storage.available():
        return PlainTextResponse("storage unavailable", status_code=503)

    headers, rows = storage.export_data(what)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows([_csv_safe(c) for c in row] for row in rows)

    # A BOM, because without one Excel and Sheets read the file as latin-1 and turn the Khmer
    # column — the only column that matters — into mojibake.
    body = "﻿" + buf.getvalue()
    day = datetime.now(timezone.utc).date().isoformat()
    return Response(
        body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="sing-khmer-{what}-{day}.csv"'},
    )


@app.get("/admin")
def admin_redirect() -> Response:
    """The stats page and the review queue are one page now, at /review.

    Kept as a redirect so existing links and bookmarks still land somewhere useful — and
    without the `?token=` it used to need, since the dashboard authenticates with an account.
    """
    return RedirectResponse("/review", status_code=302)


# The review dashboard lives beside the stats page, not on top of it. The unknown-word rate
# above is the one number that answers "is the dictionary good enough yet" — it shouldn't
# disappear to make room for the queue. Auth for these pages happens in the page itself:
# the HTML is a shell, and every /admin/api/* call requires a signed-in account.
@app.get("/review", response_class=HTMLResponse)
@app.get("/review/join", response_class=HTMLResponse)
def review_page() -> HTMLResponse:
    return HTMLResponse((ROOT / "webui" / "admin.html").read_text(encoding="utf-8"))


try:
    storage.migrate()
except Exception:
    log.exception("migrate failed at startup")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
