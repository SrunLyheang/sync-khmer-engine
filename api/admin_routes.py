"""Review dashboard API — correction queue, accept/reject, GitHub PR submission.

Every route requires a signed-in account (see `api/accounts.py`). Two things changed from the
first version of this file, both because it is about to be used by real people:

* **No shared token, and no self-declared name.** Authentication was a single `ADMIN_TOKEN`
  read from the *query string* — so it leaked into browser history, server logs and `Referer`
  headers — and the reviewer's identity came from an `X-Reviewer-Name` header the browser sets
  itself, which made "who accepted this word" unverifiable. Both are now the signed session
  cookie, which the browser cannot forge and the reviewer cannot choose.
* **Only the owner can push to GitHub.** `/submit` wields a repo-write token; that shouldn't be
  reachable by everyone who can review a word.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api import accounts, security, storage

log = logging.getLogger("sing_khmer.admin")

router = APIRouter(prefix="/admin/api")

# Unauthenticated callers get a 404, not a 401: the dashboard shouldn't confirm it exists.
_NOT_FOUND = JSONResponse({"error": "not_found"}, status_code=404)


def _guard(request: Request) -> dict | None:
    """The signed-in account, or None. Disabled accounts count as signed out."""
    return accounts.current(request)


def _owner(request: Request) -> dict | None:
    who = accounts.current(request)
    return who if who and who["role"] == "owner" else None


def _sid(request: Request) -> str:
    return getattr(request.state, "session_id", "anon")


# ---- accounts ------------------------------------------------------------------------
def _sign_in(payload: dict, reviewer_id: int, secure: bool) -> JSONResponse:
    res = JSONResponse(payload)
    res.set_cookie(
        accounts.COOKIE_NAME, accounts.issue_cookie(reviewer_id),
        max_age=accounts.COOKIE_MAX_AGE, httponly=True, samesite="lax",
        secure=secure, path="/",
    )
    return res


async def _json(request: Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


def _needs_owner(request: Request):
    """403 for a signed-in non-owner, 404 for a stranger. None when the caller is the owner."""
    if _owner(request):
        return None
    if _guard(request):
        return JSONResponse({"ok": False, "error": "owner_only"}, status_code=403)
    return _NOT_FOUND


@router.post("/bootstrap")
async def bootstrap(request: Request):
    """Create the first account, as owner, using ADMIN_TOKEN.

    Only works while no account exists, so it can't be used to add a back door later.
    """
    body = await _json(request)
    if not security.admin_ok(body.get("admin_token", "")):
        return _NOT_FOUND
    result = accounts.bootstrap_owner(body.get("name", ""), body.get("password", ""))
    if not result.get("ok"):
        return JSONResponse(result, status_code=400)
    return _sign_in(result, result["id"], request.url.scheme == "https")


@router.post("/join")
async def join(request: Request):
    """Redeem an invite link into a reviewer account."""
    if not security.allow("login", _sid(request)):
        return JSONResponse({"ok": False, "error": "slow_down"}, status_code=429)
    body = await _json(request)
    result = accounts.redeem_invite(
        body.get("invite", ""), body.get("name", ""), body.get("password", "")
    )
    if not result.get("ok"):
        return JSONResponse(result, status_code=400)
    return _sign_in(result, result["id"], request.url.scheme == "https")


@router.post("/login")
async def login(request: Request):
    if not security.allow("login", _sid(request)):
        return JSONResponse({"ok": False, "error": "slow_down"}, status_code=429)
    body = await _json(request)
    who = accounts.authenticate(body.get("name", ""), body.get("password", ""))
    if not who:
        # One message for a wrong name and a wrong password: saying which was wrong tells an
        # attacker which names are real.
        return JSONResponse({"ok": False, "error": "bad_login"}, status_code=401)
    accounts.touch(who["id"])
    return _sign_in({"ok": True, **who}, who["id"], request.url.scheme == "https")


@router.post("/reset-owner")
async def reset_owner(request: Request):
    """Set a new password on the owner account, proven by ADMIN_TOKEN.

    The way back in if the owner password is lost. Deliberately only *resets* — it can't
    create an account, so it never becomes a second door.
    """
    body = await _json(request)
    if not security.admin_ok(body.get("admin_token", "")):
        return _NOT_FOUND
    result = accounts.reset_owner_password(body.get("password", ""))
    if not result.get("ok"):
        return JSONResponse(result, status_code=400)
    return _sign_in(result, result["id"], request.url.scheme == "https")


@router.post("/logout")
def logout():
    res = JSONResponse({"ok": True})
    res.delete_cookie(accounts.COOKIE_NAME, path="/")
    return res


@router.get("/me")
def me(request: Request):
    """Who am I, and does an owner exist yet? Decides what the dashboard shows first."""
    who = _guard(request)
    if not who:
        return JSONResponse({"signed_in": False, "needs_bootstrap": accounts.count() == 0})
    return JSONResponse({"signed_in": True, **who})


@router.post("/invite")
def invite(request: Request):
    """Owner generates a single-use link. The token is shown once and never stored raw."""
    denied = _needs_owner(request)
    if denied:
        return denied
    if not accounts.invites_usable():
        return JSONResponse({
            "ok": False, "error": "no_secret_key",
            "detail": "Set SECRET_KEY in the deployment — without it an invite created on "
                      "one serverless instance can't be redeemed on another.",
        }, status_code=503)
    who = _owner(request)
    raw = accounts.create_invite(who["id"])
    base = str(request.base_url).rstrip("/")
    return JSONResponse({
        "ok": True,
        "url": f"{base}/review/join?invite={raw}",
        "expires_days": accounts.INVITE_DAYS,
    })


@router.get("/reviewers")
def reviewers(request: Request):
    denied = _needs_owner(request)
    if denied:
        return denied
    return JSONResponse({"reviewers": accounts.list_all(), "invites": accounts.list_invites()})


@router.post("/reviewer-status")
async def reviewer_status(request: Request):
    """Disable or re-enable a helper. Takes effect on their next request."""
    denied = _needs_owner(request)
    if denied:
        return denied
    body = await _json(request)
    target, status = body.get("id"), body.get("status", "")
    if not isinstance(target, int) or status not in ("active", "disabled"):
        return JSONResponse({"ok": False, "error": "bad_input"}, status_code=400)
    if target == _owner(request)["id"]:
        return JSONResponse({"ok": False, "error": "cannot_disable_self"}, status_code=400)
    return JSONResponse({"ok": accounts.set_status(target, status)})


@router.get("/stats")
def stats(request: Request):
    """Usage aggregates for the merged dashboard — counts and spellings, never messages.

    Any signed-in reviewer sees these: the unknown-word rate is how a helper can tell their
    work is moving the number. The CSV downloads beside them stay owner-only, because those
    export what users actually typed.
    """
    who = _guard(request)
    if not who:
        return _NOT_FOUND
    s = storage.stats()
    return JSONResponse({
        "unknown_rate": s.get("unknown_rate", 0),
        "copy_rate": s.get("copy_rate", 0),
        "sessions": s.get("sessions", 0),
        "conversions": s.get("conversions", 0),
        "corrections": s.get("corrections", 0),
        "location": s.get("location"),
        "can_download": who["role"] == "owner",
    })


# ---- queue -------------------------------------------------------------------------
@router.get("/queue")
def queue(request: Request):
    who = _guard(request)
    if not who:
        return _NOT_FOUND
    items = storage.admin_queue()
    counts = {
        "total": len(items),
        "accepted": sum(1 for i in items if i["review"] and i["review"]["action"] == "accept"),
        "rejected": sum(1 for i in items if i["review"] and i["review"]["action"] == "reject"),
        "pending": sum(1 for i in items if not i["review"]),
        "flagged": sum(1 for i in items if i.get("flagged")),
    }
    return JSONResponse({"items": items, "counts": counts})


# ---- accept / reject ---------------------------------------------------------------
@router.post("/act")
async def act(request: Request):
    who = _guard(request)
    if not who:
        return _NOT_FOUND
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "bad_json"}, status_code=400)
    spelling = security.clean_spelling(body.get("spelling", ""))
    khmer = security.clean_khmer(body.get("khmer", ""))
    action = body.get("action", "")
    if not spelling or not khmer:
        return JSONResponse({"ok": False, "error": "bad_input"}, status_code=400)
    if action not in ("accept", "reject"):
        return JSONResponse({"ok": False, "error": "bad_action"}, status_code=400)
    result = storage.admin_act(who["id"], who["name"], _sid(request), spelling, khmer, action)
    status = 200 if result.get("ok") else 409
    return JSONResponse(result, status_code=status)


# ---- undo --------------------------------------------------------------------------
@router.post("/undo")
async def undo(request: Request):
    who = _guard(request)
    if not who:
        return _NOT_FOUND
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "bad_json"}, status_code=400)
    action_id = body.get("id")
    if not isinstance(action_id, int) or action_id < 1:
        return JSONResponse({"ok": False, "error": "bad_id"}, status_code=400)
    result = storage.admin_undo(action_id, who["name"])
    status = 200 if result.get("ok") else 409
    return JSONResponse(result, status_code=status)


# ---- history -----------------------------------------------------------------------
@router.get("/history")
def history(request: Request):
    who = _guard(request)
    if not who:
        return _NOT_FOUND
    return JSONResponse({"actions": storage.admin_history()})


# ---- submit to GitHub --------------------------------------------------------------
def _github_api(path: str, method: str = "GET", data: dict | None = None) -> dict:
    """Call the GitHub REST API. Returns (status, response_json)."""
    import httpx

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return {"ok": False, "error": "github_token_missing"}
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"https://api.github.com{path}"
    try:
        if method == "GET":
            r = httpx.get(url, headers=headers, timeout=30)
        elif method == "POST":
            r = httpx.post(url, headers=headers, json=data, timeout=30)
        elif method == "PUT":
            r = httpx.put(url, headers=headers, json=data, timeout=30)
        else:
            return {"ok": False, "error": f"unknown_method: {method}"}
        if r.status_code >= 400:
            return {"ok": False, "error": f"github_api_error_{r.status_code}",
                    "detail": r.text[:500]}
        return {"ok": True, "data": r.json() if r.text else {}}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _get_repo() -> tuple[str, str] | None:
    """Return (owner, repo) from GITHUB_REPO env var. Default: SrunLyheang/sing-khmer-engine-2."""
    repo = os.environ.get("GITHUB_REPO", "SrunLyheang/sing-khmer-engine-2").strip()
    parts = repo.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


def _update_vocab_csv(original_content: str, accepted: list[dict]) -> tuple[str, list[str]]:
    """Apply accepted corrections to the vocabulary CSV content.

    Returns (new_csv_content, summary_lines) where summary_lines describes the changes.
    """
    reader = csv.DictReader(io.StringIO(original_content))
    rows = list(reader)
    fieldnames = reader.fieldnames or ["khmer", "frequency", "is_slang", "romanizations", "notes"]

    # Index: khmer -> row index
    khmer_index: dict[str, int] = {}
    for i, row in enumerate(rows):
        k = row.get("khmer", "").strip()
        if k:
            khmer_index[k] = i

    summary: list[str] = []
    for item in accepted:
        spelling = item["spelling"]
        khmer = item["khmer"]
        if khmer in khmer_index:
            # Existing word — add romanization if missing
            idx = khmer_index[khmer]
            existing_raw = rows[idx].get("romanizations", "") or ""
            existing = set(
                s.strip().lower()
                for s in re.split(r"[,\s]+", existing_raw)
                if s.strip()
            )
            # Normalize: spaces in spelling → '+' notation
            csv_spelling = spelling.replace(" ", "+")
            if csv_spelling.lower() not in existing and spelling.lower() not in existing:
                rows[idx]["romanizations"] = (
                    f"{existing_raw}, {csv_spelling}" if existing_raw.strip() else csv_spelling
                )
                summary.append(f"+ added '{csv_spelling}' to existing '{khmer}'")
            else:
                summary.append(f"  (skipped '{csv_spelling}' — already on '{khmer}')")
        else:
            # New word
            rows.append({
                "khmer": khmer,
                "frequency": "1",
                "is_slang": "true",
                "romanizations": spelling.replace(" ", "+"),
                "notes": "(user-submitted — verify)",
            })
            khmer_index[khmer] = len(rows) - 1
            summary.append(f"+ new word: '{khmer}' = '{spelling}'")

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue(), summary


@router.post("/submit")
async def submit(request: Request):
    """Push accepted corrections to a GitHub review branch and open a PR.

    Owner only. Reviewers judge words; the owner decides what reaches the dictionary.
    """
    if not _guard(request):
        return _NOT_FOUND
    who = _owner(request)
    if not who:
        return JSONResponse({"ok": False, "error": "owner_only"}, status_code=403)

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return JSONResponse(
            {"ok": False, "error": "GitHub token not configured. Set GITHUB_TOKEN env var."},
            status_code=503,
        )

    repo_info = _get_repo()
    if not repo_info:
        return JSONResponse({"ok": False, "error": "Bad GITHUB_REPO format"}, status_code=500)
    owner, repo = repo_info

    # 1. Get accepted items
    accepted = storage.admin_accepted_for_submit()
    if not accepted:
        return JSONResponse({"ok": False, "error": "No accepted items to submit."}, status_code=400)

    # 2. Get current vocabulary.csv from master
    file_path = "data/vocabulary.csv"
    current = _github_api(f"/repos/{owner}/{repo}/contents/{file_path}?ref=master")
    if not current["ok"]:
        return JSONResponse(
            {"ok": False, "error": "Failed to fetch vocabulary.csv",
             "detail": current.get("error", "")},
            status_code=502,
        )
    file_sha = current["data"]["sha"]
    import base64
    original = base64.b64decode(current["data"]["content"]).decode("utf-8")

    # 3. Apply changes
    new_content, summary = _update_vocab_csv(original, accepted)

    # 4. Get master SHA
    master = _github_api(f"/repos/{owner}/{repo}/git/ref/heads/master")
    if not master["ok"]:
        return JSONResponse(
            {"ok": False, "error": "Failed to get master ref",
             "detail": master.get("error", "")},
            status_code=502,
        )
    master_sha = master["data"]["object"]["sha"]

    # 5. Create review branch
    # Try to create the branch and let a collision tell us it was taken, rather than asking
    # first: checking-then-creating leaves a window where two submits both see "free" and
    # one of them dies. GitHub answers 422 when the ref already exists.
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    base_name = f"review/dictionary-update-{day}"
    branch_name = base_name
    for attempt in range(1, 12):
        create_branch = _github_api(
            f"/repos/{owner}/{repo}/git/refs",
            method="POST",
            data={"ref": f"refs/heads/{branch_name}", "sha": master_sha},
        )
        if create_branch["ok"]:
            break
        if not str(create_branch.get("error", "")).endswith("_422"):
            return JSONResponse(
                {"ok": False, "error": "Failed to create branch",
                 "detail": create_branch.get("error", "")},
                status_code=502,
            )
        branch_name = f"{base_name}-{attempt}"
    else:
        return JSONResponse(
            {"ok": False, "error": "Could not find a free branch name"}, status_code=409
        )

    # 6. Commit updated file
    commit_msg = "dict: apply reviewed corrections\n\n" + "\n".join(summary)
    encoded = base64.b64encode(new_content.encode("utf-8")).decode("ascii")
    commit_result = _github_api(
        f"/repos/{owner}/{repo}/contents/{file_path}",
        method="PUT",
        data={
            "message": commit_msg,
            "content": encoded,
            "sha": file_sha,
            "branch": branch_name,
        },
    )
    if not commit_result["ok"]:
        return JSONResponse(
            {"ok": False, "error": "Failed to commit changes",
             "detail": commit_result.get("error", "")},
            status_code=502,
        )

    # 7. Create PR
    reviewer = who["name"]
    pr_result = _github_api(
        f"/repos/{owner}/{repo}/pulls",
        method="POST",
        data={
            "title": f"Dictionary update — {day}",
            "head": branch_name,
            "base": "master",
            "body": (
                f"**Submitted by:** {reviewer}\n\n"
                f"**Changes:**\n" + "\n".join(f"- {s}" for s in summary) +
                f"\n\n---\n*Auto-generated from the admin review dashboard.*"
            ),
        },
    )
    if not pr_result["ok"]:
        return JSONResponse(
            {"ok": False, "error": "Failed to create PR",
             "detail": pr_result.get("error", "")},
            status_code=502,
        )

    # 8. Mark all accepted items as submitted — one statement, so it can't half-apply
    storage.admin_mark_submitted(accepted)

    pr_url = pr_result["data"]["html_url"]
    return JSONResponse({
        "ok": True,
        "pr_url": pr_url,
        "branch": branch_name,
        "changes": summary,
        "count": len(accepted),
    })


# ---- GitHub status (check if token is configured) ----------------------------------
@router.get("/github-status")
def github_status(request: Request):
    """Tell the dashboard whether GitHub submission is available."""
    who = _guard(request)
    if not who:
        return _NOT_FOUND
    token = bool(os.environ.get("GITHUB_TOKEN", ""))
    repo_info = _get_repo()
    return JSONResponse({
        "configured": token and repo_info is not None,
        "repo": f"{repo_info[0]}/{repo_info[1]}" if repo_info else None,
    })
