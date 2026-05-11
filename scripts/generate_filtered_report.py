#!/usr/bin/env python3
"""
generate_filtered_report.py — Run the feature extraction pipeline and generate
a filtered standalone HTML report.

Filters applied:
  - Bucket 2: Wallet/GooglePay and Wallet/ApplePay rows are dropped
  - All buckets: rows for the excluded connector list are dropped
  - Bucket 3 is connector-agnostic so only connector exclusion applies (none)

Usage:
  python3 scripts/generate_filtered_report.py            # re-run extraction then report
  python3 scripts/generate_filtered_report.py --no-refresh  # use existing CSVs
  open filtered_report.html
"""

import os
import sys
import csv
import html
import subprocess
import argparse
from datetime import datetime
from collections import Counter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---- Filter configuration ----
IGNORED_CONNECTORS = {
    "blackhawknetwork", "boku", "breadpay", "celero", "chargebee",
    "digitalvirgo", "flexiti", "getnet", "gpayments", "hyperwallet",
    "imerchantsolutions", "juspaythreedsserver", "katapult", "mpgs",
    "payeezy", "paytm", "phonepe", "powertranz", "prophetpay",
    "santander", "sift", "silverflow", "square", "tokenex",
    "trustpayments", "zift",
}

# Drop these Wallet PMTs from Bucket 2
IGNORED_WALLET_PMTS = {"GooglePay", "ApplePay"}

B1_CSV = os.path.join(REPO_ROOT, "bucket_1_connector_features.csv")
B2_CSV = os.path.join(REPO_ROOT, "bucket_2_connector_pm_features.csv")
B3_CSV = os.path.join(REPO_ROOT, "bucket_3_core_features.csv")
OUT_HTML = os.path.join(REPO_ROOT, "filtered_report.html")


# ---------------------------------------------------------------------------
# Data loading + filtering
# ---------------------------------------------------------------------------

def run_extraction():
    print("Running extract_features.py...", file=sys.stderr)
    result = subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "scripts", "extract_features.py")],
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        print("ERROR: extract_features.py failed", file=sys.stderr)
        sys.exit(1)
    print("Extraction complete.\n", file=sys.stderr)


