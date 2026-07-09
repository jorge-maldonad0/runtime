---
name: gitm-internal-status-loop
description: Internal meta-loop skill for Git.M's GTM sprint — standup DM loop, founder approval queue, and bidirectional Airtable/Slack sync.
---

# gitm-internal-status-loop

## Description

Internal meta-loop skill for Git.M's GTM sprint. Runs four output modes: a daily standup check-in DM loop (Mode 1a), a noon standup collection and post loop (Mode 1b), a founder-approval DM loop (Mode 2), and a bidirectional Airtable/Slack sync (Mode 3). No founder interruption on Mode 1. Mode 2 fires only on explicit approval triggers. Mode 3 is always-on via webhook and cron.

---

## Scheduling

Use Hermes native cron — do not use crontab. hermes chat requires an interactive terminal and cannot be invoked from crontab.

Register all jobs:

```bash
# Fork sync — pulls latest commits before check-in DMs go out
hermes cron create --skills gitm-internal-status-loop --prompt "sync fork" --schedule "50 8 * * 1-5" --name "gitm-fork-sync"

# Mode 1a — DM interns at 9:00 AM PST asking for standup responses
hermes cron create --skills gitm-internal-status-loop --prompt "send standup check-in DMs" --schedule "0 9 * * 1-5" --name "gitm-standup-checkin"

# Mode 1b — collect replies and post compiled standup at 12:00 PM PST
hermes cron create --skills gitm-internal-status-loop --prompt "collect standup replies and post" --schedule "0 12 * * 1-5" --name "gitm-standup-post"

# Mode 2 — approval queue poll every 10 minutes on weekdays
hermes cron create --skills gitm-internal-status-loop --prompt "check approval queue" --schedule "*/10 * * * 1-5" --name "gitm-approval-queue"

# Mode 3 — Airtable sync poll every 10 minutes on weekdays
hermes cron create --skills gitm-internal-status-loop --prompt "check airtable changes" --schedule "*/10 * * * 1-5" --name "gitm-airtable-sync"
```

Verify:
```bash
hermes cron list
hermes cron status
```

The Hermes gateway must be running for cron jobs to execute:
```bash
hermes gateway run &
```

If the VM restarts, the gateway will not come back up automatically unless you have added it to startup:
```bash
echo "@reboot /root/.local/bin/hermes gateway run" | crontab -
```

---

## Mode 1a: Standup check-in DMs (9:00 AM PST daily)

### Trigger
Cron. Runs at 9:00 AM PST every weekday. Invoked with prompt: `"send standup check-in DMs"`.

### Steps

1. Pull GitHub commits from the last 24h from `jorge-maldonad0/runtime`:
```
GET https://api.github.com/repos/jorge-maldonad0/runtime/commits?since={yesterday_9am_iso}&per_page=100
Authorization: token {GITHUB_TOKEN}
```
Filter by author login to identify which intern made which commits.

2. For each intern (Asmar, Jane, Giancarlos, Danny, Khoa, Arshad):
   - Look up their GitHub commits from step 1
   - Check Airtable `sprint_tracker` for their open tasks (status = `In Progress` or `Up Next`)
   - DM them using their Slack user ID from `SLACK_INTERN_IDS`:

```
Hey {name}! Time for your daily standup. Please reply to this message with:

1. *Yesterday:* What did you work on or complete?
2. *Today:* What are you working on today?
3. *Blockers:* Anything blocking you? (reply "none" if not)
4. *Task name:* What is the main task you're focused on?
5. *Status:* What is the status of your current task? (Not Started / In Progress / Complete / Blocked)
6. *Notes:* Any additional context? (optional)

I'll collect responses until noon and post the team standup. GitHub shows {commit_count} commit(s) from you in the last 24h.
```

   - If the intern has open Airtable tasks, append to the DM:
```
Your open tasks in the tracker: {task_list}
```

3. Store each DM's `ts` and `channel` in Airtable `standup_dm_index` table:
```
{ date, intern_name, slack_user_id, dm_ts, dm_channel, response_received: false }
```

4. Log to `status_loop_runs`: `{ date, mode: "standup_checkin", status: "ok", interns_DMed: 6 }`.

### Rules
- Do not DM Jalon or any founder.
- Do not post to `#gtm-founder-approvals`.
- Always use user IDs from `SLACK_INTERN_IDS`, never names or handles.
- If GitHub is unreachable, set `commit_count = 0` and continue — do not skip DMs.
- If Airtable is unreachable, skip the open tasks append — do not skip DMs.
- If a DM fails to deliver, retry once after 60s, then log and continue.

