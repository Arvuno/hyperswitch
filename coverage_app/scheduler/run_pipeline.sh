#!/usr/bin/env bash
# Run the full coverage pipeline. Logs everything to a dated file under
# coverage_app/logs/ and records start/finish in the pipeline_runs table
# via tiny inline Python snippets (so the web UI sees run history).

set -euo pipefail

# Default REPO_ROOT to /repo (Docker mount), but if that doesn't exist fall
# back to the directory two levels up from this script (so the same script
# works when run locally outside Docker).
if [[ -z "${REPO_ROOT:-}" ]]; then
  if [[ -d /repo ]]; then
    REPO_ROOT=/repo
  else
    REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  fi
fi
LOG_DIR="$REPO_ROOT/coverage_app/logs"
mkdir -p "$LOG_DIR"

STAMP=$(date +%Y%m%d-%H%M%S)
LOG="$LOG_DIR/pipeline-$STAMP.log"

cd "$REPO_ROOT"

echo "=== pipeline started at $(date -Iseconds) ===" | tee -a "$LOG"

# Insert a 'running' row, capture the id so we can update it on completion.
RUN_ID=$(python3 - <<EOF
import sqlite3, os
from datetime import datetime
conn = sqlite3.connect("$REPO_ROOT/features.db")
conn.execute("PRAGMA journal_mode = WAL")
cur = conn.execute(
    "INSERT INTO pipeline_runs (started_at, status, triggered_by, log_path) VALUES (?, 'running', ?, ?)",
    (datetime.utcnow().isoformat(), "${TRIGGERED_BY:-cron}", "$LOG"),
)
conn.commit()
print(cur.lastrowid)
conn.close()
EOF
)

mark_status() {
  python3 - <<EOF
import sqlite3
from datetime import datetime
conn = sqlite3.connect("$REPO_ROOT/features.db")
conn.execute(
    "UPDATE pipeline_runs SET finished_at = ?, status = ? WHERE id = ?",
    (datetime.utcnow().isoformat(), "$1", $RUN_ID),
)
conn.commit()
conn.close()
EOF
}

# Trap any error and mark the run failed before exiting.
trap 'mark_status failed; echo "=== pipeline FAILED at $(date -Iseconds) ===" | tee -a "$LOG"' ERR

{
  echo "[1/5] extract_features.py"
  python3 scripts/extract_features.py

  echo "[2/5] merge_prod_data.py"
  python3 scripts/merge_prod_data.py

  echo "[3/5] track_feature_history.py"
  python3 scripts/track_feature_history.py --tags 634

  echo "[4/5] build_dashboard.py"
  python3 scripts/build_dashboard.py --months 6

  echo "[5/5] merge_cypress_coverage.py"
  python3 scripts/merge_cypress_coverage.py
} >> "$LOG" 2>&1

mark_status success
echo "=== pipeline finished at $(date -Iseconds) ===" | tee -a "$LOG"
