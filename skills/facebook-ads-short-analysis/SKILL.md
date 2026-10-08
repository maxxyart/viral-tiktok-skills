---
name: facebook-ads-short-analysis
description: "Short analysis of a Facebook Ad Library advertiser (Viral Camp). Input - FB library URL (or page_id) + one or more country codes (geo). Output - full CSV with all ScrapeCreators data (incl. video/image URLs), an impression-ranked CSV (creatives ordered high→low by total_impressions), plus analytics summary: total active creatives, breakdown by media type (video/image/meme), landing destinations (App Store / Google Play / web funnels + funnel URLs), text patterns from body_text (top n-grams, duplicate clusters), impression-tier breakdown of top-reach creatives, publisher platforms, creative launch velocity, longevity (days_running), and impression buckets where Meta exposes them. The skill runs BOTH passes — relevancy/geo catalog AND an impression-sorted pass — and stamps an impression rank onto catalog rows (join by id → media asset → unique body copy). NO Gemini / no video analysis — fast and cheap. Trigger phrases - \"fb ads short analysis\", \"facebook ads overview\", \"анализ fb ads\", \"fb ad library анализ\", \"meta ads analysis\", \"facebook ad library overview\", \"fb ads breakdown\", \"analyze fb ads account\", \"fb ads by impressions\", \"топ креативов по impressions\", \"ранжирование по impressions\""
---

# Facebook Ads Short Analysis

## When to use

When the user provides a Facebook Ad Library URL (or `page_id`) and optionally one or more geo/country codes, and wants a quick overview of the account's active ad creatives — without deep video analysis.

## Prerequisites

