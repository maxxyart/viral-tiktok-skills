---
name: facebook-ads-deep-analysis
description: "Deep analysis of a Facebook Ad Library advertiser's creatives (Viral Camp) (video, image AND carousel). Takes a CSV produced by `facebook-ads-short-analysis` (catalog or *_by_impressions.csv), routes each row by `media_type`: videos are downloaded (sd, fallback hd), trimmed to the first 10 seconds with ffmpeg, and sent to Gemini for hook + timestamped script + CTA + product_moment; images are downloaded and sent directly to Gemini for OCR + visual description + emotion + CTA; carousels send up to 3 card images in ONE call (cards from the *_ads_full.json sidecar) and get a card-by-card flow. Writes enriched CSV with 7 new columns (hook_text_overlay, visual_hook, script, emotion, cta, product_moment, analysis_status) + streaming JSONL sidecar. Auto-retries with backoff, --resume re-runs only non-ok rows, --top N analyzes only the top impression-ranked creatives, Grok fallback for images/carousels when Gemini is geo-blocked. Trigger phrases - \"facebook ads deep analysis\", \"fb ads full analysis\", \"enrich fb ads csv\", \"analyze fb ad videos\", \"analyze fb ad images\", \"fb ad library gemini analysis\", \"полный анализ fb ads\", \"обогати fb ads csv\", \"анализ карусельных креативов fb\""
---

# Facebook Ads Deep Analysis

## When to use

After running `facebook-ads-short-analysis` you have a CSV with all active creatives. This skill enriches each row with model-analyzed data. **The process differs by creative type** — videos get a timestamped script + product_moment; images get an emotion tag; carousels get a card-by-card flow.

**For big accounts, prefer enriching `<prefix>_by_impressions.csv` with `--top 50/100`** — that analyzes the creatives with proven reach instead of the whole catalog, at a fraction of the cost. Enrich the full catalog only when the user needs complete coverage.

## Prerequisites

