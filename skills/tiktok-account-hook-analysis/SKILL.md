---
name: tiktok-account-hook-analysis
description: >
  TikTok cover image hook analysis: fetches last 120 videos (all available), uses Gemini Vision
  to OCR hook text from each video's cover/thumbnail image, then discovers
  repeating hook text PATTERNS and calculates analytics per pattern.
  Much faster and cheaper than full video analysis — only processes static images.
  Trigger phrases: "hook analysis tiktok", "tiktok hook analysis", "tiktok cover analysis",
  "analyze tiktok hooks", "анализ хуков тикток", "анализ обложек тикток",
  "tiktok cover hooks", "tiktok thumbnail analysis", "хук анализ тикток",
  "cover image analysis tiktok", "tiktok hook text", "анализ текста обложек"
---

# TikTok Account Hook Analysis (Cover Image OCR)

## When to use

When the user provides a TikTok handle/URL and wants to analyze the **hook text on cover images** (thumbnails) across the account's videos. This reveals which text-based hook formulas the creator uses on their covers and which ones perform best.

**Key difference from deep-analysis:** This skill analyzes static cover images (fast, cheap) instead of full videos (slow, expensive). It extracts on-screen text from thumbnails, not video scripts.

## Prerequisites

- ScrapeCreators API key (`SCRAPE_CREATORS_API_KEY` in `.env`)
- Google API key (`GOOGLE_API_KEY` in `.env`)
- `TIKTOK_SKILLS_ROOT` env var pointing at your `viral-tiktok-skills` clone (keys live in that repo's `.env`)

## Workflow

### Step 1: Extract handle

Parse the TikTok handle from the user's input. Accept formats:
- `@username`
- `https://www.tiktok.com/@username`
- just `username`

### Step 2: Run cover hook analysis

**Default: 100 videos.** If the user explicitly specifies a different number (e.g. "50 видео", "last 30", "200 videos"), use that number instead.

```bash
cd "${TIKTOK_SKILLS_ROOT:?Set TIKTOK_SKILLS_ROOT to your viral-tiktok-skills clone}"
mkdir -p /tmp/cover-hooks
npx tsx src/scripts/analyze-cover-hooks.ts HANDLE \
  --count COUNT --skip 0 --concurrency 10 \
  --out /tmp/cover-hooks/HANDLE.json \
  --out-csv /tmp/cover-hooks/HANDLE.csv
```

Where `COUNT` = number requested by user, or **100** if not specified.

Flags:
- `--concurrency N` — parallel OCR workers (default 10). With 100 videos this brings OCR phase from ~12 min to ~75 sec.
- `--out FILE.json` — write structured report to file (recommended; otherwise JSON goes to stdout).
- `--out-csv FILE.csv` — write flat per-video CSV (id, date, views, likes, saves, hook_text, pattern_name, virality_rate, link).
- `--skip N` — useful for paginated re-runs after a failure.

If neither `--out` nor `--out-csv` given, JSON is printed to stdout (legacy mode). With `--out` flags, stdout stays clean.

After the script finishes, read the JSON file to build the report.

The script:
1. Fetches videos via ScrapeCreators API (paginated)
2. Downloads each video's cover image
3. Sends each cover image to Gemini Vision (`gemini-3.1-flash-lite`) to OCR all text
4. Feeds all extracted hook texts into a SINGLE Gemini text call for pattern discovery
5. Calculates metrics per pattern
6. Outputs structured JSON to stdout

### Step 3: Present report

Use the JSON output to build the report.

#### 3.1 Overview

| Metric | Value |
|--------|-------|
| Total videos analyzed | N |
| Videos with hook text on cover | N |
| Videos without text | N |
| Account median views | N |

#### 3.2 Hook Text Patterns (sorted by virality desc)

**IMPORTANT: A "pattern" requires 3+ videos. Anything with fewer than 3 videos (1-2) is NOT a pattern** — it is statistically unreliable. Do not give 1-2 video groups their own pattern section; only mention them briefly in insights if they show an interesting signal.

**Always show the video count for each pattern** — put it in the pattern header (e.g. `### 🔥 Pattern Name — 13.9x · 4 videos`) so the reader sees how many videos back the pattern.

For each qualifying pattern (3+ videos):
- Pattern name + emoji indicator (🏆/🔥/⚡/⚠️/📉) + virality rate + **video count** in header
- Abstract formula with [PLACEHOLDERS]
- Table: Videos (count) | Median Views | Avg Views | Virality | Median Likes | Median Saves
- Table with top 3 videos: views, hook text (original language, abbreviated if long), link
- ⚠️ Flag patterns where avg >> median (one viral outlier inflating averages)

If there is a large "catch-all" / "miscellaneous" bucket, report it separately at the end with a note about what % of content has no clear formula.

#### 3.3 Key Insights

Based on the pattern data, provide analysis:
- **What works** (virality > 3x): why these patterns outperform, common emotional/structural elements
- **What doesn't work** (virality < 1x): why these patterns underperform
- **Repost degradation**: how much do repeated formulas lose on subsequent posts
- **Serial formats**: does DAY N or numbered series create retention loops
- **Saves as quality signal**: which patterns get saved vs just viewed
- **Content strategy observations**: ratio of formulaic vs experimental content
- Specific hook formulas worth replicating
- Recommendations for cover text strategy

## How it works

**Step A — Per-cover OCR (Gemini Vision + cover image):**
Each cover image is downloaded, base64-encoded, and sent to Gemini with this prompt:
```
Look at this TikTok video cover image and extract ALL text visible on it.
Return JSON: { "hookText": "...", "hasText": true/false }
```

**Step B — Pattern clustering (Gemini text-only call):**
All extracted hook texts are fed into a single Gemini text call:
```
Identify all recurring hook text PATTERNS across these covers.
Strip specific details to find underlying templates.
Assign every video to exactly one pattern.
Return JSON with patternName, formula, videoIds.
```

Videos without text on covers are grouped into a separate "No text on cover" pattern.

## Output format

- All hook texts quoted in **original language**, never translated
- Tables for pattern analytics
- Format large numbers: 1.2M, 45.3K, etc.
- TikTok links: `https://www.tiktok.com/@HANDLE/video/VIDEO_ID`
- Concise insights in bullet points

## Cost estimate

- ~8-15 ScrapeCreators API calls (pagination for 120+ videos)
- ~120 Gemini Vision calls (cover image OCR) + 1 text clustering call
- Runtime: ~3-7 minutes total (much faster than video analysis)
