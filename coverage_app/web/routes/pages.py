"""Page routes — server-rendered HTML."""

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from db import cursor

router = APIRouter()
templates = Jinja2Templates(directory="templates")


BUCKETS = {
    1: {"name": "Connector Flows", "description": "Connector × Feature (payload-level, PM-agnostic)"},
    2: {"name": "Connector × Payment Method", "description": "Connector × PM × PMT × Feature"},
    3: {"name": "Core / Schema", "description": "Platform-wide features (business_profile, merchant_account, etc.)"},
}


def _summary_stats():
    with cursor() as c:
        rows = c.execute("""
            SELECT bucket,
                   COUNT(*) AS total,
                   SUM(CASE WHEN cypress_status = 'covered' THEN 1 ELSE 0 END) AS cypress_covered,
                   SUM(CASE WHEN prod_used = 'yes' THEN 1 ELSE 0 END) AS prod_yes,
                   SUM(CASE WHEN prod_used = 'no'  THEN 1 ELSE 0 END) AS prod_no,
                   SUM(CASE WHEN assignee IS NOT NULL AND assignee != '' THEN 1 ELSE 0 END) AS assigned,
                   SUM(CASE WHEN coverage_status = 'Covered' THEN 1 ELSE 0 END) AS manual_covered
            FROM issues
            GROUP BY bucket ORDER BY bucket
        """).fetchall()
    stats = {}
    totals = {"total": 0, "cypress_covered": 0, "prod_yes": 0, "prod_no": 0, "assigned": 0, "manual_covered": 0}
    for r in rows:
        d = dict(r)
        d["bucket_name"] = BUCKETS[r["bucket"]]["name"]
        d["cypress_pct"] = round(100.0 * r["cypress_covered"] / r["total"], 1) if r["total"] else 0
        denom = r["prod_yes"] + r["prod_no"]
        d["prod_pct"] = round(100.0 * r["prod_yes"] / denom, 1) if denom else 0
        stats[r["bucket"]] = d
        for k in totals:
            totals[k] += r[k]
    totals["cypress_pct"] = round(100.0 * totals["cypress_covered"] / totals["total"], 1) if totals["total"] else 0
    denom = totals["prod_yes"] + totals["prod_no"]
    totals["prod_pct"] = round(100.0 * totals["prod_yes"] / denom, 1) if denom else 0
    return stats, totals


def _last_run():
    with cursor() as c:
        r = c.execute("""
            SELECT started_at, finished_at, status, triggered_by
            FROM pipeline_runs
            ORDER BY id DESC LIMIT 1
        """).fetchone()
        return dict(r) if r else None


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    stats, totals = _summary_stats()
    return templates.TemplateResponse("home.html", {
        "request": request,
        "stats": stats,
        "totals": totals,
        "buckets": BUCKETS,
        "last_run": _last_run(),
    })


@router.get("/bucket-{bucket_id}", response_class=HTMLResponse)
async def bucket_page(
    request: Request,
    bucket_id: int,
    connector: str = Query(""),
    cypress: str = Query(""),
    prod: str = Query(""),
    assignee: str = Query(""),
    status: str = Query(""),
    q: str = Query(""),
):
    if bucket_id not in BUCKETS:
        return HTMLResponse(status_code=404, content="Unknown bucket")

    where = ["bucket = ?"]
    params = [bucket_id]
    if connector:
        where.append("connector = ?"); params.append(connector)
    if cypress:
        where.append("cypress_status = ?"); params.append(cypress)
    if prod:
        where.append("prod_used = ?"); params.append(prod)
    if assignee:
        if assignee == "__unassigned__":
            where.append("(assignee IS NULL OR assignee = '')")
        else:
            where.append("assignee = ?"); params.append(assignee)
    if status:
        where.append("coverage_status = ?"); params.append(status)
    if q:
        where.append("(feature LIKE ? OR connector LIKE ? OR pm LIKE ? OR pmt LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like, like])

    sql = f"""SELECT * FROM issues WHERE {' AND '.join(where)}
              ORDER BY connector, pm, pmt, feature"""
    with cursor() as c:
        rows = [dict(r) for r in c.execute(sql, params).fetchall()]

        connectors = [r[0] for r in c.execute(
            "SELECT DISTINCT connector FROM issues WHERE bucket = ? AND connector != '' ORDER BY connector",
            (bucket_id,),
        ).fetchall()]
        assignees = [r[0] for r in c.execute(
            "SELECT DISTINCT assignee FROM issues WHERE assignee IS NOT NULL AND assignee != '' ORDER BY assignee"
        ).fetchall()]
        statuses = [r[0] for r in c.execute(
            "SELECT DISTINCT coverage_status FROM issues WHERE coverage_status IS NOT NULL AND coverage_status != '' ORDER BY coverage_status"
        ).fetchall()]

    return templates.TemplateResponse("bucket.html", {
        "request": request,
        "bucket_id": bucket_id,
        "bucket_name": BUCKETS[bucket_id]["name"],
        "bucket_description": BUCKETS[bucket_id]["description"],
        "rows": rows,
        "filters": {
            "connector": connector, "cypress": cypress, "prod": prod,
            "assignee": assignee, "status": status, "q": q,
        },
        "connectors": connectors,
        "assignees": assignees,
        "coverage_statuses": statuses,
    })


@router.get("/trends", response_class=HTMLResponse)
async def trends(request: Request):
    return templates.TemplateResponse("trends.html", {"request": request})