def read_b1():
    rows = []
    with open(B1_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["connector"].lower() in IGNORED_CONNECTORS:
                continue
            rows.append(row)
    return rows


def read_b2():
    rows = []
    with open(B2_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["connector"].lower() in IGNORED_CONNECTORS:
                continue
            if (row["payment_method"] == "Wallet"
                    and row["payment_method_type"] in IGNORED_WALLET_PMTS):
                continue
            rows.append(row)
    return rows


def read_b3():
    rows = []
    with open(B3_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def h(text):
    return html.escape(str(text or ""), quote=True)


def cy_badge(status):
    if status == "covered":
        return '<span class="badge covered">covered</span>'
    elif status == "not_covered":
        return '<span class="badge not-covered">not covered</span>'
    else:
        return '<span class="badge no-config">no config</span>'


def pct_str(rows, col):
    if not rows:
        return "0%"
    c = Counter(r[col] for r in rows)
    return f"{round(c.get('covered', 0) / len(rows) * 100)}%"


def cards_html(b1, b2, b3):
    total = len(b1) + len(b2) + len(b3)
    total_covered = (
        sum(1 for r in b1 if r["cypress_test_status"] == "covered")
        + sum(1 for r in b2 if r["cypress_test_status"] == "covered")
        + sum(1 for r in b3 if r["cypress_test_status"] == "covered")
    )
    overall_pct = f"{round(total_covered / total * 100)}%" if total else "0%"

    b1_connectors = len(set(r["connector"] for r in b1))
    b2_connectors = len(set(r["connector"] for r in b2))

    data = [
        ("Total Features", str(total),
         f"B1: {len(b1)} &middot; B2: {len(b2)} &middot; B3: {len(b3)}"),
        ("Cypress Covered", str(total_covered),
         f"{overall_pct} of all features"),
        ("Connector Flows (B1)", str(len(b1)),
         f"{pct_str(b1, 'cypress_test_status')} covered &middot; {b1_connectors} connectors"),
        ("Connector &times; PM (B2)", str(len(b2)),
         f"{pct_str(b2, 'cypress_test_status')} covered &middot; {b2_connectors} connectors"),
        ("Core Features (B3)", str(len(b3)),
         f"{pct_str(b3, 'cypress_test_status')} covered"),
    ]

    parts = []
    for label, value, detail in data:
        parts.append(f"""
  <div class="card">
    <div class="label">{label}</div>
    <div class="value">{value}</div>
    <div class="delta">{detail}</div>
  </div>""")
    return '<div class="cards">' + "".join(parts) + "\n</div>"


def b1_table_html(rows):
    thead = ("<thead><tr>"
             "<th>Connector</th><th>Feature</th><th>Description</th>"
             "<th>Endpoint</th><th>Cypress</th>"
             "</tr></thead>")
    trows = []
    for r in rows:
        trows.append(
            f"<tr>"
            f"<td>{h(r['connector'])}</td>"
            f"<td>{h(r['feature'])}</td>"
            f"<td>{h(r['description'])}</td>"
            f"<td><code>{h(r['hs_endpoint'])}</code></td>"
            f"<td>{cy_badge(r['cypress_test_status'])}</td>"
            f"</tr>"
        )
    tbody = "<tbody>" + "\n".join(trows) + "</tbody>"
    return (
        '<input class="search-box" placeholder="Search connector or feature&hellip;"'
        ' oninput="filterTable(this,\'b1-table\')">\n'
        f'<table id="b1-table">{thead}{tbody}</table>'
    )


def b2_table_html(rows):
    thead = ("<thead><tr>"
             "<th>Connector</th><th>Payment Method</th><th>PMT</th>"
             "<th>Feature</th><th>Description</th><th>Cypress</th>"
             "</tr></thead>")
    trows = []
    for r in rows:
        trows.append(
            f"<tr>"
            f"<td>{h(r['connector'])}</td>"
            f"<td>{h(r['payment_method'])}</td>"
            f"<td>{h(r['payment_method_type'])}</td>"
            f"<td>{h(r['feature'])}</td>"
            f"<td>{h(r['description'])}</td>"
            f"<td>{cy_badge(r['cypress_test_status'])}</td>"
            f"</tr>"
        )
    tbody = "<tbody>" + "\n".join(trows) + "</tbody>"
    return (
        '<input class="search-box" placeholder="Search connector, PM, PMT, or feature&hellip;"'
        ' oninput="filterTable(this,\'b2-table\')">\n'
        f'<table id="b2-table">{thead}{tbody}</table>'
    )


def b3_table_html(rows):
    thead = ("<thead><tr>"
             "<th>Feature</th><th>Description</th><th>Endpoint</th>"
             "<th>Source</th><th>Cypress</th>"
             "</tr></thead>")
    trows = []
    for r in rows:
        trows.append(
            f"<tr>"
            f"<td>{h(r['feature'])}</td>"
            f"<td>{h(r['description'])}</td>"
            f"<td><code>{h(r['hs_endpoint'])}</code></td>"
            f"<td><code>{h(r['source'])}</code></td>"
            f"<td>{cy_badge(r['cypress_test_status'])}</td>"
            f"</tr>"
        )
    tbody = "<tbody>" + "\n".join(trows) + "</tbody>"
    return (
        '<input class="search-box" placeholder="Search feature&hellip;"'
        ' oninput="filterTable(this,\'b3-table\')">\n'
        f'<table id="b3-table">{thead}{tbody}</table>'
    )


# ---------------------------------------------------------------------------
# Full HTML document
# ---------------------------------------------------------------------------

CSS = """
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  margin: 0; padding: 24px;
  background: #0f1115; color: #e6e6e6; font-size: 13px;
}
h1 { margin: 0 0 4px; font-size: 20px; }
.sub { color: #888; margin-bottom: 16px; font-size: 12px; }
.excluded {
  color: #777; font-size: 11px; margin-bottom: 20px;
  background: #161920; border: 1px solid #2a2e38;
  border-radius: 6px; padding: 10px 14px; line-height: 1.7;
}
.excluded strong { color: #aaa; }
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px; margin-bottom: 28px;
}
.card {
  background: #1a1d24; border: 1px solid #2a2e38;
  border-radius: 8px; padding: 14px;
}
.label { font-size: 10px; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }
.value { font-size: 24px; font-weight: 600; margin-top: 4px; }
.delta { font-size: 11px; color: #7aace8; margin-top: 4px; }
.section {
  background: #1a1d24; border: 1px solid #2a2e38;
  border-radius: 8px; margin-bottom: 20px; overflow: hidden;
}
.section-header {
  padding: 13px 18px; border-bottom: 1px solid #2a2e38;
  display: flex; align-items: center; justify-content: space-between;
  cursor: pointer; user-select: none;
}
.section-header:hover { background: #1e2230; }
.section-header h2 { margin: 0; font-size: 14px; font-weight: 500; }
.toggle { color: #666; font-size: 11px; }
.section-body { padding: 14px 18px; }
.hint { color: #777; font-size: 11px; margin: 0 0 12px; line-height: 1.6; }
.search-box {
  width: 100%; padding: 7px 11px; margin-bottom: 12px;
  background: #0f1115; border: 1px solid #2a2e38;
  border-radius: 6px; color: #e6e6e6; font-size: 12px; outline: none;
}
.search-box:focus { border-color: #5cc8ff; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th {
  text-align: left; padding: 7px 10px;
  border-bottom: 1px solid #2a2e38;
  color: #777; font-weight: 500; font-size: 10px;
  text-transform: uppercase; letter-spacing: 0.4px;
  white-space: nowrap;
}
td { padding: 6px 10px; border-bottom: 1px solid #1a1d24; vertical-align: top; }
tr:hover td { background: #1e2230; }
tr:last-child td { border-bottom: none; }
code {
  font-family: "SF Mono", Menlo, Consolas, monospace;
  font-size: 11px; color: #aaa; word-break: break-all;
}
.badge {
  display: inline-block; padding: 2px 8px; border-radius: 10px;
  font-size: 10px; font-weight: 600; white-space: nowrap;
}
.badge.covered     { background: #152d1f; color: #6bda8f; border: 1px solid #1f4a30; }
.badge.not-covered { background: #2d1515; color: #ff7070; border: 1px solid #4a1f1f; }
.badge.no-config   { background: #222; color: #777; border: 1px solid #333; }
.collapsed { display: none; }
footer { color: #444; font-size: 11px; margin-top: 28px; text-align: center; }
"""

JS = """
function toggleSection(id) {
  const body = document.getElementById(id + '-body');
  const toggle = document.getElementById(id + '-toggle');
  if (body.classList.contains('collapsed')) {
    body.classList.remove('collapsed');
    toggle.textContent = '▼';
  } else {
    body.classList.add('collapsed');
    toggle.textContent = '▶';
  }
}

function filterTable(input, tableId) {
  const q = input.value.toLowerCase();
  document.getElementById(tableId).querySelectorAll('tbody tr').forEach(row => {
    row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
}
"""


def build_html(b1, b2, b3, now):
    excluded_list = ", ".join(sorted(IGNORED_CONNECTORS))
    wallet_note = ", ".join(sorted(IGNORED_WALLET_PMTS))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hyperswitch Filtered Coverage Report</title>
<style>{CSS}</style>
</head>
<body>

<h1>Hyperswitch Filtered Coverage Report</h1>
<div class="sub">Generated {now} &nbsp;&middot;&nbsp; Wallets excluded: {h(wallet_note)} &nbsp;&middot;&nbsp; {len(IGNORED_CONNECTORS)} connectors excluded</div>

<div class="excluded">
  <strong>Excluded connectors ({len(IGNORED_CONNECTORS)}):</strong><br>
  {h(excluded_list)}
</div>

{cards_html(b1, b2, b3)}

<div class="section">
  <div class="section-header" onclick="toggleSection('b1')">
    <h2>Bucket 1 &mdash; Connector Flows
      <span style="color:#5cc8ff;font-weight:400"> &nbsp;{len(b1)} rows</span>
    </h2>
    <span class="toggle" id="b1-toggle">&#9660;</span>
  </div>
  <div class="section-body" id="b1-body">
    <p class="hint">Per-connector flow capabilities (Refund, Incremental Auth, Overcapture, Dispute Defend&hellip;). Behavior differs per connector, PM-agnostic.</p>
    <div class="table-wrap">
      {b1_table_html(b1)}
    </div>
  </div>
</div>

<div class="section">
  <div class="section-header" onclick="toggleSection('b2')">
    <h2>Bucket 2 &mdash; Connector &times; PM &times; PMT
      <span style="color:#9d7cff;font-weight:400"> &nbsp;{len(b2)} rows</span>
    </h2>
    <span class="toggle" id="b2-toggle">&#9660;</span>
  </div>
  <div class="section-body" id="b2-body">
    <p class="hint">Supported (connector, payment method, payment method type) combinations. GooglePay and ApplePay wallets excluded.</p>
    <div class="table-wrap">
      {b2_table_html(b2)}
    </div>
  </div>
</div>

<div class="section">
  <div class="section-header" onclick="toggleSection('b3')">
    <h2>Bucket 3 &mdash; Core Features
      <span style="color:#ffa56c;font-weight:400"> &nbsp;{len(b3)} rows</span>
    </h2>
    <span class="toggle" id="b3-toggle">&#9660;</span>
  </div>
  <div class="section-body" id="b3-body">
    <p class="hint">Platform-wide features &mdash; same behavior regardless of connector. No connector filtering applies here.</p>
    <div class="table-wrap">
      {b3_table_html(b3)}
    </div>
  </div>
</div>

<footer>Generated by scripts/generate_filtered_report.py &nbsp;&middot;&nbsp; source: bucket_*.csv</footer>

<script>{JS}</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate filtered HTML coverage report")
    parser.add_argument(
        "--no-refresh", action="store_true",
        help="Skip re-running extract_features.py (use existing CSV files)",
    )
    args = parser.parse_args()

    if not args.no_refresh:
        run_extraction()

    for path in [B1_CSV, B2_CSV, B3_CSV]:
        if not os.path.exists(path):
            print(
                f"ERROR: {path} not found. "
                "Run without --no-refresh or run extract_features.py first.",
                file=sys.stderr,
            )
            sys.exit(1)

    print("Reading and filtering CSV files...", file=sys.stderr)
    b1 = read_b1()
    b2 = read_b2()
    b3 = read_b3()
    print(f"  Bucket 1: {len(b1)} rows after filtering", file=sys.stderr)
    print(f"  Bucket 2: {len(b2)} rows after filtering", file=sys.stderr)
    print(f"  Bucket 3: {len(b3)} rows (connector-agnostic, no filtering)", file=sys.stderr)

    print("Building HTML report...", file=sys.stderr)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html_content = build_html(b1, b2, b3, now)

    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"\nDone. Report written to:\n  {OUT_HTML}", file=sys.stderr)
    print(f"Open with:  open {OUT_HTML}", file=sys.stderr)


if __name__ == "__main__":
    main()
