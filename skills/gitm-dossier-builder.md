---
name: gitm-dossier-builder
description: Full enrichment skill for Git.M's GTM agent stack. Engagement-triggered — builds deep dossiers from Google Scholar, arXiv, Semantic Scholar, GitHub, blog, conference talks, and podcasts. Only runs when a prospect replies, opens repeatedly, or books a call.
category: gitm
---

# gitm-dossier-builder

## Description

Full enrichment skill for Git.M's GTM agent stack. Unlike `gitm-affinity-mapper` (which runs on every prospect at top-of-funnel), this skill triggers only when a prospect engages: replies to outreach, opens a message repeatedly, or books a call. It builds a deep dossier from Google Scholar, arXiv, Semantic Scholar, GitHub activity, Substack/blog posts, conference speaker profiles, and podcast appearances — giving FDEs and the draft-voice skill rich context for personalized follow-up.

This is NOT light enrichment. Papers, talks, and blog posts take longer to find and synthesize, which is why this only runs on engaged prospects rather than every prospect in the funnel.

---

## What this skill produces

**Input:** `prospect_id` from Airtable `prospects` table, where an engagement trigger has fired.

**Output — one Airtable table:**

### Table: `dossiers`

One row per engaged prospect.

| Field | Type | Description |
|---|---|---|
| `dossier_id` | Single line text (primary) | Unique ID: `dossier_{8-char-hash}` |
| `prospect_id` | Single line text | Joins to `prospects` table |
| `full_name` | Single line text | Prospect full name |
| `current_company` | Single line text | Current employer |
| `engagement_trigger` | Single select | `reply`, `repeated_open`, `call_booked` |
| `engagement_date` | Date | When the trigger fired |
| `scholar_profile_url` | URL | Google Scholar profile if found |
| `paper_titles` | Long text | Semicolon-separated paper titles from Scholar |
| `paper_count` | Number | Total papers found on Scholar |
| `citation_count` | Number | Total citations per Scholar |
| `research_areas` | Long text | Semicolon-separated research area tags |
| `arxiv_papers` | Long text | Title + URL pairs, one per line |
| `arxiv_count` | Number | Total arXiv papers found |
| `semantic_scholar_url` | URL | Semantic Scholar profile if found |
| `h_index` | Number | h-index from Semantic Scholar |
| `recent_papers` | Long text | Most recent 3-5 papers with year |
| `github_username` | Single line text | GitHub handle if found |
| `github_repos` | Long text | Notable repos, semicolon-separated |
| `github_activity_summary` | Long text | 1-2 sentence summary of recent activity |
| `contribution_areas` | Long text | Semicolon-separated technical areas from repo topics/languages |
| `blog_url` | URL | Substack/personal blog if found |
| `recent_post_titles` | Long text | Most recent 3-5 post titles |
| `blog_topics` | Long text | Semicolon-separated topics covered |
| `conference_talks` | Long text | Event + title + year, one per line |
| `speaker_profile_url` | URL | Conference speaker page if found |
| `podcast_appearances` | Long text | Show + episode + date, one per line |
| `dossier_summary` | Long text | 1-2 paragraph synthesis for drafting — what this person works on, what they've published/spoken about, and what's most relevant for outreach |
| `sources_checked` | Long text | Semicolon-separated list of sources attempted |
| `sources_found` | Long text | Semicolon-separated list of sources with actual hits |
| `confidence_score` | Number | 1-5 |
| `notes` | Long text | Manual caveats |
| `last_updated` | Date | When dossier was built/refreshed |

---

## Dossier ID Format

Generate `dossier_id` as: `dossier_{8-char-uuid-fragment}`

---

## Engagement Triggers

This skill only runs when one of these fires for a prospect:

| Trigger | Detection |
|---|---|
| `reply` | HeyReach reply data shows `prior_engagement = 1` for this prospect in `scorer_ready_rows` |
| `repeated_open` | HeyReach shows 3+ message opens (when that data is available) |
| `call_booked` | Manual flag or calendar booking event tied to prospect |

For v0, since HeyReach reply data is not yet flowing, this skill can be invoked manually per prospect for testing. Once `prior_engagement = 1` rows appear in `scorer_ready_rows`, those prospects become the automatic trigger queue.

---

## Enrichment Steps

### Step 1 — Identify engaged prospects

Query `scorer_ready_rows` for rows where `prior_engagement = 1` and no matching row yet exists in `dossiers` for that `prospect_id`. For manual testing, a specific `prospect_id` can be passed directly.

### Step 2 — Google Scholar search