- A Gemini key in `GOOGLE_API_KEY` ([Google AI Studio](https://aistudio.google.com/apikey)), from the environment or an explicit `--env-file path/to/.env`. Never search shell configs for keys; if the key is missing, ask the user. Optional `XAI_API_KEY` — Grok fallback for image/carousel rows when Gemini is unavailable (e.g. "User location is not supported" behind some VPN exits); video rows need Gemini.
- `ffmpeg` in PATH (needed only if the CSV contains video rows)
- Python 3.10+ with `google-genai` and `httpx`: `python3 -m pip install google-genai httpx`
- `SKILL_DIR` below means the folder that contains this SKILL.md.
- Cost: one Gemini Flash Lite call per creative (cents for a top-50 run). Tell the user the row count before running the full catalog.
- Input CSV needs: `ad_archive_id`, `media_type`, and media URL columns (`video_sd_url`/`video_hd_url`, `image_url`/`video_preview_image_url`) — both the catalog CSV and `*_by_impressions.csv` from facebook-ads-short-analysis qualify.
- For multi-card carousel analysis: `<prefix>_ads_full.json` sitting next to the input CSV (written by facebook-ads-short-analysis automatically; auto-detected, or pass `--full-json`).

## Usage

```bash
python3 "$SKILL_DIR/scripts/analyze.py" \
  --input-csv biblechat_us_by_impressions.csv \
  --out-csv biblechat_us_top_enriched.csv \
  --top 50 \
  [--media all|video|image|carousel] [--start 0] [--end 20] \
  [--concurrency 10] [--clip-seconds 10] [--model gemini-3.1-flash-lite] [--resume] [--env-file .env]
```

Args:
- `--input-csv` — CSV from facebook-ads-short-analysis (catalog or by_impressions)
- `--out-csv` — where to write enriched CSV (same columns + 7 new ones)
- `--top N` — analyze only the N best rows by `impression_rank` (ranked rows first, then CSV order). Applied before `--start/--end`.
- `--media` — scope to `video` / `image` / `carousel` (default `all`)
- `--start N / --end M` — slice of eligible rows
- `--concurrency N` — parallel workers (default 10)
- `--clip-seconds N` — video trim length (default 10)
- `--model` — Gemini model (default `gemini-3.1-flash-lite`)
- `--resume` — skip rows already `ok` in `<out-csv>.jsonl`, re-run errors/stale/skips
- `--full-json PATH` — carousel cards sidecar override
- `--env-file PATH` — explicit file with `GOOGLE_API_KEY` / `XAI_API_KEY`

## Routing by creative type

### 🎬 Video rows (`media_type == "video"`, `video_sd_url` → fallback `video_hd_url`)
1. Download MP4 (retry ×3 with backoff)
2. ffmpeg trim to first N seconds (`-c copy`, fallback re-encode)
3. Gemini → strict JSON: `hook_text_overlay` (frame-0 text), `visual_hook` (first 2s), `script` (timestamped, <800 chars), `cta`, `product_moment` (when/how the product or app UI first appears — key for integration analysis)

### 🖼 Image rows (`media_type == "image"`, `image_url` or `video_preview_image_url`)
1. Download (retry ×3), mime sniffed from magic bytes (jpeg/png/webp)
2. Gemini (or Grok fallback) → `hook_text_overlay` (OCR), `visual_hook`, `emotion` (1-3 words), `cta`

### 🎠 Carousel rows (`media_type == "carousel"`)
1. If the `*_ads_full.json` sidecar yields ≥2 card images → download up to 3 cards, send in ONE model call with the carousel prompt → `hook_text_overlay` (card 1), `visual_hook` (card 1 + shared style), `script` = **card-by-card flow** (`[card 1] ... [card 2] ...` — the sequence logic), `emotion`, `cta`
2. Else falls back to the CSV's first-card media: video path if video urls present, single-image path otherwise

### ⏭ No usable media → `skip:*` status, blank columns

Model: `gemini-3.1-flash-lite`, `response_mime_type="application/json"`, `temperature=0.2`. Provider probed once at startup; on Gemini failure with `XAI_API_KEY` present, images/carousels run via Grok (`ok:grok` status), videos get `error:gemini_unavailable`.

## Output schema

Enriched CSV = all original columns + 7 appended:
- `hook_text_overlay`, `visual_hook`, `cta` — all types
- `script` — video (timestamped speech) AND carousel (card-by-card flow); blank for images
- `emotion` — image + carousel; blank for video
- `product_moment` — video only
- `analysis_status` — `ok` / `ok:grok` / `skip:<reason>` / `stale_url` / `error:<type>`. **Data columns stay clean on errors** — filter by status, never parse error text out of content columns.

Sidecar `<out-csv>.jsonl` — one line per analyzed row (incl. `_t` timings and error details), written incrementally as results finish. A crash loses nothing; re-run with `--resume`.

## Performance expectations

- **Video**: ~7-10s per creative (dl 1-2s + trim + Gemini 5-8s). ~150 videos in ~2 min at concurrency=10.
- **Image**: ~4-8s. **Carousel×3**: ~6-10s (3 downloads + one model call).
- Main bottleneck: Gemini inference. Concurrency 10 is safe; higher risks 429 (auto-retried, but slower overall).

## Errors & retries

- Downloads and model calls auto-retry ×3 with exponential backoff on 429/5xx/network errors.
- **`stale_url`** — fbcdn signed URLs expire (~1 day): HTTP 403/410, no retry. Re-run `facebook-ads-short-analysis` for a fresh CSV, then re-run this with `--resume`.
- After any partial run: same command + `--resume` finishes only what's missing.

## Step 2: Present results

Read the printed summary: per-type averages, **status breakdown** (how many ok / ok:grok / stale / error / skip). If `stale_url` appeared — tell the user to refresh the short-analysis CSV first. Optionally show 3-5 sample enriched rows per type. Point to the output CSV.

## Step 3: Pattern analysis & report (qualitative synthesis by the assistant)

After the enrichment script finishes, **ALWAYS produce a structured analytical report** by reading the enriched CSV and synthesizing patterns across all rows. This is the main value of the skill — the CSV alone is just raw data.

**Weight patterns by reach, not by count.** The input CSV now carries `impression_rank` and `days_running` (the catalog CSV also `impressions_text` buckets). "Pattern X dominates the top-25 by reach" is a much stronger finding than "pattern X appears 12 times". Long-lived + top-ranked creatives are proven winners; a pattern that exists only in the unranked long tail is an experiment, not a formula. Call this distinction out explicitly in every section.

Dump the enriched rows for inspection (write the dump next to the CSV or into the session scratchpad, not `/tmp`) — sort by `impression_rank` so the top of the file = top of the account:

```bash
python3 -c "
import csv
rows = list(csv.DictReader(open('<enriched_csv>')))
def rk(r):
    try: return (0, int(r.get('impression_rank') or ''))
    except: return (1, 0)
rows.sort(key=rk)
for r in rows:
    if not str(r.get('analysis_status','')).startswith('ok'): continue
    mt = r.get('media_type','')
    rank = r.get('impression_rank','')
    print(f'--- rank={rank or \"—\"} | {mt} | {r[\"ad_archive_id\"]} | {r.get(\"days_running\",\"\")}d ---')
    print(f'HOOK: {r[\"hook_text_overlay\"][:180]}')
    print(f'VIS:  {r[\"visual_hook\"][:220]}')
    if r.get('script'):  print(f'SCR:  {r[\"script\"][:350]}')
    if r.get('emotion'): print(f'EMO:  {r[\"emotion\"]}')
    if r.get('cta'):     print(f'CTA:  {r[\"cta\"][:100]}')
    if r.get('product_moment'): print(f'PROD: {r[\"product_moment\"][:120]}')
    print()
" > <prefix>_dump.txt
```
Then read the dump in chunks (200-300 lines at a time).

### Tailor the report to the media mix

Always open the report with a one-line **media mix** summary incl. carousels: *"100 ads — 82% video, 12% image, 6% carousel"*. This sets reader expectations.

- **Mixed**: break down sections by type where it matters (visual patterns separately — video is dynamic, image is static, carousel is sequential).
- **Pure video**: focus on hook delivery, script structure, product_moment timing (how fast the app appears = integration style), clip reuse.
- **Pure image**: focus on image↔body_text relationship, overlay formulas, visual→emotion clusters.
- **Carousel-heavy** (e-commerce): focus on card-flow logic (`script` field) — what card 1 shows vs how the sequence sells, and the CTA placement.

### Report structure — produce all five sections

#### 1. 🎬 Visual patterns
Cluster the `visual_hook` field across all rows. Build a table with:
- Pattern name (e.g. "UGC talking head in car", "reused sermon clip", "couple embracing b&w", "cinematic B-roll")
- Approx % of creatives + **share within the top-25 by rank** (two separate numbers)
- One representative example

For image-heavy datasets, also include an **emotion distribution** sub-table. For video-heavy, call out the dominant aesthetic and the typical `product_moment` (e.g. "app UI appears at 0:03-0:05 in 70% of top videos").

#### 2. 🎯 Creative Angles
List all distinct angles (usually 8-15). Group into tactical product-angles (feature-led hooks) vs emotional/identity angles (pain/testimonial hooks). For each angle: count of creatives + how many sit in the ranked top + 1 hook example. Sort by reach-weighted importance, not raw frequency. Flag any angle that repeats >5 times or holds ≥3 top-25 slots — that's a validated winner they're scaling.

#### 3. 🎯 Pain points — hierarchy
Extract pain points from hooks + scripts. Rank by % of creatives targeting each. Present as a table: Pain / % / top-rank presence / hook example. End with a one-line summary of what the advertiser is NOT targeting — that's often the open gap for an adapted product.

#### 4. ✅ Adaptation recommendations
If the user has a **target project** (ask if not specified), map each winning angle to a direct adaptation. For each top angle:
- Quote the original hook verbatim
- **Provide 1-3 reference links to the actual source creatives** in FB Ad Library. Format: `https://www.facebook.com/ads/library/?id=<ad_archive_id>`. Prefer referencing creatives from the ranked top (proven reach) over unranked ones.
- Propose the adapted hook for the target product
- Note why it works (which audience pain it targets now)
- Prefer using **raw audience language** from the target project's research (comments, reviews) over polished marketing copy

For **image creatives**, note the image↔text relationship to replicate: does the image show the *pain*, the *during*, or the *after-transformation* state? For **carousels**, name the card-flow formula being reused (e.g. "hero product shot → zoomed detail → price+CTA").

Produce 7-10 concrete adaptations — enough for a content sprint.

**🔗 REFERENCES ARE MANDATORY — NON-NEGOTIABLE**

Every single adaptation idea — in the main report AND in any follow-up / custom analysis that stems from this dataset (app-demo analysis, angle deep-dives, template breakdowns, whatever the user asks next) — MUST include clickable FB Ad Library links to the source creatives being referenced.

Format: `https://www.facebook.com/ads/library/?id=<ad_archive_id>`

Rules:
- At least 1 link per adaptation idea, ideally 2-3
- Put the link inline next to the quoted original hook or the template name, not hidden in a footer
- If you reference "the memorization game template" or "the UGC car selfie pattern" anywhere — link 1-3 example ads for that pattern
- If you can't find the `ad_archive_id` in the CSV/JSONL for the pattern you're describing, go back and find it before writing the recommendation
- This rule persists across the entire conversation, not just the first report. If the user asks a follow-up question ("now do X analysis", "write scripts for these ideas", "dig into the meditation ads"), references must still be attached to every recommendation

**⚠️ Reference-visual consistency check — DO THIS BEFORE WRITING EACH ADAPTATION**

When writing "Visual: <description>" alongside a set of reference ads, the description MUST match the actual `visual_hook` field of those referenced ads in the CSV. Common failure mode: recommending "UGC woman in car" as the visual while referencing ads that are actually cinematic AI-Jesus clips (or vice versa). Before finalizing each adaptation:
1. Pull up the `visual_hook` of each ref ad from the CSV/dump
2. Confirm the described visual format matches what those specific ads actually show
3. If they don't match — either swap the refs for ads with the right visual, OR change the visual description to match the refs. Never ship a mismatch.

A mismatched reference is worse than no reference — the user clicks through, sees something different from what you described, and loses trust in the whole recommendation set.

Why: the user needs to watch the original before adapting it. A recommendation without a reference is unusable and wastes the user's time going back to find the source themselves. A recommendation with a WRONG reference is actively harmful — it makes the user doubt every other recommendation in the report.

#### 5. 🚫 What NOT to borrow + strategic insight
- List angles that would confuse the adapted product's positioning
- End with one paragraph: what's the winning advertiser's strategic formula, and how should the target product position itself against/around that

### Good analysis heuristics

- **Look for clip reuse.** If the same `visual_hook` description appears 3+ times with different hooks, that's a reused piece of B-roll being scaled — very cheap to replicate.
- **Look for hook template patterns.** "X but Y" ("Feeling guilty I didn't X but I have this"), "POV:", "They literally made a [familiar product] for [niche]", "Ladies, if...", "[Pastor clip] + [overlay caption]" — these are reproducible frameworks, not one-off hooks.
- **Use `product_moment` to classify integration style** — instant app-demo (0:00-0:02), delayed reveal (after the pain setup), or never-shown (pure curiosity funnel). This is a strategic choice worth calling out per angle.
- **Count creatives per pain point**, not per hook. Many hooks target the same underlying pain.
- **Flag any pain point with 0 coverage** in the dataset — that's a positioning gap the target product can own.
- **Language authenticity matters more than clever copy.** If the target project has audience-research data (comments, reviews, Reddit threads), pull raw emotional phrases from it and swap them into the adapted hooks verbatim.
