---
name: social-account-hook-analysis
description: >
  Cover hook analysis for a TikTok or Instagram account (reels, or carousels + photos).
  Fetches the whole account when it has ≤150 posts (else the latest 50, or --all /
  --since) plus slides and top comments of the best carousels; covers are read natively
  (Claude or parallel Sonnet subagents), Claude clusters hooks as text formula × visual
  format and labels themes + product fit, Python computes the stats (young posts kept out
  of medians, small groups flagged) and renders an HTML / Artifact report: virals slide by
  slide, product adaptations, sortable all-posts grid, checked in headless Chrome. Exports
  a CSV. FAST mode: a cheap vision model drafts cards, Claude always clusters. Triggers:
  "hook analysis tiktok", "tiktok cover analysis", "analyze tiktok hooks",
  "instagram hook analysis", "reels hook analysis", "cover hook analysis",
  "анализ хуков тикток", "анализ обложек тикток", "хук анализ тикток",
  "анализ текста обложек", "анализ хуков инстаграм", "анализ обложек инстаграм",
  "анализ обложек рилсов"
---

# Account Cover Hook Analysis (TikTok + Instagram)

## When to use

User gives a TikTok or Instagram handle/URL and wants to know which cover/thumbnail
hook formulas the account uses and which perform best. Covers only (fast, cheap) —
not full video analysis. For TikTok carousels the slides of the top posts are pulled
too, because the hook of a hit often lives in the slide sequence, not only the cover.

**Why covers are read by a vision model, not OCR:** a cover hook = text × visual.
OCR-only pipelines lose covers whose hook is visual (memes, reacts, design series,
embedded screenshots) — verified experimentally: on a 50-reel test, text-only
clustering dumped 22% of covers into a "no hook" bucket and misread embedded
screenshots; native reading assigned 100% and found format-level patterns
(design series, no-face covers, react formats) invisible to OCR.

## Prerequisites

- `SCRAPE_CREATORS_API_KEY` — env / `~/.zshenv` / `~/.zshrc` / `./.env`
- Bundled scripts (`scripts/`): `fetch_covers.py`, `fetch_slides.py`, `pattern_stats.py`,
  `render_report.py`, `snapshot_report.py`, `export_csv.py`, `ocr_covers.py`
- Pillow for `render_report.py` image compression (falls back to sips, much bigger files)
- `ffmpeg` for frame 0 of video posts (without it videos fall back to the grid thumbnail)
- Google Chrome (or Chromium / Brave, or `CHROME=/path`) for `snapshot_report.py`
- FAST mode only: `GOOGLE_API_KEY` (Gemini) or `XAI_API_KEY` (Grok auto-fallback if Gemini
  is unavailable, e.g. geo-blocked)

## Mode selection (who writes cards.json)

| Mode | When | Who reads covers | Who clusters |
|------|------|-----------------|--------------|
| **FAN-OUT** (default) | 30–120 covers | 2–4 parallel subagents, `model: "sonnet"`, ~25 covers each | Claude |
| **NATIVE** | < 30 covers, or user wants the deepest read | Claude itself (Read tool) | Claude |
| **FAST** | user says «быстро/дёшево/fast», or count > 120 | cheap vision model → cards | Claude |

Never let the cheap model or a subagent do pattern discovery — clustering needs the
full picture in one context.

## Workflow

### Step 1 — Parse input

- Platform: `instagram.com/...` or «инста/рилсы/reels» → `instagram`; otherwise `tiktok`.
  Instagram source: «карусели / посты / фото» or an account that mostly posts carousels →
  `--ig-source posts`; «рилсы» or default → `reels`.
- Handle: strip `@`, URL parts.
- Sample: pass nothing and the script decides (the whole account when the profile has
  ≤150 posts, else the latest 50). User's number → `--count N`; «за полгода / с мая» →
  `--since YYYY-MM-DD`; «весь аккаунт» → `--all`. The old fixed 50 would have dropped 8 of
  the 13 hits of @evividm (87 posts, 2026-11-03), 52% of the hits' views, among them the
  329K and 250K carousels: they sat in the older 37 posts.
