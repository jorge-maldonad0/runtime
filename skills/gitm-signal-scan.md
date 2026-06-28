---
name: gitm-signal-scan
description: Signal discovery skill for Git.M's GTM agent stack. Crawls GitHub, LinkedIn, and X for public GPU-pain signals matching Git.M's ICP.
tags: [gtm, signals, github, airtable, scanning]
---

# gitm-signal-scan

## Description

Signal discovery skill for Git.M's GTM agent stack. Crawls GitHub, LinkedIn, and X for public GPU-pain signals matching Git.M's ICP. Produces ranked signal records written to Airtable `signals` table. Output schema aligns with Danny's scorer input contract (input_contract.md).

---

## Part 1: Trigger Keyword Library

These are the exact phrases and terms to search across all sources. Organized by pain category.

### Capacity / Utilization Pain
- `"GPU utilization"`
- `"GPUs sitting idle"`
- `"idle GPUs"`
- `"underutilizing GPU"`
- `"GPU bubbles"`
- `"improve GPU utilization"`
- `"can't fit more workloads"`
- `"cluster utilization"`

### Throughput / Latency Pain
- `"throughput-limited"`
- `"latency-limited"`
- `"p99 latency"`
- `"unpredictable latency"`
- `"throughput regression"`
- `"latency regression"`
- `"tokens per second"`
- `"requests per second"`

### Capacity Ceiling Pain
- `"hitting our allocation cap"`
- `"allocation cap"`
- `"had to add more GPUs"`
- `"need more GPUs"`
- `"scaling GPU capacity"`
- `"out of GPU memory"`
- `"OOM"`

### Performance Regression Pain
- `"performance regression"`
- `"chasing a regression"`
- `"training slowdown"`
- `"inference slowdown"`
- `"kernel regression"`
- `"CUDA regression"`

### Tooling / Observability Pain
- `"need to build performance tooling"`
- `"GPU profiling"`
- `"runtime inefficiency"`
- `"wasted compute"`
- `"compute overhead"`
- `"GPU bottleneck"`
- `"memory bottleneck"`
- `"communication bottleneck"`
- `"NCCL bottleneck"`
- `"NVLink bottleneck"`

### ICP-Specific Terms (Phase 2 verticals)
- `"molecular dynamics GPU"`
- `"protein folding compute"`
- `"CFD GPU"`
- `"robotics simulation GPU"`
- `"perception training"`
- `"scientific compute GPU"`
- `"HPC GPU"`
- `"drug discovery compute"`

---

## Part 2: Crawl Source List

### Source 1: GitHub (priority — cleanest API, run first)

Target repos and orgs:

| Repo / Org | Why |
|---|---|
| `pytorch/pytorch` | Core ML framework — issues surface runtime pain |
| `openai/triton` | GPU kernel language — perf issues are explicit |
| `vllm-project/vllm` | LLM inference — throughput and latency pain |
| `NVIDIA/nccl` | Collective comms — NCCL bottleneck signals |
| `NVIDIA/apex` | Mixed precision training — perf regression signals |
| `microsoft/DeepSpeed` | Distributed training — memory and throughput pain |
| `huggingface/transformers` | Model training — GPU utilization signals |
| `huggingface/accelerate` | Multi-GPU training — scheduling and sync pain |
| `facebookresearch/xformers` | Attention kernels — memory and throughput |
| `NVIDIA/cuda-samples` | CUDA — low-level runtime pain |

Search targets within each repo:
- Issues (open and closed, last 90 days)
- PRs (title and body, last 90 days)
- Discussion threads where available

### Source 2: X (Twitter)

Search via X API v2 recent search endpoint.

Query structure:
```
({keyword}) (lang:en) -is:retweet
```

Target accounts to monitor (in addition to keyword search):
- ML infrastructure leads at GPU-heavy companies
- HPC and scientific compute practitioners
- Anyone with `ML infra`, `GPU`, `HPC`, `compute`, `ML platform` in bio

### Source 3: LinkedIn

Search public posts via LinkedIn search (manual or via scraping where permitted).

Target queries:
- Keyword search in posts
- Posts from people with titles matching buyer persona: VP Infra, Head of ML Platform, Director of ML Engineering, CTO, PI, Computing Director

---

## Part 3: Output Schema

### Airtable Table: `signals`

One row per signal found. Aligned with Danny's scorer input contract.