---

## Mode 1b: Collect replies and post standup (12:00 PM PST daily)

### Trigger
Cron. Runs at 12:00 PM PST every weekday. Invoked with prompt: `"collect standup replies and post"`.

### Steps

1. For each intern, look up their `dm_ts` and `dm_channel` from `standup_dm_index` for today's date.

2. Fetch the DM thread replies using the Slack conversations.replies API:
```
GET https://slack.com/api/conversations.replies?channel={dm_channel}&ts={dm_ts}
Authorization: Bearer {SLACK_BOT_TOKEN}
```

3. Parse each intern's reply and extract:
   - `yesterday` — from "Yesterday:" field in reply
   - `today` — from "Today:" field in reply
   - `blockers` — from "Blockers:" field in reply
   - `task_name` — from "Task name:" field in reply
   - `status` — from "Status:" field in reply (Not Started / In Progress / Complete / Blocked)
   - `notes` — from "Notes:" field in reply (optional)

4. If no reply received by noon: mark all fields as `no response` — do not omit the intern.

5. Write or update one row per intern in Airtable `sprint_tracker`:
   - `owner` = intern name
   - `task_name` = from reply
   - `status` = from reply
   - `blockers` = from reply
   - `notes` = from reply
   - `updated_at` = today's date

6. Compile all six summaries and post to `#gtm-standup` using channel ID from `SLACK_STANDUP_CHANNEL`:

```
*GTM standup - {date}*

*Asmar:* Yesterday: {yesterday} | Today: {today} | Blockers: {blockers}
*Jane:* Yesterday: {yesterday} | Today: {today} | Blockers: {blockers}
*Giancarlos:* Yesterday: {yesterday} | Today: {today} | Blockers: {blockers}
*Danny:* Yesterday: {yesterday} | Today: {today} | Blockers: {blockers}
*Khoa:* Yesterday: {yesterday} | Today: {today} | Blockers: {blockers}
*Arshad:* Yesterday: {yesterday} | Today: {today} | Blockers: {blockers}
```

7. Update `standup_dm_index` rows: set `response_received = true` for interns who replied.

8. Log to `status_loop_runs`: `{ date, mode: "standup_post", status: "ok", responses_received: N, no_response: M }`.

### Rules
- Always post at noon even if zero interns replied — mark non-responders as `no response`.
- Never overwrite existing `sprint_tracker` rows — update in place using `owner` + `date` as key.
- Always use channel ID from `SLACK_STANDUP_CHANNEL`, never the channel name.
- If Airtable write fails, retry once after 30s, log and continue — do not skip the Slack post.

---

## Airtable: standup_dm_index table

New table required to track DM timestamps for reply collection.

| Field | Type | Description |
|---|---|---|
| `date` | Date | Date of standup |
| `intern_name` | Single line text | Intern name |
| `slack_user_id` | Single line text | Intern Slack user ID |
| `dm_ts` | Single line text | Slack message timestamp of the check-in DM |
| `dm_channel` | Single line text | DM channel ID returned by Slack when DM was sent |
| `response_received` | Checkbox | Whether intern replied before noon |
| `response_text` | Long text | Raw reply text from intern |

---

## Mode 2: Founder approval (DM Jalon, event-driven)

### Trigger
Cron poll every 10 minutes. Invoked with prompt: `"check approval queue"`. Also fires from Slack webhook if configured.

Fires when any of the following conditions are detected:

| Trigger type | Detection method |
|---|---|
| Tool account approval needed | Airtable `approval_queue` - new row with `type = tool_account` and `status = pending` |
| Copy variant sign-off needed | Airtable `approval_queue` - new row with `type = copy_variant` and `status = pending` |
| Cross-team blocker | Airtable `blockers` - new row with `escalation = founder` OR Slack trigger phrase in any `#gtm-*` channel |
| VM / infra decision | Airtable `approval_queue` - new row with `type = infra` and `status = pending` |

Trigger phrases for Slack scan: `"need sign-off"`, `"founder decision"`, `"blocked on Jalon"`, `"needs approval"`, `"escalate"`.

### Steps

1. Query Airtable `approval_queue` for rows where `status = pending`.
2. Also query `blockers` for rows where `escalation = founder`.
3. Skip any rows already in `approved`, `rejected`, or `on_hold` — do not re-trigger.
4. Batch multiple pending items within a 5-minute window into a single DM.
5. Fetch full context for each item and DM Jalon using `SLACK_JALON_USER_ID`:

```
*Approval needed: {trigger_type}*

{context_summary}

Options:
{options_if_applicable}

Recommendation: {recommendation_if_applicable}

Reply with *approve*, *reject*, or *hold*.
```

6. On reply:
   - `approve` -> update Airtable row `status = approved`, DM requesting intern
   - `reject` -> update Airtable row `status = rejected`, DM requesting intern with reason
   - `hold` -> update Airtable row `status = on_hold`, DM requesting intern

7. Post summary to `#gtm-founder-approvals` using channel ID from `SLACK_APPROVALS_CHANNEL`:

```
*{trigger_type} - {approved/rejected/on_hold}*
Requested by: {intern}
Decision: {decision}
Time to decision: {elapsed}
```

8. Log to `status_loop_runs`: `{ date, mode: "founder_approval", status: "ok", trigger_type: <one_of_valid> }`. If no items found, log `status: "no_pending"` and omit `trigger_type`.

### Rules
- Only DM Jalon. Do not DM other founders.
- Do not post approval requests to `#gtm-standup`.
- Always use Jalon's Slack user ID from `SLACK_JALON_USER_ID`, not his name or handle.
- When no pending items are found in either table, log `status: "no_pending"` with no `trigger_type` and exit cleanly.

---

## Mode 3: Bidirectional sync (Airtable <-> Slack)

### Overview
Two-way live sync between `sprint_tracker` and `#gtm-standup`. Any status change in Airtable posts to Slack. Any thread reply in Slack updates the tracker `notes` field.

---

### Direction 1: Airtable change -> Slack post

#### Trigger
Cron poll every 10 minutes. Invoked with prompt: `"check airtable changes"`. Checks `sprint_tracker` for rows where `updated_at` >= last poll time.

#### Steps

1. Determine last poll time:
   - Option A: Use `latest_run_of_mode('airtable_to_slack')` from `airtable_utils.py` and read `record['createdTime']` from the returned record. Fall back to `datetime.now() - timedelta(minutes=10)` if no prior run exists.
   - Option B (simpler): Always use a 15-minute lookback window (`datetime.now() - timedelta(minutes=15).isoformat()`). This works reliably because the cron fires every 10 minutes — the extra 5-minute overlap ensures no changes are missed.
   - Do NOT sort by `created_at` — that field does not exist in `status_loop_runs` and will cause a 422 error.
2. For each changed row, extract: `task_name`, `owner`, `status`, `updated_at`.
3. Post to `#gtm-standup` using channel ID from `SLACK_STANDUP_CHANNEL`:

```
*Tracker update*
Task: {task_name}
Owner: {owner}
Status changed to: {status}
```

4. Store the Slack message `ts` and `thread_ts` against the Airtable row ID in `sync_index` table.
5. Log to `status_loop_runs`: `{ date, mode: "airtable_to_slack", status: "ok", record_id, task_name, new_status }`.

#### Rules
- Do not re-post if the row was already posted in the last poll cycle (check `sync_index` for existing `airtable_record_id`).
- If Slack post fails, retry once after 30s, then log and continue.
- An empty `sprint_tracker` is not an error — log `status: "ok"` and exit cleanly.

---

### Direction 2: Slack thread reply -> Airtable update

#### Trigger
Cron poll every 10 minutes as fallback. Checks `#gtm-standup` for new thread replies since last poll.

#### Steps

1. Fetch recent thread replies in `#gtm-standup`.
2. For each reply, check `sync_index` for a matching `slack_thread_ts`.
3. If no match: ignore (not a tracker thread).
4. If match found:
   - Append reply to the `notes` field of the matching `sprint_tracker` row:
     ```
     [{slack_user_name} via Slack, {timestamp}]: {reply_text}
     ```
   - Append only — never overwrite existing notes.
5. React with a checkmark emoji to confirm sync.
6. Log to `status_loop_runs`: `{ date, mode: "slack_to_airtable", status: "ok", record_id, slack_user }`.

#### Rules
- Append only to `notes` field.
- Ignore replies from the Hermes bot account `U0B94BY1M2R` (prevents feedback loops).
- If Airtable write fails, retry once after 30s, then DM the reply author: `"Could not sync your reply to the tracker - please update manually."`

---

## Airtable schema dependencies

