---
name: gitm-draft-voice
description: Drafting skill for Git.M's GTM agent stack. Takes a scored prospect-sender pair from scorer_ready_rows, pulls sender persona from Airtable and voice rules from Pinecone, selects the right copy variant, personalizes the message in Git.M's voice, and writes the draft to outreach_drafts for Jalon's review queue.
category: gitm
---

# gitm-draft-voice

## Description

Drafting skill for Git.M's GTM agent stack. Runs after scoring. Takes a prospect-sender pair from `scorer_ready_rows`, pulls the sender persona from Airtable and voice rules from Pinecone, selects the right copy variant based on signal data, personalizes the message in Git.M's voice, and writes the draft to the `outreach_drafts` table for FDE review.

This is NOT the full dossier follow-up. That's `gitm-draft-voice-followup` (future). This skill drafts the first cold outbound message only.

---

## What this skill produces

**Input:** `prospect_id` + `sender_id` from `scorer_ready_rows`.

**Output:** One row per prospect-sender pair written to `outreach_drafts`.

### Table: `outreach_drafts`

| Field | Type | Description |
|---|---|---|
| `draft_id` | Single line text (primary) | Unique ID: `draft_{8-char-hash}` |
| `prospect_id` | Single line text | Joins to `prospects` table |
| `sender_id` | Single select | `asmar`, `jane`, `giancarlos` |
| `full_name` | Single line text | Prospect full name |
| `current_company` | Single line text | Current employer |
| `current_title` | Single line text | Current role |
| `linkedin_url` | URL | Prospect LinkedIn |
| `variant_id` | Single line text | Which variant was used: `v0_pick_your_brain`, `v0_industry_study`, `v0_sanity_check` |
| `hook_type` | Single select | `curiosity-flattery`, `research-framing`, `hypothesis-validation` |
| `draft_message` | Long text | The personalized draft message ready to send |
| `domain_used` | Single line text | The `[their domain]` slot fill used |
| `failure_mode_used` | Single line text | The `[failure mode]` slot fill used (sanity-check only) |
| `warmth_type` | Single select | From affinity edge |
| `company_tier` | Number | 1, 2, or 3 |
| `signal_recency` | Number | From scorer |
| `pain_acknowledged` | Number | 0 or 1 |
| `score` | Number | Final score from scorer (if available) |
| `status` | Single select | `pending_review`, `approved`, `rejected`, `sent` |
| `review_notes` | Long text | FDE or founder notes on the draft |
| `created_at` | Date | When draft was generated |

---

## Variant Selection Logic

Select variant based on available signal data:

```
if pain_acknowledged == 1 and signal_recency > 0:
    variant = v0_sanity_check   # has a real pain signal to reference
elif prospect_id ends in odd hash digit:
    variant = v0_pick_your_brain
else:
    variant = v0_industry_study
```

Even distribution of pick-your-brain and industry-study across prospects with no pain signal. Sanity-check only fires when there's a real pain signal to use — never fabricate a failure mode.

---

## Copy Variant Templates

### v0_pick_your_brain
```
Hi [Name]! I'm a UC Berkeley student going deep on how [their domain] teams run GPU workloads at scale, and you're one of the few people who actually lives this. Would love to pick your brain on where it really breaks down. Would value 15 min if you're open to it.
```

### v0_industry_study
```
Hi [Name]! I'm a UC Berkeley student putting together a study on how [their domain] teams handle GPU execution at scale and where the hours really go. You're exactly who I'm hoping to learn from, and I'd share the aggregated findings back. Would value 15 min if you're open to it.
```

### v0_sanity_check
```
Hi [Name]! I'm a UC Berkeley student trying to learn how [their domain] teams run GPU infra from people who've lived it. I keep hearing [failure mode], and I want to sanity-check whether that read holds. You'd know. Would value 15 min, or even a one-line reply.
```

---

## Domain Slot Fill

`[their domain]` must be specific to the prospect's company and workload type. Never use a generic category.

Rules:
- Use `technical_signal` + `current_company` + `current_title` to infer domain
- Never write "X or Y" — pick the most specific one
- Never write a generic category like "AI" or "machine learning"