| Field | Type | Description | Scorer field |
|---|---|---|---|
| `signal_id` | Single line text (primary) | e.g. `sig_001` | — |
| `prospect_name` | Single line text | Full name of person who posted | — |
| `prospect_company` | Single line text | Their current company | — |
| `prospect_title` | Single line text | Their current title | — |
| `prospect_linkedin_url` | URL | LinkedIn profile if found | — |
| `source` | Single select | `github`, `x`, `linkedin` | — |
| `source_url` | URL | Direct link to the post, issue, or PR | `pain_signal_url` |
| `signal_date` | Date | Date of the post or issue | `pain_signal_date` |
| `days_since_signal` | Number | Days between signal_date and today | Used for `signal_recency` |
| `signal_recency` | Number | `exp(-days_since_signal / 30)` | `signal_recency` |
| `raw_quote` | Long text | Exact quote from the post or issue | `pain_signal_summary` |
| `pain_summary` | Long text | One-sentence summary of the pain | `pain_signal_summary` |
| `pain_category` | Single select | `utilization`, `throughput`, `latency`, `regression`, `tooling`, `capacity`, `vertical_specific` | — |
| `keyword_matched` | Single line text | The trigger keyword that matched | — |
| `pain_acknowledged` | Number | 1 (all signals in this table are pain-confirmed) | `pain_acknowledged` |
| `icp_fit` | Single select | `phase_1`, `phase_2`, `unknown` | — |
| `vertical` | Single select | `biotech`, `robotics`, `hpc`, `managed_gpu`, `sovereign_compute`, `other` | — |
| `rank_score` | Number | Composite rank: signal_recency × icp_weight | — |
| `status` | Single select | `new`, `enriched`, `scored`, `outreached`, `discarded` | — |
| `notes` | Long text | Manual caveats | — |

### Ranking Formula

```
rank_score = signal_recency × icp_weight

icp_weight:
  phase_1 company = 1.0
  phase_2 company = 0.8
  unknown          = 0.4

signal_recency = exp(-days_since_signal / 30)
```

Higher rank_score = higher priority for outreach queue.

---

## Part 4: GitHub Scan — Step by Step

This is the first source to run. GitHub has the cleanest API and requires no scraping.

### Auth

```
GITHUB_TOKEN    # read from environment — token is required for authenticated requests (5000 req/hr vs 60 req/hr unauthenticated)
```

> **NOTE: Always verify token is loaded from env before making requests. Use `os.environ.get("GITHUB_TOKEN", "")` and check length > 0.**
>
> **PITFALL: GITHUB_TOKEN may be set but empty.** `$([ -n "$GITHUB_TOKEN" ] && echo yes)` returns "yes" even when the value is `""` (empty string). Python's `os.environ['GITHUB_TOKEN']` will return `""` — causing 401 errors. The unauthenticated API works but is rate-limited (60 req/hr). Always verify the token is actually non-empty before relying on it:
>
> ```python
> token = os.environ.get('GITHUB_TOKEN') or ''
> headers = {'Authorization': f'token {token}'} if token else {'Accept': 'application/vnd.github.v3+json'}
> ```

### Search query format

GitHub code search API:
```
https://api.github.com/search/issues?q={keyword}+repo:{owner}/{repo}&sort=created&order=desc&per_page=20
```

> **PITFALL: GitHub's quoted-phrase search is fuzzy.** Results returned by `"GPU utilization"` may NOT all contain the exact phrase — GitHub applies loose matching and can return items where the terms appear near each other rather than as a contiguous string. Always verify with a regex match on title + body before recording the raw_quote. Only ~20-30% of returned items typically have the literal phrase.
>
> ```python
> import re
> match = re.search(r'[^.]*' + re.escape(keyword) + r'[^.]*\.', full_text, re.IGNORECASE)
> raw_quote = match.group(0).strip() if match else ''
> ```

### Steps

1. For each repo in the target repo list:
   - For each keyword in the trigger keyword library:
     - Query GitHub issues and PRs created in the last 90 days
     - Filter results where the keyword appears in title OR body (verify with regex — see pitfall above)
     - Extract: issue/PR URL, title, body excerpt (first 500 chars), author login, created_at date
     - Look up author profile via `GET /users/{login}`: name, company field, location
       - **name fallback**: if `name` is `null` in the API response, use `login` as the display name
       - **company fallback**: if `company` is `null`, leave as empty string
     - Skip bots (author login contains `[bot]`)

