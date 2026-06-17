# gitm-internal-status-loop

## Description

Internal meta-loop skill for Git.M's GTM sprint. Runs three output modes: a daily team standup loop (Mode 1), a founder-approval DM loop (Mode 2), and a bidirectional Airtable/Slack sync (Mode 3). No founder interruption on Mode 1. Mode 2 fires only on explicit approval triggers. Mode 3 is always-on via webhook and cron.

---

## Scheduling

Mode 1 runs on a cron schedule. Modes 2 and 3 are event-driven but also poll as a fallback.

Use Hermes native cron — do not use crontab. hermes chat requires an interactive terminal and cannot be invoked from crontab.

Register the three jobs:

```bash
hermes cron create --skills gitm-internal-status-loop --prompt "run standup mode" --schedule "0 9 * * 1-5" --name "gitm-standup"

hermes cron create --skills gitm-internal-status-loop --prompt "check approval queue" --schedule "*/10 * * * 1-5" --name "gitm-approval-queue"

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

## Mode 1: Team standup (auto, 9:00 AM daily)

### Trigger
Cron. Runs at 9:00 AM every weekday. Invoked with prompt: `"run standup mode"`.

### Inputs
- GitHub: commits from the last 24h from `jorge-maldonad0/runtime` (fork of GitM-Labs/runtime), filtered by author
- Slack: `#gtm-standup` — messages posted since yesterday 9:00 AM
- Airtable: `sprint_tracker` — rows where `updated_at` >= yesterday 9:00 AM

### GitHub API call
```
GET https://api.github.com/repos/jorge-maldonad0/runtime/commits?since={yesterday_9am_iso}&per_page=100
Authorization: token {GITHUB_TOKEN}
```

Filter results by commit author login or email to attribute commits to each intern. If the `sprint_tracker` table is empty or has no rows updated since yesterday, report `no activity logged` for Airtable — do not treat an empty response as an error.

### Steps

1. For each intern (Asmar, Jane, Giancarlos, Danny, Khoa, Arshad):
   - Pull their GitHub commits from the last 24h from `jorge-maldonad0/runtime`
   - Pull their Airtable rows where `owner` = their name and `updated_at` >= yesterday 9:00 AM
   - Pull any Slack messages they posted in `#gtm-standup` since yesterday
   - Synthesize into three fields:
     - **Yesterday:** what they shipped or progressed
     - **Today:** next open tasks from Airtable (status = In Progress or Up Next)
     - **Blockers:** blocker flags in Airtable OR blocker language in Slack messages
   - DM each intern their summary for review using their Slack user ID from `SLACK_INTERN_IDS`:

```
Hey {name} - here's your standup for today:

Yesterday: {yesterday}
Today: {today}
Blockers: {blockers_or_none}

Reply to correct anything before I post to #gtm-standup.
```

2. Wait 15 minutes for replies. Apply any corrections.

3. Compile all six summaries and post to `#gtm-standup` using channel ID from `SLACK_STANDUP_CHANNEL`:

```
*GTM standup - {date}*

*Asmar:* Yesterday: ... | Today: ... | Blockers: ...
*Jane:* Yesterday: ... | Today: ... | Blockers: ...
*Giancarlos:* Yesterday: ... | Today: ... | Blockers: ...
*Danny:* Yesterday: ... | Today: ... | Blockers: ...
*Khoa:* Yesterday: ... | Today: ... | Blockers: ...
*Arshad:* Yesterday: ... | Today: ... | Blockers: ...
```

4. Log to Airtable `status_loop_runs`: `{ date, mode: "standup", status: "ok", interns_DMed: 6 }`.

### Rules
- Do not DM Jalon or any founder.
- Do not post to `#gtm-founder-approvals`.
- If an intern has no activity, mark Yesterday as `no activity logged` — do not omit them.
- If Slack, GitHub, or Airtable is unreachable, log the error and skip that source. Do not fail the whole run.
- Always use channel IDs (format: `C0XXXXXXXX`), never channel names, in all Slack API calls.
- The fork `jorge-maldonad0/runtime` is not auto-synced. A sync cron job runs at 8:50 AM daily to pull latest commits from `GitM-Labs/runtime` before standup fires. If the sync job has not run yet, use whatever commits are available in the fork.

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
2. Skip any rows already in `approved`, `rejected`, or `on_hold` — do not re-trigger.
3. Batch multiple pending items within a 5-minute window into a single DM.
4. Fetch full context for each item and DM Jalon using `SLACK_JALON_USER_ID`:

```
*Approval needed: {trigger_type}*

{context_summary}

Options:
{options_if_applicable}

Recommendation: {recommendation_if_applicable}

Reply with *approve*, *reject*, or *hold*.
```

