"""Sing Khmer web app — the real engine behind a small, hardened HTTP API.

Deployable counterpart to `scripts/serve.py` (which stays as the zero-dependency local
tester). One engine serves the browser, and real usage is recorded so the vocabulary grows
from how people actually type.

    GET  /              the web app
    POST /api/convert   {text} -> {words[], readings[], text}
    POST /api/record    a finished conversion; the server re-runs the engine and derives
                        every signal itself, so the browser cannot misreport what happened
    POST /api/feedback  "this spelling should be this Khmer word"
    GET  /api/health    engine + storage status
    GET  /admin         aggregate stats, behind ADMIN_TOKEN

Run locally:  PYTHONPATH=src uvicorn api.index:app --reload
"""

from __future__ import annotations

import html
import logging
import sys
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from api import security, storage  # noqa: E402
from sing_khmer_engine.lookup import Engine  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sing_khmer.api")

# Built once per cold start, reused by every warm request (~0.5s build, ms per conversion).
ENGINE = Engine()

MAX_TEXT = 2000
app = FastAPI(title="Sing Khmer", docs_url=None, redoc_url=None, openapi_url=None)


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
    if not storage.available():
        return JSONResponse({"ok": True, "stored": False})
    source = "inline" if body.source == "inline" else "form"
    try:
        storage.record_correction(request.state.session_id, spelling, khmer, source)
    except Exception:
        log.exception("record_correction failed")
        return JSONResponse({"ok": False}, status_code=200)
    return JSONResponse({"ok": True, "stored": True})


# ---- pages --------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    # Named webui/ deliberately: Vercel serves a public/ folder statically, which would
    # shadow this route.
    return HTMLResponse((ROOT / "webui" / "index.html").read_text(encoding="utf-8"))


@app.get("/app.js")
def app_js() -> Response:
    return Response(
        (ROOT / "webui" / "app.js").read_text(encoding="utf-8"),
        media_type="application/javascript",
    )


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots() -> str:
    return "User-agent: *\nDisallow: /admin\n"


@app.get("/api/health")
def health() -> JSONResponse:
    m = storage.mode()
    return JSONResponse({
        "ok": m != "disabled",
        "status": "degraded" if m == "disabled" else "ok",
        "detail": (
            "No DATABASE_URL — data would be lost on redeploy, so writes are refused."
            if m == "disabled" else ""
        ),
        "words": len(ENGINE.vocab),
        "spellings": len(ENGINE.index),
        "storage": m,
    }, status_code=200 if m != "disabled" else 503)


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request, token: str = "") -> HTMLResponse:
    """Aggregates only — never anyone's messages."""
    if not security.admin_ok(token or request.headers.get("x-admin-token")):
        return HTMLResponse("<h1>404</h1>", status_code=404)
    s = storage.stats()
    e = html.escape

    def rows(items, cols):
        if not items:
            return "<tr><td colspan='9'>nothing yet</td></tr>"
        return "".join(
            "<tr>" + "".join(f"<td>{e(str(it[c]))}</td>" for c in cols) + "</tr>"
            for it in items
        )

    return HTMLResponse(f"""<!doctype html><meta charset="utf-8">
<meta name="robots" content="noindex"><title>Sing Khmer — stats</title>
<style>body{{font-family:system-ui;margin:2rem auto;max-width:56rem;padding:0 1rem}}
table{{border-collapse:collapse;width:100%;margin:.5rem 0 2rem}}
td,th{{border:1px solid #ddd;padding:.4rem .6rem;text-align:left;font-size:.9rem}}
th{{background:#0f766e;color:#fff}} .big{{font-size:2rem;font-weight:700}}
.card{{display:inline-block;border:1px solid #ddd;border-radius:10px;padding:.8rem 1.2rem;
margin:0 .8rem .8rem 0}}</style>
<h1>Sing Khmer — usage</h1>
<div>
  <div class="card"><div class="big">{s.get('unknown_rate', 0)}%</div>words we couldn't convert</div>
  <div class="card"><div class="big">{s.get('copy_rate', 0)}%</div>conversions copied</div>
  <div class="card"><div class="big">{s.get('sessions', 0)}</div>people</div>
  <div class="card"><div class="big">{s.get('conversions', 0)}</div>conversions</div>
  <div class="card"><div class="big">{s.get('corrections', 0)}</div>corrections sent</div>
</div>
<p><b>Words we couldn't convert</b> is the number to watch — it's the share of everything typed
that the dictionary is still missing. Sorted by how many <i>different</i> people hit each one.</p>
<table><tr><th>missing spelling</th><th>times</th><th>people</th></tr>
{rows(s.get('top_missing', []), ['spelling', 'times', 'people'])}</table>
<p><b>Words people corrected by hand</b> — the engine ranked the wrong option first. Strongest
evidence you have, because they chose it and then used it.</p>
<table><tr><th>spelling</th><th>engine said</th><th>they chose</th><th>people</th><th>times</th></tr>
{rows(s.get('top_overrides', []), ['spelling', 'engine_top', 'chosen', 'people', 'times'])}</table>
<p style="color:#666;font-size:.85rem">storage: {e(str(s.get('storage')))} · aggregates only,
no messages shown here.</p>""")


try:
    storage.migrate()
except Exception:
    log.exception("migrate failed at startup")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
