---
name: tiktok-account-hook-analysis
description: >
  Cover/thumbnail hook analysis for a TikTok OR Instagram account. Fetches last N
  videos (default 50), downloads covers, then CLAUDE reads the cover images natively
  (both text and visual composition), clusters hook patterns across two axes
  (text formula × visual format), and computes honest per-pattern analytics via a
  deterministic python script. Optional FAST mode: a cheap vision model (Gemini,
  auto-fallback Grok) extracts per-cover cards instead of native reading — but
  clustering is ALWAYS done by Claude, never by the cheap model.
  Trigger phrases: "hook analysis tiktok", "tiktok hook analysis", "tiktok cover analysis",
  "analyze tiktok hooks", "анализ хуков тикток", "анализ обложек тикток",
  "tiktok cover hooks", "хук анализ тикток", "анализ текста обложек",
  "instagram hook analysis", "анализ хуков инстаграм", "анализ обложек инстаграм",
  "reels hook analysis", "анализ обложек рилсов", "cover hook analysis"
---

# Account Cover Hook Analysis (TikTok + Instagram)

## When to use

User gives a TikTok or Instagram handle/URL and wants to know which cover/thumbnail
hook formulas the account uses and which perform best. Covers only (fast, cheap) —
not full video analysis.

**Why Claude reads the covers itself (default):** a cover hook = text × visual.
OCR-only pipelines lose covers whose hook is visual (memes, reacts, design series,
embedded screenshots) — verified experimentally: on a 50-reel test, text-only
clustering dumped 22% of covers into a "no hook" bucket and misread embedded
screenshots; native reading assigned 100% and found format-level patterns
(design series, no-face covers, react formats) invisible to OCR.

## Prerequisites

- `SCRAPE_CREATORS_API_KEY` — shell env / `~/.zshenv` / `~/.zshrc` / repo `.env`
  (via `TIKTOK_SKILLS_ROOT`) / `./.env`
- Bundled scripts: `scripts/fetch_covers.py`, `scripts/pattern_stats.py`, `scripts/ocr_covers.py`
- FAST mode only: `GOOGLE_API_KEY` (Gemini) or `XAI_API_KEY` (Grok auto-fallback if Gemini
  is unavailable, e.g. geo-blocked)

## Mode selection

| Mode | When | Who reads covers | Who clusters |
|------|------|-----------------|--------------|
| **NATIVE** (default) | ≤ 80 covers | Claude (Read tool) | Claude |
| **FAST** | user says «быстро/дёшево/fast», or count > 120 | cheap vision model → cards | Claude |
| 80–120 covers | prefer NATIVE via subagent fan-out (see Scaling) | subagents | Claude |

Never let the cheap model do pattern discovery — that was the main quality flaw
of the old pipeline.

## Workflow

### Step 1 — Parse input

- Platform: `instagram.com/...` or «инста/рилсы/reels» → `instagram`; otherwise `tiktok`.
- Handle: strip `@`, URL parts.
- Count: user's number, else **50**.
- Work dir: `WORK_DIR=<scratchpad>/hook-analysis/<handle>`

### Step 2 — Fetch metadata + covers

```bash
python3 ~/.claude/skills/tiktok-account-hook-analysis/scripts/fetch_covers.py HANDLE \
  --platform tiktok|instagram --count N --out-dir "$WORK_DIR"
```

Writes `meta.json` (per-video metrics, index-aligned) and `covers/NN_ID.jpg`
(HEIC auto-converted). Prints `index | views | date | id` digest.

### Step 3 — Per-cover cards

**NATIVE:** Read cover images with the Read tool, ~10 per message, all batches.
While reading, build a mental card per cover:

- `hook_text` — verbatim, original language, **preserve typos** (a repeated typo
  reveals a reused template), casing, emoji;
- `visual_format` — talking_head / face_plus_screenshot / designed_promo /
  meme_reaction / pov_lifestyle / ui_screen_only / diagram_scheme / comparison_grid;
- `embedded_context` — if the cover contains someone else's content (tweet, article,
  app UI, viral video, celebrity photo): what and whose. **Text inside an embedded
  screenshot is NOT the hook** — it's context/proof;