5. On reply:
   - `approve` -> update Airtable row `status = approved`, DM requesting intern
   - `reject` -> update Airtable row `status = rejected`, DM requesting intern with reason
   - `hold` -> update Airtable row `status = on_hold`, DM requesting intern

6. Post summary to `#gtm-founder-approvals` using channel ID from `SLACK_APPROVALS_CHANNEL`:

```
*{trigger_type} - {approved/rejected/on_hold}*
Requested by: {intern}
Decision: {decision}
Time to decision: {elapsed}
```

7. Log to `status_loop_runs`: `{ date, mode: "founder_approval", trigger_type, decision, elapsed_minutes }`.

### Rules
- Only DM Jalon. Do not DM other founders.
- Do not post approval requests to `#gtm-standup`.
- Always use Jalon's Slack user ID from `SLACK_JALON_USER_ID`, not his name or handle.

---

## Mode 3: Bidirectional sync (Airtable <-> Slack)

### Overview
Two-way live sync between `sprint_tracker` and `#gtm-standup`. Any status change in Airtable posts to Slack. Any thread reply in Slack updates the tracker `notes` field.

---

### Direction 1: Airtable change -> Slack post

#### Trigger
Cron poll every 10 minutes. Invoked with prompt: `"check airtable changes"`. Checks `sprint_tracker` for rows where `updated_at` >= last poll time.

#### Steps

1. Query `sprint_tracker` for rows changed since last poll.
2. For each changed row, extract: `task_name`, `owner`, `status`, `updated_at`.
3. Post to `#gtm-standup` using channel ID from `SLACK_STANDUP_CHANNEL`:

```
*Tracker update*
Task: {task_name}
Owner: {owner}
Status changed to: {status}
```

4. Store the Slack message `ts` and `thread_ts` against the Airtable row ID in `sync_index` table.
5. Log to `status_loop_runs`: `{ date, mode: "airtable_to_slack", record_id, task_name, new_status }`.

#### Rules
- Do not re-post if the row was already posted in the last poll cycle (check `sync_index` for existing `airtable_record_id`).
- If Slack post fails, retry once after 30s, then log and continue.
- An empty `sprint_tracker` is not an error — log `no_changes_found` and exit cleanly.

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
6. Log to `status_loop_runs`: `{ date, mode: "slack_to_airtable", record_id, slack_user }`.

#### Rules
- Append only to `notes` field.
- Ignore replies from the Hermes bot account `U0B94BY1M2R` (prevents feedback loops).
- If Airtable write fails, retry once after 30s, then DM the reply author: `"Could not sync your reply to the tracker - please update manually."`

---

## Airtable schema dependencies

| Table | Fields used |
|---|---|
| `sprint_tracker` | `owner`, `status`, `updated_at`, `task_name`, `blockers`, `notes` |
| `approval_queue` | `type`, `status`, `requested_by`, `context`, `created_at` |
| `blockers` | `description`, `raised_by`, `escalation`, `created_at` |
| `status_loop_runs` | `date`, `mode`, `status`, `interns_DMed`, `trigger_type`, `decision`, `elapsed_minutes`, `record_id`, `slack_user` |
| `sync_index` | `airtable_record_id`, `slack_message_ts`, `slack_thread_ts`, `task_name`, `created_at` |

Note: `sprint_tracker` must have rows with the correct `owner` field values (Asmar, Jane, Giancarlos, Danny, Khoa, Arshad) for standup data to appear. An empty table will result in `no activity logged` for all interns — this is expected behavior, not an error.

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

## Error handling

- Source unreachable (GitHub / Airtable / Slack): log warning, skip source, continue run. Append `[source unavailable]` to affected fields.
- Slack DM delivery failure: retry once after 60s, then log to Airtable and continue.
- No activity detected for an intern: do not skip — report `no activity logged`.
- Empty Airtable tables (`sprint_tracker`, `approval_queue`): not an error — log `no_changes_found` and exit cleanly.
- Duplicate trigger detected (same `approval_queue` row): no-op, already handled.
- Duplicate sync detected (same `airtable_record_id` in `sync_index`): no-op, skip re-post.
- GitHub 404: check that `jorge-maldonad0/runtime` fork exists and GITHUB_TOKEN belongs to `jorge-maldonad0`.
- Gateway not running: all cron jobs will silently fail. Run `ps aux | grep "hermes gateway"` to verify the gateway process is alive.

---

## Install

```bash
curl -o ~/.hermes/skills/gitm-internal-status-loop.md \
  https://raw.githubusercontent.com/GitM-Labs/runtime/main/skills/gitm-internal-status-loop.md

hermes skills list | grep gitm-internal-status-loop
```

## Test manually

```bash
hermes chat --skills gitm-internal-status-loop
# then type: run standup mode
# then type: check approval queue
# then type: check airtable changes
```

Note: the prompt must be typed interactively inside the chat session, not passed as an inline argument.
