---
name: carousel-account-patterns
description: >
  Analyze the last N (default 50) carousels of a TikTok account and extract the top
  hook/structure formulas worth adapting for the user's product. Pipeline: one script
  fetches carousels via direct ScrapeCreators REST (cursor pagination) and OCRs every
  slide via a cheap vision model (Gemini Flash Lite, auto-fallback to Grok when Gemini
  is unavailable/geo-blocked), Claude discovers patterns from the ranked digest,
  natively Reads the top-reference slides to ground the visual layer, aggregates honest
  per-pattern stats (with mapping validation), and writes a structured Russian report
  with verbatim examples, fill-in-the-blank templates, and ready-to-shoot hooks adapted
  for the product. Trigger phrases: "разбор паттернов каруселей",
  "проанализируй карусели аккаунта", "топ паттерны формулы каруселей", "carousel account
  patterns", "carousel patterns analysis", "формулы каруселей аккаунта", "вытащи формулы
  каруселей", "analyze account carousels", "carousel formulas from account"
---

# Carousel Account Patterns

Turn a TikTok account link into a formula-mining report: which carousel patterns the
account runs, how each performs (peak / avg / save-rate), the meta-formula skeleton,
and ready-to-use hooks adapted for the user's product.

## Inputs

- **Account**: TikTok URL (`https://www.tiktok.com/@handle`) or bare handle. Required.
- **N carousels**: default 50 (user may say "последние 30/100").
- **Product to adapt for**: default = the product of the current project (read its
  CLAUDE.md). User may name another product.

## Requirements

- `SCRAPE_CREATORS_API_KEY` + an OCR provider key: `GOOGLE_API_KEY` (Gemini, preferred)
  or `XAI_API_KEY` (Grok fallback). The script reads keys from shell env or from
  `~/.zshenv` / `~/.zshrc` / the repo `.env` (via `TIKTOK_SKILLS_ROOT`) / `./.env` —
  no `source` needed.
  Default `--provider auto` probes Gemini and falls back to Grok automatically
  (e.g. when Gemini is geo-blocked: «User location is not supported»).
- Optional, for Step 5 on macOS: `sips` (built-in) — converts HEIC slides TikTok
  sometimes serves under a `.webp` name. On other platforms the file is kept as-is.
- Cost: ~5-15 ScrapeCreators calls (10 posts/page; carousel-heavy account ≈ N/10+ pages)
  + 1 cheap vision call per slide (~100-150 for N=50). Whole pipeline ≈ 1-2 min.

## Process

### Step 1 — fetch + OCR (one command, ~60-90s for N=50)

```bash
source ~/.zshrc 2>/dev/null
python3 ~/.claude/skills/carousel-account-patterns/scripts/fetch_and_ocr.py \
  "<URL_OR_HANDLE>" --out "<scratchpad>/carousel_patterns_<handle>" --limit <N>
```

The script paginates the profile feed directly via REST (no MCP — MCP dumps 200-350KB
per page into context), filters carousel posts (`image_post_info != null`), dedupes
pinned posts, sorts by recency, takes the newest N, then downloads + OCRs every slide
in one thread pool (15 workers). Outputs:

- `carousels_ocr.json` — full dataset (metrics, post `url`, slide URLs, `slide_text[]`)
- `DIGEST.txt` — ranked by views: header stats, then per carousel one block with
  metrics + save% + `URL:` (link to the TikTok post) + `HOOK:` (slide 1 text) +
  `BODY:` (remaining slides). The `URL:` is the reference link — carry it into the report.

Only a short summary hits stdout. If it warns "only X carousels available", proceed
with what exists and note it in the report. If 0 carousels — the account is video-only;
tell the user and suggest `tiktok-account-hook-analysis` instead.

### Step 2 — read digest, discover patterns (Claude's actual job)

`Read` the `DIGEST.txt` (fits in one read for N=50). Discover the repeating patterns
yourself — do NOT reuse pattern names from previous runs; every account is different.
For each pattern note: hook formula, emotional mechanism (curiosity / authority /
transformation / insider secret / contrarian...), which slide-2 structure it pairs with.