Search Google Scholar for the prospect's full name plus current company as disambiguation. If a profile is found, extract:
- Profile URL
- Paper titles (semicolon-separated)
- Total paper count
- Total citation count
- Research area tags (from Scholar's listed interests)

If no Scholar profile is found, or if ambiguous (common name, multiple matches), leave fields blank and note in `notes`.

### Step 3 — arXiv search

Search arXiv (`https://arxiv.org/a/{lastname}_{firstinitial}` or the arXiv API `http://export.arxiv.org/api/query?search_query=au:{lastname}_{firstinitial}`) for papers matching the prospect's name. Cross-reference with current company or known research area to avoid false matches on common names. Extract:
- Paper title + URL pairs (one per line)
- Total count

### Step 4 — Semantic Scholar search

Use the Semantic Scholar API (`https://api.semanticscholar.org/graph/v1/author/search?query={name}`) to find the author profile. Extract:
- Profile URL
- h-index
- 3-5 most recent papers with year

Cross-reference author ID matches against Scholar/arXiv results already found to confirm it's the same person.

### Step 5 — GitHub activity

If `linkedin_url` or prior enrichment from `gitm-affinity-mapper` revealed a GitHub username (check `sender_affinity_edges.technical_signal` and `notes` fields for any prior mention), pull:
- Profile via `GET https://api.github.com/users/{username}`
- Top repos by stars via `GET https://api.github.com/users/{username}/repos?sort=stars`
- Recent activity summary (1-2 sentences on what they've been building/contributing to)
- Contribution areas inferred from repo languages and topics

If no GitHub username is known, search GitHub users by name + company as a best-effort fallback, but mark confidence lower if no other corroborating signal exists.

### Step 6 — Blog / Substack search

Search for a personal blog or Substack tied to the prospect's name. Common patterns: `{name}.substack.com`, personal domain mentioned in bio/LinkedIn, or a blog link from their GitHub profile. Extract:
- Blog URL
- 3-5 most recent post titles
- Topics covered (semicolon-separated)

### Step 7 — Conference speaker search

Search for the prospect's name alongside terms like "speaker", "keynote", "talk" plus relevant conference names (NeurIPS, ICML, MLSys, GTC, KubeCon, etc. depending on their technical area). Extract:
- Event + talk title + year (one per line)
- Speaker profile URL if a dedicated page exists

### Step 8 — Podcast appearances

Search for the prospect's name plus "podcast" or "interview". Extract:
- Show name + episode title + date (one per line)

### Step 9 — Synthesize dossier summary

Write a 1-2 paragraph summary covering:
- What this person works on technically (drawn from papers, GitHub, blog topics)
- What they've published or spoken about that's most relevant to Git.M's pitch (GPU runtime, performance, infra)
- Any specific framing or angle this dossier suggests for a personalized follow-up

This summary is what `gitm-draft-voice` (future skill) will use directly when drafting a personalized follow-up message.

### Step 10 — Compute confidence and sources

- `sources_checked`: list every source attempted (Scholar, arXiv, Semantic Scholar, GitHub, blog, conference, podcast) regardless of whether anything was found
- `sources_found`: list only sources where real data was found
- `confidence_score`: 5 if 4+ sources found with strong corroboration (same name+company across sources), 3 if 2-3 sources found, 1-2 if only 1 weak/ambiguous source found

### Step 11 — Write to Airtable

Write one row to `dossiers` with all fields populated. If a dossier already exists for this `prospect_id` (re-trigger case, e.g. prospect engages again later), update the existing row rather than creating a duplicate — refresh `last_updated` and append any new findings to existing long-text fields rather than overwriting.

### Step 12 — Log run

```
{ date, mode: "dossier_builder", prospect_id, engagement_trigger, sources_found_count, confidence_score }
```

---

## Validation Rules

Before writing any row:

1. `prospect_id` is present and exists in `prospects` table
2. `engagement_trigger` is one of `reply`, `repeated_open`, `call_booked`
3. `confidence_score` is between 1 and 5
4. `sources_checked` lists all 7 sources even if empty results
5. If a field has no data, leave blank — do not write placeholder text like "N/A" or "none found" into URL fields
6. `dossier_summary` is never blank if `confidence_score >= 3` — if 3+ sources have data, a summary must be synthesized

---

## Error Handling

- Source returns no data: record in `sources_checked` but not `sources_found`, continue to next source
- Source API rate-limited or unreachable: log the failure in `notes`, continue with remaining sources, do not fail the whole dossier
- Ambiguous name match (common name, multiple candidates): note the ambiguity in `notes`, use the best match only if corroborated by company/role, otherwise leave that source's fields blank
- Airtable write fails: retry once after 30s, log and continue
- Re-trigger on already-dossiered prospect: update existing row, append new findings, do not duplicate

---

## Environment Variables Required

```
AIRTABLE_API_KEY
AIRTABLE_BASE_ID
GITHUB_TOKEN          # for GitHub activity lookup, Authorization: Bearer header
```

No API keys are required for Google Scholar, arXiv, or Semantic Scholar searches in v0 — these use public search/API endpoints. Semantic Scholar's API works without a key at low volume; an API key can be added later if rate limits become an issue.

---

## Manual Test

```bash
hermes chat --skill gitm-dossier-builder --yolo
```

Type inside the session:

```
Build a dossier for prospect_id {prospect_id}. Treat this as engagement_trigger=call_booked for testing purposes. Search Google Scholar, arXiv, Semantic Scholar, GitHub, personal blog/Substack, conference speaker pages, and podcast appearances for this person using their full_name and current_company from the prospects table. Synthesize a dossier_summary and write the row to the dossiers table. Log the run to status_loop_runs.
```

---

## Cron Schedule

This skill is engagement-triggered, not time-polled like `gitm-affinity-mapper`. For v0, run it manually against specific prospects. Once HeyReach reply data flows into `scorer_ready_rows.prior_engagement`, register a poll:

```bash
hermes cron create "*/30 * * * *" "check scorer_ready_rows for prior_engagement=1 rows with no matching dossier, build dossiers for any found" --skill gitm-dossier-builder --name "gitm-dossier-builder"
```

Do not register this cron until reply data is actually flowing — otherwise it will poll an empty trigger condition every 30 minutes for no reason.

---

## Install

```bash
curl -o ~/.hermes/skills/gitm-dossier-builder.md \
  https://raw.githubusercontent.com/jorge-maldonad0/runtime/main/skills/gitm-dossier-builder.md

hermes skills list | grep gitm-dossier-builder
```