Examples:
- CoreWeave + GPU infra → "GPU cloud infrastructure"
- Recursion + biotech → "drug discovery compute"
- Boston Dynamics + robotics → "robotics simulation and training"
- Lambda + ML platform → "GPU-accelerated ML serving"
- HPC lab → "scientific compute workloads"

**Pitfall — current_title may be inaccurate.** Some scorer_ready_rows records have current_title set to the company name (e.g. "Rescale" instead of "Director of Strategic Finance"). When current_title duplicates current_company, cross-reference with sender_affinity_edges records for the same prospect_id — the technical_signal field there often contains the real title from the LinkedIn profile scrape. This matters because the domain should reflect the company's core business, not be misdirected by a missing title.

**Pitfall — Multiple sender_affinity_edges records may exist.** The same prospect-sender pair can have both a generic scrape-based edge (with notes like "manual review needed") and a detailed one with full technical_signal text. When multiple records exist, prefer the one with the longer/more detailed technical_signal for domain inference.

---

## Failure Mode Slot Fill (sanity-check only)

`[failure mode]` must come from real `pain_signal_summary` data — never fabricated.

Rules:
- Pull from `pain_signal_summary` field in `scorer_ready_rows` or `signals` table
- Rewrite in the prospect's language, not Git.M's language
- Keep it to one specific, concrete failure mode — not a list
- Must sound like something a practitioner would say, not a vendor

Examples:
- "long MD runs leave GPUs idle between pipeline stages once teams scale"
- "scale-up training runs quietly burn GPU time nobody can trace"
- "p99 latency spikes after the model hits a certain context length"
- "NCCL collectives become the bottleneck once you go past 8 GPUs"

---

## Context Pull Steps

### Step 1 — Pull prospect data from Airtable

Query `scorer_ready_rows` for the prospect-sender pair:
- `warmth`, `warmth_type`, `signal_recency`, `pain_acknowledged`, `company_tier`
- `full_name`, `current_company`, `current_title`, `linkedin_url`

Query `sender_affinity_edges` for:
- `technical_signal`, `technical_keywords`, `pain_signal_summary` (if available)

### Step 2 — Pull sender persona from Airtable

Query `context_sender_personas` where `sender_id` matches. Extract:
- `full_name`, `school`, `voice_register`, `credibility_anchor`, `tone_notes`

### Step 3 — Pull voice rules from Pinecone

Query Pinecone index `gitm-context-store` with:
```
query: "voice rules for cold LinkedIn outreach from {sender_id} sender"
top_k: 5
filter: { record_type: "voice_rule" }
```

Use OpenRouter embeddings to generate the query vector:
```
POST https://openrouter.ai/api/v1/embeddings
Authorization: Bearer {OPENROUTER_API_KEY}
Body: { "model": "openai/text-embedding-3-small", "input": "{query}" }
```

Extract the top 5 voice rules from Pinecone results. These will constrain the draft.

**IMPLEMENTATION NOTE (critical):** Do the embedding + Pinecone query in a single Python script using the `execute_code` tool. Read all API keys with `os.environ['OPENROUTER_API_KEY']` and `os.environ['PINECONE_API_KEY']` INSIDE the Python code. Do NOT interpolate keys into shell commands, echo them, or write them to intermediate files — the shell masks secret values as `***`, which corrupts the key and causes 401/402 errors. The keys are already present in the environment; read them directly in-process. Use `urllib.request` (stdlib), not `requests`. Pinecone host: `https://gitm-context-store-kjtkn5t.svc.aped-4627-b74a.pinecone.io/query`, header `Api-Key`, body `{"vector": [...], "topK": 5, "includeMetadata": true, "filter": {"record_type": "voice_rule"}}`.

### Step 4 — Select variant

Apply variant selection logic from above.

### Step 5 — Fill domain slot

Using `technical_signal`, `current_company`, `current_title`, and `technical_keywords`, determine the most specific `[their domain]` fill. This is a single phrase — specific to what this person's team actually builds.

