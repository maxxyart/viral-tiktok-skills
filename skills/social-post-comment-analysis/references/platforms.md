# ScrapeCreators adapters

Verified against the [official OpenAPI spec](https://docs.scrapecreators.com/openapi.json)
on 2026-09-15. Refresh the relevant endpoint contract if an actual schema error
occurs; do not guess replacement endpoints or silently return an empty dataset.

| Platform | Comments | Selected replies |
| --- | --- | --- |
| TikTok | `/v1/tiktok/video/comments` | `/v1/tiktok/video/comment/replies` |
| Instagram | `/v2/instagram/post/comments` | `/v1/instagram/post/comment/replies` |

All use GET with `x-api-key`. Comments require `url`, subsequent pages use the exact
returned `cursor`. Replies also require `comment_id` (parent's raw ID). Response
arrays are `comments` for both platforms and both endpoints. Follow `has_more`
where present; Instagram comments can expose only a cursor. Stop on exhausted or
repeated/missing cursors and duplicate-only pages; record the reason.

TikTok: ID `cid`, likes `digg_count`, timestamp `create_time` (epoch seconds), user
`unique_id`/`nickname`/`uid`, reply count `reply_comment_total`, embedded previews
`reply_comment`. `reply_id` identifies the root; `reply_to_reply_id` may identify a
specific reply. Do not trust `thread_has_more=false` as proof all replies are inline.

Instagram: ID `id` (some saved formats use `pk`), likes `comment_like_count`, timestamp
`created_at`, user `username`/`id`, reply count `child_comment_count` **may be null**,
embedded `replies`, `parent_comment_id`. Missing likes/reply counts stay null, not 0.
`include_replies=true` returns only the first replies page per comment and is
[documented as 15 credits per request](https://scrapecreators.com/instagram-comments-api),
even if no replies are found. The collector never sets this flag; select individual
threads instead. Do not imply both platforms expose identical reply completeness.

Built-in budgets cap HTTP attempts and elapsed time, not guaranteed billed credits.
`credits_charged` is summed only when returned. Timeouts/network failures can have
unknown charges; do not call them free. Auth/payment/not-found failures stop, while
429/5xx/network errors get at most one retry within the original budget.

Use canonical public post URLs. Short links should be resolved through an existing
browser/provider read first; do not send arbitrary hosts or unsupported account URLs
to the collector. The scraper uses a fixed ScrapeCreators API origin.