- Product: the product block of the report needs the user's product. Take it from the
  project's CLAUDE.md / research files; if there is none and the user wants adaptations,
  ask one question («под какой продукт адаптировать?») before Step 6, not at the start.
- Work dir: `WORK_DIR=<scratchpad>/hook-analysis/<handle>`

### Step 2 — Fetch metadata, covers, top carousels (one call, ~65 s for 87)

```bash
python3 ~/.claude/skills/social-account-hook-analysis/scripts/fetch_covers.py HANDLE \
  --platform tiktok|instagram --out-dir "$WORK_DIR" --slides-top 6 \
  [--count N | --all | --since YYYY-MM-DD] [--ig-source reels|posts] [--auto-max 150]
```

- `meta.json`: `profile` (followers, totalPosts, likes, bio), `metric` (`views`, or `likes`
  for Instagram posts), `sample` {mode all|latest|since, since, fetched, accountTotal,
  skippedPinned, autoMax} + index-aligned videos with views/likes/comments/shares/saves,
  date, `slides` (0 = video), `isCarousel`, `kind` (video / carousel / reel / photo),
  `isPinned`, `music`, `link` (`/photo/` for carousels, `/video/` otherwise), `coverFile`.
- `--since`: pinned posts (up to 3, at the top of the feed whatever their date) are skipped
  when older than the cutoff, and paging stops at the first old post after them.
- `--ig-source posts` (`/v2/instagram/user/posts`): carousels, photos and reels in one feed,
  carousel slide URLs for `--slides-top`, comments via `/v2/instagram/post/comments`.
  Instagram shows no views for carousels and photos and no saves/shares at all, so the run
  switches `metric` to likes: medians, × median, hits and the renderer all count likes.
- `covers/NN_ID.jpg` (HEIC auto-converted), `slide_urls.json`.
- **Videos and reels: `covers/` holds frame 0 of the video, not the platform thumbnail.**
  The thumbnail (`image_versions2` on Instagram, `origin_cover` on TikTok) is whatever frame
  or uploaded image the creator picked for the profile grid; the feed starts the video at
  frame 0, so that is the hook viewers see. On @alfredoromero.ai (2026-11-03) reel #14 had a
  mid-video dashboard as thumbnail while frame 0 carried «Unethical ways to get clients for
  your AI Agency (part 2)», and the «DAY N» challenge reels had designed covers nobody sees
  in the feed. The thumbnail stays in `thumbs/` (`thumbFile`); `coverSource` per video says
  `first_frame`, `frame_0.5s` (frame 0 was a flat fade-in, grayscale stddev < 12, so 0.5 s was
  grabbed instead) or `thumbnail` (ffmpeg failed), and stdout prints a `FIRST FRAMES: x/y` line.
  Carousels are unaffected: their cover is slide 1. Reading thumbnails distorts the stats, not
  only the hooks: on that account the dashboard thumbnail put #14 (11×) into the income-proof
  pattern and showed it at 6.3×; on frame 0 the same pattern is 1.4× and #14 belongs elsewhere.
  If a cover looks off against the post, Read `thumbs/` and `covers/` side by side.
- `--slides-top 6` (TikTok): `carousels/NN/slideK.jpg` + `carousels/NN/post.json` with the
  top-20 text comments for the 6 most viewed carousels. Add more later without re-fetching
  the feed: `fetch_slides.py "$WORK_DIR" --indexes 37,48`.
- Stdout opens with a `SAMPLE:` line (after `FIRST FRAMES:` when there are videos): mode,
  fetched of account total and its share, kinds (carousels / videos / photos), metric. In
  `latest` mode it warns that older posts, possible hits included, are outside the sample.
  One digest line per post follows. **Always report whether the sample is complete** and
  what share of the account it covers; the renderer prints the same note under the hero.
  5 retries with exponential backoff are built in; a page that still fails aborts loudly.

### Step 3 — cards.json (always written, both modes)

Card schema, index-aligned array (same as `ocr_covers.py`, plus background/has_person/series):