### Step 6 — Fill failure mode slot (sanity-check only)

If variant is `v0_sanity_check`, pull `pain_signal_summary` and rewrite as a practitioner-voiced failure mode. If no pain signal exists, fall back to `v0_pick_your_brain`.

### Step 7 — Draft the message

Apply the template with filled slots. Then apply voice rules:
- No em dashes
- No filler words ("genuinely", "honestly", "leverage", "utilize", "synergy", "streamline", "innovative")
- No bullet points
- No feature lists
- One CTA only
- Peer-curious register — humble, direct, no sales language
- Lead with output, not cost
- Match sender's school and tone from persona

Final message should be 3-4 sentences maximum. LinkedIn message length.

### Step 8 — Write to Airtable

Write one row to `outreach_drafts` with all fields. Set `status = pending_review`.

### Step 9 — Log run to status_loop_runs

Write one row to `status_loop_runs` with fields:
- `date` — today's date (e.g. `2026-07-09`)
- `status` — `ok`, `error`, or `partial`

Note: `status_loop_runs` only has three fields (`date`, `status`, `mode`). The `mode` field is a single-select column with a restricted option set — "draft_voice" is not an allowed value. Do NOT write `prospect_id`, `sender_id`, `variant_id`, or a new mode value; just `date` and `status`.

---

## Validation Rules

Before writing any row:

1. `draft_message` is present and non-empty
2. `[Name]`, `[their domain]`, `[failure mode]` slots are all filled — no unfilled placeholders in the final message
3. `variant_id` is one of `v0_pick_your_brain`, `v0_industry_study`, `v0_sanity_check`
4. `status` is `pending_review`
5. `domain_used` is specific — reject if it contains "AI", "machine learning", "technology", or "X or Y"
6. If `variant_id = v0_sanity_check`, `failure_mode_used` must be present
7. Draft message contains no em dashes (—)
8. Draft message is under 400 characters

---

## Error Handling

- Pinecone query fails: fall back to reading voice rules directly from `context_voice_rules` Airtable table
- No pain signal for sanity-check: fall back to `v0_pick_your_brain`
- Domain slot too generic: retry with more specific prompt before writing
- Airtable write fails: retry once after 30s, log and continue
- `status_loop_runs` write fails with `INVALID_MULTIPLE_CHOICE_OPTIONS`: the `mode` field is a single-select with a restricted option set — drop the `mode` field and write only `date` + `status`
- `status_loop_runs` write fails with `UNKNOWN_FIELD_NAME`: the field does not exist in that table — drop it and retry

---

## Environment Variables Required

```
AIRTABLE_API_KEY
AIRTABLE_BASE_ID
OPENROUTER_API_KEY      # for Pinecone query embedding
PINECONE_API_KEY        # for voice rule retrieval
PINECONE_INDEX_HOST     # gitm-context-store-kjtkn5t.svc.aped-4627-b74a.pinecone.io
```

---

## Manual Test

```bash
hermes chat --skill gitm-draft-voice --yolo
```

Type inside the session:

```
Generate a draft outreach message for the next unprocessed prospect-sender pair in scorer_ready_rows that does not yet have a row in outreach_drafts. Pull sender persona from context_sender_personas in Airtable. Pull voice rules from Pinecone index gitm-context-store (or context_voice_rules as fallback). Select the correct copy variant based on signal data. Fill all slots with specific, prospect-accurate values. Write the draft to outreach_drafts with status=pending_review. Log date + status to status_loop_runs.
```

---

## Cron Schedule

Run once daily to populate the next day's review queue:

```bash
hermes cron create "0 7 * * 1-5" "generate draft outreach messages for all unprocessed scorer_ready_rows" --skill gitm-draft-voice --name "gitm-draft-voice"
```

---

## Install

```bash
curl -o /root/.hermes/skills/gitm/gitm-draft-voice/SKILL.md \
  https://raw.githubusercontent.com/jorge-maldonad0/runtime/main/skills/gitm-draft-voice.md

hermes skills list | grep gitm-draft-voice
```
