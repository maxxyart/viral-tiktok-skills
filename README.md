# Viral TikTok Skills for Claude Code

Four self-contained [Claude Code](https://claude.com/claude-code) skills for **TikTok growth**: three for fast, cheap account research + one that turns the mined formulas into **ready-to-post carousels**. No database, no heavy setup.

| Skill | What it does | Needs | Speed / cost |
|-------|--------------|-------|--------------|
| **`tiktok-account-short-analysis`** | Fetches all of an account's videos, computes aggregate metrics (total / avg / median views), shows the top 5 with virality & engagement rates, and a short topic read. | ScrapeCreators key | ~30–60s, ~3–8 API calls |
| **`tiktok-account-hook-analysis`** | OCRs the **hook text on each video's cover** (Gemini Vision), clusters them into repeating **hook patterns**, and reports per-pattern analytics (median/avg views, virality). | ScrapeCreators + Google (Gemini) keys | ~3–7 min, image-only (no full video) |
| **`carousel-account-patterns`** | Fetches the last N **carousels (photo posts)**, OCRs **every slide**, Claude maps the repeating patterns, then a script computes honest per-pattern stats (peak / avg / save-rate) with top-reference links → a formula-mining report with fill-in-the-blank hooks adapted for **your** product. | ScrapeCreators + Google (Gemini) keys | ~1–2 min for N=50, Python stdlib only |
| **`hook-notes-carousel`** | **Generates** batches of the highest-converting minimal carousel format: slide 1 = lifestyle photo with a raw lowercase hook, slide 2 = a pixel-faithful **iOS Notes screenshot** (real value in items 1–3, your product *as a personal habit* in item 4, community CTA in item 5). Reads your project context, proposes texts by 3 proven hook formulas, renders deterministic slides, verifies them. | Pillow + any image generator (or your own photos) for backgrounds | slide render <1s, local & free; backgrounds = your generator's price |

The three research skills only read public TikTok data and summarize it — nothing is posted or modified. `hook-notes-carousel` writes PNG slides into your project folder; publishing is still up to you.

> **The loop:** mine an account's winning formulas with `carousel-account-patterns` → hand the report to `hook-notes-carousel` → get a batch of on-formula carousels for your product.

> **Built with the carousel skill:** [boont.ai/carousels](https://boont.ai/carousels/) — a searchable library of 15 app cases × 26 accounts × ~1000 OCR'd carousels, with an [agent entrypoint](https://boont.ai/carousels/AGENT.md) for "pick a reference and adapt it to my product".

---

## Prerequisites

- **Node.js ≥ 18.17** — for the two video skills
- **Python 3.9+** — stdlib only for `carousel-account-patterns`; `pip3 install Pillow` for `hook-notes-carousel`
- **[ScrapeCreators](https://scrapecreators.com) API key** — required for the three research skills
- **[Google AI Studio](https://aistudio.google.com/apikey) key** — required for `tiktok-account-hook-analysis` and `carousel-account-patterns` (Gemini Vision/OCR)
- **Any image source for `hook-notes-carousel` slide-1 backgrounds** — an image-gen skill/CLI (Higgsfield, Midjourney, GPT Image, Flux…), stock, or your own photos; the skill is generator-agnostic and needs no API key itself
- macOS `sips` (built-in) — optional, used by `carousel-account-patterns` to convert HEIC slides TikTok sometimes serves. `hook-notes-carousel` renders best with macOS fonts (Helvetica Neue + Apple Color Emoji) and falls back to DejaVu/Liberation/Segoe on Linux/Windows

No database is required.

## Install

```bash
# 1. Clone
git clone https://github.com/<you>/viral-tiktok-skills.git
cd viral-tiktok-skills

# 2. Install deps
npm install

# 3. Add your keys
cp .env.example .env
#   then edit .env and paste your keys

# 4. Tell the skills where this repo lives (add to ~/.zshrc or ~/.bashrc)
export TIKTOK_SKILLS_ROOT="$(pwd)"

# 5. Make the skills available to Claude Code
cp -R skills/tiktok-account-short-analysis ~/.claude/skills/
cp -R skills/tiktok-account-hook-analysis ~/.claude/skills/
cp -R skills/carousel-account-patterns ~/.claude/skills/
cp -R skills/hook-notes-carousel ~/.claude/skills/
```

The two Node `SKILL.md` files `cd "$TIKTOK_SKILLS_ROOT"` before running, so the repo's `.env` (your keys) is picked up automatically wherever you invoke the skill from.

The carousel skill is **self-contained Python** (its scripts live inside the skill folder) and reads the keys from your shell environment — export them in `~/.zshrc` / `~/.bashrc`:

```bash
export SCRAPE_CREATORS_API_KEY="..."
export GOOGLE_API_KEY="..."
```

## Use it

**Via Claude Code** — just ask in natural language; the trigger phrases in each skill fire automatically:

> "сделай короткий анализ тикток @secretherbsnana"
> "analyze the cover hooks of @username"
> "generate a batch of hook+notes carousels for my project"

**Or run the scripts directly:**

```bash
# Short analysis
npm run short-analysis -- secretherbsnana
npm run short-analysis -- secretherbsnana --since=2026-01-01   # large accounts

# Hook analysis (cover OCR + pattern clustering)
npm run hook-analysis -- secretherbsnana --count 100 --concurrency 10 \
  --out /tmp/hooks.json --out-csv /tmp/hooks.csv
```

```bash
# Carousel patterns — step 1: fetch last 50 carousels + OCR every slide
python3 ~/.claude/skills/carousel-account-patterns/scripts/fetch_and_ocr.py @username \
  --out /tmp/car_username --limit 50
# (Claude reads DIGEST.txt, writes mapping.json) — step 2: honest per-pattern stats
python3 ~/.claude/skills/carousel-account-patterns/scripts/aggregate.py \
  /tmp/car_username/carousels_ocr.json /tmp/car_username/mapping.json
# optional — download the winner's slides
python3 ~/.claude/skills/carousel-account-patterns/scripts/download_slides.py \
  /tmp/car_username/carousels_ocr.json /tmp/car_username/slides
```

```bash
# Hook+Notes carousel — render a whole batch from one config
python3 ~/.claude/skills/hook-notes-carousel/scripts/batch.py --config batch.json
# ...or the two renderers standalone:
python3 ~/.claude/skills/hook-notes-carousel/scripts/render_notes.py \
  --content notes.json --out final/slide_2.png
python3 ~/.claude/skills/hook-notes-carousel/scripts/overlay_hook.py \
  --config slides_config.json --input-dir v1 --output-dir v1/final
```

`HANDLE` accepts `@username`, a full `https://www.tiktok.com/@username` URL, or just `username`.

## How it works

- **ScrapeCreators** is the social parser — it fetches the account's videos with metrics, cover URLs, and descriptions.
- **`quick-stats.ts`** aggregates metrics with a 6h local cache (`~/.cache/tiktok_quick_stats/`) and incremental re-fetch.
- **`analyze-cover-hooks.ts`** downloads each cover, sends it to **Gemini `gemini-3.1-flash-lite`** for OCR of on-screen text, then runs a single Gemini text call to cluster the hooks into patterns and scores each pattern by virality.
- **`fetch_and_ocr.py`** (carousel skill) paginates the profile feed, keeps only photo posts, then downloads + OCRs **every slide** in one thread pool (Gemini Flash Lite, key sent via header; image MIME sniffed — TikTok serves webp/jpeg/heic interchangeably). Outputs `carousels_ocr.json` + a ranked `DIGEST.txt`. Claude does the actual pattern discovery from the digest, `aggregate.py` turns the mapping into an honest stats table (n / peak / avg / total / save%), and `download_slides.py` grabs the winning carousel's slides (HEIC→JPEG on macOS).
- **`hook-notes-carousel`** is pure deterministic Pillow — no AI in the render path. `render_notes.py` draws a pixel-faithful iOS Notes screenshot (status bar, "‹ Notes" nav, date header synced to the status-bar clock, smart quotes, color emoji from the native font, a font ladder that shrinks text to fit and exits non-zero if it can't). `overlay_hook.py` puts the hook on the photo (white bold + dark halo), measures the luminance of the exact band where the text sits and applies a gradient scrim only as strong as needed, auto-wraps and auto-shrinks long titles. `batch.py` drives N carousels from one JSON and prints an OK/FAIL manifest. Claude's job is the part scripts can't do: reading your project, writing hooks by the proven formulas, and visually verifying the output.

## Cost notes

- ScrapeCreators bills per API call (a few calls for short analysis, a bit more pagination for hook analysis; ~5–15 pages for a 50-carousel run).
- Gemini Vision is billed per image OCR: ~100 covers for a default hook run, ~100–150 slides for a 50-carousel run (Flash Lite — fractions of a cent per image).
- `hook-notes-carousel` renders are local and free; the only cost is whatever image generator you use for slide-1 backgrounds (or zero with your own photos).

## Security

No keys are committed — everything reads from `.env` / environment variables (`SCRAPE_CREATORS_API_KEY`, `GOOGLE_API_KEY`). Keep your `.env` private (it's gitignored).

## License

MIT — see [LICENSE](LICENSE).