```json
{"index": 0, "hook_text": "verbatim", "has_text": true, "visual_format": "photo_text_overlay",
 "background": "religious_place", "has_creator_face": false, "has_person": false,
 "embedded_context": "", "series": ""}
```

- `hook_text` — verbatim, original language, **preserve typos** (a repeated typo reveals a
  reused template), casing, emoji; distinct text blocks joined with ` / `. Text inside an
  embedded screenshot is NOT the hook — it goes to `embedded_context`. Burned-in
  auto-subtitles (word-by-word speech captions, 1–3 words, often lowercase, mid or low in the
  frame) are NOT the hook either: leave them out. Put this rule in every subagent prompt –
  without it Sonnet wrote subtitle words into 28 of 50 reel hooks («makes», «callers»).
- `visual_format` — talking_head / face_plus_screenshot / designed_promo / meme_reaction /
  pov_lifestyle / ui_screen_only / diagram_scheme / comparison_grid / photo_text_overlay.
- `background` — person_selfie / person_other / religious_place / landscape_nature /
  object_still / designed_graphic / screenshot / other.
- `has_creator_face` — face clearly visible (> half); `has_person` — any person/body part.
- `series` — recurring template name, else "".

**FAN-OUT:** launch the subagents in ONE message (`subagent_type: "general-purpose"`,
`model: "sonnet"`), each with an index range, the covers folder, the schema and field rules
above, and an output path `$WORK_DIR/cards-part-K.json`; each replies with one line only
(count + unreadable covers), never the cards. While they run, Read the slides in
`carousels/NN/` of the hits (≥5× median, up to 4) yourself — that is where formulas come
from — and write what you read to `carousels/NN/slides.json`, verbatim, typos kept:

```json
[{"slide": 1, "text": "easy ways to\nunrot your brain\nto feel more present and productive",
  "visual": "girl in a flower crown from behind in a lupin field, no face"}]
```

Without this file the slide texts lived only in the conversation and were lost for the
next post, the CSV and the next run. The renderer uses them as img alt only (nothing is
printed under a viral); export_csv.py puts them in the `slide_texts` column. Then merge:

```bash
python3 -c "import json,glob,sys; c=sorted((x for f in sorted(glob.glob(sys.argv[1]+'/cards-part-*.json')) for x in json.load(open(f))), key=lambda x:x['index']); json.dump(c, open(sys.argv[1]+'/cards.json','w'), ensure_ascii=False, indent=1); print(len(c), 'cards')" "$WORK_DIR"
```

Check the count equals N. Before clustering, Read the covers of the top-10 by views and of
any card that looks off — you need to see the hits, not only their cards. Sonnet
occasionally "fixes" an author typo despite the rule (1 of 10 typos on the test run), so
compare the hooks of the covers you Read with their cards.

**NATIVE:** Read cover images with the Read tool, ~10 per message, all batches, and write
cards.json with the Write tool.

**FAST:**

```bash
python3 ~/.claude/skills/social-account-hook-analysis/scripts/ocr_covers.py \
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

### Step 4b — labels.json: theme and product fit (Claude)

Patterns group covers by hook form; the user also asks «какие темы заходят» and «что из
этого взять для продукта». Label every index with a topic and its fit to the user's product,
in the same pass as clustering (you already know every cover):

```json
{"names": {"theme": {"brainrot": "Brain rot, внимание, телефон", "recs": "Подборки"},
           "product_fit": {"direct": "Прямо в тему продукта", "adjacent": "Рядом", "off": "Мимо"}},
 "labels": [{"index": 0, "theme": "learning", "product_fit": "adjacent"}]}
