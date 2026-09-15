# Viral Camp social analysis upgrade — 2026-09-15

This audit covers the previous two TikTok analysis skills, their scripts, and the account-analysis session that motivated the update. It is a method audit, not a fresh claim about any creator's performance. The carousel skills are outside the change.

| Observed issue | Correction in the new skills |
|---|---|
| Short analysis supported TikTok only; hook skill had a TikTok name despite Instagram support. | Two platform-neutral skills with the requested Viral Camp display names and explicit platform parsing. |
| A profile URL ending in `/reels/` could become handle `reels`. | Host-aware profile parsing; ambiguous bare handles require platform context. |
| Fetch stopped after first N feed items; no ID deduplication; mixed photo posts possible. | Stable-ID deduplication, videos-only filtering, complete-page reads, timestamp sorting and extra boundary pages. Reordering forces exhaustion or partial status. |
| Old pinned/cached item could stop collection; capped datasets could look complete. | Explicit collection stop reason, source-exhaustion flag, scope/order checks and partial exit status. Instagram feed exclusions remain disclosed. |
| Cached videos retained old counters while new videos had fresh counters. | Fresh snapshot directory; no invisible mixed-age cache. Replay keeps original capture timestamp. |
| Missing counters became `0`; `or` fallback replaced legitimate zero views. | Null-aware metric mapping with view-field provenance; zero remains zero. |
| Different engagement definitions across reports; missing weighted CR; summed rates risk. | Explicit CR definitions, complete-pair weighted denominator, coverage counts and no sum of rates/multiples. |
| Rounded median in display could obscure the exact baseline; buffered rows exported with latest-60 multiples. | Separate fetched buffer from selected cohort; full-precision math and cohort-specific exports. |
| Monthly publication cohorts were interpreted as historical account dynamics or saturation. | Explain cumulative snapshot versus views earned per month; age/period confounding and within-month group summaries. |
| Cover observations were extended into claims about first-second edits and product reveal timing. | Evidence scope per card; footage/transcript evidence required for time-based assertions. Proposed sequences labeled as tests. |
| Exact quotes were sometimes normalized, punctuation repeated from a common template, unclear emojis omitted. | Raw quote versus normalized formula stored separately; individual-image review; partial/illegible status instead of guessing. |
| Embedded screenshot text was categorically excluded as a hook. | Preserve embedded text and assess whether it is the dominant hook from layout. |
| Rare formulas were thrown into unassigned, or a single winner was ranked as proven. | Retain labeled singletons and pairs with explicit evidence strength; peak plus typical references. |
| Formula and visual co-occurred, but recommendations implied independent/causal effects. | Separate axes and cross-axis stats; confounding acknowledged; factorial tests proposed. |
| Comment CTA was treated as proof of monetization or automatic messages. | Distinguish observed CTA from leads, sales, automation and sentiment, which require evidence. |
| CLI access described as MCP. | Actual transport recorded and disclosed; MCP import path avoids a duplicate paid scrape. |
| Cover resizing cropped original images; renamed bytes could masquerade as JPEG. | Decode and convert images; contain/letterbox rather than crop; keep failed-cover rows. |
| HTML referenced a local image folder and visual preview failed. | Embedded image assets; draft flag until insights added; explicitly distinguish static checks from visual review. |
| Instructions hard-coded Claude home paths, model providers and automatic subagent thresholds. | Skill-relative scripts, native vision by default, optional provider use and authorization-aware delegation. |
| Saved Markdown was presented as guaranteed future memory. | Library linked as a project artifact; no promise of automatic recall. |

## What remains deliberately limited

- A public feed cannot guarantee visibility of private, deleted or provider-omitted posts.
- Instagram pinned-post reconciliation and post-detail enrichment are guided workflows, not silently assumed completed by the feed helper.
- Native image inspection and qualitative analysis require an agent; the HTML generator does not generate or certify insights.
- Cover analysis cannot measure retention, qualified leads or conversion.
- No TikTok/Instagram live account is hard-coded in the new tests. Offline fixtures exercise both response shapes and edge cases without redistributing creator media or spending API credits.

## Release checks

Run `python3 tools/sync_social_skills.py --check`, `python3 -m unittest discover -s tests -v`, and `python3 tools/package_social_skills.py`. Validate both SKILL.md frontmatters with the skill-creator validator where available. The supplied GitHub Actions template repeats portable offline tests and packages two installable ZIPs after activation by someone with workflow-write access. CI is not enabled by this release. These checks validate mechanics, not future model reasoning or external API uptime.

Release validation: 15 offline tests passed locally with Pillow, both skills passed the skill-creator validator, and the unchanged legacy TypeScript code passed `npm run typecheck`. Replaying the session's saved 60-reel Instagram sample reproduced 2,498,761 total views and a 2,753.5 median without a fresh scrape. That sample is not distributed. Live TikTok behavior and the Linux/Windows CI matrix have not been executed as part of this release.
