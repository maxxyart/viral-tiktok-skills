# Collection contract

## Provider and transport

Prefer callable ScrapeCreators MCP tools. Discover their schema at runtime. Save each page response (or its extracted JSON data) as `page-0001.json`, `page-0002.json`, etc. Save the profile separately. The importer understands plain responses, `data` envelopes, `structuredContent`, and one JSON text MCP content block. If the provider returns multiple blocks, extract the JSON payload explicitly. Never treat a success-looking tool wrapper as proof the nested request succeeded.

Fallbacks, only if consistent with the user's request:

- `--transport cli`: installed, authenticated official `scrapecreators`; check its `--help` before use. The script runs argument arrays without a shell and never prints credentials.
- `--transport api`: environment `SCRAPE_CREATORS_API_KEY` or `SCRAPECREATORS_API_KEY`. No automatic discovery of private shell files, no token in URLs/logs, no credit purchases. Secrets can be loaded through an explicit user-approved environment setup; this helper does not search unrelated files.

Record the real transport. Imported pages require an original capture timestamp. If replaying a CLI/API export, pass `--import-transport cli` / `--import-transport api`; the default is `mcp`. The source capture time must survive replay. Don't relabel an old dump as a fresh scrape.

## Endpoints and fields

Verified against official docs on 2026-09-15; check current schemas when an adapter fails.

| Platform | Feed | Pagination | Media / counters |
|---|---|---|---|
| Instagram | `/v1/instagram/user/reels` | `paging_info.max_id` / top-level `max_id`, `more_available` | `items[].media` or trimmed `items[]`; `created_at` ISO / `taken_at` Unix; `play_count` (fallback fields recorded), `comment_count`, `like_count` |
| TikTok | `/v3/tiktok/profile/videos`, `sort_by=latest` | `max_cursor`, `has_more` | `aweme_list[]`; `create_time`; `statistics.play_count`, `digg_count`, `comment_count`, `share_count`, `collect_count`; `video.duration` milliseconds |

Profiles: `/v1/instagram/profile`, `/v1/tiktok/profile`. For Instagram, a numeric user ID can make requests faster. Missing captions or missing/ambiguous view counters may require `/v1/instagram/post?url=...`; preserve old and new raw evidence and record the actual metric capture time when enriching. Do not blend Instagram and cross-posted Facebook views in one field.

Instagram's Reels feed may omit pinned reels and captions. Thus “all available feed reels” is distinct from “all posts on the account.” If literal complete-account coverage is required, reconcile pinned/profile-post inventory and details using the current endpoint schema before claiming completeness. The bundled feed collector deliberately does not claim that reconciliation.

TikTok feeds can contain photo posts. Exclude `image_post_info` and known photo types from a videos-only cohort, count exclusions, and paginate until the requested number of **videos**, not feed items. If a nonempty public account returns an empty feed, inspect region/access errors; an explicitly selected relevant region may help. Don't keep retrying a private/deleted account indefinitely.

Official sources:

- [Instagram Reels](https://docs.scrapecreators.com/v1/instagram/user/reels/)
- [Instagram post details](https://docs.scrapecreators.com/v1/instagram/post/)
- [TikTok profile videos](https://docs.scrapecreators.com/v3/tiktok/profile/videos/)
- [MCP integration](https://docs.scrapecreators.com/integrations/mcp/)
- [CLI integration](https://docs.scrapecreators.com/integrations/cli/)

## Pagination and completeness

Deduplicate by stable platform video ID; sort by full publication timestamps, then select latest N. Pinned display order is not chronological. Read full pages rather than stopping inside a page. The collector reads two additional pages after reaching N; explicit pinned items do not break chronological checks. If unpinned dates are missing or increase across pages, it continues to source exhaustion or the page cap instead of pretending a fixed buffer proves latest ordering.

Stop when the source explicitly says no more. For latest N, an observed chronological boundary can finish the available-feed scope earlier. Missing/looping cursors, repeated pages, empty pages with more/unknown state, schema errors, auth/credit errors and max-page limits produce partial status. “No more feed pages” still does not prove the provider exposes deleted/private/pinned content.

Default max pages = 100, overridable. It is a safety cap, not an implicit claim of all-history completion. If it is reached, disclose progress and continue with a deliberate larger limit or a narrower user-approved scope. Don't silently truncate “all”. Avoid ending a date-range scrape after one old pinned video; collect an ordered boundary or exhaust, then filter and recalculate the entire baseline.

Use a fresh output directory per capture. No silent merging of old metrics with fresh rows. A resume/replay uses saved raw pages and their capture provenance. Compare historical metrics only when both dated snapshots actually exist.

## Outputs

- `raw/page-*.json`: unchanged provider page bodies.
- `profile.json` or explicit unavailable status; MCP users save the profile separately.
- `snapshot.json`: scope, count, transport, time, stop reason, ordering/coverage, limitations.
- `fetched-videos.json`: buffer/all fetched unique rows without cohort multiples.
- `videos.json`: exact selected cohort, stable IDs and rank; unavailable values are null.
- `videos.csv`, `months.csv`, `analysis.json`, `analyzed-videos.json`: calculations for that cohort only.

Normalized view counts retain `views_source_field`. Zero is a real value and must not trigger another fallback counter. Missing dates are not Unix epoch. Preserve full captions; they can contain offer/CTA evidence. CSV escapes leading spreadsheet formula characters; raw JSON preserves exact text.
