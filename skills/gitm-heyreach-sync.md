---
name: gitm-heyreach-sync
description: Daily HeyReach reply-ingestion for Git.M's GTM stack. Polls HeyReach for reply, connection, and campaign activity across active campaigns, classifies each lead's status, upserts into the Airtable `replies` table, and sets prior_engagement = 1 on the matching scorer_ready_rows row so reply outcomes reach Danny's scorer and activate the dossier-builder trigger queue. Sole owner of the prior_engagement field. Runs on a 7 AM PST cron. Use when reply data needs to flow from HeyReach into Airtable and the scorer.
---

# gitm-heyreach-sync

## Description

Reply-ingestion skill for Git.M's GTM agent stack. Polls HeyReach once daily for activity across active campaigns, classifies each lead (replied / connection accepted / awaiting / benign no-action / failed), writes it to the Airtable `replies` table, and flips `prior_engagement = 1` on the matching `scorer_ready_rows` row so replies flow into the scorer and activate the `gitm-dossier-builder` trigger queue.

This is the pipeline referenced as "Jorge (via HeyReach reply pipeline)" in `input_contract.md` and as the `prior_engagement` source in `gitm-affinity-mapper`. It is the one skill allowed to write `prior_engagement`.

---

## Implementation notes (verified against a live run, 90 leads / 3 campaigns)

Three things that are NOT obvious from a first read of the HeyReach API and broke the first implementation. Keep these correct or the run silently produces wrong data:

1. **Lead identity is nested.** `firstName`, `lastName`, and `profileUrl` live inside a `linkedInUserProfile` sub-object on each lead, NOT at the top level. Read `lead["linkedInUserProfile"]["profileUrl"]`, etc. Reading top-level returns nulls and every row looks anonymous/unmatched.
2. **Reply status is `MessageReply`, not `REPLIED`.** Detect a reply with `leadMessageStatus == "MessageReply"`. Checking for the string `"REPLIED"` matches nothing and no reply ever flips `prior_engagement`.
3. **Airtable `performUpsert` is not supported on this base.** Use a find-or-create pattern instead: query the `replies` table for a row with the same `prospect_linkedin_url`, update it if found, otherwise create it. Do not rely on the upsert API.

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
- `linkedInUserProfile.firstName`, `linkedInUserProfile.lastName`  *(nested — see note 1)*
- `linkedInUserProfile.profileUrl` (LinkedIn URL — unique join key, nested)
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
3. Collect every lead, reading name and `profileUrl` from the `linkedInUserProfile` sub-object (note 1).

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
    if leadMessageStatus == "MessageReply":     # note 2 — NOT "REPLIED"
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

### Step 3 — Write to the `replies` table (find-or-create, dedup on `linkedin_url`)

**Airtable `performUpsert` is not supported on this base (note 3).** For each lead: query `replies` for an existing row with the same normalized `prospect_linkedin_url`; update it in place if found, otherwise create a new row. Never append duplicates. **Benign and connection-accept rows are written too, with their accurate `sender_status`** — not just replies and failures.

| Field | Type | Source |
|---|---|---|
| `prospect_linkedin_url` | Single line text (primary) | HeyReach `linkedInUserProfile.profileUrl`, normalized — join key |
| `prospect_name` | Single line text | `linkedInUserProfile.firstName` + `lastName` |
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

If no `prospects` match is found: leave `matched_prospect_id` null, `synced_to_scorer` false, note it. Do not create a prospect row from reply data — out of scope for v0. (Expected today: the current replies come from a different outreach list than the prospects table, so they write to `replies` unmatched and correctly do not touch the scorer. They flip automatically once those prospects are added.)

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

`gitm-dossier-builder` triggers on `scorer_ready_rows.prior_engagement = 1`. Once matched replies start flipping that field, the dossier-builder trigger queue becomes real, so its cron can be registered (it was intentionally left unregistered until reply data was flowing).

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
- Duplicate lead (same `linkedin_url`): update in place (find-or-create), never append.

---

## Environment variables required

```
HEYREACH_API_KEY        # in ~/.hermes/.env (X-API-KEY header). Note: key contains '=' — verify it loads intact.
AIRTABLE_API_KEY
AIRTABLE_BASE_ID        # appi400mk6PHDF6Ex (GTM Reservoir)
```

---

