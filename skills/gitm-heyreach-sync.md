---
name: gitm-heyreach-sync
description: Daily HeyReach reply-ingestion for Git.M's GTM stack. Polls HeyReach for reply, connection, and campaign activity across active campaigns, classifies each lead's status, upserts into the Airtable `replies` table, and sets prior_engagement = 1 on the matching scorer_ready_rows row so reply outcomes reach Danny's scorer and activate the dossier-builder trigger queue. Sole owner of the prior_engagement field. Runs on a 7 AM PST cron. Use when reply data needs to flow from HeyReach into Airtable and the scorer.
---

# gitm-heyreach-sync

## Description

Reply-ingestion skill for Git.M's GTM agent stack. Polls HeyReach once daily for activity across active campaigns, classifies each lead (replied / connection accepted / awaiting / benign no-action / failed), writes it to the Airtable `replies` table, and flips `prior_engagement = 1` on the matching `scorer_ready_rows` row so replies flow into the scorer and activate the `gitm-dossier-builder` trigger queue.

This is the pipeline referenced as "Jorge (via HeyReach reply pipeline)" in `input_contract.md` and as the `prior_engagement` source in `gitm-affinity-mapper`. It is the one skill allowed to write `prior_engagement`.

---

## HeyReach API reference

Base host: `https://api.heyreach.io` (confirm against HeyReach docs if a call 404s).

**Auth header is `X-API-KEY`, NOT `Authorization: Bearer`.**

```
X-API-KEY: {HEYREACH_API_KEY}
Content-Type: application/json
```

Endpoints used:

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/public/campaign/GetAll` | POST | Enumerate campaigns and their IDs. Filter to active campaigns. |
| `/api/public/campaign/GetLeadsFromCampaign` | POST | Pull leads for a campaign. Body: `{ "campaignId": <id>, "offset": <int>, "limit": <int> }`. Paginate with offset/limit until fewer than `limit` rows return. |
| `/api/public/li_account/GetAll` | POST | Sender LinkedIn accounts, to corroborate sender names if needed. |

Per-lead fields of interest returned by `GetLeadsFromCampaign`:
- `firstName`, `lastName`
- `profileUrl` (LinkedIn URL — unique join key)
- `linkedInSenderFullName` (which FDE sent it)
- `leadCampaignStatus`, `leadConnectionStatus`, `leadMessageStatus`
- `lastActionTime`
- `errorCode` (present on blocked/failed actions)

---

## Trigger

Hermes cron, once daily at 7:00 AM PST — ahead of the 8:50 fork sync and 9:00 standup so the day's queue has fresh reply data. Clear of the every-30-min affinity poll.

---

## Enrichment steps

### Step 1 — Fetch activity from HeyReach

1. `POST /api/public/campaign/GetAll`, filter to active campaigns (the three live senders: Asmar, Jane, Giancarlos; Evan later).
2. For each active campaign, `POST /api/public/campaign/GetLeadsFromCampaign` and paginate on `offset`/`limit` until exhausted.
3. Collect every lead with the fields listed above.

Normalize `profileUrl` before using it as a key: strip locale suffixes (`/en`, `/fr`, etc.) and query params, same normalization the affinity mapper applies, so match keys are consistent across skills.

### Step 2 — Classify each lead

HeyReach exposes several status fields plus an `errorCode`. Do NOT collapse every non-reply into `failed` — most error codes are benign campaign states (already-connected, rate-limit timeout), not delivery failures. Classify into one normalized `sender_status`:

```
FATAL_ERROR_CODES = { }   # empty for v0 — populate only with codes confirmed to be
                          # permanent delivery failures. Until then nothing is marked FAILED.

BENIGN_ERROR_CODES = {
    "ConnectionRequestAlreadySent",
    "CannotSendMessage_Timeout",
    # extend as new non-fatal codes appear
}

classify(lead):
    if replied (leadMessageStatus == "REPLIED" or leadCampaignStatus indicates a reply):
        sender_status = "REPLIED";            replied = 1; failed = 0
    elif leadConnectionStatus indicates accepted/connected and not replied:
        sender_status = "CONNECTION_ACCEPTED"; replied = 0; failed = 0
    elif errorCode in FATAL_ERROR_CODES:
        sender_status = "FAILED";             replied = 0; failed = 1
    elif errorCode present (benign or unknown):
        sender_status = "BENIGN_NO_ACTION";   replied = 0; failed = 0
        # unknown (not in BENIGN_ERROR_CODES): still BENIGN_NO_ACTION, add a manual-review note.
        # Never default an unknown code to FAILED — that pollutes the table with fake failures.
    else:
        sender_status = "AWAITING_REPLY";     replied = 0; failed = 0