| Table | Fields used |
|---|---|
| `sprint_tracker` | `owner`, `status`, `updated_at`, `task_name`, `blockers`, `notes` |
| `standup_dm_index` | `date`, `intern_name`, `slack_user_id`, `dm_ts`, `dm_channel`, `response_received`, `response_text` |
| `approval_queue` | `type`, `status`, `requested_by`, `context`, `created_at` |
| `blockers` | `description`, `raised_by`, `escalation`, `created_at` |
| `status_loop_runs` | `date`, `mode`, `status`, `interns_DMed`, `trigger_type`, `decision`, `elapsed_minutes`, `record_id`, `slack_user` |
| `sync_index` | `airtable_record_id`, `slack_message_ts`, `slack_thread_ts`, `task_name`, `created_at` |

Note: `sprint_tracker` is now written to by Hermes at noon based on intern DM replies. Interns do not need to update Airtable manually. An empty table at standup time is expected — Hermes populates it after collecting replies.

---

## Airtable singleSelect enum constraints

The `status_loop_runs` table uses singleSelect fields with strict enum values. Writing an unrecognized value causes `422 INVALID_MULTIPLE_CHOICE_OPTIONS`:

| Field | Valid options |
|---|---|
| `mode` | `standup`, `founder_approval`, `airtable_to_slack`, `slack_to_airtable`, `signal_scan_github`, `heyreach_sync` |
| `status` | `ok`, `error`, `partial` |
| `trigger_type` | `tool_account`, `copy_variant`, `infra`, `cross_team_blocker` |

When no items are found (Mode 2 empty queue, Mode 3 no changes), log `status: "ok"` and omit `trigger_type` — do not attempt to write `no_changes_found` (it is not a valid option).

## Pitfalls

### `status_loop_runs` has no `created_at` field

The `status_loop_runs` table does NOT have a user-created `created_at` field. Each record has an Airtable-system `createdTime` (available at `record['createdTime']`), but you cannot sort by a field that doesn't exist — that causes `422 INVALID_MULTIPLE_CHOICE_OPTIONS`.

To find the last poll time for a mode, use `latest_run_of_mode(mode)` from `airtable_utils.py` — it sorts by Airtable's internal `createdTime` value (which works as a sort field name). Then fall back to `datetime.now() - timedelta(minutes=10)` if no prior run exists.

Do NOT use `sort[0][field]=created_at` — that field does not exist in the schema.

### BOM prefix on `sprint_tracker.task_name`

The `sprint_tracker` table has a BOM (byte order mark `\ufeff`) prefix on `task_name`. The field name in Airtable meta shows as `﻿task_name` (with invisible BOM). When querying or filtering by this field name, use the key `task_name` in field access (it works), but be aware the Airtable API schema lists it with the BOM prefix.

## Airtable query syntax

When sorting Airtable records, use query parameter syntax, not a `sort` key in params:

```python
# CORRECT:
params = {'sort[0][field]': 'created_at', 'sort[0][direction]': 'desc'}
requests.get(url, headers=headers, params=params)

# WRONG (422 error):
params = {'sort': [{'field': 'created_at', 'direction': 'desc'}]}
```

Filter formulas with string values: wrap in single quotes inside the formula:
```python
params = {'filterByFormula': "{status}='pending'"}
```

---

## Environment variables required

```
SLACK_BOT_TOKEN         # needs chat:write, im:write, channels:read, channels:history
SLACK_STANDUP_CHANNEL   # #gtm-standup channel ID (format: C0XXXXXXXX, not channel name)
SLACK_APPROVALS_CHANNEL # #gtm-founder-approvals channel ID (format: C0XXXXXXXX)
SLACK_JALON_USER_ID     # Jalon's Slack user ID (format: U0XXXXXXXX)
SLACK_INTERN_IDS        # JSON map: { "Asmar": "U...", "Jane": "U...", "Giancarlos": "U...", "Danny": "U...", "Khoa": "U...", "Arshad": "U..." }
AIRTABLE_API_KEY
AIRTABLE_BASE_ID
GITHUB_TOKEN            # repo scope. Token belongs to jorge-maldonad0.
GITHUB_REPO             # jorge-maldonad0/runtime (fork of GitM-Labs/runtime)
```

---

## Environment variables: load strategy

Environment variables may live in any of these locations. Check all when running outside the Hermes cron context:

- `/root/.env`
- `/root/.hermes/.env`
- `/root/runtime/.env`
- `os.environ` (set by Hermes cron)

Hermes cron jobs set env vars automatically; for manual testing, source the env file first.

---

## Error handling

