# Viral Camp — TikTok, Instagram & Facebook Ads Skills

Research **Instagram and TikTok posts** with ScrapeCreators, turn observed hooks into referenced formulas, and adapt them to your product. Ten skills cover account research, hook research, audience comments, competitor Facebook ads, carousel production and video production. The skill folders are independently installable in Claude Code, Codex and other SKILL.md-compatible agents. The repository URL remains `maxxyart/viral-tiktok-skills` for existing users.

| Skill | Outcome |
|---|---|
| **[Social Account Short Analysis (Viral Camp)](skills/social-account-short-analysis/SKILL.md)** | CSV + concise HTML: views and comments totals/means/medians, comment rates, publication-month cohorts, top five with virality multiples, topic and offer. |
| **[Social Account Hook Analysis (Viral Camp)](skills/social-account-hook-analysis/SKILL.md)** | Every cover of the account when it has ≤150 posts (else the latest 50, or `--all` / `--since`); TikTok and Instagram reels, carousels and photos; frame 0 for videos; text formula × visual format patterns, themes and product fit; posts younger than 7 days kept out of medians; HTML report with virals slide by slide, product adaptations and a sortable all-posts grid, checked in headless Chrome; CSV export. |
| **[Social Post Comment Analysis (Viral Camp)](skills/social-post-comment-analysis/SKILL.md)** | Bounded Instagram/TikTok comment collection, CSV, semantic audience themes, root/reply statistics and product experiments. |
| **[Carousel Account Finder (Viral Camp)](skills/carousel-account-finder/SKILL.md)** | TikTok accounts that grow on carousels in your niche: keywords drafted from your research or CLAUDE.md and approved by you, Top search and feed screening, super carousels and repeated winning formulas, verbatim slide OCR and niche fit by sub-agents, one HTML page with an account per screen. |
| **[Carousel Account Patterns](skills/carousel-account-patterns/SKILL.md)** | Research recurring photo-post formulas across a TikTok account. |
| **[Hook + Notes Carousel](skills/hook-notes-carousel/SKILL.md)** | Produce the fixed two-slide photo hook and Notes-style payload format. |
| **[Reference Carousel Adapter](skills/reference-carousel-adapter/SKILL.md)** | Adapt one TikTok/Instagram carousel to your product: source analysis, new hooks and slide copy, HTML storyboard, clean backgrounds and editable text overlays. |
| **[Emotion + Demo Video](skills/emotion-demo-video/SKILL.md)** | Short vertical video from a reference: your AI character in real donor scenes, a silent emotion hook (Nano Banana 2 + Omni 1.1 on kie.ai), TikTok-native hook overlay and your product demo. |
| **[Reference Reel Clone](skills/reference-reel-clone/SKILL.md)** | One-to-one clone of a talking-creator reel with your AI avatar: storyboard, Nano Banana Pro first frame, Omni 1.1 clips with native voice and lip-sync, cloned voice only for faceless voice-over, motion graphics rendered as code, side-by-side check. |
| **[Facebook Ads Short Analysis (Viral Camp)](skills/facebook-ads-short-analysis/SKILL.md)** | All active ads of an advertiser from Facebook Ad Library via ScrapeCreators: catalog CSV, impression-ranked CSV, formats, landings (App Store / Google Play / web funnels), countries, days live, launch velocity and repeated text. No model calls. |
| **[Facebook Ads Deep Analysis (Viral Camp)](skills/facebook-ads-deep-analysis/SKILL.md)** | Enriches the short-analysis CSV with Gemini: hook text, first-seconds visual, timestamped script, product moment, emotion and CTA for video, image and carousel creatives, then an interactive HTML report: angles with playable creatives, reach shares, CTA and copy tables, pains and adaptations with Ad Library links. |

Both account-analysis skills honor an explicit sample size or all-available scope. Missing data remains missing; partial collection is labeled. A cover-only analysis does not pretend to have inspected the opening video. Every displayed hook formula links to 1–2 specific source posts.

## Install

