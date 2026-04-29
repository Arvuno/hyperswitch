"""REST API for inline editing and admin actions."""

import os
import subprocess
from datetime import datetime
from fastapi import APIRouter, HTTPException, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse

from db import cursor

router = APIRouter()

# Only these columns can be modified via the UI. Everything else is owned
# by the cron-driven extraction scripts.
EDITABLE_COLUMNS = {"assignee", "coverage_status", "status", "notes"}

VALID_STATUS = {"open", "picked_up", "covered"}

REPO_ROOT = os.environ.get("REPO_ROOT", "/repo")


@router.get("/issues/{issue_id}")
def get_issue(issue_id: int):
    with cursor() as c:
        row = c.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone()
        if not row:
            raise HTTPException(404, "issue not found")
        return dict(row)


@router.patch("/issues/{issue_id}")
async def patch_issue(issue_id: int, payload: dict):
    fields = {k: v for k, v in payload.items() if k in EDITABLE_COLUMNS}
    if not fields:
        raise HTTPException(400, "no editable fields in payload")
    if "status" in fields and fields["status"] not in VALID_STATUS:
        raise HTTPException(400, f"status must be one of {VALID_STATUS}")
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    params = list(fields.values()) + [issue_id]
    with cursor() as c:
        cur = c.execute(
            f"UPDATE issues SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            params,
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "issue not found")
        row = c.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone()
        return dict(row)


@router.post("/issues/{issue_id}/cell", response_class=HTMLResponse)
async def update_cell_htmx(
    issue_id: int,
    column: str = Form(...),
    value: str = Form(""),
):
    """HTMX-friendly endpoint: returns the rendered cell after update."""
    if column not in EDITABLE_COLUMNS:
        raise HTTPException(400, f"column {column!r} is not editable")
    if column == "status" and value and value not in VALID_STATUS:
        raise HTTPException(400, f"status must be one of {VALID_STATUS}")

    val = value if value != "" else None
    with cursor() as c:
        cur = c.execute(
            f"UPDATE issues SET {column} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (val, issue_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "issue not found")

    display = val or '<span class="text-zinc-500 italic">—</span>'
    return HTMLResponse(
        f'<td class="cell" data-id="{issue_id}" data-column="{column}" '
        f'hx-trigger="click" hx-get="/api/issues/{issue_id}/cell-edit?column={column}" '
        f'hx-swap="outerHTML">{display}</td>'
    )


@router.get("/issues/{issue_id}/cell-edit", response_class=HTMLResponse)
async def cell_editor_htmx(issue_id: int, column: str):
    """Return the inline editor HTML for a cell."""
    if column not in EDITABLE_COLUMNS:
        raise HTTPException(400, f"column {column!r} is not editable")
    with cursor() as c:
        row = c.execute(f"SELECT {column} FROM issues WHERE id = ?", (issue_id,)).fetchone()
    if not row:
        raise HTTPException(404, "issue not found")
    current = row[0] or ""

    if column == "status":
        opts = "".join(
            f'<option value="{s}"{" selected" if s == current else ""}>{s}</option>'
            for s in ("open", "picked_up", "covered")
        )
        body = (
            f'<select name="value" autofocus '
            f'hx-post="/api/issues/{issue_id}/cell" hx-trigger="change" '
            f'hx-vals=\'{{"column": "{column}"}}\' hx-swap="outerHTML" hx-target="closest td" '
            f'class="bg-zinc-800 border border-zinc-600 rounded px-2 py-1">'
            f'{opts}</select>'
        )
    elif column == "coverage_status":
        choices = ["", "Covered", "Review", "Creds not available", "Sandbox creds is not there",
                   "Not possible", "UCS only connector", "Internal subflow should be ignored"]
        opts = "".join(
            f'<option value="{s}"{" selected" if s == current else ""}>{s or "—"}</option>'
            for s in choices
        )
        body = (
            f'<select name="value" autofocus '
            f'hx-post="/api/issues/{issue_id}/cell" hx-trigger="change" '
            f'hx-vals=\'{{"column": "{column}"}}\' hx-swap="outerHTML" hx-target="closest td" '
            f'class="bg-zinc-800 border border-zinc-600 rounded px-2 py-1">'
            f'{opts}</select>'
        )
    else:
        body = (
            f'<input name="value" autofocus value="{current}" '
            f'hx-post="/api/issues/{issue_id}/cell" hx-trigger="blur, keyup[key==\'Enter\']" '
            f'hx-vals=\'{{"column": "{column}"}}\' hx-swap="outerHTML" hx-target="closest td" '
            f'class="bg-zinc-800 border border-zinc-600 rounded px-2 py-1 w-full"/>'
        )
    return HTMLResponse(f'<td>{body}</td>')


@router.get("/runs")
def list_runs(limit: int = 30):
    with cursor() as c:
        rows = c.execute(
            "SELECT * FROM pipeline_runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def _kick_pipeline():
    """Run the daily pipeline synchronously. Called from a BackgroundTask."""
    started = datetime.utcnow().isoformat()
    log_path = f"/repo/coverage_app/logs/manual-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.log"
    with cursor() as c:
        cur = c.execute(
            "INSERT INTO pipeline_runs (started_at, status, triggered_by, log_path) VALUES (?, 'running', 'manual', ?)",
            (started, log_path),
        )
        run_id = cur.lastrowid
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w") as f:
            subprocess.run(
                ["bash", "/repo/coverage_app/scheduler/run_pipeline.sh"],
                stdout=f, stderr=subprocess.STDOUT, check=True, cwd=REPO_ROOT,
            )
        result = "success"
    except subprocess.CalledProcessError:
        result = "failed"
    finally:
        with cursor() as c:
            c.execute(
                "UPDATE pipeline_runs SET finished_at = ?, status = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), result, run_id),
            )


@router.post("/admin/run-pipeline")
async def run_pipeline_now(background_tasks: BackgroundTasks):
    background_tasks.add_task(_kick_pipeline)
    return JSONResponse({"queued": True})


@router.get("/stats")
def stats():
    with cursor() as c:
        rows = c.execute("""
            SELECT bucket,
                   COUNT(*) AS total,
                   SUM(CASE WHEN cypress_status = 'covered' THEN 1 ELSE 0 END) AS cypress_covered,
                   SUM(CASE WHEN prod_used = 'yes' THEN 1 ELSE 0 END) AS prod_yes,
                   SUM(CASE WHEN assignee IS NOT NULL AND assignee != '' THEN 1 ELSE 0 END) AS assigned
            FROM issues GROUP BY bucket ORDER BY bucket
        """).fetchall()
        return [dict(r) for r in rows]
