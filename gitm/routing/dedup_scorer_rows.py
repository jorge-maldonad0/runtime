#!/usr/bin/env python3
"""
Dedup scorer_ready_rows: keep exactly one row per (prospect_id, sender_id) pair,
the newest by createdTime, delete the rest.

Safe because the duplicate copies are value-identical (seed load vs affinity-mapper
pass) — verified before writing this. Keeps newest as a clean, future-consistent rule.

Run on the VM:
    export $(grep AIRTABLE ~/.hermes/.env | xargs)
    python3 dedup_scorer_rows.py            # dry run: reports what it WOULD delete
    python3 dedup_scorer_rows.py --apply    # actually deletes
"""

import os
import sys
import json
import urllib.request
import urllib.parse
from collections import defaultdict

BASE_ID = "appi400mk6PHDF6Ex"
TABLE = "scorer_ready_rows"
APPLY = "--apply" in sys.argv

API_KEY = os.environ.get("AIRTABLE_API_KEY")
if not API_KEY:
    sys.exit("AIRTABLE_API_KEY not set. Run: export $(grep AIRTABLE ~/.hermes/.env | xargs)")

HDR = {"Authorization": f"Bearer {API_KEY}"}


def api(url, method="GET"):
    req = urllib.request.Request(url, headers=HDR, method=method)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


# Read all rows
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

# Group by (prospect_id, sender_id)
groups = defaultdict(list)
for r in records:
    f = r.get("fields", {})
    groups[(f.get("prospect_id"), f.get("sender_id"))].append(r)

keep, delete = [], []
for pair, rows in groups.items():
    rows.sort(key=lambda r: r.get("createdTime", ""), reverse=True)  # newest first
    keep.append(rows[0]["id"])
    delete.extend(r["id"] for r in rows[1:])

print(f"Total rows:      {len(records)}")
print(f"Distinct pairs:  {len(groups)}")
print(f"Would keep:      {len(keep)}")
print(f"Would delete:    {len(delete)}")

# Sanity: kept count must equal distinct pairs
assert len(keep) == len(groups), "keep count != distinct pairs — aborting"

if not APPLY:
    print("\nDRY RUN — nothing deleted. Re-run with --apply to delete.")
    sys.exit(0)

# Delete in batches of 10
deleted = 0
for i in range(0, len(delete), 10):
    batch = delete[i : i + 10]
    qs = "&".join(f"records[]={rid}" for rid in batch)
    url = f"https://api.airtable.com/v0/{BASE_ID}/{urllib.parse.quote(TABLE)}?{qs}"
    api(url, method="DELETE")
    deleted += len(batch)

print(f"\nDeleted {deleted} rows. {len(keep)} remain (one per pair).")