2. For each result:
   - Compute `days_since_signal` = today - created_at
   - Compute `signal_recency` = exp(-days_since_signal / 30)
   - Extract the exact matching sentence as `raw_quote` via regex (`[^.]*{keyword}[^.]*\.`)
   - Write a 1-2 sentence `pain_summary` describing the problem the user is actually facing (not just restating the keyword)
   - Classify `pain_category` from the keyword matched (map from keyword library above)
   - Set `pain_acknowledged = 1`
   - Set `icp_fit`:
     - `phase_1`: company is an orchestrator / managed GPU provider (e.g. RunPod, Vast.ai, Lambda, CoreWeave, Salad, Replicate, Together)
     - `phase_2`: vertical-specific compute (biotech, robotics, HPC, sovereign compute)
     - `unknown`: big-tech companies (Meta, NVIDIA, AMD, Intel, Google, Microsoft, Amazon — they build in-house), consultancies, or missing company field
   - Set `vertical`:
     - Infer from company vertical if known (biotech, robotics, hpc, managed_gpu, sovereign_compute)
     - Default to `other` for tools/infra repos like pytorch/pytorch where contributors work on the framework itself, not on GPU-consuming applications
   - Compute `rank_score` = signal_recency × icp_weight

3. Deduplicate: if same author appears more than once, keep the highest rank_score row only.

4. Write top 20 results sorted by `rank_score` descending to Airtable `signals` table.

5. Log run to Airtable `status_loop_runs`:
   ```
   { date, mode: "signal_scan_github", signals_found, signals_written, decision: "N signals written" }
   ```
   > **PITFALL: `status_loop_runs.mode` single-select may not include `"signal_scan_github"`.** The Airtable schema had options `['standup', 'founder_approval', 'airtable_to_slack', 'slack_to_airtable']` as of June 2026. If `signal_scan_github` isn't an option, either add it to the Airtable field definition or use the closest match and note it in the `decision` field.

### Target: first 20 signals

Pull until 20 unique non-bot authors with valid signal records are written to Airtable.

### Reference: real run output

See `references/gpu-utilization-pytorch-scan-2026-06-28.md` for a concrete example of extraction logic, output shape, and Airtable schema quirks encountered during an actual run targeting "GPU utilization" on pytorch/pytorch.

---

## Part 5: Airtable Schema Hygiene

Before each scan run, verify these Airtable table schemas match what this skill expects. Mismatches cause silent write failures or data-loss.

### `signals` table — single-select option mismatches (as of June 2026)

| Field | Expected (skill) | Actual (Airtable) | Impact |
|---|---|---|---|
| `source` | `github`, `x`, `linkedin` | `github`, `x`, `llinkedin` (typo) | Writes to `llinkedin` instead of `linkedin` — fix the Airtable field option to `linkedin` |

### `status_loop_runs` table — missing mode option

| Field | Expected | Actual | Impact |
|---|---|---|---|
| `mode` | `signal_scan_github` | `standup`, `founder_approval`, `airtable_to_slack`, `slack_to_airtable` | Cannot log scan runs properly — add `signal_scan_github` to the mode single-select list |

### Field references

```
signals table id:   tblb13ohxggez10OC
status_loop_runs:   tblrFUbyg9Y5l04Br
```

---

## Cron Schedule

Add to Hermes cron after first manual run passes:

```
hermes cron create --skill gitm-signal-scan --prompt "run github signal scan" --schedule "0 */6 * * *" --name "gitm-signal-scan-github"
```

Runs every 6 hours. Expand to X and LinkedIn once GitHub scan is stable.

---

## Seeding the signals table in Airtable

Create table `signals` with all fields listed in Part 3 before running the scan.

Single select options for `source`: `github`, `x`, `linkedin`
Single select options for `pain_category`: `utilization`, `throughput`, `latency`, `regression`, `tooling`, `capacity`, `vertical_specific`
Single select options for `icp_fit`: `phase_1`, `phase_2`, `unknown`
Single select options for `vertical`: `biotech`, `robotics`, `hpc`, `managed_gpu`, `sovereign_compute`, `other`
Single select options for `status`: `new`, `enriched`, `scored`, `outreached`, `discarded`

---

## Running the scan manually

Install the skill on the VM, then open a Hermes chat session:

```bash
hermes chat --skill gitm-signal-scan
```

Type inside the session:
```
Run the GitHub signal scan. For each repo in the target list, search GitHub issues and PRs from the last 90 days using the trigger keyword library. Extract prospect name, company, title, source URL, signal date, raw quote, and pain summary for each match. Compute signal_recency and rank_score. Deduplicate by author. Write the top 20 results sorted by rank_score to the Airtable signals table using AIRTABLE_API_KEY and AIRTABLE_BASE_ID from the environment. Log the run to status_loop_runs.
```

---

## Install

Upload to GitM-Labs/runtime, then on the VM:

```bash
curl -o ~/.hermes/skills/gitm-signal-scan.md \
  https://raw.githubusercontent.com/jorge-maldonad0/runtime/main/skills/gitm-signal-scan.md

hermes skills list | grep gitm-signal-scan
```