- A [ScrapeCreators](https://scrapecreators.com) key in `SCRAPE_CREATORS_API_KEY` (or `SCRAPECREATORS_API_KEY`), or an explicit `--env-file path/to/.env`. Never search shell configs for keys; if the key is missing, ask the user.
- Python 3.10+ with `httpx`: `python3 -m pip install httpx`
- `SKILL_DIR` below means the folder that contains this SKILL.md (e.g. `~/.claude/skills/facebook-ads-short-analysis` or `~/.codex/skills/facebook-ads-short-analysis`).
- Cost: ScrapeCreators bills per request. A small advertiser in one country is 2–5 requests; `--countries ALL` with the geo breakdown probes ~50 countries and costs accordingly. The script prints `[COST] API requests`.

## Input format

User provides:
1. **Page URL** — e.g. `https://www.facebook.com/ads/library/?...&view_all_page_id=142979542221369` — extract `view_all_page_id`. Also accept raw `page_id`. If the user only knows the brand name, find the page in Ad Library first (or via ScrapeCreators' company search) and confirm it with the user.
2. **Geo** — one or more 2-letter country codes (`US`, `US,CA`, `ALL`). If user says "все страны" / "all" / not specified → fall back to `ALL`.

## Workflow

`cd` into the user's project directory first (output files land in CWD), then:

```bash
python3 "$SKILL_DIR/scripts/analyze.py" \
  --page-id 142979542221369 \
  --countries US \
  --out-prefix biblechat_us
```

Useful flags: `--env-file PATH` (explicit key file), `--include-inactive` (what they recently stopped running), `--impressions-cap N` (bound the rank pull),
`--offline` (reuse cache regardless of age — free re-analysis), `--no-impressions-rank` (geo catalog only).

The script runs **two passes** — the relevancy/geo catalog AND an impression-sorted pass — then stamps an impression rank onto the catalog rows:

1. **Catalog pass:** `GET .../adLibrary/company/ads` with `status=ACTIVE, media_type=ALL, sort_by=relevancy_monthly_grouped` per country, paginating via cursor. All shards run in parallel (semaphore 10) with **retry + exponential backoff** on 429/5xx/network errors. A shard that still fails is used partially for this run but **never cached**; failed shards are listed in the report. Disk cache TTL 6h (`--cache-ttl`, `--no-cache`, `--offline`).
2. For each country, collects ALL ads. If multiple countries passed, deduplicates by `ad_archive_id` and records in which countries each ad appears.
3. **Geo breakdown:** when `--countries ALL` is used, the script auto-probes a default set of major markets (`DEFAULT_PROBE_GEOS` — US/CA/GB/AU/NZ/IE/ZA, major EU, LATAM, APAC, MENA, CIS) to attribute each ad to specific countries (the `ALL` shard returns the union but `targeted_or_reached_countries` is empty in the API response). Disable with `--no-geo-breakdown`; override the probe list with `--probe-geos US,CA,GB`. Ads seen in `ALL` but in no probed geo are counted in the report as **unattributed** — a signal of markets outside the probe list. Note: `trim=true` was measured to save only ~9% of payload and zero credits (billing is per request), so the script does not use it.
4. **Impressions pass:** unless `--no-impressions-rank` is set, a separate pass with `sort_by=total_impressions` (high → low). If the user asked for exactly ONE real country, the rank is pulled **for that country** (otherwise `ALL`). Builds three rank maps — ad id, media-asset stem, unique body copy — and stamps `impression_rank` + `impression_rank_match` (`id`/`media`/`body`) onto catalog rows. Cap with `--impressions-cap N` (default 0 = ALL). The cache stores exhausted/truncated metadata, so a capped pull can never masquerade as a full list on a later run, and the truncation warning survives cache hits.
   - **Rank ≠ views.** Meta exposes no impression numbers in this view — it's an ordinal rank only.
   - **~1000-ad ceiling.** Deep cursor pagination trips the server's HTTP 431 header-size limit. The script stops gracefully and flags truncation; top ranks are always complete.
   - **Collation / id mismatch.** The impression view returns collation representatives; only part joins back by id — media-stem and unique-body fallbacks recover more. Match by creative content, not id.
5. **Impression buckets:** the per-country catalog sometimes carries `impressions_text` (coarse ranges like `<100`); captured as a CSV column + report section when present. This is the only place Meta shows any numbers for commercial advertisers.
6. **Outputs:**
   - `<prefix>_ads.csv` — full catalog: all top-level fields + snapshot highlights + `days_running`, `total_active_time`, `impressions_text`, `impression_rank`, `impression_rank_match`. Carousel creatives are extracted from `snapshot.cards` (body/title/link/CTA/media), so carousel rows are no longer empty.
   - `<prefix>_by_impressions.csv` — the authoritative ranked list (self-contained): rank, ad_library_url, in_catalog, `days_running`, media/landing/text/urls.
   - `<prefix>_ads_full.json` — raw snapshot dump (compact).
   - `<prefix>_meta.json` — run metadata: counts, failed/truncated shards, API requests spent (≈ credits).
   - `<prefix>_inactive.csv` — with `--include-inactive`: recently stopped ads (no probes/rank).
7. **Report** `<prefix>_analytics.md`:
   - Header warnings: failed shards, truncated shards, unattributed ads
   - Creatives ranked by impressions: coverage lines (id/media/body split), cumulative tier table (top 10/25/50/100/all — media mix, top landing, avg collation, **avg days live**, dominant hook), Top 15 list with `ad_library_url` and days live
   - Per-country breakdown + solo-geo ads
   - Media type breakdown; **publisher platforms** (FB/IG/AN)
   - Landing destinations (App Store / Google Play / web funnels with URLs)
   - CTA button types; **impression buckets** (when Meta exposes them)
   - **Creative launch velocity** — still-active creatives by launch month (last 12, with bars)
   - Text patterns in body_text: openings, bigrams, trigrams, near-dup clusters, unigrams
   - Recently stopped ads section (with `--include-inactive`)

The `ALL` meta-shard is excluded from the per-country aggregates (otherwise every ad would be tagged `ALL`).

## Step 2: Present results

After script runs, read `<prefix>_analytics.md` and present:

1. Summary table (total, by media type, **by country** — sorted descending; flag the top 3-5 markets, any zero-coverage major markets, and the unattributed count if present)
2. **Creatives ranked by impressions** — tier table + Top 15 (clickable `ad_library_url`). State the *rank ≠ absolute views* caveat and surface the truncation warning if hit. Point to `<prefix>_by_impressions.csv` as the authoritative list.
3. Landing destinations with **clickable funnel URLs**
4. Launch velocity + longevity highlights (long-running top creatives = proven winners)
5. Text patterns section (top phrases + duplicate clusters)
6. Paths to the CSVs for further work; mention `[COST] API requests` from script output

Keep output concise. Don't re-run analysis — the script already did it.

## Notes

- No Gemini, no video downloads.
- `link_url` can be an FB redirect (`fb.me/...`, `l.facebook.com/...`). Recorded as-is; classification heuristics handle common cases.
- Re-running with the same prefix is cheap: 6h disk cache; `--offline` forces cache reuse beyond TTL (free re-analysis / report tweaks).

### Impression ranking caveats (read before interpreting)

- **It's a rank, not numbers.** Meta hides exact impressions/spend for commercial advertisers; the only numbers it shows are the coarse `impressions_text` buckets in the per-country catalog (partial coverage).
- **Match by creative, not by id.** The impression pass returns collation representatives; expect a partial id-join (media-asset + unique-body fallbacks recover more). The low join rate is fundamental, not a bug — use `<prefix>_by_impressions.csv` standalone.
- **~1000-ad practical ceiling** per paginated chain (HTTP 431 cursor limit) — affects both the impressions pass and giant catalog shards; both are flagged in the report. For a top-N view this is irrelevant.
- Skip the whole second pass with `--no-impressions-rank` if you only need the geo catalog.

## Next step

For hooks, scripts, visuals and adaptation ideas, run **facebook-ads-deep-analysis** on `<prefix>_by_impressions.csv` (usually `--top 50`). The `*_ads_full.json` sidecar must stay next to the CSV for carousel cards.
