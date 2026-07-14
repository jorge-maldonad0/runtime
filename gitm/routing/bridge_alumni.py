#!/usr/bin/env python3
"""
Bridge: Meet Alfred LinkedIn alumni intake -> prospects.

Meet Alfred fires a webhook -> Zapier -> creates rows in the `alumni_intake`
table. This bridge reads unprocessed intake rows, dedups against existing
prospects by normalized linkedin_url, and lands clean rows in `prospects` as
enrichment_status=pending, source=linkedin_alumni, so the enrich -> score ->
draft -> HeyReach chain runs on them unchanged.

Idempotent: dedups on linkedin_url and marks intake rows processed, so re-running
never double-adds. Creates the alumni_intake table if it doesn't exist yet.

Run on the VM:
    export $(grep AIRTABLE ~/.hermes/.env | xargs)
    python3 bridge_alumni.py            # dry run — reports what it WOULD land
    python3 bridge_alumni.py --apply    # insert + mark intake processed
"""

import os
import sys
import re
import json
import urllib.request
import urllib.error
import urllib.parse

BASE_ID = "appi400mk6PHDF6Ex"
INTAKE = "alumni_intake"
APPLY = "--apply" in sys.argv

API_KEY = os.environ.get("AIRTABLE_API_KEY")
if not API_KEY:
    sys.exit("AIRTABLE_API_KEY not set. Run: export $(grep AIRTABLE ~/.hermes/.env | xargs)")

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


def norm_url(u):
    if not u:
        return ""
    u = u.strip().split("?")[0].rstrip("/")
    u = re.sub(r"/(en|fr|de|es|it|pt|zh|ja|ko)$", "", u)
    return u.lower()


def slug(s):
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", (s or "").lower())).strip("_")


def read_all(table):
    out, off = [], None
    while True:
        u = f"https://api.airtable.com/v0/{BASE_ID}/{urllib.parse.quote(table)}?pageSize=100"
        if off:
            u += f"&offset={off}"
        d = api(u)
        out += d.get("records", [])
        off = d.get("offset")
        if not off:
            break
    return out


# 0. Ensure alumni_intake exists (create with the schema Zapier maps into)
meta = api(f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables")
tables = {t["name"]: t for t in meta["tables"]}
if INTAKE not in tables:
    if not APPLY:
        print(f"NOTE: `{INTAKE}` table does not exist yet. Re-run with --apply to create it, "
              "or create it manually. Fields Zapier should map into:")
        print("  full_name (text, primary), linkedin_url (url), current_company (text),")
        print("  current_title (text), location (text), mutual_connections (number),")
        print("  source_sender (single select: asmar/jane/giancarlos/evan),")
        print("  collected_at (dateTime), processed (checkbox)")
        sys.exit(0)
    api(
        f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables",
        data={
            "name": INTAKE,
            "description": "Raw LinkedIn alumni leads from Meet Alfred (via Zapier). Bridge promotes to prospects.",
            "fields": [
                {"name": "full_name", "type": "singleLineText"},
                {"name": "linkedin_url", "type": "url"},
                {"name": "current_company", "type": "singleLineText"},
                {"name": "current_title", "type": "singleLineText"},
                {"name": "location", "type": "singleLineText"},
                {"name": "mutual_connections", "type": "number", "options": {"precision": 0}},
                {"name": "source_sender", "type": "singleSelect", "options": {"choices": [
                    {"name": "asmar"}, {"name": "jane"}, {"name": "giancarlos"}, {"name": "evan"}]}},
                {"name": "collected_at", "type": "dateTime", "options": {
                    "timeZone": "America/Los_Angeles",
                    "dateFormat": {"name": "iso"}, "timeFormat": {"name": "24hour"}}},
                {"name": "processed", "type": "checkbox", "options": {"icon": "check", "color": "greenBright"}},
            ],
        },
        method="POST",
    )
    print(f"Created `{INTAKE}` table. Point Meet Alfred's Zapier at it and re-run.")
    sys.exit(0)

# prospects schema (write only fields that exist)
pf = {f["name"] for f in tables["prospects"]["fields"]}

existing = {norm_url(r["fields"].get("linkedin_url", "")) for r in read_all("prospects")}
existing.discard("")

intake = read_all(INTAKE)
to_add, mark_done, seen = [], [], set()
skipped_nourl = skipped_dup = already_done = 0

for r in intake:
    f = r["fields"]
    if f.get("processed"):
        already_done += 1
        continue
    url = norm_url(f.get("linkedin_url", ""))
    if not url:
        skipped_nourl += 1
        continue
    if url in existing or url in seen:
        skipped_dup += 1
        mark_done.append(r["id"])  # dup: mark processed so it doesn't re-check forever
        continue
    seen.add(url)
    name = f.get("full_name", "")
    company = f.get("current_company", "")
    pid = f"prospect_{slug(company) or 'unknown'}_{slug(name) or url.split('/')[-1]}"
    rec = {"prospect_id": pid}
    if "linkedin_url" in pf:
        rec["linkedin_url"] = f.get("linkedin_url", "")
    if "enrichment_status" in pf:
        rec["enrichment_status"] = "pending"
    if "full_name" in pf:
        rec["full_name"] = name
    if "current_company" in pf:
        rec["current_company"] = company
    if "current_title" in pf:
        rec["current_title"] = f.get("current_title", "")
    if "source" in pf:
        rec["source"] = "linkedin_alumni"
    to_add.append({"fields": rec})
    mark_done.append(r["id"])

print(f"intake rows:                {len(intake)}")
print(f"already processed:          {already_done}")
print(f"already in prospects (dup): {skipped_dup}")
print(f"skipped (no linkedin_url):  {skipped_nourl}")
print(f"new to land in prospects:   {len(to_add)}")
print(f"prospects fields available: {sorted(pf)}")

if not APPLY:
    print("\nDRY RUN — nothing written. Re-run with --apply to insert + mark processed.")
    if to_add:
        print("sample:", json.dumps(to_add[0], indent=2))
    sys.exit(0)

added = 0
for i in range(0, len(to_add), 10):
    api(
        f"https://api.airtable.com/v0/{BASE_ID}/{urllib.parse.quote('prospects')}",
        data={"records": to_add[i : i + 10]},
        method="POST",
    )
    added += len(to_add[i : i + 10])

marked = 0
if "processed" in {f["name"] for f in tables[INTAKE]["fields"]}:
    for i in range(0, len(mark_done), 10):
        batch = [{"id": rid, "fields": {"processed": True}} for rid in mark_done[i : i + 10]]
        api(
            f"https://api.airtable.com/v0/{BASE_ID}/{urllib.parse.quote(INTAKE)}",
            data={"records": batch},
            method="PATCH",
        )
        marked += len(batch)

print(f"\nLanded {added} alumni into prospects (enrichment_status=pending, source=linkedin_alumni).")
print(f"Marked {marked} intake rows processed.")
print("affinity-mapper will enrich them on its next 30-min tick.")