## Airtable setup required (already applied)

The `replies` table exists (`tbljG6baSvcCQt8G3`). These were added and are in place:

1. `replies.sender_status` single-select option **`BENIGN_NO_ACTION`** (alongside `REPLIED`, `AWAITING_REPLY`, `CONNECTION_ACCEPTED`, `FAILED`).
2. `status_loop_runs.mode` single-select option **`heyreach_sync`**.

---

## Cron schedule

Currently running as a self-contained, no-agent job (avoids the agent-exploration stall on scheduled runs). Registered 2026-07-08:

```bash
hermes cron create "0 7 * * *" "poll heyreach replies and sync to airtable" \
  --script heyreach_sync.sh --no-agent --name gitm-heyreach-sync
```

Execution chain: cron → `/root/.hermes/scripts/heyreach_sync.sh` (no-agent; sources `~/.hermes/.env`) → execs `fetch_heyreach.py`, which performs all five steps. Job id `852040bf98c2`, next run daily 7:00 AM PST.

**Both `heyreach_sync.sh` and `fetch_heyreach.py` must be version-controlled in the fork** (e.g. under `scripts/`) — the actual logic lives in `fetch_heyreach.py`, and this SKILL.md alone does not capture it. If re-registering from scratch as an agent skill instead, the equivalent form is:

```bash
hermes cron create "0 7 * * *" "poll heyreach replies and sync to airtable" --skill gitm-heyreach-sync --name gitm-heyreach-sync
```

Use one or the other, not both — do not double-register.

---

## Manual test

```bash
hermes chat --skill gitm-heyreach-sync --yolo
```

Then type:

```
Poll HeyReach across the active campaigns using GetAll then GetLeadsFromCampaign with the X-API-KEY header. Read name and profileUrl from the linkedInUserProfile sub-object. Classify each lead (reply = leadMessageStatus MessageReply; connection accepted / awaiting / benign / failed per the rules), normalize profileUrl, and find-or-create into the replies table keyed on prospect_linkedin_url. For each replied lead, resolve linkedin_url to prospect_id via the prospects table, map sender name to sender_id, and set prior_engagement = 1 on the matching scorer_ready_rows row. Log the run to status_loop_runs with mode heyreach_sync.
```

**Validation oracle (last 30 days):** 2 real replies — Jane Dong → Li (`ltfang`, 2026-07-01) and Asmar Khasmammadli → Andrew Birnberg (`andrew-birnberg`, 2026-06-23). They flip `prior_engagement = 1` only once the matching prospects exist in `prospects`; until then they land in `replies` with `synced_to_scorer = false`. Expect ~11 `CONNECTION_ACCEPTED`, ~21 `BENIGN_NO_ACTION`, and 0 `FAILED`. Anything in `FAILED` means a benign code is being mis-bucketed.

---

## Install

The cron execs `fetch_heyreach.py` from inside the skill dir, so the install must fetch the
worker too — curling `SKILL.md` alone leaves the 7 AM job failing with file-not-found.

```bash
mkdir -p ~/.hermes/skills/gitm/gitm-heyreach-sync ~/.hermes/scripts

# skill doc
curl -fsSL -o ~/.hermes/skills/gitm/gitm-heyreach-sync/SKILL.md \
  https://raw.githubusercontent.com/jorge-maldonad0/runtime/main/skills/gitm-heyreach-sync.md

# worker (the actual logic the cron runs)
curl -fsSL -o ~/.hermes/skills/gitm/gitm-heyreach-sync/fetch_heyreach.py \
  https://raw.githubusercontent.com/jorge-maldonad0/runtime/main/skills/gitm-heyreach-sync/fetch_heyreach.py

# runner
curl -fsSL -o ~/.hermes/scripts/heyreach_sync.sh \
  https://raw.githubusercontent.com/jorge-maldonad0/runtime/main/scripts/heyreach_sync.sh
chmod +x ~/.hermes/scripts/heyreach_sync.sh

hermes skills list | grep gitm-heyreach-sync
```

`heyreach_sync.sh` is `source /root/.hermes/.env` then `exec python3 <skill dir>/fetch_heyreach.py`.
The `source` (not `export $(... xargs)`) is deliberate: it preserves the `=` inside
`HEYREACH_API_KEY`. Do not change it to the xargs pattern.