While reading, also detect the **business layer** — this is usually the most valuable
insight: does the account softly plug a product/app inside the tips? Where exactly
(which list item, what wording)? Are there engineered-virality CTAs ("copy this
slideshow", "read the caption")? Count them.

### Step 3 — honest per-pattern numbers

Write a mapping `{carousel_id: "P1 short-name"}` for ALL carousels to `mapping.json`
in the same dir, then:

```bash
python3 ~/.claude/skills/carousel-account-patterns/scripts/aggregate.py \
  <dir>/carousels_ocr.json <dir>/mapping.json
```

This prints the pattern table (n, peak, avg, total, save%) ranked by peak views,
followed by a **top-reference URL per pattern** (the peak-views carousel for each) —
use those exact links as each pattern's clickable reference in the report.
It also WARNS about mapping ids that don't exist in the dataset (typos) and lists
unlabeled carousels — fix the mapping and rerun until both lists are empty (or
consciously leave them unclassified and say so in the report).
Never eyeball-aggregate — the table in the report must come from this script.
Key reading: **peak/avg views = reach patterns; save-rate = intent patterns** (for a
utility app save-rate matters most). Repeated hooks with wildly different views on
different posts = "virality is a lottery, formula is constant; repost winners" — call
this out if present.

### Step 3.5 — visual pass on top references (mandatory before writing)

OCR text does not carry the visual layer (note-screenshot aesthetic, fonts, photo vs
text slides, design series) — and «Микро-приёмы» must not be guessed from text. For
the top 2-3 patterns, download the reference carousel's slides and **Read them
natively** (slide 1 + one body slide each is enough):

```bash
python3 ~/.claude/skills/carousel-account-patterns/scripts/download_slides.py \
  "<dir>/carousels_ocr.json" "<dir>/slides_<id>" --id <carousel_id>
```

While reading, verify OCR verbatimness on these covers (cheap models silently fix
typos; a recurring typo = a reused template) and note: background style, typography,
text density per slide, where the product appears visually.

### Step 4 — write the report

Save into the current project: `analyzed_carousels/<handle>/`:

- `PATTERNS_FOR_<PRODUCT>.md` — the report (template below)
- copy `carousels_ocr.json` + `DIGEST.txt` alongside as raw artifacts

Then `open` the report (it's the main deliverable) and give the user a markdown link
(relative path, never `file://`) + absolute path in backticks.

## Report template (sections, in this order)

Report language: **Russian** (strategy discussion). Hooks/examples: **the target
audience's language**. Keep verbatim quotes verbatim.

**Link every referenced carousel.** Whenever the report cites a specific carousel
(top posts, a pattern's example, a peak-views winner), render it as a clickable
markdown link `[короткая подпись](https://www.tiktok.com/@handle/photo/<id>)` using
the post `url` from the digest / aggregate output — never a bare id or plain number.

1. **Шапка** — account, follower count, N carousels analyzed + date range, method,
   links to raw files, and a **«Топ-референсы»** list: the 3-5 highest-view carousels
   as clickable markdown links (title = hook + views), straight from the top of the digest.
2. **🎯 Главный вывод** — the single most important thing (usually the business layer:
   what the account *really* is, how the product is embedded, exact wording of the
   soft-plug). This must come before any formula.
3. **📊 Таблица формул** — from aggregate.py output, with a role column
   (охват / сохранения / демо продукта) and a **реф** column linking each pattern's
   peak-views carousel (the top-reference URL aggregate.py prints). Note which patterns
   win on peak vs save-rate.
4. **🧬 Мета-формула** — the structural skeleton shared by most carousels (slide count,
   slide 1 role, slide 2 layout, where value sits, where the product sits). ASCII
   diagram.
5. **🔑 Топ формулы хуков** — for each of the top 4-6 patterns: verbatim example from
   the account **as a clickable link to the source post** (`[verbatim hook](url)`) →
   numbers → fill-in-the-blank template (`i've been [x] for [y] and...`)
   → adapted hook for the product (respect the product's voice/JTBD from its CLAUDE.md,
   and the audience's verbatim language if the project documents it).
6. **🩹 Микро-приёмы** — small copyable techniques (note-screenshot aesthetic,
   lowercase/slang, product-as-habit-not-offer, curiosity gap to slide 2, community
   loops, hashtag strategy, repost-winners cadence).
7. **⚠️ Что НЕ копировать** — ethically or brand-wise (fabricated authority, synthetic
   data screenshots...) and why the product's honest alternative is a differentiator.
8. **✅ Готовые хуки** — 5-6 ready-to-shoot hooks for the product, each tagged with its
   pattern + role (охват / сохранения / демо).

Product-specific rules live in the project's CLAUDE.md / memory — check them before
writing adaptations (tone rules, banned phrases, required product-demo elements, etc.).

### Step 5 (optional) — download the top carousel's slides

For a visual library/report, pull the actual slides of the winner:

```bash
python3 ~/.claude/skills/carousel-account-patterns/scripts/download_slides.py \
  "<dir>/carousels_ocr.json" "<dest_dir>" [--id <carousel_id>]
```

Clears stale `slide_*` files in dest, downloads every slide of the max-views carousel
(or the one passed via `--id`), auto-converts HEIC→JPEG (macOS `sips`), and prints one
JSON line: metrics + hook + `slide_texts[]` + `local_paths[]`. Failed downloads appear
as `[ERR ...]` strings inside `local_paths` — filter them.

## Instagram fallback (untested path)

If the user gives an Instagram account instead: the pipeline script is TikTok-only.
Use `GET https://api.scrapecreators.com/v2/instagram/user/posts` (header `x-api-key`),
inspect the response for carousel items (`carousel_media`), and adapt: build the same
compact JSON (id/date/metrics/slide urls), reuse the OCR half by writing slide URLs
into the same structure, then Steps 2-4 are identical. Inspect the first response
before scripting against it.

## Failure modes

- **Missing keys** → the script searches shell env + `~/.zshenv` / `~/.zshrc` + repo
  `.env` itself; if it still exits with a key error, ask the user.
- **Gemini «User location is not supported»** → nothing to do; `--provider auto`
  already fell back to Grok (check the script's stdout line).
- **OCR errors > 5%** → rerun the script (it re-fetches everything; cheap) or note
  affected carousels in the report.
- **Account has < N carousels** → proceed, state the real count in the report header.
- **Very long carousels (10+ slides)** → fine; BODY in digest will be long, skim it.