Download the two ZIPs from [Releases](https://github.com/maxxyart/viral-tiktok-skills/releases), or clone:

```bash
git clone https://github.com/maxxyart/viral-tiktok-skills.git
cd viral-tiktok-skills

# Claude Code
mkdir -p "$HOME/.claude/skills"
cp -R skills/social-account-short-analysis "$HOME/.claude/skills/"
cp -R skills/social-account-hook-analysis "$HOME/.claude/skills/"

# Codex — use these instead of the Claude paths
mkdir -p "$HOME/.codex/skills"
cp -R skills/social-account-short-analysis "$HOME/.codex/skills/"
cp -R skills/social-account-hook-analysis "$HOME/.codex/skills/"
```

Each folder contains its runtime scripts and references. It needs neither the repository checkout nor `TIKTOK_SKILLS_ROOT` after installation. Review existing installed folders before replacing an older copy.

To install the independently added comment skill, copy `skills/social-post-comment-analysis` to the same agent skills directory. It needs Python 3.9+ and no npm dependencies. Set `SCRAPE_CREATORS_API_KEY` / `SCRAPECREATORS_API_KEY` or use its explicit `--env-file` option.

To install the carousel adaptation skill for a class project, copy `skills/reference-carousel-adapter` to the same agent skills directory. For example, after cloning:

```bash
# Codex
cp -R skills/reference-carousel-adapter "$HOME/.codex/skills/"

# Claude Code: use this path instead
cp -R skills/reference-carousel-adapter "$HOME/.claude/skills/"
```

**Install a font before creating slides.** For TikTok-native captions, download [TikTok Sans from the official Google Fonts page](https://fonts.google.com/specimen/TikTok+Sans), install the variable `.ttf`, and supply its file path to the overlay renderer. The [text overlay guide](skills/reference-carousel-adapter/references/text-overlay.md) gives macOS, Windows and Linux steps and explains regular/bold weights. If your reference uses a different font, use that licensed font instead. The sample config is a template, not a finished carousel; replace its text, backgrounds and font paths for your product. Rendering needs `python3 -m pip install Pillow`.

> Адаптируй эту TikTok-карусель под мой продукт: [ссылка]. Разбери смысловую и визуальную формулу, предложи несколько хуков, собери HTML-макет и готовые PNG. Используй $reference-carousel-adapter.

Для этого навыка приложите ссылку на референс и короткое описание своего продукта. Агент сохранит исходный порядок слайдов, предложит новые тексты, покажет HTML-макет и соберёт финальные PNG. Исходные фото референса и материалы учеников остаются в их проектах; в репозитории опубликован только демонстрационный пример Holy60.

**Пример одного формата:** [готовая карусель Holy60](examples/holy60-evelyn-carousel/README.md), сделанная по [оригинальному TikTok-референсу @studywith.evelyn](https://www.tiktok.com/@studywith.evelyn/photo/7627272727711255830). В примере видны все семь итоговых кадров; изображения исходного поста в репозиторий не добавлены. Рядом — [гайд по text overlay](skills/reference-carousel-adapter/references/text-overlay.md) для сборки текста поверх чистых фото.

### Carousel account finder

Copy `skills/carousel-account-finder` to the same agent skills directory. It needs Python 3.10+ with Pillow, a [ScrapeCreators](https://scrapecreators.com) key exported as `SCRAPE_CREATORS_API_KEY`, and an agent that reads images and runs sub-agents (Claude Code). On Linux or Windows add `pillow-heif` for HEIC slides; macOS converts them with the built-in `sips`. A run of ~60 screened accounts costs up to ~12 ScrapeCreators credits per account; the skill states the agent token estimate before OCR.

```bash
python3 -m pip install Pillow pillow-heif
```

> Найди TikTok-аккаунты, которые растут на каруселях, по теме «[тема]». Контекст продукта возьми из ресерча или CLAUDE.md в папке [папка], ключевые фразы покажи мне на согласование. Окно 12 месяцев. Собери страницу с карусельными аккаунтами, супер-каруселями и повторяющимися формулами. Используй $carousel-account-finder.

Контекст продукта агент берёт из ресерча (персоны, боли, контент-энглы), если его нет – из CLAUDE.md проекта, если нет и его – из вашего запроса. Когда непонятно, что за продукт и для кого он, агент спросит об этом до начала работы. Затем он подберёт 6–10 поисковых фраз и покажет их таблицей: фраза, сегмент аудитории, почему она должна приводить к каруселям. Поиск начнётся только после вашего «го». Проверки частотности нет: слабые запросы видны по выдаче, замену им агент тоже согласует с вами. Дальше скилл отбирает аккаунты, где карусели составляют от 40% постов и стабильно набирают просмотры. Слайды читают дешёвые саб-агенты, соответствие нише и персоне решают более сильные. Результат – одна HTML-страница и `accounts.csv`.

### Emotion + demo videos

Copy `skills/emotion-demo-video` to the same agent skills directory (`$HOME/.claude/skills/` or `$HOME/.codex/skills/`). It needs `ffmpeg`, `yt-dlp`, Python 3.9+ with Pillow, a [kie.ai API key](https://kie.ai/api-key) as `KIE_API_KEY`, and a caption font: install [TikTok Sans](https://fonts.google.com/specimen/TikTok+Sans) as described in its [text overlay guide](skills/emotion-demo-video/references/text-overlay.md).

> Сделай видео emotion + demo по этому референсу: [ссылка]. Персонаж – мой лист персонажа из assets/characters, фоны – первые кадры из этих роликов: [ссылки], демо – assets/demos/demo.mp4. Предложи 3 хука. Используй $emotion-demo-video.

Агент сам запросит всё, чего не хватает: персонажа, фоны, демку продукта и описание аудитории. Чужие лица и чужие экраны приложений он не подставляет. Перед генерацией видео покажет стоп-кадры с персонажем и назовёт стоимость. Ассеты складываются в проект (`assets/characters`, `assets/backgrounds`, `assets/demos`) и переиспользуются в следующих роликах.

### Reference reel clone

Copy `skills/reference-reel-clone` to the same agent skills directory. It needs `ffmpeg`, Python 3.9+, `pip install faster-whisper` for word-level checks, Node with Playwright for motion graphics and screen recordings, a [kie.ai API key](https://kie.ai/api-key) as `KIE_API_KEY` (or the user's own generation platform), `SCRAPE_CREATORS_API_KEY`, and – only for faceless voice-over – a key for ElevenLabs, Fish Audio or Inworld.

> Сделай клон этого ролика с моим аватаром: [ссылка]. Аватар – портрет и лист персонажа в avatar/. Повторяем один в один: сцены, тайминг, моушн-графику, субтитры и текст. Голос в кадре – сразу в Omni, клон голоса только для кусков без лица. Останавливайся после каждого этапа. Используй $reference-reel-clone.

### Facebook ads research

Copy `skills/facebook-ads-short-analysis` and `skills/facebook-ads-deep-analysis` to the same agent skills directory. Short analysis needs Python 3.10+ with `httpx` and a [ScrapeCreators](https://scrapecreators.com) key as `SCRAPE_CREATORS_API_KEY`. Deep analysis adds `google-genai`, `ffmpeg` and a [Gemini key](https://aistudio.google.com/apikey) as `GOOGLE_API_KEY` (optional `XAI_API_KEY` covers images and carousels when Gemini is unavailable). Both scripts accept an explicit `--env-file`.

```bash
python3 -m pip install httpx google-genai
```

> Собери всю активную рекламу этого конкурента из Facebook Ad Library по US: [ссылка на страницу в Ad Library]. Отсортируй по показам, покажи форматы, куда ведут, самые долгоживущие и повторяющиеся тексты. Используй $facebook-ads-short-analysis.

> Возьми топ-50 по показам из этой выгрузки и разбери хуки, сценарии и визуал. Собери HTML-отчёт: энглы с роликами, боли и 7–10 адаптаций под мой продукт со ссылками на объявления. Используй $facebook-ads-deep-analysis.

Meta shows commercial advertisers' impressions only as a rank, so the impression order is a ranking, not a view count. Long-running creatives near the top of that ranking are the proven ones.

### Requirements

- **Python 3.10+**. Short analysis uses only the standard library.
- **Pillow** for hook report image compression: `python3 -m pip install Pillow` (falls back to macOS `sips` with much bigger files). Prefer a virtual environment where appropriate.
- **ffmpeg** for the hook skill: video covers are frame 0 of the video, the frame viewers see in the feed, not the grid thumbnail.
- **Google Chrome** (or Chromium / Brave, or `CHROME=/path`) for the hook report's layout check.
- A connected **ScrapeCreators MCP**, or authenticated official `scrapecreators` CLI, or `SCRAPE_CREATORS_API_KEY` in the environment for REST fallback. [Provider integration docs](https://docs.scrapecreators.com/integrations/mcp/).
- An agent capable of reading images for hook research. Cover reading needs no Gemini/xAI key; FAST mode (`ocr_covers.py`) uses `GOOGLE_API_KEY` with `XAI_API_KEY` as fallback.

Short analysis: use the requested transport; CLI/REST is never described as MCP; raw MCP pages can be imported without repeating API requests; no automatic key search through shell configuration. Hook analysis calls the ScrapeCreators REST API and reads `SCRAPE_CREATORS_API_KEY` from the environment, or from an `export` line in `~/.zshenv`, `~/.zshrc` or `./.env`. Neither skill buys credits.

## Ask the agent

> Use $social-account-short-analysis to analyze all available Reels from this Instagram account. Save CSV and a concise HTML report.

> Сделай анализ хуков TikTok-аккаунта @handle: все обложки, формулы × визуал, темы, что взять для моего продукта, отчёт и CSV. Используй $social-account-hook-analysis.

> Keep formulas and quotations in the reference's original language. Attach 1–2 source links and covers per formula.

## Run the deterministic helpers

Run from the repository, or replace `src/social` with an installed skill's `scripts` folder. Use a fresh output directory for each capture.

```bash
# Instagram, authenticated official CLI
python3 src/social/social.py collect https://www.instagram.com/ACCOUNT/reels/ \
  --count 60 --transport cli --out runs/instagram-ACCOUNT

# TikTok, REST API key in environment; --all means paginate all available videos
python3 src/social/social.py collect https://www.tiktok.com/@ACCOUNT \
  --all --transport api --out runs/tiktok-ACCOUNT

# MCP export: page-0001.json, page-0002.json, ...; original capture time required
python3 src/social/social.py collect ACCOUNT --platform instagram --count 60 \
  --pages-dir /path/to/raw-pages --fetched-at 2026-09-15T12:00:00Z \
  --out runs/imported-ACCOUNT
```

Hook analysis (`H=skills/social-account-hook-analysis/scripts`, or the installed skill's `scripts`):

```bash
# Feed + covers (frame 0 for videos) + slides and top comments of the 6 best carousels.
# No --count: the whole account if it has <=150 posts, else the latest 50 with a warning.
python3 $H/fetch_covers.py ACCOUNT --platform tiktok --out-dir runs/hooks-ACCOUNT --slides-top 6
#   Instagram carousels + photos + reels: --platform instagram --ig-source posts (metric = likes)
#   A period: --since 2026-05-01; a fixed size: --count 60; everything: --all

# The agent reads every cover and writes cards.json, clusters.json, labels.json and
# carousels/NN/slides.json (schemas in SKILL.md), then:
python3 $H/pattern_stats.py runs/hooks-ACCOUNT/meta.json runs/hooks-ACCOUNT/clusters.json \
  --cards runs/hooks-ACCOUNT/cards.json --labels runs/hooks-ACCOUNT/labels.json \
  --out runs/hooks-ACCOUNT/report.json
python3 $H/render_report.py runs/hooks-ACCOUNT --out runs/hooks-ACCOUNT/report \
  --insights runs/hooks-ACCOUNT/insights.json --lang ru
python3 $H/snapshot_report.py runs/hooks-ACCOUNT/report      # 390 px + 1280 px screenshots, exit 2 on overflow
python3 $H/export_csv.py runs/hooks-ACCOUNT --save-to research/ACCOUNT-hooks
```

`--max-pages` defaults to 100. A cap or collection failure returns exit code **2** with partial artifacts; it does not mean all videos were collected. The agent must inspect `snapshot.json`. The feed helper supports latest-N and all-available scope; date-range requests require an ordered/exhaustive capture, filtering and recalculating the cohort as described in the skill. The shared `src/social/report.py` remains the concise renderer for the short-analysis skill. The v2.0.0 hook helpers (`covers.py` contact sheets, `audio_transcribe.py`, `hook_report.py`) are kept in `src/social` and `legacy/skills/social-account-hook-analysis-v2/`.

## Artifacts and metrics

Short analysis:

- `videos.csv`, `months.csv`: exact selected cohort and publication-month calculations.
- `analysis.json`: reproducible metrics; `snapshot.json`, `raw/`, `videos.json`, `fetched-videos.json`: provenance and auditable scope.

Hook analysis:

- `meta.json` (sample mode, metric, profile, per-post metrics and cover paths), `covers/`, `thumbs/`, `carousels/NN/` (slides, `post.json` with top comments, `slides.json` with verbatim slide texts).
- `cards.json`, `clusters.json`, `labels.json`: the agent's cover reading, patterns, themes and product fit; `report.json`: every number of the report, computed by `pattern_stats.py`.
- `report/index.html` + `covers/` + `slides/`: opens locally, or is published as a claude.ai Artifact in batches; `report/_check/`: layout screenshots, never published.
- `<handle>_posts.csv`: one row per post with metrics, × median, ER, hook, pattern, labels, top comment and slide texts.

Comment rate = comments/views × 100. The report distinguishes mean, median and weighted rates, with missing-data coverage. Virality is a **view multiple of the selected cohort median**, not a prediction, probability, or shares rate. Publication-month totals are cumulative views at capture time, not views earned during each month. Instagram feed limitations, missing captions and Instagram-only play counts are disclosed. Single-example patterns remain hypotheses; n ≥ 3 is an observation, not causal proof. Hook analysis: ER = (likes + comments + shares + saves) / views × 100, posts younger than 7 days stay out of every median, groups under 3 posts are flagged, and Instagram carousel/photo runs compare likes because the feed has no views for them.

## Upgrade from the old skills

| Old name | New name |
|---|---|
| `tiktok-account-short-analysis` | `social-account-short-analysis` |
| `tiktok-account-hook-analysis` | `social-account-hook-analysis` |

v2.1.0 replaced the v2.0.0 hook implementation (sheets of 20, audio transcription, self-contained HTML) with the version above; v2.0.0 is frozen in `legacy/skills/social-account-hook-analysis-v2/`. See the [v2.1.0 notes](docs/releases/v2.1.0.md).

Install the new folders and retire the two old installed skills to avoid duplicate routing. Their previous instructions and Python scripts remain under `legacy/skills/` for reference, with `INSTRUCTIONS.md` instead of discoverable `SKILL.md`. The previous Node pipelines remain in `src/scripts/` and are accessible as `npm run legacy:short-analysis` / `legacy:hook-analysis`; they are not the recommended path.

The [upgrade audit](docs/social-analysis-audit.md) explains the session and repository errors corrected: pagination, zero-versus-missing counters, stale caches, quote fidelity, cover/footage confusion, causal overclaims, reference quality and portable reports.

## Social post comment analysis (Viral Camp)

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


## Carousel workflows

Choose the skill for the job:

- [carousel-account-finder](skills/carousel-account-finder/SKILL.md): find carousel-first TikTok accounts, super carousels and repeated formulas for a topic; ScrapeCreators + Pillow, slide reading and niche fit by sub-agents, no other paid APIs.
- [carousel-account-patterns](skills/carousel-account-patterns/SKILL.md): TikTok photo-post formula research using ScrapeCreators + Gemini, with optional xAI fallback.
- [hook-notes-carousel](skills/hook-notes-carousel/SKILL.md): render hook-photo + iOS Notes-style carousel slides with Pillow and your chosen background images.
- [reference-carousel-adapter](skills/reference-carousel-adapter/SKILL.md): adapt **one** reference carousel to any product. Its [Pillow overlay script](skills/reference-carousel-adapter/scripts/render_overlay.py) keeps text editable and fails clearly on overflow; it does not generate backgrounds or call paid APIs.

Their prerequisites and scripts are documented in their own SKILL.md files. Reference creator images and private product assets are not included in this repository.

## Develop and publish

Shared maintained code lives in `src/social/`; vendored copies make each skill independently installable. Edit canonical files, then synchronize:

```bash
python3 tools/sync_social_skills.py
python3 tools/sync_social_skills.py --check
python3 -m unittest discover -s tests -v
python3 tools/package_social_skills.py
```

The packager creates two clean ZIPs in `dist/`. A [ready GitHub Actions workflow](docs/github-actions/social-skills.yml) tests Python 3.10/3.13 on Linux and Windows and uploads skill archives. To enable it, place it at `.github/workflows/social-skills.yml` using credentials with workflow-write access. It is supplied as a template in this release; CI for the two account skills is not automatically enabled; the independently added comment-analysis workflow remains active. Tests use synthetic fixtures; API keys, account dumps and creator images are not included. For legacy Node development only: `npm ci && npm run typecheck`.

## License

MIT — [LICENSE](LICENSE). Third-party account content remains the property of its owners and is not bundled in releases.