```

- 4–8 themes, short keys, display names in `names` (the renderer and the CSV use them).
- `product_fit`: `direct` = the post's topic is the problem the product solves, `adjacent` =
  same audience, other topic, `off` = unrelated. Without a known product skip `product_fit`.
- On @evividm the theme split answered the question patterns could not: brainrot posts had
  a median of 9 470 (2.6×) and 5 of 13 hits; `direct` posts 7 579 against 2 685 `adjacent`.

### Step 5 — Deterministic stats

```bash
python3 ~/.claude/skills/social-account-hook-analysis/scripts/pattern_stats.py \
  "$WORK_DIR/meta.json" "$WORK_DIR/clusters.json" --cards "$WORK_DIR/cards.json" \
  --labels "$WORK_DIR/labels.json" --out "$WORK_DIR/report.json" \
  [--since YYYY-MM-DD] [--min-age-days 7]
```

Validation is strict: on missing/duplicate indexes it exits 1 listing them — fix
`clusters.json` and rerun. Besides per-pattern stats, report.json has account save/share
rates, `concentration` (top-1/top-5 share, `hits` ≥5× median and their share of all views)
and `splits`: `format` (video / photo / 1 / 2-3 / 4+ slides), `pinned`, `period`
(publication month, quarters when the sample spans > 12 months), every categorical card
field (`has_creator_face`, `has_person`, `background`, `visual_format`…) and every
labels.json field (restrict with `--split-by`).

- **Young posts**: posts younger than `--min-age-days` (7) on `fetchedAt` are still
  collecting views. They stay out of every median and split (`young.indexes`) but are still
  listed as hits (`young: true`) and shown in the grids. On @evividm (2026-11-03) a 2-day-old
  post already had 253K and that morning's post 5 378: neither is the number the post ends
  with, and the latter would pull its pattern's median down. If every post is young,
  nothing is excluded (`fallbackAllYoung`).
- `--since` narrows the stats to a window without re-fetching (`window.excluded`); the
  stderr `window:` line says how many posts are in it.
- Every pattern and split bucket carries `belowMinimum` (< 3 posts); the renderer draws
  those bars thin and marks them «мало данных». Do not draw conclusions from them.
- ER = (likes + comments + shares + saves) / views × 100, the same formula as
  `social-account-short-analysis` (ex `tiktok-account-short-analysis`), so the two skills give the same numbers for one account.
  In likes mode (Instagram posts) ER is `null`: there are no views to divide by. For "selfie vs place/landscape" use `background`: `has_person` also counts
people in the background of a church or landscape shot. Compare every category on its own:
lumping "no person" covers together hid that church covers beat selfies (1870 vs 1440)
while landscapes dragged the group down (684). **Never present stats computed by hand/LLM** — every number in the report,
including face/no-face and slide-count comparisons, must come from report.json.

### Step 6 — Report (language: user's, hooks verbatim in original)

Content, whatever the output form:

1. **Overview**: SAMPLE line (complete or not, share of account), account median views,
   carousels vs videos, view concentration.
2. **Patterns** sorted by virality, header per pattern:
   `### 🔥 Name — 4.0x · 7 videos` (🏆 >5x / 🔥 >3x / ⚡ >1.5x / ⚠️ <1x / 📉 <0.5x).
   For each: formula, visual format, stats row (median/avg views, virality, median
   likes/saves, save rate, engagement), top-3 videos with links + verbatim hooks, flags from
   report.json (`outlierWarning` → «⚠️ среднее раздуто одним виралом»,
   `belowMinimum` → not a real pattern).
3. **Virals slide by slide** (TikTok carousels): large slides plus one row of metrics as
   icon + number (views, × median, likes, comments, saves, shares, slides, date, open link).
   Nothing else: no hook text (it is already on the slides), no top comment, no description
   blocks (formula name, «почему сработало») – user feedback (2026-11-03): they repeat what the slides already show.
   Mechanics of the hits go into summary, patterns and formulas; read the top comments in
   `carousels/NN/post.json` for your own analysis.
4. **Visual-layer insights** from `splits`: face vs no-face, slide count, background, design
   series, embedded proof, what the top-1 cover does differently.
5. **Key insights**: what works >3x and why, what underperforms <1x, repost degradation,
   serial formats, saves as quality signal, themes from the `theme` split.
6. **Product**: 2–4 adaptations of the account's best formulas to the user's product, each
   tied to a source post: the hook rewritten for the product and how to build the slides.
   Prefer sources with `product_fit = direct`. Product context from the project's CLAUDE.md /
   research files (Step 1).
