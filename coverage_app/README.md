# Hyperswitch Coverage Dashboard

A self-hosted web dashboard for browsing the feature/cypress inventory in `features.db`,
with inline editing for `assignee`, `coverage_status`, `status`, and `notes`.
The companion scheduler container re-runs the extraction pipeline daily at **10:00 IST**.

## Layout

```
coverage_app/
├── docker-compose.yml      # 2 services, both mount the parent repo as /repo
├── web/                    # FastAPI + Jinja2 + HTMX
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py             # entrypoint
│   ├── db.py               # sqlite helper (WAL mode)
│   ├── routes/
│   │   ├── pages.py        # /, /bucket-N, /trends
│   │   └── api.py          # /api/*
│   ├── templates/          # base.html, home.html, bucket.html, trends.html
│   └── static/
└── scheduler/              # Debian + cron + python3
    ├── Dockerfile
    ├── crontab             # 0 10 * * * → pipeline
    └── run_pipeline.sh     # the actual pipeline (extract → merge → history → dashboard)
```

## Run

From the repo root:

```bash
cd coverage_app
docker compose up --build
```

Then open <http://localhost:8000>.

## Pages

| Path | Purpose |
|---|---|
| `/` | Summary cards (total features, cypress %, prod %), per-bucket cards, last-run status, manual "run now" button |
| `/bucket-1` | Connector × Feature inline-edit table |
| `/bucket-2` | Connector × PM × PMT inline-edit table |
| `/bucket-3` | Core / schema features inline-edit table |
| `/trends` | Embedded `dashboard.html` showing time-series graphs |

## Inline edit

Click any cell under **Assignee**, **Coverage Status**, **Status**, or **Notes**.
The cell turns into an input/select; blur or change posts to
`POST /api/issues/{id}/cell` and re-renders. Other columns are read-only.

## API

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/issues/{id}` | — | Single issue row |
| PATCH | `/api/issues/{id}` | JSON of editable fields | Updated row |
| POST | `/api/issues/{id}/cell` | form: `column`, `value` | HTML cell (HTMX) |
| GET | `/api/issues/{id}/cell-edit?column=…` | — | HTML editor (HTMX) |
| GET | `/api/runs?limit=N` | — | Last N pipeline runs |
| POST | `/api/admin/run-pipeline` | — | `{queued: true}` (kicks pipeline async) |
| GET | `/api/stats` | — | Per-bucket totals |

## Daily pipeline

`scheduler/run_pipeline.sh`, cron-fired at 10:00 IST:

1. `scripts/extract_features.py` — refresh `bucket_*.csv` and the `issues` table
2. `scripts/merge_prod_data.py` — add `prod_used` columns to bucket CSV/XLSX
3. `scripts/track_feature_history.py --tags 634` — refresh `tag_snapshots`
4. `scripts/build_dashboard.py --months 6` — regenerate `dashboard.html`
5. `scripts/merge_cypress_coverage.py` — produce `merged_*` CSV/XLSX, sync Assignee/Coverage Status into the DB

Each run creates a `pipeline_runs` row (id, started_at, finished_at, status, log_path)
so the home page can display the latest status and the `/runs` endpoint history.
Logs land in `coverage_app/logs/pipeline-YYYYMMDD-HHMMSS.log`.

## Editing rules

The web UI can change ONLY:
- `assignee`
- `coverage_status` (manual triage label, e.g. *Covered*, *Review*, *Not possible*)
- `status` (`open` / `picked_up` / `covered`)
- `notes`

Everything else (cypress detection, prod usage, descriptions) is owned by the
extraction scripts and gets refreshed every pipeline run **without touching**
the human-edited columns.
