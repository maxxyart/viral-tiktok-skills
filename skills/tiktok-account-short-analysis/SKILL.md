---
name: tiktok-account-short-analysis
description: >
  Quick TikTok account overview: fetches ALL videos, calculates aggregate metrics
  (total/avg/median views), shows top 5 videos with virality & engagement rates,
  and gives a brief analysis of the account's topic and what it promotes.
  No Gemini / video analysis — fast and cheap.
  Trigger phrases: "short analysis tiktok", "tiktok quick analysis", "tiktok overview",
  "быстрый анализ тикток", "обзор аккаунта тикток", "tiktok account overview",
  "tiktok stats", "статистика тикток", "краткий анализ тикток"
---

# TikTok Account Short Analysis

## When to use

When the user provides a TikTok handle/URL and wants a quick overview of the account's performance — without deep hook/script analysis.

## Prerequisites

- ScrapeCreators API key (`SCRAPE_CREATORS_API_KEY` in `.env`)
- `TIKTOK_SKILLS_ROOT` env var pointing at your `viral-tiktok-skills` clone (keys live in that repo's `.env`)

## Workflow

### Step 1: Extract handle

Parse the TikTok handle from the user's input. Accept formats:
- `@username`
- `https://www.tiktok.com/@username`
- just `username`

### Step 2: Run quick-stats script

```bash
cd "${TIKTOK_SKILLS_ROOT:?Set TIKTOK_SKILLS_ROOT to your viral-tiktok-skills clone}"
npx tsx src/scripts/quick-stats.ts HANDLE [--since=YYYY-MM-DD]
```

The script outputs JSON to stdout (progress + `[TIMING]` breakdown to stderr).

**`--since=YYYY-MM-DD` (recommended for large accounts)** — stop pagination at the first video older than the cutoff. Critical for huge catalogs: a ~4000-video account without `--since` can take 10+ min and may hit API timeouts; with `--since=2026-01-01` it usually finishes in seconds. Default (no `--since`): fetch ALL videos.

**Caching & incremental fetch** (enabled by default):
- Cache dir: `~/.cache/tiktok_quick_stats/<handle>.json`, TTL 6h.
- **Fresh cache** (age ≤ TTL): zero API calls, instant return.
- **Stale cache** (age > TTL): incremental fetch — paginates "latest" only until it hits a video ID already in cache, then merges. Re-runs on the same account are typically 2-5s instead of 30-60s.
- Flags: `--no-cache` (skip cache entirely), `--force-refresh` (ignore cache, overwrite), `--cache-ttl=SECONDS` (override default).
- Output JSON includes `_meta.fromCache`, `_meta.newlyFetched`, `_meta.pagesFetched`, `_meta.stoppedAtCutoff`, `_meta.sinceFilter` — reflect these in the report.

Trade-offs:
- Cached stats on old videos are frozen at last refresh — for fresh numbers use `--force-refresh`.
- `--since` + cache: cache stores the filtered subset; if you later ask for an earlier `--since`, use `--force-refresh`.

### Step 3: Present report

Use the JSON output to build the report.

#### 3.1 Account Metrics

| Metric | Value |
|--------|-------|
| Total videos | N |
| Total views | N |
| Average views | N |
| Median views | N |

#### 3.2 Top 5 Videos (by views)

Table with columns:
- Video (link to TikTok)
- Date
- Views
- Virality Rate (views / account median views) — e.g. `12.5x`
- Engagement Rate (likes+comments+shares+saves / views) — e.g. `8.3%`
- Comments

#### 3.3 Account Topic Analysis

Based on the `descriptions` array from the JSON output, write a brief (3-5 bullet points) analysis:
- Main topic / niche
- What the account promotes (products, services, brand, lifestyle)
- Content style (educational, entertaining, promotional, storytelling)
- Target audience

## Output format

- Format large numbers: 1.2M, 45.3K, etc.
- TikTok links: `https://www.tiktok.com/@HANDLE/video/VIDEO_ID`
- Keep the report concise — this is a quick overview, not a deep dive

## Cost estimate

- ~3-8 ScrapeCreators API calls (depends on video count)
- No Gemini calls
- Runtime: ~30-60 seconds