7. If `unassigned` is large, report it honestly with % — «у аккаунта нет формулы» is
   itself a finding.

**Chat report:** markdown as above, every post and the account as clickable links.

**Artifact report** (when the user wants a page, «отчёт артефактом», covers, links):
do not hand-write HTML. Write `$WORK_DIR/insights.json` — only texts: summary bullets,
virals (index only, to pick which hits to show; no texts), `product` (lead, notes,
adaptations `[{index, title, hook, how}]`: the source cover is shown with its own hook, so
`hook` is only the product's version), pattern notes, visual notes, formulas as storyboards,
do/don't, caveats; `"allPosts": false` hides the sortable all-posts grid. Schema in the
`render_report.py` docstring (supports **bold**, *italic*,
markdown links to a URL or to `#pN`, the N-th pattern by virality). Then:

```bash
python3 ~/.claude/skills/social-account-hook-analysis/scripts/render_report.py "$WORK_DIR" \
  --insights "$WORK_DIR/insights.json" --out "$WORK_DIR/report" --lang ru
```

It renders `report/index.html` (covers uncropped 9:16 at `minmax(260px,1fr)`, the size of a
TikTok web profile grid; hooks from cards.json; numbers from report.json),
recompresses covers (≤480 px) and hit slides (≤540 px) with PIL q74, and prints publish
batches (≤25 files, ≤2.5 MB). Under the hero it prints the sample note (complete / latest N
of M / since, young posts, likes mode); sections: summary, virals, product, patterns, visual,
formulas, rules, all posts (sortable by date / views), caveats.

**Check the page before publishing** (~10 s):

```bash
python3 ~/.claude/skills/social-account-hook-analysis/scripts/snapshot_report.py "$WORK_DIR/report"
```

Headless Chrome loads the page in a 390 px iframe (Chrome will not open a window narrower
than 500 px, so a plain 390 window silently checks 500) and at 1280, runs an in-page check
and screenshots the top of the page and every section into `report/_check/` (never
published). Exit 2 + `PROBLEM:` lines = horizontal overflow on the phone (with the offending
elements) or broken images: fix and rerun. Then Read the 390 shots of every section and the
1280 shots of top, virals and product. Look for what the check cannot see: cut-off text,
duplicated text, empty blocks, wrong numbers.

Without the claude.ai Artifact tool (Codex, other agents) stop here: `report/index.html` with
`covers/` and `slides/` next to it opens locally in any browser. In Claude Code with the
Artifact tool, load the `artifact-design` skill or run `quickstart` as the tool requires, then publish:

1. Batch 1: Artifact publish `file_path=report/index.html`, `root=report`, `files=<batch 1>`,
   `icon`. Batches 2..K: the same `file_path` and `root`, next list, no icon. Later
   publishes add files, earlier ones stay.
2. Verify: `action: "list", scope: "files", url=<artifact>` (no `limit` with this scope);
   the count must be K-batch files + page.
3. **"publish outcome unknown"**: never resend the identical package. List the files,
   republish only what is missing. Never publish ~7 MB in one call: two such attempts hung
   7 and 15 min and died with `SSLV3_ALERT_BAD_RECORD_MAC`, while 2 MB batches took 2–9 s.
4. `EPROTO` / `BAD_RECORD_MAC` from the API and the Artifact tool at the same time = the
   network (VPN, Wi-Fi), retries will not fix it; tell the user.

### Step 7 — CSV + save the run into the project (always, also for a chat-only report)

The scratchpad is wiped with the session; before this step the cover texts lived only in
the conversation. Last step of every run:

```bash
python3 ~/.claude/skills/social-account-hook-analysis/scripts/export_csv.py "$WORK_DIR" \
  --save-to "$CLAUDE_PROJECT_DIR/research/<fetchedAt>-<handle>-<platform>/hook-analysis"
```

- Copies the work dir (json files, covers/, thumbs/, carousels/ with slides.json, report/
  without `_check`) and points the paths inside meta.json and post.json at the copy, so
  `render_report.py` and `pattern_stats.py` run on it directly. ~25 MB for 87 posts.
- Writes `<handle>_posts.csv` there (utf-8-sig for Excel/Numbers), one row per post sorted
  by the metric: rank, date, age_days, young, in_window, url, owner_url, views, likes,
  comments, shares, saves, x_median, save_rate, share_rate, er, slides, kind, is_pinned,
  hook_text, pattern, formula, every cards.json and labels.json field, top_comment,
  slide_texts, caption, cover_file, cover_source.
- No project (session in the home dir) → `--out` a CSV next to the work dir and tell the user
  the run lives only in the scratchpad.
- In the final message link the CSV and the folder relative to the project root (spaces as
  `%20`).

## Scaling (>120 covers)

FAST mode, or FAN-OUT with 4–5 Sonnet subagents of ~25–30 covers. Main context merges
cards → Step 4. Clustering never happens inside a subagent (needs the full picture).

## Cost & runtime (measured 2026-11-03, 50 TikTok covers, 41 carousels)

| Step | Time |
|---|---|
| Step 2 fetch: feed, profile, 50 covers, 6 carousels with slides + comments | 40 s |
| Step 3 NATIVE: Claude reads 50 covers (+ writing cards.json) | ~2.5 min, +~100k tokens in the main context |
| Step 3 FAN-OUT: 2 Sonnet subagents × 25, in parallel | ~2 min wall clock (98 s / 102 s), ~124k Sonnet tokens each, main context untouched |
| Reading 4 hit carousels (~25 slides), during the fan-out | ~1 min |
| Steps 4–5 clusters + stats | ~1–2 min (stats script < 1 s) |
| insights.json + render (< 1 s) + 3 publish batches | ~3–4 min |

FAN-OUT quality on the test run vs Claude's own verbatim reading: 48/50 hooks identical,
the 2 diffs were one author typo corrected (`celabrate` → `celebrate`) and one cover
transcribed more fully than Claude had; `background = person_selfie` matched Claude's selfie
set 50/50. Speed is about the same as NATIVE; the gain is that the main model stays free
(read hit slides, prepare clusters) and its context does not grow by 50 images.

A full run with an artifact report took 45 min before these scripts existed: 22 min went
to two failed one-shot publishes, 6 min to reworking covers that were too small, and
~6 min to hand-written HTML. With the renderer and batches the same report is ~10 min.

Measured on @evividm, 87 carousels (2026-11-03): fetch with `--slides-top 6` 64 s, stats
< 1 s, render < 1 s (148 KB page, 104 images, 5.1 MB, 5 batches), snapshot check 8 s
(14 screenshots), export + save 1 s.

## Notes

- The old pipeline (`src/scripts/analyze-cover-hooks.ts` in the repo, Gemini OCR →
  Gemini clustering) is deprecated for this skill: cheap-model clustering silently
  dropped unassigned videos (28% loss on test) and discarded all visual signal.
- If Gemini returns «User location is not supported» (VPN exit in an unsupported
  region), `ocr_covers.py --provider auto` falls back to Grok automatically.
- Comments: `/v1/tiktok/video/comments` can return an empty list for posts with < 10
  comments; sticker/GIF comments without text are dropped.
- Instagram: `/user/reels` returns reels only, so `profile.totalPosts` (all media) is not
  comparable to the sample size; no slide data. It returns no saves or shares (always 0):
  say so in caveats; the renderer hides those chips when the whole sample has none.
- Instagram `--ig-source posts`: one feed of carousels (`media_type` 8), photos (1) and
  reels (2); `play_count` exists only for reels, so every comparison runs on likes
  (`metric: likes`), ER is not computed, and the hero says why. Pinned posts carry no pin
  flag in this endpoint. Tested on @natgeo (12 posts: 3 carousels, 7 reels, 2 photos).
- Large accounts (32 142 posts on @natgeo): never `--all`; use `--since` for a period or
  `--count`, and say in the report that hits outside the window are unknown.
