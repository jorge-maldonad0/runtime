# gitm-affinity-mapper

## Description

Light enrichment skill for Git.M's GTM agent stack. Runs on every prospect at top-of-funnel. Takes a LinkedIn profile URL, extracts public affinity features (education, prior employers, OSS, affiliations, conferences), computes warmth per sender, and writes results to two Airtable tables: `sender_affinity_edges` (one row per prospect-sender pair) and `scorer_ready_rows` (scorer-ready view).

This is NOT the full dossier. Papers, talks, and blog posts are handled by gitm-dossier-builder, which triggers only on engagement. This skill is fast and lightweight and runs on every new prospect automatically.

---

## What this skill produces

**Input:** `prospect_id` + `linkedin_url` from Airtable `prospects` table.

**Output — two Airtable tables:**

### Table 1: `sender_affinity_edges`

One row per prospect-sender pair. Matches Khoa's FINAL_75 schema exactly.

| Field | Type | Description |
|---|---|---|
| `affinity_edge_id` | Single line text (primary) | Unique ID: `edge_{8-char-hash}` |
| `prospect_id` | Single line text | e.g. `prospect_coreweave_sarah_tsai` |
| `sender_id` | Single select | `asmar`, `jane`, `giancarlos` |
| `sender_name` | Single line text | Full sender name |
| `full_name` | Single line text | Prospect full name |
| `current_company` | Single line text | Current employer |
| `current_title` | Single line text | Current role |
| `linkedin_url` | URL | Prospect LinkedIn |
| `company_tier` | Number | 1, 2, or 3 (from Arshad's company table) |
| `education_schools` | Long text | Schools found on profile |
| `shared_school` | Long text | Matched school tokens (e.g. `berkeley; university of california`) |
| `warmth` | Number | 0-1 per warmth rubric |
| `warmth_type` | Single select | `cold_stranger`, `same_school_no_direct_overlap`, `mutual_connection`, `affinity_group`, `same_employer_no_direct_overlap`, `direct_prior_colleague`, `manual_review` |
| `warmth_reason_code` | Single line text | e.g. `SHARED_SCHOOL` |
| `warmth_evidence_url` | URL | Required if warmth > 0.1 |
| `warm_path_edge` | Number | 1 if warm path exists, 0 if cold stranger |
| `technical_signal` | Long text | 1-2 sentence summary of technical relevance |
| `technical_keywords` | Long text | Semicolon-separated: `gpu_infrastructure;ml_platform;hpc` |
| `confidence_score` | Number | 1-5 |
| `notes` | Long text | Manual caveats |

### Table 2: `scorer_ready_rows`

One row per prospect-sender pair. Feeds directly into Danny's scorer.

| Field | Type | Description |
|---|---|---|
| `prospect_id` | Single line text | Joins to affinity edges |
| `sender_id` | Single select | `asmar`, `jane`, `giancarlos` |
| `warmth` | Number | From affinity edge |
| `signal_recency` | Number | From signal-scan (0 if no signal found) |
| `company_tier` | Number | From Arshad's company table |
| `pain_acknowledged` | Number | 0 or 1 (from signal-scan) |
| `engagement_score` | Number | From engagement-scout (default 0) |
| `prior_engagement` | Number | 0 or 1 (from HeyReach reply pipeline, default 0) |
| `warmth_type` | Single select | From affinity edge |
| `warmth_evidence_url` | URL | From affinity edge |
| `full_name` | Single line text | Prospect name |
| `current_company` | Single line text | Current employer |
| `current_title` | Single line text | Current role |
| `linkedin_url` | URL | Prospect LinkedIn |
| `reason_codes` | Long text | Comma-separated reason codes |
| `notes` | Long text | Manual caveats |

---

## Prospect ID Format

Generate `prospect_id` as: `prospect_{company_slug}_{name_slug}`

Examples:
- `prospect_coreweave_sarah_tsai`
- `prospect_crusoe_john_smith`
- `prospect_lambda_jane_doe`

---

## Sender Profiles (for warmth computation)

Active senders in W1-W2. Compute warmth against each.

| sender_id | sender_name | School | Key affiliations |
|---|---|---|---|
| `asmar` | Asmar Khasmammadli | UC Berkeley | Check LinkedIn |
| `jane` | Jane | UC Berkeley | Check LinkedIn |
| `giancarlos` | Giancarlos | UC Berkeley | Check LinkedIn |

W3 senders (Jalon, Adit) added when leadership outreach activates.

---

## Warmth Rubric

Use the strongest confirmed signal only. Do not average.

| Warmth situation | warmth | warmth_type |
|---|---|---|
| Cold stranger, no connection | 0.1 | `cold_stranger` |
| Same school, no direct overlap | 0.3 | `same_school_no_direct_overlap` |
| Mutual connection | 0.4 | `mutual_connection` |
| Extracurricular / affinity group | 0.5 | `affinity_group` |
| Same employer, no direct overlap | 0.6 | `same_employer_no_direct_overlap` |
| Direct prior colleague | 0.9 | `direct_prior_colleague` |

If warmth > 0.1, `warmth_evidence_url` must be present. If no evidence URL exists, fall back to `cold_stranger = 0.1`.

---

## Engagement Score Formula

From Khoa's engagement_logic.md:

```
engagement_score = min(1.0, base_event_score * recency_multiplier * relevance_multiplier)
prior_engagement = 1 if engagement_score > 0 else 0
```

Base event scores:
- No visible interaction: 0.0
- Liked a relevant post: 0.3
- Connected with someone at Git.M: 0.5
- Commented on a relevant post: 0.6
- Posted original GPU/infra/ML pain content: 0.8
- Replied to outreach: 1.0

Recency multiplier:
- 0-30 days: 1.0
- 31-90 days: 0.75
- 91-180 days: 0.50
- 181+ days: 0.25
- Unknown date: 0.50

Relevance multiplier:
- Direct GPU/ML infra/HPC/runtime pain: 1.0
- Adjacent AI infra/cloud/compute: 0.75
- Generic AI/company content: 0.50
- Unrelated/unclear: 0.25

Default when no engagement found:
```
engagement_type = none
engagement_score = 0.0
prior_engagement = 0
confidence_score = 5
notes = no_visible_engagement_found
```

---

## Technical Keywords

Match against these when scanning profile headline, summary, and skills:

```
gpu_infrastructure, ml_platform, hpc, cuda, triton, nccl, kubernetes,
slurm, distributed_training, performance_engineering, runtime_systems,
compute_efficiency, robotics_simulation, biotech_compute, edge_compute,
developer_relations
```

Write matched keywords semicolon-separated to `technical_keywords`.

---

## Enrichment Steps

### Step 1 — Pull next pending prospect

Query `prospects` table for rows where `enrichment_status = pending`, limit 1.

### Step 2 — Scrape LinkedIn public profile

Use Apify LinkedIn Profile Scraper:

```
POST https://api.apify.com/v2/acts/harvestapi~linkedin-profile-scraper/run-sync-get-dataset-items
Authorization: Bearer {APIFY_API_TOKEN}
Body: { "profileUrls": ["{linkedin_url}"] }
```

Extract from response (array, take index 0):
- `education[].schoolName` → education schools
- `experience[].companyName` → past employers
- `volunteering[].organizationName` → affiliations
- `skills[].name` → technical keywords
- `headline` → technical signal
- `about` → technical signal supplement

If Apify fails or returns no data: mark `enrichment_status = failed`, log to `status_loop_runs`, continue.

### Step 3 — Extract affinity features

- `education_schools`: all `education[].schoolName` values joined
- `past_employers`: all `experience[].companyName` values (deduplicated)
- `affiliations`: all `volunteering[].organizationName` values
- `technical_signal`: 1-2 sentence summary from `headline` + `about` + top `skills[].name` values
- `technical_keywords`: semicolon-separated matched keywords from `skills[].name` against keyword list

### Step 4 — Compute warmth per sender

For each active sender:
1. Check school overlap → `same_school_no_direct_overlap = 0.3`
2. Check employer overlap → `same_employer_no_direct_overlap = 0.6`
3. Check affiliation overlap → `affinity_group = 0.5`
4. Check mutual connection → `mutual_connection = 0.4`
5. Take highest confirmed score only
6. No overlap → `cold_stranger = 0.1`

Generate `affinity_edge_id` as `edge_{8-char-uuid-fragment}`.

Set `warm_path_edge = 1` if warmth > 0.1, else `warm_path_edge = 0`.

### Step 5 — Compute reason codes

Warmth codes (one per row): `COLD_STRANGER`, `SHARED_SCHOOL`, `MUTUAL_CONNECTION`, `SHARED_AFFILIATION`, `SHARED_EMPLOYER`, `DIRECT_PRIOR_COLLEAGUE`

Technical codes (all that apply): `GPU_INFRA_ROLE`, `ML_PLATFORM_ROLE`, `HPC_ROLE`, `PERFORMANCE_ENGINEERING`, `DISTRIBUTED_TRAINING`

Engagement code (default at top of funnel): `NO_ENGAGEMENT_FOUND`

### Step 6 — Write to Airtable

Write 3 rows to `sender_affinity_edges` (one per sender: asmar, jane, giancarlos).

Write 3 rows to `scorer_ready_rows` (one per sender) with:
- `signal_recency = 0` (default — updated by signal-scan if pain found)
- `pain_acknowledged = 0` (default — updated by signal-scan)
- `engagement_score = 0` (default — updated by engagement-scout)
- `prior_engagement = 0` (default — updated by HeyReach reply pipeline)

### Step 7 — Update prospect status

Set `enrichment_status = enriched` and `enriched_at = today` on the prospect row.

### Step 8 — Log run

```
{ date, mode: "affinity_mapper", prospect_id, enrichment_status, senders_computed: 3 }
```

---

## Validation Rules

Before writing any row:

1. `prospect_id` is present
2. `warmth` is between 0 and 1
3. If `warmth > 0.1`, `warmth_evidence_url` is present — otherwise fall back to `cold_stranger`
4. `confidence_score` is between 1 and 5
5. `technical_keywords` uses semicolons as separator, not commas
6. `scorer_ready_rows` defaults (`signal_recency`, `pain_acknowledged`, `engagement_score`, `prior_engagement`) are all 0 — never null

---

## Error Handling

- Apify returns no data: `enrichment_status = failed`, log, continue to next prospect
- Airtable write fails: retry once after 30s, log and continue
- Warmth evidence missing for non-cold warmth: fall back to `cold_stranger = 0.1`
- Partial data (e.g. education found but no employers): write what was found, set `confidence_score = 2`

---

## Environment Variables Required

```
AIRTABLE_API_KEY
AIRTABLE_BASE_ID
APIFY_API_TOKEN       # LinkedIn profile scraping
```

---

## Cron Schedule

Poll every 30 minutes for new pending prospects:

```bash
hermes cron create --skill gitm-affinity-mapper --prompt "run affinity enrichment on pending prospects" --schedule "*/30 * * * *" --name "gitm-affinity-mapper"
```

---

## Manual Test

```bash
hermes chat --skill gitm-affinity-mapper
```

Type inside the session:
```
Run affinity enrichment on the next pending prospect in the prospects table. Scrape their LinkedIn profile using Apify, extract education, past employers, affiliations, and technical keywords, compute warmth for senders asmar, jane, and giancarlos using the warmth rubric, and write results to sender_affinity_edges and scorer_ready_rows in Airtable. Log the run to status_loop_runs.
```

---

## Install

```bash
curl -o ~/.hermes/skills/gitm-affinity-mapper.md \
  https://raw.githubusercontent.com/jorge-maldonad0/runtime/main/skills/gitm-affinity-mapper.md

hermes skills list | grep gitm-affinity-mapper
```
