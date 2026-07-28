"""Admin review dashboard API — correction queue, accept/reject, GitHub PR submission.

All routes require ADMIN_TOKEN via cookie or header.  The reviewer identifies
themselves with a name stored in a client-side cookie so multiple people can
review from the same deployed instance.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import re
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api import security, storage

log = logging.getLogger("sing_khmer.admin")

router = APIRouter(prefix="/admin/api")


# ---- auth guard (applied to every route) -------------------------------------------
def _guard(request: Request) -> str | None:
    """Return the admin token if valid; otherwise None (caller returns 404)."""
    token = request.query_params.get("token") or request.headers.get("x-admin-token", "")
    if security.admin_ok(token):
        return token
    return None


def _reviewer(request: Request) -> str:
    """Return the reviewer name from the X-Reviewer-Name header, or 'unknown'."""
    return (request.headers.get("x-reviewer-name") or "unknown").strip()[:64]


def _sid(request: Request) -> str:
    return getattr(request.state, "session_id", "anon")


# ---- queue -------------------------------------------------------------------------
@router.get("/queue")
def queue(request: Request):
    if not _guard(request):
        return JSONResponse({"error": "not_found"}, status_code=404)
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
    if not _guard(request):
        return JSONResponse({"error": "not_found"}, status_code=404)
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
    result = storage.admin_act(_reviewer(request), _sid(request), spelling, khmer, action)
    status = 200 if result.get("ok") else 409
    return JSONResponse(result, status_code=status)


# ---- undo --------------------------------------------------------------------------
@router.post("/undo")
async def undo(request: Request):
    if not _guard(request):
        return JSONResponse({"error": "not_found"}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "bad_json"}, status_code=400)
    action_id = body.get("id")
    if not isinstance(action_id, int) or action_id < 1:
        return JSONResponse({"ok": False, "error": "bad_id"}, status_code=400)
    result = storage.admin_undo(action_id, _reviewer(request))
    status = 200 if result.get("ok") else 409
    return JSONResponse(result, status_code=status)


# ---- history -----------------------------------------------------------------------
@router.get("/history")
def history(request: Request):
    if not _guard(request):
        return JSONResponse({"error": "not_found"}, status_code=404)
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
    """Push accepted corrections to a GitHub review branch and open a PR."""
    if not _guard(request):
        return JSONResponse({"error": "not_found"}, status_code=404)

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
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    branch_name = f"review/dictionary-update-{day}"
    # Check if branch exists; if so, append a counter
    existing_branch = _github_api(f"/repos/{owner}/{repo}/git/ref/heads/{branch_name}")
    counter = 1
    while existing_branch["ok"]:
        branch_name = f"review/dictionary-update-{day}-{counter}"
        existing_branch = _github_api(f"/repos/{owner}/{repo}/git/ref/heads/{branch_name}")
        counter += 1

    create_branch = _github_api(
        f"/repos/{owner}/{repo}/git/refs",
        method="POST",
        data={"ref": f"refs/heads/{branch_name}", "sha": master_sha},
    )
    if not create_branch["ok"]:
        return JSONResponse(
            {"ok": False, "error": "Failed to create branch",
             "detail": create_branch.get("error", "")},
            status_code=502,
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
    reviewer = _reviewer(request)
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

    # 8. Mark all accepted items as submitted
    for item in accepted:
        storage.admin_mark_submitted(item["spelling"], item["khmer"])

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
    if not _guard(request):
        return JSONResponse({"error": "not_found"}, status_code=404)
    token = bool(os.environ.get("GITHUB_TOKEN", ""))
    repo_info = _get_repo()
    return JSONResponse({
        "configured": token and repo_info is not None,
        "repo": f"{repo_info[0]}/{repo_info[1]}" if repo_info else None,
    })
