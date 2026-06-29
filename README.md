# Viral TikTok Skills for Claude Code

Two self-contained [Claude Code](https://claude.com/claude-code) skills for **fast, cheap TikTok account research**. No database, no heavy setup — just two API keys and `npm install`.

| Skill | What it does | Needs | Speed / cost |
|-------|--------------|-------|--------------|
| **`tiktok-account-short-analysis`** | Fetches all of an account's videos, computes aggregate metrics (total / avg / median views), shows the top 5 with virality & engagement rates, and a short topic read. | ScrapeCreators key | ~30–60s, ~3–8 API calls |
| **`tiktok-account-hook-analysis`** | OCRs the **hook text on each video's cover** (Gemini Vision), clusters them into repeating **hook patterns**, and reports per-pattern analytics (median/avg views, virality). | ScrapeCreators + Google (Gemini) keys | ~3–7 min, image-only (no full video) |

Both are "research" skills: they read public TikTok data and summarize it. Nothing is posted or modified.

---

## Prerequisites

- **Node.js ≥ 18.17**
- **[ScrapeCreators](https://scrapecreators.com) API key** — required for both skills
- **[Google AI Studio](https://aistudio.google.com/apikey) key** — required only for `tiktok-account-hook-analysis` (Gemini Vision)

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
```

The two `SKILL.md` files `cd "$TIKTOK_SKILLS_ROOT"` before running, so the repo's `.env` (your keys) is picked up automatically wherever you invoke the skill from.

## Use it

**Via Claude Code** — just ask in natural language; the trigger phrases in each skill fire automatically:

> "сделай короткий анализ тикток @secretherbsnana"
> "analyze the cover hooks of @username"

**Or run the scripts directly:**

```bash
# Short analysis
npm run short-analysis -- secretherbsnana
npm run short-analysis -- secretherbsnana --since=2026-01-01   # large accounts

# Hook analysis (cover OCR + pattern clustering)
npm run hook-analysis -- secretherbsnana --count 100 --concurrency 10 \
  --out /tmp/hooks.json --out-csv /tmp/hooks.csv
```

`HANDLE` accepts `@username`, a full `https://www.tiktok.com/@username` URL, or just `username`.

## How it works

- **ScrapeCreators** is the social parser — it fetches the account's videos with metrics, cover URLs, and descriptions.
- **`quick-stats.ts`** aggregates metrics with a 6h local cache (`~/.cache/tiktok_quick_stats/`) and incremental re-fetch.
- **`analyze-cover-hooks.ts`** downloads each cover, sends it to **Gemini `gemini-3.1-flash-lite`** for OCR of on-screen text, then runs a single Gemini text call to cluster the hooks into patterns and scores each pattern by virality.

## Cost notes

- ScrapeCreators bills per API call (a few calls for short analysis, a bit more pagination for hook analysis).
- Gemini Vision is billed per cover image OCR (~100 images for a default hook run) plus one clustering call.

## Security

No keys are committed — everything reads from `.env` / environment variables (`SCRAPE_CREATORS_API_KEY`, `GOOGLE_API_KEY`). Keep your `.env` private (it's gitignored).

## License

MIT — see [LICENSE](LICENSE).