- Source unreachable (GitHub / Airtable / Slack): log warning with `status: "error"`, skip source, continue run. Append `[source unavailable]` to affected fields.
- Slack DM delivery failure: retry once after 60s, then log to Airtable and continue.
- No reply from intern by noon: mark all fields as `no response` — do not omit from standup post.
- Empty Airtable tables: not an error — use `status: "ok"` in `status_loop_runs` and exit cleanly. Do NOT write `no_changes_found` — not a valid enum.
- Airtable 422 on logging: double-check the `status` and `trigger_type` values against the singleSelect enum constraints above.
- Duplicate trigger detected (same `approval_queue` row): no-op, already handled.
- Duplicate sync detected (same `airtable_record_id` in `sync_index`): no-op, skip re-post.
- GitHub 404: check that `jorge-maldonad0/runtime` fork exists and GITHUB_TOKEN belongs to `jorge-maldonad0`.
- Gateway not running: all cron jobs will silently fail. Run `ps aux | grep "hermes gateway"` to verify the gateway process is alive.

## Tirith security scanner (cron execution)

Hermes cron jobs run with tirith security scanning enabled (`security.tirith_enabled: true` in config.yaml). This blocks certain inline execution patterns:

| Blocked pattern | Example | Workaround |
|---|---|---|
| `curl \| python3` | `curl ... \| python3 -m json.tool` | Write a `.py` script file and run it |
| `python3 -c` | `python3 -c "import os; ..."` | Write script to `/tmp/` and execute it |
| Shell var interpolation with secrets | `curl -H "Authorization: Bearer $KEY"` | Use `os.environ['KEY']` inside the Python script instead |

**Preferred approach for API calls in cron jobs:**

1. Write a standalone Python script to `/tmp/<task>.py` using `write_file`
2. The script uses `urllib.request` (stdlib — no pip deps needed) and reads env vars via `os.environ[]`
3. Execute with `python3 /tmp/<task>.py`
4. The script handles all API calls (Airtable, Slack, GitHub) in a single process

Example pattern for Airtable queries:
```python
import os, json, urllib.request
key = os.environ['AIRTABLE_API_KEY']
base = os.environ['AIRTABLE_BASE_ID']
def query(table, params=''):
    url = f'https://api.airtable.com/v0/{base}/{table}?{params}'
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {key}'})
    return json.loads(urllib.request.urlopen(req).read())
```

Note: `env_passthrough` in config.yaml must include the env var keys for them to be accessible in terminal/execute_code contexts. Check `docker_env` section in config.yaml if vars are missing from environment.

---

## Airtable setup required

Before running, create the `standup_dm_index` table in the GTM Reservoir base (`appi400mk6PHDF6Ex`) with these fields:
- `date` (Date)
- `intern_name` (Single line text)
- `slack_user_id` (Single line text)
- `dm_ts` (Single line text)
- `dm_channel` (Single line text)
- `response_received` (Checkbox)
- `response_text` (Long text)

---

## Cron jobs summary

| Job name | Schedule | Prompt |
|---|---|---|
| `gitm-fork-sync` | 8:50 AM weekdays | `sync fork` |
| `gitm-standup-checkin` | 9:00 AM weekdays | `send standup check-in DMs` |
| `gitm-standup-post` | 12:00 PM weekdays | `collect standup replies and post` |
| `gitm-approval-queue` | every 10 min weekdays | `check approval queue` |
| `gitm-airtable-sync` | every 10 min weekdays | `check airtable changes` |

---

## Install

```bash
curl -o ~/.hermes/skills/gitm-internal-status-loop.md \
  https://raw.githubusercontent.com/jorge-maldonad0/runtime/main/skills/gitm-internal-status-loop.md

hermes skills list | grep gitm-internal-status-loop
```

## Reference files

- [references/airtable_utils.py](references/airtable_utils.py) — Reusable Airtable client class (stdlib-only, tirith-safe for cron execution). Use `airtable_client()`, `.query()`, `.create()`, `.update()`, `.log_run()` in all cron tasks. Includes `sprint_tracker_changes_since()`, `sync_index_for_record()`, and `latest_run_of_mode()` helpers.
- [references/airtable_schema.md](references/airtable_schema.md) — Full Airtable schema with all tables, field types, singleSelect choices, and key constraints. Consult this before writing queries to avoid 422 errors from invalid field names or enum values.

## Test manually

```bash
hermes chat --skills gitm-internal-status-loop
# then type: send standup check-in DMs
# then type: collect standup replies and post
# then type: check approval queue
# then type: check airtable changes
```

Note: the prompt must be typed interactively inside the chat session, not passed as an inline argument.