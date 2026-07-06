---
name: gitm-heyreach-sync
description: Daily HeyReach reply-ingestion for Git.M's GTM stack. Polls HeyReach for new reply, connection, and failure activity across active campaigns, upserts each into the Airtable `replies` table, and sets prior_engagement = 1 on the matching scorer_ready_rows row so reply outcomes reach Danny's scorer and activate the dossier-builder trigger queue. This is the sole owner of the prior_engagement field. Runs on a 7 AM PST cron. Use when reply data needs to flow from HeyReach into Airtable and the scorer.
---

# gitm-heyreach-sync

## Description

Reply-ingestion skill for Git.M's GTM agent stack. Polls HeyReach once daily for new reply/connection activity across active campaigns, writes it to the Airtable `replies` table, and flips `prior_engagement = 1` on the matching `scorer_ready_rows` row so reply outcomes flow into the scorer and activate the `gitm-dossier-builder` trigger queue.

This is the pipeline referenced as "Jorge (via HeyReach reply pipeline)" in `input_contract.md` and as the `prior_engagement` source in `gitm-affinity-mapper`. It is the one skill allowed to write `prior_engagement`.

---

## Trigger

Hermes cron, once daily at 7:00 AM PST — ahead of the 8:50 fork sync and 9:00 standup so the day's queue has fresh reply data. Clear of the every-30-min affinity poll.

---

## Enrichment steps

### Step 1 — Fetch reply activity from HeyReach

Pull all activity since the last run. Statuses of interest: `REPLIED`, `AWAITING_REPLY`, `CONNECTION_ACCEPTED`, `FAILED`.

Extract per prospect:
- `lead_first_name`, `lead_last_name`
- `lead_linkedin_url` (unique join key)
- `sender_first_name`, `sender_last_name`
- `last_action_taken`, `last_action_time`
- `sender_status`
- `failed_reason_code` (if present)

Normalize `lead_linkedin_url` before using it as a key: strip locale suffixes and query params (same normalization the affinity mapper applies), so match keys are consistent across skills.

### Step 2 — Compute derived fields

- `replied` (int 0/1): 1 if `sender_status == REPLIED`
- `days_to_reply` (float or null): only if both send and reply timestamps are available. HeyReach's export exposes only `last_action_time`, so this is a known data gap — write null, not 0. Do not fabricate.
- `failed` (int 0/1): 1 if `sender_status == FAILED`
- `failed_reason` (string or null): pass through `failed_reason_code`

### Step 3 — Write to the `replies` table (dedup on `linkedin_url`)

Upsert one row per prospect keyed on `prospect_linkedin_url`. Update in place if the row exists — never append duplicates.

| Field | Type | Source |
|---|---|---|
| `prospect_linkedin_url` | Single line text (primary) | HeyReach — join key |
| `prospect_name` | Single line text | `lead_first_name` + `lead_last_name` |
| `sender_name` | Single line text | `sender_first_name` + `sender_last_name` |
| `sender_id` | Single select | Mapped from sender name (see map below) |
| `sender_status` | Single select | HeyReach `sender_status` |
| `last_action` | Single line text | HeyReach `last_action_taken` |
| `last_action_time` | Date/time | HeyReach `last_action_time` |
| `replied` | Number (int 0/1) | Computed |
| `days_to_reply` | Number (decimal) or null | Computed — null for v0 |
| `failed` | Number (int 0/1) | Computed |
| `failed_reason` | Single line text or null | HeyReach |
| `sentiment` | Single select or null | Null for v0 (separate skill later) |
| `variant_served` | Single line text or null | Null for v0 (manual lookup later) |
| `matched_prospect_id` | Single line text or null | Resolved in Step 4; null if no match |
| `synced_to_scorer` | Checkbox | True once Step 4 write succeeds |

### Step 4 — Resolve to prospect and update the scorer

For each row where `replied == 1`:

1. Look up `prospects` for a row whose `linkedin_url` matches `prospect_linkedin_url` (after normalization). Record `prospect_id` into `replies.matched_prospect_id`.
2. Map `sender_name → sender_id` (see map). This selects the correct prospect-sender row.
3. In `scorer_ready_rows`, find the row where `prospect_id` + `sender_id` match, and set `prior_engagement = 1`.
4. Set `replies.synced_to_scorer = true`.

If no `prospects` match is found: leave `matched_prospect_id` null, `synced_to_scorer` false, and note it. Do not create a prospect row from reply data — out of scope for v0.

A reply comes in through one sender, so this updates only that prospect-sender row.

**This skill does not write `engagement_score`.** The engagement rubric scores a reply at 1.0, but `engagement_score` is Khoa's field; a second writer would collide with the affinity/engagement pipeline. This skill owns `prior_engagement` only. Recomputing `engagement_score` on reply is engagement-scout's job unless ownership is reassigned.

### Step 5 — Log run

Log to `status_loop_runs`: `{ date, mode: "heyreach_sync", replies_found, rows_upserted, scorer_rows_updated, unmatched }`.

---

## Sender name → sender_id map

Active campaigns:

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
3. `prior_engagement` is only ever set to 1 by this skill — never 0 (defaults are owned by affinity-mapper at row creation).
4. Scorer write only fires on a confirmed `prospect_id` + `sender_id` match.
5. `days_to_reply` is null, not 0, when the timestamp is unavailable.

---

## Error handling

- HeyReach unreachable: log warning, exit cleanly, retry next run. Do not partially write.
- No `prospects` match: write `replies` row, leave scorer untouched, note unmatched.
- Airtable write fails: retry once after 30s, log, continue to next prospect.
- Unmappable `sender_name`: write `replies` row without `sender_id`, skip scorer write, note it.
- Duplicate reply (same `linkedin_url`): update in place, never append.

---

## Environment variables required

```
HEYREACH_API_KEY        # add to ~/.hermes/.env before first run
AIRTABLE_API_KEY
AIRTABLE_BASE_ID        # appi400mk6PHDF6Ex (GTM Reservoir)
```

---

## Airtable setup required

Create the `replies` table in GTM Reservoir (`appi400mk6PHDF6Ex`) with the Step 3 fields before first run. Single-select options:
- `sender_id`: `asmar`, `jane`, `giancarlos`, `evan`
- `sender_status`: `REPLIED`, `AWAITING_REPLY`, `CONNECTION_ACCEPTED`, `FAILED`
- `sentiment`: leave without options for v0 (populated later)

---

## Cron schedule

Register after the first manual run passes:

```bash
hermes cron create "0 7 * * *" "poll heyreach replies and sync to airtable" --skill gitm-heyreach-sync --name gitm-heyreach-sync
```

---

## Manual test

```bash
hermes chat --skill gitm-heyreach-sync
```

Then type:

```
Poll HeyReach for new reply activity across active campaigns. Upsert each prospect into the replies table in Airtable keyed on prospect_linkedin_url. For each replied prospect, resolve linkedin_url to prospect_id via the prospects table, map sender name to sender_id, and set prior_engagement = 1 on the matching scorer_ready_rows row. Log the run to status_loop_runs.
```

---

## Install

```bash
curl -o ~/.hermes/skills/gitm/gitm-heyreach-sync/SKILL.md \
  https://raw.githubusercontent.com/jorge-maldonad0/runtime/main/skills/gitm-heyreach-sync.md

hermes skills list | grep gitm-heyreach-sync
```
