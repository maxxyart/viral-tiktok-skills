# Viral Camp — Social Account Skills

Research **Instagram Reels and TikTok videos** with ScrapeCreators, turn observed hooks into referenced formulas, and adapt them to your product. Five skills cover account research, hook research, audience comments and carousel production. The two updated account skills are independently installable in Claude Code, Codex and other SKILL.md-compatible agents. The repository URL remains `maxxyart/viral-tiktok-skills` for existing users.

| Skill | Outcome |
|---|---|
| **[Social Account Short Analysis (Viral Camp)](skills/social-account-short-analysis/SKILL.md)** | CSV + concise HTML: views and comments totals/means/medians, comment rates, publication-month cohorts, top five with virality multiples, topic and offer. |
| **[Social Account Hook Analysis (Viral Camp)](skills/social-account-hook-analysis/SKILL.md)** | Latest 60 videos by default; covers and sheets of 20; optional real-audio transcription; text formulas × visuals × character roles; interactive local HTML with a sortable all-video table, linked evidence and a controlled test plan. |
| **[Social Post Comment Analysis (Viral Camp)](skills/social-post-comment-analysis/SKILL.md)** | Bounded Instagram/TikTok comment collection, CSV, semantic audience themes, root/reply statistics and product experiments. |

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

### Requirements

- **Python 3.10+**. Short analysis uses only the standard library.
- **Pillow** for hook cover downloads/contact sheets: `python3 -m pip install Pillow`. Optional `pillow-heif` enables HEIC decoding. Prefer a virtual environment where appropriate.
- A connected **ScrapeCreators MCP**, or authenticated official `scrapecreators` CLI, or `SCRAPE_CREATORS_API_KEY` in the environment for REST fallback. [Provider integration docs](https://docs.scrapecreators.com/integrations/mcp/).
- An agent capable of reading images for hook research. Audio transcription is optional; it requires `ffmpeg` and a Gemini API key. Cover-only reports do not need a Gemini/xAI key.

Use the requested transport. CLI/REST is never described as MCP. Raw MCP pages can be imported without repeating API requests. No automatic key search through shell configuration and no automatic credit purchases.

## Ask the agent

> Use $social-account-short-analysis to analyze all available Reels from this Instagram account. Save CSV and a concise HTML report.

> Сделай разбор 60 последних роликов TikTok: обложки по 20, точные хуки, формулы × визуал, рекомендации для моего продукта. Используй $social-account-hook-analysis и ScrapeCreators MCP.

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

# Hook analysis: build image evidence, then let the agent inspect and write cards.json
python3 src/social/covers.py --out runs/instagram-ACCOUNT
# Only if audio was requested: preview scope, then transcribe actual video audio.
# This reuses saved feed pages and does not call ScrapeCreators again.
python3 src/social/audio_transcribe.py --out runs/instagram-ACCOUNT --dry-run
python3 src/social/audio_transcribe.py --out runs/instagram-ACCOUNT
python3 src/social/covers.py --out runs/instagram-ACCOUNT --sheets-only
# The agent inspects covers/audio and writes cards.json, including uncertain rows.
python3 src/social/social.py analyze --out runs/instagram-ACCOUNT \
  --cards runs/instagram-ACCOUNT/cards.json

# Agent writes grounded insights.json; the renderer does not invent findings
python3 skills/social-account-hook-analysis/scripts/hook_report.py --out runs/instagram-ACCOUNT \
  --insights runs/instagram-ACCOUNT/insights.json --lang ru
```

`--max-pages` defaults to 100. A cap or collection failure returns exit code **2** with partial artifacts; it does not mean all videos were collected. The agent must inspect `snapshot.json`. The feed helper supports latest-N and all-available scope; date-range requests require an ordered/exhaustive capture, filtering and recalculating the cohort as described in the skill. The audio helper supports both TikTok and Instagram and caches each selected video; `--dry-run` makes no downloads or Gemini calls. It does not perform full-video visual analysis. `--lang ru|en` selects the hook report's main headings and navigation; standard metric labels remain in English, and narrative language comes from the agent's insights. The shared `src/social/report.py` remains the concise renderer for the short-analysis skill.

## Artifacts and metrics

- `report.html`: portable, self-contained hook report with embedded covers, evidence map, linked examples and searchable/sortable table of every selected video.
- `videos.csv`, `months.csv`: exact selected cohort and publication-month calculations.
- With requested audio: `transcripts.json`, `audio_usage.json`, and `videos_with_transcripts.csv` with original-language full speech and separately transcribed first three seconds.
- `analysis.json`: reproducible metrics and hook patterns; `cards.json`: agent's visual annotations.
- `snapshot.json`, `raw/`, `videos.json`, `fetched-videos.json`: provenance and auditable scope.
- `covers/`, `sheets/`: original-ratio cover evidence and labeled batches of 20.

Comment rate = comments/views × 100. The report distinguishes mean, median and weighted rates, with missing-data coverage. Virality is a **view multiple of the selected cohort median**, not a prediction, probability, or shares rate. Publication-month totals are cumulative views at capture time, not views earned during each month. Instagram feed limitations, missing captions and Instagram-only play counts are disclosed. Single-example patterns remain hypotheses; n ≥ 3 is an observation, not causal proof.

## Upgrade from the old skills

| Old name | New name |
|---|---|
| `tiktok-account-short-analysis` | `social-account-short-analysis` |
| `tiktok-account-hook-analysis` | `social-account-hook-analysis` |

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


## Existing carousel workflows

These two skills remain unchanged:

- [carousel-account-patterns](skills/carousel-account-patterns/SKILL.md): TikTok photo-post formula research using ScrapeCreators + Gemini, with optional xAI fallback.
- [hook-notes-carousel](skills/hook-notes-carousel/SKILL.md): render hook-photo + iOS Notes-style carousel slides with Pillow and your chosen background images.

Their prerequisites and scripts are documented in their own SKILL.md files. Existing generated carousel work is not part of this upgrade.

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
