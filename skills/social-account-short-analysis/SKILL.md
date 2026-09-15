---
name: social-account-short-analysis
description: Analyze an Instagram Reels or TikTok video account with ScrapeCreators. Produce CSV, publication-month metrics, top five videos, and a concise HTML account overview. Use for account performance, comment rate, virality, and what the account promotes; use social-account-hook-analysis for visual hook research.
---

# Social Account Short Analysis (Viral Camp)

Deliver a concise, evidence-backed account overview in the user's language. Support Instagram and TikTok equally. Preserve the user's source, scope, output format, and exclusions.

## Resolve scope

- Accept a profile URL or handle. Infer platform from a URL; ask if a bare handle has no platform context. A `/reels/` suffix is not the handle.
- Default to the **latest 60 videos** when scope is unspecified. If the user requests all videos, use all available feed videos and paginate to an explicit end. Honor an explicit number/date range; never quietly replace “all” with 60.
- TikTok photo posts and Instagram carousels are excluded from a video cohort. If the user asks for all post types, disclose the distinction and use appropriate post endpoints; do not count carousel cover exposure as video plays.
- Read relevant existing project/product context for tailored recommendations. Do not assume the user owns the analyzed account or imports its niche. Generic account research needs no product intake.

## Collect and verify

Read [references/collection.md](references/collection.md) before collecting. It defines MCP/API/CLI routing, pagination, field mapping, and failure handling.

Use **ScrapeCreators MCP when available**, particularly when requested. Discover actual tool schemas; don't invent tool names. Save raw page results for replay. An authenticated ScrapeCreators CLI or REST API is a fallback, **not MCP**; disclose the actual transport. If the user requires MCP exclusively and it is unavailable, report that blocker rather than silently substituting another service.

The scripts resolve relative to this `SKILL.md` directory, not a hard-coded `~/.claude` path. Python 3.10+; no Node dependency or model key required. Examples below use `<skill-dir>` and `<run-dir>` as placeholders for resolved absolute paths.

```bash
python3 <skill-dir>/scripts/social.py collect https://www.instagram.com/ACCOUNT/reels/ --count 60 --transport cli --out <run-dir>
python3 <skill-dir>/scripts/social.py collect https://www.tiktok.com/@ACCOUNT --all --transport api --out <run-dir>
```

MCP results can enter the same pipeline without a second paid scrape:

```bash
python3 <skill-dir>/scripts/social.py collect ACCOUNT --platform instagram --count 60 --pages-dir <raw-page-dir> --fetched-at <original-UTC-timestamp> --out <run-dir>
```

Snapshot is mandatory: exact platform, scope, selected/fetched counts, capture time, transport, pagination stop reason, source limitations. A page cap, broken cursor, schema error, or inaccessible/private feed means **partial**, not empty or complete. Exit code 2 preserves partial output; inspect `snapshot.json` and continue safe reporting without inventing completeness.

## Calculate and interpret

Read [references/metrics.md](references/metrics.md). Use `analysis.json`, `videos.csv`, and `months.csv`; do not calculate report figures from memory or rounded screen labels.

Report:

1. Scope, date coverage and missing metrics.
2. Views and comments: total, mean, median. Comment rate: weighted aggregate, per-video mean and median. Virality: per-video view/median multiplier, mean and median; no meaningless sum of percentages/multiples.
3. Table by **publication month**: N, views/comments total/mean/median, comment rates, median virality. These are cumulative snapshot counters, not views earned that month or follower growth.
4. Top five by views, with original post URLs, date, views, comments, CR and virality multiplier against the same selected cohort. No mixing an all-history numerator with a latest-60 baseline without labeling it.
5. Short account read: topic, recurring offer, CTA, likely audience. Ground promotion claims in observed bio, captions, link destination or video; distinguish inference from evidence. A comment CTA is not proof of automated DMs or sales.

If most views sit in a few posts, show concentration and give median priority over mean. Missing counters stay null; zero views produce undefined CR. Do not compare platform engagement formulas using different available components.

## Deliver

Read [references/reporting.md](references/reporting.md). Write `insights.json` with grounded conclusions, then generate a **portable HTML** report:

```bash
python3 <skill-dir>/scripts/report.py --out <run-dir> --insights <run-dir>/insights.json --lang ru
```

Default deliverables: `report.html`, `videos.csv`, `months.csv`, `analysis.json`, `snapshot.json`; retain raw pages locally. Honor another requested format. Short mode does not download covers or call vision services unless requested.

Open the report through a permitted preview, inspect readability and links, and state any visual verification limitation. If a browser action is blocked, don't bypass the block with another surface or localhost. Finish with the report link and 3–5 findings, including material collection limitations.
