#!/usr/bin/env python3
"""Fetch HeyReach leads, classify, upsert to Airtable, set prior_engagement."""
import urllib.request, urllib.error
import json, re, os, sys
from datetime import datetime, timezone

AIRTABLE_BASE_ID = "appi400mk6PHDF6Ex"
REPLIES_TABLE = "tbljG6baSvcCQt8G3"
PROSPECTS_TABLE = "tblkiIjx9YO97Kt7J"
SCORER_TABLE = "tblbLSL34Yg8BItv9"
STATUS_TABLE = "tblrFUbyg9Y5l04Br"

SENDER_MAP = {"Asmar Khasmammadli": "asmar", "Jane Dong": "jane", "Giancarlos Sarabia": "giancarlos"}
BENIGN_ERROR_CODES = {"ConnectionRequestAlreadySent", "CannotSendMessage_Timeout"}
FATAL_ERROR_CODES = set()

def _load_env():
    p = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(p):
        with open(p) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line: continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'").strip('"'))
_load_env()
HAK = os.environ.get("HEYREACH_API_KEY", "")
AAK = os.environ.get("AIRTABLE_API_KEY", "")
if not HAK or not AAK:
    print("FATAL: Missing HEYREACH_API_KEY or AIRTABLE_API_KEY", flush=True); sys.exit(1)


