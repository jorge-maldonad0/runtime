#!/usr/bin/env python3
"""
Promote signals -> prospects. The missing head of the autonomous pipeline.

Reads the signals table, dedups against existing prospects by normalized
linkedin_url, and inserts new people into prospects as enrichment_status=pending
so affinity-mapper picks them up on its next 30-min tick.

Idempotent: dedups on linkedin_url, so running it repeatedly never double-adds.
Schema-aware: only writes prospects fields that actually exist.

Run on the VM:
    export $(grep AIRTABLE ~/.hermes/.env | xargs)
    python3 promote_signals.py            # dry run — reports what it WOULD add
    python3 promote_signals.py --apply    # actually insert
"""

import os
import sys
import re
import json
import urllib.request
import urllib.parse

BASE_ID = "appi400mk6PHDF6Ex"
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
    u = re.sub(r"/(en|fr|de|es|it|pt|zh|ja|ko)$", "", u)  # strip locale suffix
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


# Which fields does prospects actually have? Only write those.
meta = api(f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables")
pf = {f["name"] for t in meta["tables"] if t["name"] == "prospects" for f in t["fields"]}

# Existing prospects keyed by normalized linkedin_url (dedup set)
existing = {norm_url(r["fields"].get("linkedin_url", "")) for r in read_all("prospects")}
existing.discard("")

signals = read_all("signals")
to_add, seen = [], set()
skipped_nourl = skipped_dup = 0

for r in signals:
    f = r["fields"]
    raw = f.get("prospect_linkedin_url", "")
    url = norm_url(raw)
    if not url:
        skipped_nourl += 1
        continue
    if url in existing or url in seen:
        skipped_dup += 1
        continue
    seen.add(url)
    name = f.get("prospect_name", "")
    company = f.get("prospect_company", "")
    pid = f"prospect_{slug(company) or 'unknown'}_{slug(name) or url.split('/')[-1]}"
    rec = {"prospect_id": pid}
    if "linkedin_url" in pf:
        rec["linkedin_url"] = raw
    if "enrichment_status" in pf:
        rec["enrichment_status"] = "pending"
    if "full_name" in pf:
        rec["full_name"] = name
    if "current_company" in pf:
        rec["current_company"] = company
    if "current_title" in pf:
        rec["current_title"] = f.get("prospect_title", "")
    to_add.append({"fields": rec})

print(f"signals read:               {len(signals)}")
print(f"already in prospects (dup): {skipped_dup}")
print(f"skipped (no linkedin_url):  {skipped_nourl}")
print(f"new to promote:             {len(to_add)}")
print(f"prospects fields available: {sorted(pf)}")

if not APPLY:
    print("\nDRY RUN — nothing written. Re-run with --apply to insert.")
    if to_add:
        print("sample record:", json.dumps(to_add[0], indent=2))
    sys.exit(0)

added = 0
for i in range(0, len(to_add), 10):
    batch = to_add[i : i + 10]
    api(
        f"https://api.airtable.com/v0/{BASE_ID}/{urllib.parse.quote('prospects')}",
        data={"records": batch},
        method="POST",
    )
    added += len(batch)

print(f"\nPromoted {added} signals into prospects as enrichment_status=pending.")
print("affinity-mapper will pick them up on its next 30-min tick.")
