---
name: carousel-account-finder
description: >
  Find carousel-first ("моно-карусельные" / majority-carousel) TikTok accounts for a topic or
  keywords and publish them as a swipeable English HTML page. Pipeline: search keywords picked from
  the product's research (personas, content angles) -> ScrapeCreators Top search -> collect carousel
  authors -> screen each account's feed (5 pages, default 12 months) -> three blocks: carousel-first
  accounts (>=40% carousels), single super carousels (>=100k views and >=5x account median) and
  successful repeats (3+ carousels with the same meaning-level hook and formula, each >=10k, group
  median >=2x) -> Haiku sub-agents OCR every slide and describe the visual, Sonnet sub-agents decide
  fit (in niche / adjacent / off) against the product and pick the research persona and angle -> page
  with tabs for the three blocks, one account per screen, integration quotes. Input: topic or explicit
  keywords, product research files, optional reference accounts. Trigger phrases: "найди карусельные
  аккаунты", "моно-карусельные аккаунты", "монокарусельные аккаунты", "карусельные аккаунты по теме",
  "кто в нише делает карусели", "поиск карусельных аккаунтов", "find carousel accounts",
  "carousel-first accounts", "mono carousel accounts", "carousel account finder"
---

# Carousel Account Finder

Topic or keywords in -> HTML page with TikTok accounts whose main format is carousels and whose
carousels keep getting views. One viral carousel on a video account does not count.

## Inputs

- **Topic** (e.g. "trauma bonding") or **explicit keywords** (use them verbatim). Required.
- **Product research**, optional but recommended: personas / target audience, voice of customer, content
  angles. Keywords and the niche verdicts are built from it. Without it, ask for 2–3 lines on the product
  and its audience.
- **Reference accounts**, optional: always screened, badge "★ reference" on the page.
- **Window**, optional: default 12 months for both the found carousel and the account activity.
- **Thresholds**, optional overrides (defaults below).

## Requirements

- Python 3.10+ with Pillow (`python3 -m pip install Pillow`). Slides come as JPEG, WebP or HEIC: macOS
  converts them with the built-in `sips`; on Linux / Windows install `pillow-heif` as well.
