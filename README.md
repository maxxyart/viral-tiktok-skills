# Viral TikTok Skills for Claude Code

Five self-contained skills for **TikTok and Instagram research and content**. Use them to study accounts, mine cover and carousel patterns, analyze audience comments, and create ready-to-post carousels. No database required. The new Viral Camp comment-analysis skill works in both [Claude Code](https://claude.com/claude-code) and Codex.

| Skill | What it does | Needs | Speed / cost |
|-------|--------------|-------|--------------|
| **[`social-post-comment-analysis`](skills/social-post-comment-analysis/)** (Viral Camp) | Bounded TikTok/Instagram comment collection, safe CSV, semantic audience themes, separate root/reply statistics and product/campaign experiments. Reuses saved data and stops on request. | Python 3.9+ standard library; ScrapeCreators key for collection | Default: target 300 roots, ≤20 API attempts, ≤120s collection; offline analysis has no API cost |
| **`tiktok-account-short-analysis`** | Fetches all of an account's videos, computes aggregate metrics (total / avg / median views), shows the top 5 with virality & engagement rates, and a short topic read. | ScrapeCreators key | ~30–60s, ~3–8 API calls |
| **`tiktok-account-hook-analysis`** (v2) | **Claude reads each video's cover natively** — text AND visual composition — and clusters repeating **hook patterns** across two axes (text formula × visual format), with honest per-pattern analytics and zero silently-dropped videos. Works on **TikTok and Instagram**. Optional FAST mode uses a cheap vision model for the per-cover pass. | ScrapeCreators key (Gemini/xAI key only for FAST mode) | ~5 min native · ~2–4 min FAST |
| **`carousel-account-patterns`** | Fetches the last N **carousels (photo posts)**, OCRs **every slide**, Claude maps the repeating patterns, then a script computes honest per-pattern stats (peak / avg / save-rate) with top-reference links, and Claude **natively reads the top-reference slides** to ground the visual layer → a formula-mining report with fill-in-the-blank hooks adapted for **your** product. | ScrapeCreators + Gemini key (auto-fallback to xAI/Grok) | ~1–2 min for N=50, Python stdlib only |
| **`hook-notes-carousel`** | **Generates** batches of the highest-converting minimal carousel format: slide 1 = lifestyle photo with a raw lowercase hook, slide 2 = a pixel-faithful **iOS Notes screenshot** (real value in items 1–3, your product *as a personal habit* in item 4, community CTA in item 5). Reads your project context, proposes texts by 3 proven hook formulas, renders deterministic slides, verifies them. | Pillow + any image generator (or your own photos) for backgrounds | slide render <1s, local & free; backgrounds = your generator's price |

The research skills read public social data and write local analysis files. They do not post comments or message users. `hook-notes-carousel` writes PNG slides into your project folder; publishing is still up to you.

> **The loop:** mine an account's winning formulas with `carousel-account-patterns` → hand the report to `hook-notes-carousel` → get a batch of on-formula carousels for your product.

> **Built with the carousel skill:** [boont.ai/carousels](https://boont.ai/carousels/) — a searchable library of 15 app cases × 26 accounts × ~1000 OCR'd carousels, with an [agent entrypoint](https://boont.ai/carousels/AGENT.md) for "pick a reference and adapt it to my product".

---

## Prerequisites

- **Node.js ≥ 18.17** — for `tiktok-account-short-analysis` only
- **Python 3.9+** — stdlib only for comment analysis, `tiktok-account-hook-analysis` and `carousel-account-patterns`; `pip3 install Pillow` for `hook-notes-carousel`
- **[ScrapeCreators](https://scrapecreators.com) API key** — required for live research collection; offline comment export/analysis needs no key
- **[Google AI Studio](https://aistudio.google.com/apikey) key** — for `carousel-account-patterns` slide OCR and hook-analysis FAST mode. Optional **[xAI key](https://console.x.ai)** — automatic Grok fallback when Gemini is unavailable (e.g. geo-blocked). Default hook-analysis mode needs **no vision key at all** — Claude reads the covers itself
- **Any image source for `hook-notes-carousel` slide-1 backgrounds** — an image-gen skill/CLI (Higgsfield, Midjourney, GPT Image, Flux…), stock, or your own photos; the skill is generator-agnostic and needs no API key itself
- macOS `sips` (built-in) — optional, used by `carousel-account-patterns` to convert HEIC slides TikTok sometimes serves. `hook-notes-carousel` renders best with macOS fonts (Helvetica Neue + Apple Color Emoji) and falls back to DejaVu/Liberation/Segoe on Linux/Windows

No database is required.

## Install

```bash
# 1. Clone
git clone https://github.com/maxxyart/viral-tiktok-skills.git
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
cp -R skills/social-post-comment-analysis ~/.claude/skills/
```

For Codex, copy `skills/social-post-comment-analysis` into `~/.codex/skills/` instead.
The comment skill is self-contained and does not need npm dependencies or
`TIKTOK_SKILLS_ROOT`. Set `SCRAPE_CREATORS_API_KEY` in the environment, or pass an
explicit `--env-file`. `SCRAPECREATORS_API_KEY` is also supported.

The Node short-analysis entrypoint uses `TIKTOK_SKILLS_ROOT` to locate the repo and its `.env`.

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
> "проанализируй комментарии этого рилса через ScrapeCreators, сохрани CSV и предложи тесты для моего продукта"

### Social post comment analysis (Viral Camp)

```bash
# Either a canonical TikTok video/photo URL or Instagram reel/post URL:
python3 skills/social-post-comment-analysis/scripts/comments.py fetch 'POST_URL' \
  --out /tmp/post-comments --limit 300 --max-calls 20 --max-seconds 120

# Rebuild from the saved cache without making network calls:
python3 skills/social-post-comment-analysis/scripts/comments.py export --out /tmp/post-comments

# The agent reads reading.jsonl and writes semantic labels.json using SKILL.md:
python3 skills/social-post-comment-analysis/scripts/comments.py analyze \
  --out /tmp/post-comments --labels /tmp/post-comments/labels.json

# Offline regression tests (synthetic data only):
python3 -m unittest discover -s skills/social-post-comment-analysis/tests -v
```

Collection saves raw pages, a timestamped request manifest, lossless `records.json`,
`reading.jsonl`, and Excel-safe `comments.csv`. Analysis validates every assigned ID
and writes `analysis.json`; the agent writes the evidence-backed `report.md`.
The final response page is preserved, so the row target may be exceeded by one page.
Replies are opt-in per parent (`--reply-id`); Instagram's bulk replies option is
deliberately unused because its documented per-page cost is substantially higher.
API attempt limits are not a guaranteed credit price; the manifest tracks returned
charges and unknown-charge attempts. See the [skill instructions](skills/social-post-comment-analysis/SKILL.md)
and [platform contracts](skills/social-post-comment-analysis/references/platforms.md).

Unlike account-growth metrics, comment themes describe a nonrandom audience sample.
The report keeps top-level comments, replies, creators and unreviewed rows explicit;
likes are amplification, not a count of buyers.

**Or run the scripts directly:**

```bash
# Short analysis
npm run short-analysis -- secretherbsnana
npm run short-analysis -- secretherbsnana --since=2026-01-01   # large accounts

# Hook analysis v2 — step 1: fetch metadata + covers (TikTok or Instagram)
python3 ~/.claude/skills/tiktok-account-hook-analysis/scripts/fetch_covers.py username \
  --platform tiktok --count 50 --out-dir /tmp/hooks_username
# (Claude reads the covers natively and writes clusters.json) — step 2: honest stats
python3 ~/.claude/skills/tiktok-account-hook-analysis/scripts/pattern_stats.py \
  /tmp/hooks_username/meta.json /tmp/hooks_username/clusters.json
# FAST mode (large accounts): per-cover cards from a cheap vision model instead
python3 ~/.claude/skills/tiktok-account-hook-analysis/scripts/ocr_covers.py \
  /tmp/hooks_username/meta.json --out /tmp/hooks_username/cards.json --provider auto
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

- **Comment analysis** uses a bounded, interruptible ScrapeCreators REST collector for both platforms. The agent reads comments in context and supplies semantic labels; Python validates label coverage and computes topic frequencies. Reversible CSV escaping and namespaced IDs protect text and long identifiers. No fixed keyword taxonomy or external LLM API is used.
- **ScrapeCreators** is the social parser — it fetches the account's videos with metrics, cover URLs, and descriptions.
- **`quick-stats.ts`** aggregates metrics with a 6h local cache (`~/.cache/tiktok_quick_stats/`) and incremental re-fetch.
- **Hook analysis v2** is three self-contained Python scripts: `fetch_covers.py` pulls the last N videos of a TikTok **or Instagram** account and downloads every cover (HEIC→JPEG); **Claude then reads the covers natively** — verbatim text (typos preserved: a repeated typo reveals a reused template), visual format, embedded screenshots — and clusters the patterns itself; `pattern_stats.py` computes per-pattern analytics deterministically and **refuses to run if any video is missing or double-assigned** (the old pipeline silently dropped up to ~28% of videos). `ocr_covers.py` is the optional FAST path — a cheap vision model (Gemini, auto-fallback Grok) builds per-cover cards, but pattern discovery still belongs to Claude. The legacy TS pipeline (`analyze-cover-hooks.ts`) stays in `src/` for reference.
- **`fetch_and_ocr.py`** (carousel skill) paginates the profile feed, keeps only photo posts, then downloads + OCRs **every slide** in one thread pool (Gemini Flash Lite with automatic Grok fallback when Gemini is unavailable; key sent via header; image MIME sniffed — TikTok serves webp/jpeg/heic interchangeably). Outputs `carousels_ocr.json` + a ranked `DIGEST.txt`. Claude does the actual pattern discovery from the digest, `aggregate.py` turns the mapping into an honest stats table (n / peak / avg / total / save%) and warns about typo'd or unlabeled ids, and `download_slides.py` grabs the winning carousel's slides (HEIC→JPEG on macOS).
- **`hook-notes-carousel`** is pure deterministic Pillow — no AI in the render path. `render_notes.py` draws a pixel-faithful iOS Notes screenshot (status bar, "‹ Notes" nav, date header synced to the status-bar clock, smart quotes, color emoji from the native font, a font ladder that shrinks text to fit and exits non-zero if it can't). `overlay_hook.py` puts the hook on the photo (white bold + dark halo), measures the luminance of the exact band where the text sits and applies a gradient scrim only as strong as needed, auto-wraps and auto-shrinks long titles. `batch.py` drives N carousels from one JSON and prints an OK/FAIL manifest. Claude's job is the part scripts can't do: reading your project, writing hooks by the proven formulas, and visually verifying the output.

## Cost notes

- ScrapeCreators bills per API call (a few calls for short analysis, a bit more pagination for hook analysis; ~5–15 pages for a 50-carousel run).
- Native hook-analysis mode spends Claude context (~70–80k tokens per 50 covers) and zero vision-API dollars. FAST mode / carousel OCR bill per image: ~100–150 cheap-model calls per run (fractions of a cent each).
- `hook-notes-carousel` renders are local and free; the only cost is whatever image generator you use for slide-1 backgrounds (or zero with your own photos).

## Security

No keys are committed — everything reads from `.env` / environment variables (`SCRAPE_CREATORS_API_KEY`, `GOOGLE_API_KEY`, optional `XAI_API_KEY`). Keep your `.env` private (it's gitignored).

## License

MIT — see [LICENSE](LICENSE).