```

Derived fields:
- `days_to_reply` (float or null): HeyReach exposes only `lastActionTime`, not a separate send+reply pair, so this stays **null** for v0. Do not fabricate.
- `failed_reason` (string or null): the raw `errorCode`, only when `sender_status == FAILED`. Null otherwise.
- `last_action` (string): raw `leadMessageStatus`/action, including the benign code (e.g. `ConnectionRequestAlreadySent`) so the full picture is visible on benign rows.

### Step 3 — Write to the `replies` table (dedup on `linkedin_url`)

Upsert one row per prospect keyed on `prospect_linkedin_url`. Update in place if the row exists — never append duplicates. **Benign and connection-accept rows are written too, with their accurate `sender_status`** — not just replies and failures.

| Field | Type | Source |
|---|---|---|
| `prospect_linkedin_url` | Single line text (primary) | HeyReach `profileUrl`, normalized — join key |
| `prospect_name` | Single line text | `firstName` + `lastName` |
| `sender_name` | Single line text | `linkedInSenderFullName` |
| `sender_id` | Single select | Mapped from sender name (see map below) |
| `sender_status` | Single select | Classified: `REPLIED`, `CONNECTION_ACCEPTED`, `AWAITING_REPLY`, `BENIGN_NO_ACTION`, `FAILED` |
| `last_action` | Single line text | Raw action / status detail (incl. benign code) |
| `last_action_time` | Date/time | HeyReach `lastActionTime` |
| `replied` | Number (int 0/1) | Computed |
| `days_to_reply` | Number (decimal) or null | Null for v0 |
| `failed` | Number (int 0/1) | Computed — 1 only for FATAL codes |
| `failed_reason` | Single line text or null | Raw `errorCode`, only when FAILED |
| `sentiment` | Single select or null | Null for v0 |
| `variant_served` | Single line text or null | Null for v0 |
| `matched_prospect_id` | Single line text or null | Resolved in Step 4; null if no match |
| `synced_to_scorer` | Checkbox | True once Step 4 write succeeds |

### Step 4 — Resolve to prospect and update the scorer

For each row where `replied == 1`:

1. Look up `prospects` for a row whose `linkedin_url` matches `prospect_linkedin_url` (after normalization). Record `prospect_id` into `replies.matched_prospect_id`.
2. Map `sender_name → sender_id` (see map). This selects the correct prospect-sender row.
3. In `scorer_ready_rows`, find the row where `prospect_id` + `sender_id` match, and set `prior_engagement = 1`.
4. Set `replies.synced_to_scorer = true`.

Only `REPLIED` rows touch the scorer. Connection-accepts, benign, and failed rows are recorded in `replies` but do not set `prior_engagement`.

If no `prospects` match is found: leave `matched_prospect_id` null, `synced_to_scorer` false, note it. Do not create a prospect row from reply data — out of scope for v0.

A reply comes in through one sender, so this updates only that prospect-sender row.

**This skill does not write `engagement_score`.** The engagement rubric scores a reply at 1.0, but `engagement_score` ownership is unresolved (Khoa per the schema docs; possibly Danny). A second writer would collide with the affinity/engagement pipeline. This skill owns `prior_engagement` only until ownership is confirmed.

### Step 5 — Log run

Log to `status_loop_runs`: `{ date, mode: "heyreach_sync", replies_found, rows_upserted, connection_accepts, benign, failed, scorer_rows_updated, unmatched }`.

---

## Sender name → sender_id map

Match on HeyReach `linkedInSenderFullName`:

```
"Asmar Khasmammadli"   -> asmar
"Jane Dong"            -> jane
"Giancarlos Sarabia"   -> giancarlos
```

Evan is added later. If a `sender_name` doesn't map, write the `replies` row but leave `sender_id` blank, skip the scorer write, and note it — do not guess.

---

## Downstream effect

`gitm-dossier-builder` triggers on `scorer_ready_rows.prior_engagement = 1`. Once this skill is live and flipping that field, the dossier-builder trigger queue becomes real, so its cron can be registered (it was intentionally left unregistered until reply data was flowing).

---

## Validation rules

1. `prospect_linkedin_url` present before writing a `replies` row.
2. `replied`, `failed` are 0 or 1.
3. `failed = 1` only for `errorCode in FATAL_ERROR_CODES`. Benign/unknown codes are `failed = 0`, `sender_status = BENIGN_NO_ACTION`.
4. `prior_engagement` is only ever set to 1 by this skill — never 0 (defaults owned by affinity-mapper at row creation).
5. Scorer write only fires on a confirmed `prospect_id` + `sender_id` match, and only for `REPLIED`.
6. `days_to_reply` is null, not 0, when unavailable.

---

## Error handling

- HeyReach unreachable / non-200: log warning, exit cleanly, retry next run. Do not partially write.
- Auth rejected (401/403): almost always the `X-API-KEY` header or a mangled key value — do not retry-loop, log and exit.
- No `prospects` match: write `replies` row, leave scorer untouched, note unmatched.
- Airtable write fails: retry once after 30s, log, continue to next lead.
- Unmappable `sender_name`: write `replies` row without `sender_id`, skip scorer write, note it.
- Unknown `errorCode`: classify `BENIGN_NO_ACTION`, never `FAILED`, add manual-review note.
- Duplicate lead (same `linkedin_url`): update in place, never append.

---

## Environment variables required

```
HEYREACH_API_KEY        # in ~/.hermes/.env (X-API-KEY header). Note: key contains '=' — verify it loads intact.
AIRTABLE_API_KEY
AIRTABLE_BASE_ID        # appi400mk6PHDF6Ex (GTM Reservoir)
```

---

## Airtable setup required

The `replies` table already exists (`tbljG6baSvcCQt8G3`). Two adjustments needed before first run:

1. On `replies.sender_status`, add the single-select option **`BENIGN_NO_ACTION`** (existing options: `REPLIED`, `AWAITING_REPLY`, `CONNECTION_ACCEPTED`, `FAILED`).
2. On `status_loop_runs.mode`, add the single-select option **`heyreach_sync`**, or the Step 5 log write fails.

---

## Cron schedule

Register after the first manual run passes:

```bash
hermes cron create "0 7 * * *" "poll heyreach replies and sync to airtable" --skill gitm-heyreach-sync --name gitm-heyreach-sync
```

---

## Manual test

```bash
hermes chat --skill gitm-heyreach-sync --yolo
```

Then type:

```
Poll HeyReach across the active campaigns using GetAll then GetLeadsFromCampaign with the X-API-KEY header. Classify each lead (replied / connection accepted / awaiting / benign / failed) per the skill rules, normalize profileUrl, and upsert into the replies table keyed on prospect_linkedin_url. For each replied lead, resolve linkedin_url to prospect_id via the prospects table, map sender name to sender_id, and set prior_engagement = 1 on the matching scorer_ready_rows row. Log the run to status_loop_runs with mode heyreach_sync.
```

**Validation oracle (from the discovery run, last 30 days):** exactly two real replies should flip `prior_engagement = 1`, assuming both resolve against `prospects`:
- Jane Dong → Li (`ltfang`), 2026-07-01
- Asmar Khasmammadli → Andrew Birnberg (`andrew-birnberg`), 2026-06-23

Also expect roughly: Jane ~22 `BENIGN_NO_ACTION` (ConnectionRequestAlreadySent) + ~4 `CONNECTION_ACCEPTED`; Giancarlos ~3 `BENIGN_NO_ACTION` (CannotSendMessage_Timeout) + ~5 `CONNECTION_ACCEPTED`; Asmar ~4 `CONNECTION_ACCEPTED`. Zero rows in `failed` on this pass (no fatal codes defined yet). If anything lands in `FAILED`, the classifier is mis-bucketing a benign code.

---

## Install

```bash
curl -o ~/.hermes/skills/gitm/gitm-heyreach-sync/SKILL.md \
  https://raw.githubusercontent.com/jorge-maldonad0/runtime/main/skills/gitm-heyreach-sync.md

hermes skills list | grep gitm-heyreach-sync
```
