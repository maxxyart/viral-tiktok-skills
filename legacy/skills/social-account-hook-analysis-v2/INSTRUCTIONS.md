---
name: social-account-hook-analysis
description: Analyze Instagram Reels or TikTok hooks using ScrapeCreators and visual inspection. Study the latest 60 videos by default, optionally transcribe actual audio, compare text formulas × visuals × character roles, and deliver a self-contained HTML report with a searchable all-video table and source evidence.
---

# Social Account Hook Analysis (Viral Camp)

Produce a reusable account-specific hook library with linked evidence and testable recommendations. Support Instagram and TikTok. User instructions override defaults; do not invoke Boont OS, another data provider, a paid OCR service, or a generator merely because an older workflow used it.

## 1. Scope and collect

Default: **60 latest videos**, covers grouped in **batches of 20**, HTML + CSV. Honor a different count, all-history scope, or specific output. Infer platform only from explicit URL/context; a bare handle is ambiguous. Read relevant project context before adapting hooks to the user's product.

Read [references/collection.md](references/collection.md) and [references/metrics.md](references/metrics.md). Use discovered **ScrapeCreators MCP** tools when available/requested; a CLI/API fallback must be named accurately. Follow collection safeguards: timestamps, deduplication, media-type filtering, pagination boundaries, source-level exclusions, and original capture time. Never claim all account posts when the source omits pinned items.

Bundled scripts are self-contained. Resolve `<skill-dir>` from this file. Python 3.10+; Pillow for images, optional pillow-heif for HEIC; no vision API key required.

```bash
python3 <skill-dir>/scripts/social.py collect https://www.instagram.com/ACCOUNT/reels/ --count 60 --transport cli --out <run-dir>
python3 <skill-dir>/scripts/social.py collect https://www.tiktok.com/@ACCOUNT --count 60 --transport api --out <run-dir>
python3 <skill-dir>/scripts/covers.py --out <run-dir>
```

For MCP, import saved `page-*.json` with `--pages-dir` and original `--fetched-at`, as documented in collection.md. Don't scrape the same cohort twice just to use the scripts.

## 2. Inspect every cover

Read [references/hook-analysis.md](references/hook-analysis.md) before annotation.

Open all contact sheets in `sheets/`. Each tile has stable rank, publication date, views and comments; image fitting preserves the full cover. Inspect individual covers at readable resolution whenever text, punctuation, emojis, embedded UI or composition is uncertain. A contact sheet is an overview, not sufficient proof of verbatim OCR. Missing covers remain in the denominator and get a failure status.

Persist `cards.json`, one row per **stable video ID**, as you go. Record exact hook text and separate embedded text, visual technique, framing, expression, character role, and evidence scope. Preserve source language, capitalization and typos; `[illegible]` is preferable to a plausible guess. Quotes are not captions or normalized formula templates.

**A cover is not necessarily the opening frame.** A cover-only report may analyze cover hooks and propose first-second edits, but cannot claim observed spoken hooks, cuts, reveal timing, retention or full-video structure. If the user requests opening/full-video analysis, inspect that footage or obtain timestamped evidence, and label coverage per video. Report unavailable footage explicitly.

Prefer native visual inspection. External OCR is optional only when allowed by the user's constraints and available credentials. Treat OCR as a draft and verify source quotes visually. Delegate only when the user/environment authorizes it; do not automatically fan out agents based on sample size.

### Audio, only when requested

Read [references/audio-transcription.md](references/audio-transcription.md). Use the bundled helper after collection; it reads saved feed pages and does **not** make more ScrapeCreators requests. Inspect its dry-run coverage before paid Gemini calls. It requires `ffmpeg` and an explicitly configured `GOOGLE_API_KEY` or `GEMINI_API_KEY`; never search private files for credentials. Default model is Gemini 2.5 Flash-Lite, overridable with `--model` when availability or the user's preference requires it.