- A [ScrapeCreators](https://scrapecreators.com) key exported as `SCRAPE_CREATORS_API_KEY`. The scripts
  read it from the environment only; they never search shell config or `.env` files.
- An agent that reads images and runs sub-agents (Claude Code: Agent tool with `model: "haiku"` /
  `"sonnet"`). Without sub-agents, run the same prompts yourself in smaller batches.

## Defaults

| Rule | Default | Flag |
|---|---|---|
| Carousel = photo post with ≥ 2 slides (single photos are not carousels) | – | – |
| Window (search freshness + account feed) | 12 months | `--since` |
| Share of carousels among all posts in window | ≥ 40% (>50% «карусельный», 40–50% «пограничный») | `--min-share 0.4` |
| Median carousel views | ≥ 2,000 | `--min-median` |
| Total carousel views in window | ≥ 100,000 | `--min-total` |
| Carousels in window | ≥ 5 (fewer = one-hit account) | `--min-carousels` |
| Page cap: search pages per query / feed pages per account (10 posts each) | 5 / 5 | `search.py --pages`, `screen.py --max-pages` |
| Single super carousel (any screened account) | ≥ 100,000 views and ≥ 5× account median (all posts in window) | `candidates.py --super-views --super-x` |
| Successful repeat | ≥ 3 carousels, same meaning-level hook + formula, each ≥ 10,000 views, group median ≥ 2× account median | `candidates.py --rep-views --rep-x` |
| OCR + visual | Haiku sub-agents, every slide verbatim | `references/ocr_prompt.md` |
| Niche fit (в нише / смежная ниша / вне ниши), persona, angle, repeat groups | Sonnet sub-agents on the OCR text; persona and angle only as ids from `taxonomy.json` built from the product research | `references/decide_prompt.md` |

The 40% share (not 50%) is deliberate: strong carousel accounts often mix in videos. One reference
account ran ~44% carousels, every one of them above 50k views.

The Russian strings «в нише», «смежная ниша», «вне ниши», «высокая / средняя / низкая» are machine keys
in the agents' JSON; `build.py` translates them to English on the page.

## Pipeline

Narrate each step to the user in one line before running it.

**0. Setup.**
```bash
SKILL_DIR="<folder of this SKILL.md>"   # e.g. $HOME/.claude/skills/carousel-account-finder
OUT="<project root>/research/carousel-accounts-<topic-slug>-<YYYY-MM-DD>"   # absolute path
SINCE=<today minus window, YYYY-MM-DD>
python3 -c "import PIL" && echo pillow-ok
test -n "$SCRAPE_CREATORS_API_KEY" && echo key-ok
```
Run all scripts with plain `python3` and absolute paths.

**1. Keywords from the research.** Keywords given -> use them as-is. Otherwise:
- Find the product's research in its project folder: personas / target audience, voice of customer,
  content angles, plus any content rules in the project's instructions. Read them.
- Write 12–20 English seed phrases straight from it: each persona's situation and pain in viewers' words,
  every content angle, the product's job ("meeting notes", "follow-up email"). Note which persona each
  seed comes from.
- Pick 6–10 of them as search queries: 2–4 words a viewer would type into TikTok search, one situation or
  pain per query, covering every persona. Avoid single broad words (they pull memes and fandom accounts
  that pass the numeric filters) and brand names unless the user asks for them.
- Save `$OUT/keywords.json` = `[{"keyword", "persona", "seed", "note"}]` and show the user the list with the
  persona each query serves.
There is no search-volume check. A query proves itself by what it returns: `search.py` prints carousels
per page for every query. Replace queries that bring almost no carousels in step 2.

**2. Search.**
```bash
python3 "$SKILL_DIR/scripts/search.py" "$OUT" --since $SINCE [--include ref1,ref2] "q1" "q2" ...
```
Prints carousels per query page, carousel authors found and pool size. If the pool is under ~20 accounts,
add 2–4 more queries (reworded seeds from the research) and rerun the same command (results merge;
searched queries are skipped). Note the queries that yielded nothing for the reply.

**3. Screen** (run in the background; ~5–15 min for 60 accounts; wait for it to finish, don't poll):
```bash
python3 "$SKILL_DIR/scripts/screen.py" "$OUT" --since $SINCE --pool "$OUT/pool.txt"
```
Prints the PASS list. Accounts flagged `CAPPED` hit `--max-pages` (5 pages = last ~50 posts): share and
median are measured on those recent posts, totals are a lower bound, say so. Most carousel farms post daily
and will be CAPPED; that is expected and keeps the cost at ≤ 12 credits per account.

**3b. Candidates for the three blocks** (no API calls):
```bash
python3 "$SKILL_DIR/scripts/candidates.py" "$OUT"
```
Writes `candidates.json`: mono accounts (passed screening), single super carousels on any screened account,
repeat candidates (≥3 carousels ≥10k with at least 2 of them ≥2× median, up to 12 per account) and `jobs`
= which carousels of which account the OCR agents read. Baseline for every x: median of all posts of the
account in the window.

**4. Assets + briefs** (all slides of every carousel in `jobs`, strips, thumbs, contact sheets, `brief.json`
with roles and x per carousel):
```bash
python3 "$SKILL_DIR/scripts/fetch_top5.py" "$OUT" --jobs
```

**5. Taxonomy, then OCR (Haiku), then decisions (Sonnet).**
- Write `$OUT/taxonomy.json` by hand from the product research: `{"source": [paths], "personas": [{"id": "P1",
  "name": "<exact heading from the research>", "label_en": "<short English gloss>", "note": "<1 line>"}],
  "angles": [{"id": "A1", "name": "<exact row/heading>", "label_en": "...", "personas": ["P1"], "note": "..."}]}`.
  Copy names verbatim (personas incl. the anti-persona; every row of an angle table; trigger and feature-angle
  sections of other research reports). Short ids (P1, A3, T3.2, F4). Never add an angle that is not in the files.
- Triage first: `scripts/triage.py "$OUT"` builds one sheet per job account (first slides of up to 8
  carousels); Haiku agents with `references/triage_prompt.md` (~25 accounts each) write `triage/<h>.fit.json`;
  only "в нише" / "смежная ниша" go on. ~5.6k tokens per account.
- **Full vs cover-only OCR:** full slide-by-slide OCR only for the top-N carousels by views (default N = 10 per
  OCR wave, `hooks.py --full-top N`); every other carousel gets slide 1 only (`scripts/hooks.py` sheets +
  `references/hook_prompt.md`, ~20 accounts per Haiku agent). Cover-only files carry `"ocr_scope": "cover only"`
  (full ones `"full"`), `formula` is "" there, and the page labels them. Full OCR costs ~8k tokens per carousel
  on Haiku; cover-only ~2.9k. Sonnet decide: ~10k per account.
- Stage A: fill `references/ocr_prompt.md` (`{HANDLES}`, `{OUT}`), Agents with `model: "haiku"`, 6 accounts each,
  all in ONE message (background). Then `python3 "$SKILL_DIR/scripts/validate.py" "$OUT" --stage ocr`, spot-check a
  few `ocr/*.json` against the sheets, rerun bad accounts (on Sonnet if Haiku misreads).
- Stage B: fill `references/decide_prompt.md` (`{HANDLES}`, `{OUT}`, `{PRODUCT}`, `{NICHE}`, `{RULES}`), Agents with
  `model: "sonnet"`, 8 accounts each, all in ONE message. They write `analysis/<h>.json` with per-carousel
  fit / persona / angle in "carousels" (niche_fit, fit_reason, persona, angle, angle_use, product, repeats groups). Then
  `validate.py "$OUT"` (checks keys, fit, and that every persona / angle id exists in taxonomy.json) and rerun
  what it lists. `build.py` shows ids as "P1 · <research name>".
- Before agents: tell the user the number of job accounts / carousels and the token estimate (Haiku ~8k per
  carousel read in full, ~2.9k cover-only, Sonnet ~4k per carousel of OCR text + ~10k per account) and wait for a
  go-ahead on big runs.
- `references/ocr_decide_prompt.md` is the older one-agent variant (Sonnet does both); only for small runs.

**5b. Integration quotes.** For every passing account with `"product_yes": true`, read
`references/integration_prompt.md`, fill `{HANDLES}` and `{OUT}`, 6 accounts per agent, all in ONE
message (background). Each writes `analysis/<h>.integration.json` with 2–5 verbatim quotes and where
they sit. The page shows the product name (`product_name`) and these quotes in the exact wording, never a
paraphrase. `$OUT/product_names.json` (`{"handle": "name"}`) overrides a name by hand.

**6. Build.**
```bash
python3 "$SKILL_DIR/scripts/shrink.py" "$OUT"          # once: smaller strips, uploads stop dropping
python3 "$SKILL_DIR/scripts/build.py" "$OUT" --topic "<topic>" --title "<Name> Carousel Accounts" \
  --max-accounts 60 [--reference ref1,ref2] [--pin h1,h2 --pin-label "<theme>"] [--fav h1] \
  [--max-supers 120 --max-repeats 60 --drop-off --strip-thumbs]
```
Writes `carousel-accounts.html`, `accounts.csv`, `publish_batches.json` (≤ 3 MB each). The page, in English:
- **Summary tiles** on top: accounts found (and how many in niche), carousel posts in the window, total
  carousel views (lower bound because of CAPPED feeds).
- Facts chips with the filters, then the **integration filter**: All / With integration / Without
  integration, with counts; the choice is remembered per viewer.
- **One account per screen** (checked at 1440×850 and 375×812): handle, a clickable ☆ favorite star
  (kept in the viewer's browser; `--fav` accounts start starred and go first), badges (🚩 pin label,
  carousel-first share, consistency, niche, integration yes/no); top-5 rail + slide viewer with post
  metrics overlaid; right panel: followers / likes, **avg views / followers** (yellow), posts,
  carousels, total views, median, average, comments, saves, comment rate; then the integration block
  (product name + verbatim quotes with where they sit; 2 quotes on phones, up to 5 on laptops).
- **Tabs** under the header: Carousel-first accounts / Single super carousels / Successful repeats.
- Each account head carries a fit line: persona and research angle (from the agents) + one-line reason; the
  panel adds "How to use for our product".
- **Single super carousels** block: card per carousel (all slides in a scrollable strip, views, x to median,
  verbatim hook, formula, visual, fit, persona, angle). In niche first, then by views.
- **Successful repeats** block: per group the hook template, formula, what repeats, persona / angle and the
  3+ carousels with views and x. Groups are kept only if each is ≥10k and the group median ≥2×.
- Bio text and the full screening table stay in `accounts.csv` and `analysis/`, off the page.
Order: `--fav`, then `--pin` in the given order, then in-niche, adjacent, off-niche; inside each group by
consistency, then median. Use `--pin` when the user asks to lift a theme to the top (e.g. "red flags in
communication": pick accounts by their hooks, list them with one reason each).

More `build.py` options: `--mark h1,h2 --mark-label "new"` (badge without reordering), `--group-filter
"A=Relationships,B=Intimacy"` (account groups from the agents' `group` key, badge + filter row), `--demote-tag
"<tag>"` (accounts with that tag go last inside their niche group; tags from the agents' `tags` list or
`$OUT/tags.json` `{handle: [tags]}`), `--christian-rule` (faith products: agents add a `christian` bool; Christian
accounts stay if in niche or adjacent, others only if strictly in niche), `--allow-dupes` (show a carousel in
several blocks).

Quick local check before publishing: `python3 -m http.server 8765 --directory "$OUT"` in the background, open
`http://localhost:8765/carousel-accounts.html` in a browser, check 1440×850 and mobile width, confirm no `.panel`
overflows (`scrollHeight > clientHeight`) and the console is clean, then stop the server.
A `file://` preview may render without the images; use the local server.

**7. Publish.** The page is self-contained HTML plus the JPEG strips next to it.
- Claude.ai Artifacts: first call the page alone (`file_path` = `$OUT/carousel-accounts.html`, an icon, a
  one-sentence description) to lock the link. Then publish the same `file_path` with `root` = `$OUT` and `files`
  = one batch of `publish_batches.json` as `[{"path": ...}]`, **one call at a time** (parallel calls drop). After
  the last batch list the artifact's files and resend whatever is missing. Later page-only changes (order,
  labels) need only a page publish: the images stay.
- Any static host works too: upload `carousel-accounts.html` and the `acc/` folder as they are.

**8. Reply** (in the user's language):
- page link;
- the queries with the persona each serves and how many carousel authors each brought (from
  `search_candidates.json`); queries that yielded nothing;
- table of passing accounts: clickable `[@handle](https://www.tiktok.com/@handle)`, carousel share,
  median, total, consistency, product;
- 3–4 bullets: best in-niche accounts with one template, product integrations inside carousels,
  accounts that live on one outlier;
- caveats: feed may miss posts (lower bound), CAPPED accounts, judgement calls on niche fit;
- local files: `accounts.csv`, `carousel-accounts.html` and the `$OUT` folder path.

## Second round into the same OUT

Save the round-1 screened list, run `search.py` with new queries (searched ones are skipped), screen ONLY new
handles (`screen.py` rescreens everything it gets, ~12 credits each), `fetch_top5.py OUT h1 h2 ...` for new
passers only, shrink only the new strips (re-running `shrink.py` shrinks round-1 strips a second time), then
`build.py --mark h1,h2 --mark-label "new · round 2"` (badge without reordering) and publish only the new files.
In zsh `$VAR` with a space-separated list is ONE argument: pipe through `xargs` instead.

To badge accounts missing from an earlier page, take the set difference of handles and pass them to
`build.py --mark <new handles> --mark-label "new since <date>"`.

## Gotchas

- Claude Code runs at most 20 sub-agents at once: size OCR batches so a stage needs ≤ 20 agents (e.g. ~55
  carousels each for 1,000 carousels), or launch the rest as slots free up.
- `/v1/tiktok/search/keyword` returns videos only. Carousels come only from `/v1/tiktok/search/top`.
- `search/top` with `publish_time=last-6-months` returned zero carousels. Filter dates locally.
- Top results run out after ~6 pages (~250 posts) per query, and one query yields few fresh carousels.
  Several queries are needed. Repeated calls return a reshuffled set.
- Authors of older carousels can still be active; the account screen is what decides.
- Profile feed: 10 posts per page, pinned posts first (ignored for the stop rule), not exhaustive.
- Photo posts with one slide inflate "carousel" counts (one account had 409 of them). `screen.py`
  counts them separately as `single_photos_win`.
- Broad words in Top search surface memes and fandom accounts that pass the numeric filters. Agents tag
  `niche_fit`; off-niche accounts sit at the end of the page.
- TikTok only. ScrapeCreators search for Instagram returns reels only (no carousels, and IG carousels
  have no view counts).
- Caption keywords miss on-topic accounts: empty captions, hashtags only, or generic text over slides.
  Judge niche by slides, never by captions alone.
- TikTok CDN image links in saved feeds die after ~2 weeks: run `fetch_top5.py` soon after screening.
- Publish in batches of ≤ 3 MB, one call at a time: 6–14 MB batches and parallel calls kept dying with
  "socket hang up". Run `shrink.py` first: it cut 87 MB of strips to ~43 MB. 511 files = ~51 accounts on the page.
- The page needs its own `<meta charset="utf-8">` and viewport meta (the template has them): without
  them a local preview shows mojibake and phones render a 980px desktop layout.
- Three blocks blow past 511 files fast (557 supers + 128 repeat groups = 1,698 files, 278 MB on one run).
  `--strip-thumbs` reuses the strip as the thumbnail (CSS crops slide 1), halving files; `--drop-off` keeps off-niche
  out of blocks 2 and 3; `--max-supers` / `--max-repeats` cap them (in niche first, then by views / group x).
  60 accounts + 120 supers + 60 groups = 486 files, 146 MB. Merged publish batches (~9 MB) fail with an SSL
  error: keep build.py's ≤3 MB batches; a single failed batch usually goes through on retry.
- Artifact limits: 511 files per version, 255 files and 64 MB per publish. Slides go in one strip per
  carousel and `build.py` splits files into batches.

## Cost

ScrapeCreators charges ~2 credits per profile or feed call (measured: 711 profiles + 2,895 feed pages = 3,606
calls, 7,329 credits) and 1 credit per search page (227 pages, 227 credits). Estimate screening as
2 × (1 + pages) per account, i.e. up to 12 per account at the 5-page cap, and check the balance (`screen.py` prints
`credits left`) after the first ~50 accounts before screening the rest.

Agents: one run with 307 job accounts / 1,991 carousels took ≈ 20M tokens for the full two-stage pass; run the
Haiku triage (one contact sheet per account, drop off-niche) before full OCR. Measured: full OCR 6.4M tokens for
808 carousels, cover-only 729k for 253 covers, Sonnet decide 2.17M for 215 accounts.

## Related skills

- `carousel-account-patterns` – deep formula mining of one account found here.
- `reference-carousel-adapter` – adapt one carousel found here to your product.
