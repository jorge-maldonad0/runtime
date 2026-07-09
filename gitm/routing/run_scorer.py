#!/usr/bin/env python3
"""
Stage 3 harness — wires Danny's scorer_v0.py to Airtable.

scorer_v0.py is a pure function library (no I/O). This reads scorer_ready_rows,
coerces each field to the type the scorer expects (crucially company_tier -> int,
so single-select strings don't silently score tier 3), scores each row via
score_prospect(), and writes priority_score back onto scorer_ready_rows.

Run on the VM:
    export $(grep AIRTABLE ~/.hermes/.env | xargs)
    python3 run_scorer.py
"""

import os
import sys
import json
import urllib.request
import urllib.error
import urllib.parse

BASE_ID = "appi400mk6PHDF6Ex"
TABLE = "scorer_ready_rows"
SCORER_DIR = "/root/runtime/gitm/routing"

API_KEY = os.environ.get("AIRTABLE_API_KEY")
if not API_KEY:
    sys.exit("AIRTABLE_API_KEY not set. Run: export $(grep AIRTABLE ~/.hermes/.env | xargs)")

# Import the real scorer function (pure, no pandas needed for score_prospect)
sys.path.insert(0, SCORER_DIR)
try:
    from scorer_v0 import score_prospect
except Exception as e:
    sys.exit(f"Could not import score_prospect from {SCORER_DIR}/scorer_v0.py: {e}")

HDR_R = {"Authorization": f"Bearer {API_KEY}"}
HDR_W = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


def api(url, data=None, method="GET"):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode() if data else None,
        headers=HDR_W if data else HDR_R,
        method=method,
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


# --- coercion helpers: guarantee the scorer sees the types it expects ---
def to_float(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def to_int01(v, d=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return d


def to_tier(v):
    """company_tier must be int 1/2/3. Strings, floats, blanks all handled. Default 3."""
    try:
        t = int(float(v))
        return t if t in (1, 2, 3) else 3
    except (TypeError, ValueError):
        return 3


# 1. Ensure the priority_score field exists (idempotent; ignore if already there)
try:
    meta = api(f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables")
    tbl = next(t for t in meta["tables"] if t["name"] == TABLE)
    if not any(f["name"] == "priority_score" for f in tbl["fields"]):
        api(
            f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables/{tbl['id']}/fields",
            data={"name": "priority_score", "type": "number", "options": {"precision": 2}},
            method="POST",
        )
        print("Created priority_score field.")
except Exception as e:
    print(f"Field check/create note: {e} (continuing)")

# 2. Read all scorer_ready_rows
records, offset = [], None
while True:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{urllib.parse.quote(TABLE)}?pageSize=100"
    if offset:
        url += f"&offset={offset}"
    page = api(url)
    records.extend(page.get("records", []))
    offset = page.get("offset")
    if not offset:
        break

print(f"Read {len(records)} scorer_ready_rows.")

# 3. Score each row
updates = []
nan_rows = 0
for rec in records:
    f = rec.get("fields", {})
    score = score_prospect(
        warmth=to_float(f.get("warmth")),
        signal_recency=to_float(f.get("signal_recency")),
        company_tier=to_tier(f.get("company_tier")),
        pain_acknowledged=to_int01(f.get("pain_acknowledged")),
        engagement_score=to_float(f.get("engagement_score")),
        prior_engagement=to_int01(f.get("prior_engagement")),
    )
    updates.append({"id": rec["id"], "fields": {"priority_score": score}})

# 4. Write priority_score back in batches of 10 (Airtable limit)
written = 0
for i in range(0, len(updates), 10):
    batch = updates[i : i + 10]
    api(
        f"https://api.airtable.com/v0/{BASE_ID}/{urllib.parse.quote(TABLE)}",
        data={"records": batch},
        method="PATCH",
    )
    written += len(batch)

print(f"Wrote priority_score to {written} rows.")
top = sorted(updates, key=lambda u: u["fields"]["priority_score"], reverse=True)[:5]
print("Top 5 scores:", [u["fields"]["priority_score"] for u in top])
print("Done.")