```bash
python3 <skill-dir>/scripts/audio_transcribe.py --out <run-dir> --dry-run
python3 <skill-dir>/scripts/audio_transcribe.py --out <run-dir>
python3 <skill-dir>/scripts/covers.py --out <run-dir> --sheets-only
```

The helper caches full-audio and separately clipped first-three-second transcripts by video ID, records token usage, and uses a sampled opening frame only when a cover is unavailable. Preserve failed or uncertain rows. A speech transcript supports spoken-hook claims, not claims about on-screen actions or cuts. If video URLs in the saved feed have expired, report missing coverage and get a fresh authorized capture instead of silently switching providers.

## 3. Discover patterns without losing outliers

Classify each cover independently on:

- **Text formula**: discovery gap, experience challenge, low-effort promise, before/after, etc.; derive labels from this account.
- **Visual technique**: framing, face vs object, expression, text treatment, demonstration, collage, screenshot, environment.
- **Character role**: creator, demonstrator, narrator, recurring fictional persona, no person, unknown. Do not infer age, profession, identity or relationship from appearance alone.

Then compare **text × visual** combinations. A single video stays a labeled example; 2 videos are exploratory; 3+ is a repeated observation, not causal proof. Keep unreadable/no-text/missing-image/unassigned distinct. Do not force rare formats into a fake recurring pattern.

```bash
python3 <skill-dir>/scripts/social.py analyze --out <run-dir> --cards <run-dir>/cards.json
```

This rejects missing, duplicate or extra card IDs and recomputes all metrics from the selected cohort. Examine `analysis.json` for per-axis and combined stats, monthly slices, view concentration and up to two references per pattern (peak + typical). A smaller sample can be the best test candidate, but must not be called the best proven formula.

## 4. Explain and adapt

Read [references/reporting.md](references/reporting.md) and [references/local-html.md](references/local-html.md). Build the report in the user's language, while keeping **formulas and direct quotes in the language of the reference**. Every displayed formula gets **1–2 specific source post links** and local cover references. A translation or product adaptation is labeled separately from a quote.

Include:

1. Cohort metrics and top five with CR and median multiples.
2. Original-language formula library with exact examples, visual techniques, character roles, n, median/mean, CR and typical vs peak performance.
3. Text-only, visual-only and cross-axis comparisons. Say “associated with higher views in this sample”, not “caused growth”. Call out correlated variables: this account may only use one text formula with one visual.
4. Contradicting examples, repeated-hook dispersion, outlier concentration, and publication-age differences. Calendar snapshot comparisons cannot establish saturation or repost decay.
5. Account topic, observed product and CTA. No assumption that comments mean leads, sales, automated DMs or positive sentiment.
6. Three test priorities tied to source evidence and feasible production changes. Adapt them to the user's product when its audience, offer and goal are known; otherwise make them reusable for an unspecified product. Propose a small test matrix varying one axis at a time, with evaluation at comparable post age. Do not carry source performance promises into a new product.

## 5. Deliver and retain

```bash
python3 <skill-dir>/scripts/hook_report.py --out <run-dir> --insights <run-dir>/insights.json --lang ru
```

Deliver `report.html` as a single local file with embedded cover assets, an executive summary, linked video map, group comparisons, source-backed findings, and a searchable/sortable **table of every selected video**. With `transcripts.json`, the renderer joins audio by video ID, adds spoken opening and full-transcript columns, and writes `videos_with_transcripts.csv`. Also keep `videos.csv` including annotations, `months.csv`, `cards.json`, `analysis.json`, `snapshot.json`, original covers and sheets, and raw responses for audit. Visually inspect the report where permitted; don't label parser/link checks as a visual review or circumvent a preview block. Deployment/publication is a separate action, only when the user requests it.

When asked to save formulas, write a project-local Markdown library with source URLs, exact source quote, generalized formula, adaptations, evidence strength, visual recipe and date. Link it from project documentation when appropriate; saving a file does not guarantee memory in future unrelated tasks.
