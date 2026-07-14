---
name: hook-notes-carousel
description: Generate batches of 2-slide viral TikTok/Instagram carousels (photo hook + iOS-Notes-screenshot payload) to promote any project or app. Reads project context, asks how many variants, proposes texts & visuals, then renders deterministic slides with bundled Pillow scripts (auto-scrim, auto-fit, real Notes chrome) and verifies them. Trigger phrases - "hook notes carousel", "notes carousel", "2-slide carousel batch", "carousel batch", "батч каруселей", "карусель хук + заметка", "карусели формата 1+1", "сделай батч каруселей", "notes-style carousel".
---

# Hook + Notes Carousel (1+1 format)

Batch-generate the highest-converting minimal carousel format on TikTok/IG:

- **Slide 1 — HOOK**: an authentic lifestyle photo with a raw, lowercase, first-person
  hook. **No product mention.**
- **Slide 2 — PAYLOAD**: what looks like a personal screenshot of the iOS Notes app —
  date header + bold title + 4–5 numbered items. Items 1–3 deliver real value,
  item 4 mentions the product *as a personal habit*, item 5 is a community CTA.

Why it works: the format was reverse-engineered from an account where 46/50 carousels
used exactly this structure (peak 1.95M views, ~1 post/day). The first 3 items give
enough real value that viewers save the post before they ever reach the product; the
product reads as a habit, not an ad, so trust survives. The Notes aesthetic ("a screenshot,
not a design") maximizes credibility.

## Prerequisites

- Python 3.8+ with Pillow (`pip3 install Pillow`)
- Any way to produce 9:16 background photos for slide 1 (pick whatever exists in the
  session): an image-gen skill/CLI (Higgsfield Soul, Nano Banana, GPT Image, Flux, ...),
  stock photos, or photos supplied by the user. Recommended size **1152×2048** (any 9:16 works).
- Fonts: best on macOS (Helvetica Neue + Apple Color Emoji). Falls back to DejaVu/Liberation
  (Linux) and Segoe UI (Windows) automatically. Emoji degrade gracefully if no color-emoji
  font is found.

## CRITICAL: step-by-step approval

**Never run the whole pipeline in one shot.** Stop after each step and get explicit
user approval before the next one:

1. Context summary + variant count → approve
2. Texts & visual plan → approve
3. Generated backgrounds → approve
4. Final slides → review

## Step 0 — Project context

Read the project's own docs first: `CLAUDE.md`, `README.md`, landing page copy, app-store
description — whatever exists. Extract:

- **Product**: what it is, 2–3 concrete features worth name-dropping (for item 4)
- **Audience**: who, where, and **what language they speak** (slides are written in the
  audience's language; conversation stays in the user's language)
- **Pain**: the moment of pain the product solves, in the audience's own words
- **Voice**: how this niche talks (slang, emoji, taboos, tone)
- **Proof**: any real numbers/credentials available (never invent them — see Ethics)

If context is missing, ask the user at most 2–3 targeted questions. Then present a
5-line context summary.

## Step 1 — Ask how many variants

Ask the user how many carousels to produce and (optionally) the strategic mix. Rule of
thumb for a batch of 3: two for **reach** (F1 + F2), one for **saves** (F3). A/B variants
of the same hook with a different photo also count — that's the cheapest test.

## Step 2 — Texts (present ALL before generating anything)

Slide 1 hook formulas (fill-in-the-blank; pick per strategic goal):

| # | Formula | Template | Goal |
|---|---------|----------|------|
| F1 | Time-in-action → numbered lessons | `i've been [doing X] for [period] and these are the [N] things that actually [result] (no. [k] broke me)` | reach |
| F2 | Transformation testimony | `[change] literally changed my life and my [family/work/skin]. here's why u need to start today (no matter how [objection])` | reach |
| F3 | Credential → tiny checklist | `i [credential, e.g. "coached 200+ clients"] for [period] and these [N] tiny things are why [audience result]` | saves |

Slide 2 payload (the meta-formula — copy the skeleton exactly):

```
date header        e.g. "July 8, 2026 at 7:12 AM"  (recent, believable)
bold title         echoes the hook's promise
1. real value      works without the product
2. real value      works without the product
3. real value      the emotional one — pays off the "(no. 3 broke me)" tease
4. product habit   "i open [App] the second [trigger moment]" — NEVER "download [App]"
5. community CTA   "save this for [their hard moment]" / "send this to a [person] who needs it"
```

Text rules:

- lowercase, first person, testimony voice; contractions; mild slang of the niche
- hook must be legible in 0.5s: front-load the first 5 words
- one emotional beat per carousel; a `(no. K broke me)` tease on slide 1 must pay off in item K
- if hook promises N things, slide 2 has exactly N numbered items (+ optional CTA line)
- write in the **audience's language**

**Ethics (non-negotiable):** never fabricate credentials, employee "insiders", or fake
statistics. Use only credentials/data the user actually has. This is both trust-preserving
and what differentiates the account long-term.

Present per variant: hook (exact lines), full slide-2 content, visual description, and a
caption (hashtags for the niche). **STOP for approval.**

## Step 3 — Backgrounds (slide 1)

One 9:16 photo per variant. Prompt skeleton that works:

```
Candid 35mm film photograph of [subject matching the hook's narrator],
[emotional state], [location tied to the pain moment].
[Audience-matching age/appearance]. Warm muted tones, cinematic color grade,
visible film grain, shallow depth of field, authentic unposed documentary
moment, natural skin texture. Generous empty negative space in the upper
third for text. Vertical composition. No text, no watermark, no logo.
```

- The subject = the person *speaking* the hook (the narrator), not an illustration of chaos.
- Keep the upper ~third clean for the hook; the overlay script auto-darkens bright tops,
  but composition beats correction.
- Generate **sequentially or via background jobs** — a long parallel foreground batch is
  easy to kill accidentally (see Troubleshooting for crash recovery).
- Show every background to the user (Read tool). **STOP for approval.**

Output convention (same as other carousel skills):

```
generated_carousel/{name}/v1/slide_1_bg.png     # background
generated_carousel/{name}/v1/notes.json          # slide 2 content
generated_carousel/{name}/v1/slides_config.json  # hook overlay config
generated_carousel/{name}/v1/final/slide_1.png   # final slides
generated_carousel/{name}/v1/final/slide_2.png
```

## Step 4 — Render

**Batch (3+ carousels): one config, one command.** Write `batch.json`:

```json
{
  "output_root": "generated_carousel",
  "version": "v1",
  "size": [1152, 2048],
  "carousels": [
    {
      "name": "pause",
      "hook": {
        "title_lines": ["learning to pause before", "i react changed my life"],
        "body_text": "here's why to start today — no matter how many times you've failed",
        "text_y_start_pct": 0.05,
        "scrim": "auto"
      },
      "notes": {
        "date": "July 8, 2026 at 7:12 AM",
        "title": "why the pause changed everything",
        "items": ["...", "...", "...", "i open [App] the second ..."],
        "cta": "send this to a mom who needs it",
        "cta_emoji": "🤍"
      }
    },
    {
      "name": "second-hook",
      "hook": { "title": "one long hook string to auto-wrap", "title_emoji": "👀" },
      "notes": { "date": "July 10, 2026 at 9:47 PM", "title": "...", "items": ["...", "..."] }
    }
  ]
}
```

```bash
python3 ~/.claude/skills/hook-notes-carousel/scripts/batch.py --config batch.json
```

Each carousel needs `generated_carousel/{name}/v1/slide_1_bg.png` to exist (or pass
`"background": "path.png"`).

**Single carousel:** call the two renderers directly:

```bash
python3 .../scripts/overlay_hook.py --config slides_config.json --input-dir v1 --output-dir v1/final
python3 .../scripts/render_notes.py --content notes.json --out v1/final/slide_2.png
```

### Hook config (`overlay_hook.py`)

| Field | Description | Default |
|---|---|---|
| `filename` / `out_name` | input bg / output name | required / `slide_1.png` |
| `title_lines` OR `title` | manual lines, or one string to auto-wrap (auto-shrinks if >4 lines) | required |
| `body_text` | smaller second block | none |
| `title_emoji` | emoji appended to last title line | none |
| `text_y_start_pct` | top offset (0–1) | 0.05 |
| `title_size` / `body_size` | px | 56 / 40 |
| `outline_width` | dark halo width | 3 |
| `scrim` | `"auto"` (luminance-based), `"none"`, or 0–255 | `"auto"` |
| `scrim_height_pct` | gradient depth | 0.45 |

### Notes content (`render_notes.py`)

| Field | Description | Default |
|---|---|---|
| `date` | header, e.g. `"July 8, 2026 at 7:12 AM"` | required |
| `clock` | status-bar time | derived from `date` |
| `title` / `items` / `cta` / `cta_emoji` | note body | title+items required |
| `theme` | `"light"` or `"dark"` | light |
| `smart_quotes` | `'`→`’`, `"`→`“ ”` (iOS realism) | true |

Auto-behaviors: font ladder shrinks text to fit (exit code 2 if it can't), clock syncs
to the date header, emoji rendered from the native color font.

## Step 5 — Verify & present

1. Check script exit codes (batch.py prints a manifest; nonzero = something failed).
2. **Read every final slide** and check: hook legible on a phone; scrim not crushing the
   photo; emoji actually rendered; clock == date time; item count == hook's promise;
   nothing important covered by text; slide 1 has no product mention.
3. Present a summary table (variant, formula, hook, files) + captions. Offer next
   iterations: A/B first photos for the winner, more variants of the winning formula.

## Troubleshooting

- **`OSError: invalid pixel size` on emoji** — Apple Color Emoji only exposes fixed
  strikes (96/160 px). The bundled scripts probe valid sizes automatically; don't render
  the emoji font at arbitrary sizes in custom code.
- **Parallel generation crashed / exit 137** — image jobs usually completed server-side.
  Re-list the provider's recent jobs (e.g. `higgsfield generate list --json`) and download
  the result URLs instead of re-paying for generation. Prefer sequential foreground runs
  or proper background jobs.
- **White text unreadable on a bright photo** — keep `"scrim": "auto"`; force a number
  (150–200) only if auto guesses wrong.
- **Orphan word on the payoff line** — shorten `body_text` or drop `body_size` a step so
  the parenthetical tease fits one line.
- **Linux/Windows fonts** — DejaVu/Liberation/Segoe are picked up automatically; override
  with env vars `HNC_FONT_REGULAR` / `HNC_FONT_BOLD` / `HNC_FONT_MEDIUM` / `HNC_FONT_EMOJI`.
- **Notes text overflows** (exit 2) — cut item wording; 4 items ≈ 60 words total is the
  sweet spot.

## Platform notes

- TikTok photo mode & IG carousels both accept 9:16; TikTok shows slide 1 as the cover.
- Caption: hashtags only (niche discovery) or a short script-recruiting line.
- Repost winners: same hook + new first photo is a legitimate strategy — virality is a
  lottery, the formula is the constant.