- `has_creator_face` — face vs no-face covers often split performance;
- series markers — recurring design template, recurring corner cues
  (e.g. "Hold for 2x speed"), recurring characters.

**FAST:**

```bash
python3 ~/.claude/skills/tiktok-account-hook-analysis/scripts/ocr_covers.py \
  "$WORK_DIR/meta.json" --out "$WORK_DIR/cards.json" --provider auto
```

Then read `cards.json`; manually Read every cover with `ocr_failed: true`, empty
`hook_text`, or a card that looks inconsistent. Known FAST limitations: cheap models
silently fix typos and sometimes mislabel visual_format — treat cards as raw material,
not truth.

### Step 4 — Cluster patterns (Claude, always)

Cluster across **two axes: text formula × visual format**. A pattern is a repeating
combination worth replicating (e.g. «CAPS "[VERB] X WITH [TOOL]" on a branded dark
design» or «accusation hook over embedded tweet-proof»). Rules:

- Pattern needs **3+ videos**; 1–2 similar covers → `unassigned` (mention in insights
  only if the signal is interesting).
- Every index appears **exactly once** across `patterns[].indexes` + `unassigned`.
- Formulas with [PLACEHOLDERS]; keep hook examples verbatim.

Write `clusters.json`:

```json
{
  "patterns": [
    {"patternName": "…", "formula": "… [X] …", "visualFormat": "…", "indexes": [0, 7]}
  ],
  "unassigned": [3]
}
```

### Step 5 — Deterministic stats

```bash
python3 ~/.claude/skills/tiktok-account-hook-analysis/scripts/pattern_stats.py \
  "$WORK_DIR/meta.json" "$WORK_DIR/clusters.json" --out "$WORK_DIR/report.json"
```

Validation is strict: on missing/duplicate indexes it exits 1 listing them — fix
`clusters.json` and rerun. Never present stats computed by hand/LLM.

### Step 6 — Report (language: user's, hooks verbatim in original)

1. **Overview**: videos analyzed, account median views, covers with/without text,
   count of no-face covers.
2. **Patterns** sorted by virality, header per pattern:
   `### 🔥 Name — 4.0x · 7 videos` (🏆 >5x / 🔥 >3x / ⚡ >1.5x / ⚠️ <1x / 📉 <0.5x).
   For each: formula, visual format, stats row (median/avg views, virality, median
   likes/saves, engagement), top-3 videos with links + verbatim hooks, flags from
   report.json (`outlierWarning` → «⚠️ среднее раздуто одним виралом»,
   `belowMinimum` → not a real pattern).
3. **Visual-layer insights** (native mode's edge): face vs no-face performance,
   design series and their consistency, embedded-proof usage, what the top-1 video's
   cover does differently.
4. **Key insights**: what works >3x and why, what underperforms <1x, repost
   degradation, serial formats, saves as quality signal, 3–5 concrete cover
   recommendations for the user's own content.
5. If `unassigned` is large, report it honestly with % — «у аккаунта нет формулы» is
   itself a finding.

## Scaling (>80 covers)

Fan out `general-purpose` subagents, ~40 covers each: each Reads its covers and
returns structured cards (index, hook_text, visual_format, embedded_context,
has_creator_face, series markers). Main context merges cards → Step 4. Clustering
never happens inside a subagent (needs the full picture).

## Cost & runtime

| | NATIVE 50 | FAST 120 |
|---|---|---|
| time | ~5 min | ~2–4 min |
| cost | ~70–80k tokens of context | pennies (API) + light context |
| quality | full visual layer | text + rough format labels |

## Notes

- The old pipeline (`src/scripts/analyze-cover-hooks.ts` in this repo, Gemini OCR →
  Gemini clustering) is legacy: cheap-model clustering silently
  dropped unassigned videos (28% loss on test) and discarded all visual signal.
- If Gemini returns «User location is not supported» (VPN exit in an unsupported
  region), `ocr_covers.py --provider auto` falls back to Grok automatically.