def _hr(endpoint, body=None):
    req = urllib.request.Request(f"https://api.heyreach.io/api/public/{endpoint}",
        data=json.dumps(body or {}).encode(),
        headers={"X-API-KEY": HAK, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        bd = e.read().decode()[:500]; print(f"    [ERR] HeyReach HTTP {e.code}: {bd}", flush=True)
        return {"error": f"HTTP {e.code}"}
    except Exception as e:
        print(f"    [ERR] HeyReach: {e}", flush=True); return {"error": str(e)}

def _at_get(tid, params=None):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{tid}"
    if params:
        qs = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in params.items())
        url += "?" + qs
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {AAK}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        bd = e.read().decode()[:500]; print(f"    [ERR] AT GET {e.code}: {bd}", flush=True)
        return {"error": f"HTTP {e.code}"}

def _at_patch(tid, rid, fields):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{tid}/{rid}"
    req = urllib.request.Request(url, data=json.dumps({"fields": fields}).encode(),
        headers={"Authorization": f"Bearer {AAK}", "Content-Type": "application/json"}, method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        bd = e.read().decode()[:300]; print(f"    [ERR] AT PATCH {e.code}: {bd}", flush=True)
        return {"error": f"HTTP {e.code}"}

def _at_create(tid, records):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{tid}"
    req = urllib.request.Request(url, data=json.dumps({"records": records}).encode(),
        headers={"Authorization": f"Bearer {AAK}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        bd = e.read().decode()[:500]; print(f"    [ERR] AT CREATE {e.code}: {bd}", flush=True)
        return {"error": f"HTTP {e.code}"}

def _at_post(tid, records):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{tid}"
    req = urllib.request.Request(url, data=json.dumps({"records": records}).encode(),
        headers={"Authorization": f"Bearer {AAK}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        bd = e.read().decode()[:500]; print(f"    [ERR] AT POST {e.code}: {bd}", flush=True)
        return {"error": f"HTTP {e.code}"}


def norm_url(url):
    if not url: return url
    url = url.rstrip("/")
    url = re.sub(r'/([a-z]{2})(-[A-Z]{2})?$', '', url)
    return url.split('?')[0].split('#')[0]

def extract(lead):
    p = lead.get("linkedInUserProfile") or {}
    if isinstance(p, dict):
        return p.get("firstName","") or lead.get("firstName",""), \
               p.get("lastName","") or lead.get("lastName",""), \
               p.get("profileUrl","") or lead.get("profileUrl","")
    return lead.get("firstName",""), lead.get("lastName",""), lead.get("profileUrl","")

def classify(lead):
    lms = lead.get("leadMessageStatus"); lcs = lead.get("leadCampaignStatus")
    lcn = lead.get("leadConnectionStatus"); err = lead.get("errorCode")
    if lms == "MessageReply":
        return {"st": "REPLIED", "rep": 1, "fail": 0, "fr": None, "la": str(lms)}
    if lcn in ("ConnectionAccepted","Accepted") or (lcn and "ACCEPTED" in str(lcn).upper()):
        return {"st": "CONNECTION_ACCEPTED", "rep": 0, "fail": 0, "fr": None, "la": str(lcn or lms)}
    if err and err in FATAL_ERROR_CODES:
        return {"st": "FAILED", "rep": 0, "fail": 1, "fr": err, "la": err}
    if err:
        note = " [manual-review: '{}']".format(err) if err not in BENIGN_ERROR_CODES else ""
        return {"st": "BENIGN_NO_ACTION", "rep": 0, "fail": 0, "fr": None, "la": err + note}
    return {"st": "AWAITING_REPLY", "rep": 0, "fail": 0, "fr": None, "la": str(lms or lcs or "AWAITING")}

def fetch_leads(cid, limit=100):
    all_l = []; off = 0
    while True:
        print(f"    off={off}...", flush=True)
        d = _hr("campaign/GetLeadsFromCampaign", {"campaignId": cid, "offset": off, "limit": limit})
        if "error" in d: return all_l
        items = d.get("items",[]); all_l.extend(items)
        print(f"    got {len(items)} (total: {len(all_l)})", flush=True)
        if len(items) < limit: break
        off += limit
    return all_l


def upsert_one(table_id, fields, key_field="prospect_linkedin_url"):
    """Find existing record by key field value, then PATCH or CREATE."""
    key_val = fields.get(key_field, "")
    if not key_val:
        return None
    # Search for existing
    formula = "{" + key_field + "}='" + key_val.replace("'", "\\'") + "'"
    result = _at_get(table_id, {"filterByFormula": formula, "maxRecords": 1})
    if "error" in result:
        return None
    existing = result.get("records", [])
    if existing:
        rid = existing[0].get("id", "")
        pr = _at_patch(table_id, rid, fields)
        if "error" not in pr:
            return rid
        return None
    else:
        cr = _at_create(table_id, [{"fields": fields}])
        if "error" not in cr:
            return cr.get("records",[{}])[0].get("id","")
        return None


def main():
    print("=" * 60, flush=True)
    print("  HEYREACH SYNC", flush=True)
    print(f"  {datetime.now(timezone.utc).isoformat()}", flush=True)
    print("=" * 60, flush=True)

    st = {"rep_found":0,"up":0,"conn":0,"benign":0,"fail":0,"await":0,"scorer":0,"unmatched":0,"total":0}

    print("\n[1] Campaigns...", flush=True)
    camps = _hr("campaign/GetAll")
    if "error" in camps: print(f"FATAL: {camps['error']}", flush=True); sys.exit(1)
    active = [c for c in camps.get("items",[]) if c["status"]=="IN_PROGRESS" and c.get("campaignAccountIds")]
    print(f"  {len(active)} active:", flush=True)
    for c in active: print(f"    ID={c['id']} | {c['name']}", flush=True)
    if not active: print("  Nothing to do."); return

    print("\n[2] Leads...", flush=True)
    all_l = []
    for c in active:
        print(f"\n  {c['name']} (ID={c['id']})", flush=True)
        leads = fetch_leads(c["id"])
        cn = c["name"].lower()
        sn = "Jane Dong" if "jane" in cn else ("Giancarlos Sarabia" if "giancarlos" in cn else "Asmar Khasmammadli")
        for lead in leads:
            lead["_camp"] = c["name"]
            lead["linkedInSenderFullName"] = sn
        all_l.extend(leads)
    print(f"\n  Total: {len(all_l)}", flush=True); st["total"] = len(all_l)

    print("\n[3] Classify...", flush=True)
    cl = []
    for lead in all_l:
        cls = classify(lead); cls["lead"] = lead; cl.append(cls)
        s = cls["st"]
        if s == "REPLIED": st["rep_found"] += 1
        elif s == "CONNECTION_ACCEPTED": st["conn"] += 1
        elif s == "BENIGN_NO_ACTION": st["benign"] += 1
        elif s == "FAILED": st["fail"] += 1
        elif s == "AWAITING_REPLY": st["await"] += 1

    print(f"  REPLIED: {st['rep_found']}")
    print(f"  CONNECTION_ACCEPTED: {st['conn']}")
    print(f"  BENIGN_NO_ACTION: {st['benign']}")
    print(f"  FAILED: {st['fail']}")
    print(f"  AWAITING_REPLY: {st['await']}")

    for cls in cl:
        if cls["st"] == "REPLIED":
            fn, ln, url = extract(cls["lead"])
            print(f"  REPLY: {fn} {ln} | {url} | {cls['lead'].get('linkedInSenderFullName','')} | {cls['lead'].get('lastActionTime','')}")

    sc = {}
    for cls in cl:
        sn = cls["lead"].get("linkedInSenderFullName","")
        sc.setdefault(sn,{}).setdefault(cls["st"],0); sc[sn][cls["st"]] += 1
    print("\n  Per-sender:", flush=True)
    for sn, cnts in sorted(sc.items()): print(f"    {sn}: {cnts}")

    print("\n[4] Upsert to replies (find-or-create)...", flush=True)
    rid_map = {}
    for cls in cl:
        lead = cls["lead"]; fn, ln, ru = extract(lead); pu = norm_url(ru)
        if not pu: continue
        sn = lead.get("linkedInSenderFullName",""); sid = SENDER_MAP.get(sn, "")
        lat = lead.get("lastActionTime")
        if lat and "T" not in str(lat):
            try: lat = datetime.fromtimestamp(int(lat), tz=timezone.utc).isoformat()
            except: pass
        flds = {"prospect_linkedin_url": pu, "prospect_name": f"{fn} {ln}".strip(),
                "sender_name": sn, "sender_status": cls["st"], "last_action": cls["la"],
                "replied": cls["rep"], "failed": cls["fail"]}
        if sid: flds["sender_id"] = sid
        if lat: flds["last_action_time"] = lat
        if cls["fr"]: flds["failed_reason"] = cls["fr"]
        print(f"  {fn} {ln} -> {pu}", flush=True)
        rid = upsert_one(REPLIES_TABLE, flds)
        if rid:
            rid_map[pu] = rid
            st["up"] += 1
    print(f"  Upserted: {st['up']} records", flush=True)

    print("\n[5] Resolve replied...", flush=True)
    rcl = [cls for cls in cl if cls["st"] == "REPLIED"]
    if rcl:
        all_pros = []; off = None
        while True:
            p = {"maxRecords": 100}
            if off: p["offset"] = off
            r = _at_get(PROSPECTS_TABLE, p)
            if "error" in r: break
            all_pros.extend(r.get("records",[]))
            off = r.get("offset")
            if not off: break
        pl = {}; pid = {}
        for rec in all_pros:
            ff = rec.get("fields",{}); pu = norm_url(ff.get("linkedin_url","") or "")
            if pu: pl[pu] = rec.get("id",""); pid[pu] = ff.get("prospect_id", rec.get("id",""))
        print(f"  {len(pl)} prospects loaded", flush=True)

        for cls in rcl:
            fn, ln, ru = extract(cls["lead"]); pu = norm_url(ru)
            sn = cls["lead"].get("linkedInSenderFullName",""); sid = SENDER_MAP.get(sn, "")
            print(f"  {fn} {ln} | {pu} | {sn} (sid={sid})", flush=True)
            pr_id = pl.get(pu)
            if not pr_id:
                print(f"    [WARN] No prospect match (prospects has {len(pl)} URLs)")
                # Show what URLs we have in prospects
                for k in list(pl.keys())[:5]:
                    print(f"      Have: {k}")
                st["unmatched"] += 1; continue
            print(f"    Matched: prospect record={pr_id}, p_id={pid.get(pu)}", flush=True)
            rrid = rid_map.get(pu)
            if rrid:
                _at_patch(REPLIES_TABLE, rrid, {"matched_prospect_id": str(pid.get(pu,pr_id)), "synced_to_scorer": True})
            if not sid:
                print(f"    No sender_id"); st["unmatched"] += 1; continue
            pids = str(pid.get(pu, pr_id))
            formula = f"AND({{prospect_id}}='{pids}',{{sender_id}}='{sid}')"
            sr = _at_get(SCORER_TABLE, {"filterByFormula": formula, "maxRecords": 10})
            if "error" in sr: continue
            rows = sr.get("records",[])
            if rows:
                scid = rows[0].get("id","")
                _at_patch(SCORER_TABLE, scid, {"prior_engagement": 1})
                st["scorer"] += 1
                print(f"    ✓ prior_engagement=1 on {scid}", flush=True)
            else:
                print(f"    [WARN] No scorer_ready_rows row for prospect_id={pids}, sender_id={sid}", flush=True)
                st["unmatched"] += 1
    else:
        print("  No replied leads.")

    print("\n[6] Log run...", flush=True)
    logf = {"date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "mode": "heyreach_sync", "status": "ok"}
    lr = _at_post(STATUS_TABLE, [{"fields": logf}])
    if "error" in lr: print(f"  [WARN] Log fail: {lr.get('error')}", flush=True)
    else: print(f"  ✓ Logged: {lr.get('records',[{}])[0].get('id','')}", flush=True)

    print("\n"+"="*60, flush=True)
    print("  DONE", flush=True)
    print("="*60, flush=True)
    print(json.dumps(st, indent=2), flush=True)
    print(f"\n  Validation:", flush=True)
    print(f"  Replies: {st['rep_found']}/2 | Failed: {st['fail']}/0 | Scorer: {st['scorer']}", flush=True)

if __name__ == "__main__":
    main()
