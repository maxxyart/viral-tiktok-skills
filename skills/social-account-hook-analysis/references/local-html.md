# Interactive local HTML report

The hook report is a **single `report.html` that opens from disk**. It embeds covers, CSS and JavaScript; it must not require a server, external fonts, remote scripts or publication. Source links still open the original Instagram/TikTok posts. Keep the original covers, contact sheets, CSV, annotations and raw responses beside it for audit.

The format borrows the useful reading sequence of a deep research report while staying account- and topic-agnostic:

1. Hero with account, platform, capture date, publication span and four cohort KPIs.
2. Five or fewer short findings ordered by evidence strength. Each claim names its denominator, measured metric and caveat; link specific posts where possible.
3. Linked map of view multiple × comment rate, then top-five cover cards.
4. Expandable comparisons for text formula, visual format, character role and text × visual. Keep `n`, median, mean, comment rate, outlier concentration and peak/typical cover examples together.
5. Authored explanations: recurring formulas, counterexamples, what the account promotes, and a small test plan. Separate observed quotes, generalized formulas and proposed adaptations.
6. Publication-month table, searchable/sortable **row table** of every selected video, and collection/method limits. The video table keeps cover, original-language hook, views, view multiple, comment rate, duration, source link and labels together. Clickable headers sort metrics; filters and search work across the whole cohort.

When the user requests audio transcription, obtain it from actual audio rather than captions or a cover. Save `transcripts.json` as an array keyed by the selected video IDs, with `status`, original-language `transcript` and `opening_0_3s`. Transcribe the first three seconds from a separately clipped audio segment; a whole-clip ASR response is not reliable evidence for exact opening timing. The renderer adds both transcript fields to the row table, and its search includes them. Preserve `no_speech`, `uncertain` and errors as separate states; do not fabricate speech.

Use the bundled `scripts/hook_report.py` after `social.py analyze`. Its `--lang ru|en` controls the main section headings and navigation; standard metric labels remain in English. Author narrative in the user's language. The script renders the data but does not invent qualitative conclusions.

## `insights.json`

Write this after inspecting the cohort and `analysis.json`. `summary` is shown at the top; `sections` become detailed cards. Use real selected video IDs from `videos.json`, never row numbers. Optional `formula` requires one or two reference IDs. All free text is escaped by the renderer.

```json
{
  "summary": [
    {
      "title": "A concise finding",
      "text": "n, observed median or rate, comparison, and what remains uncertain.",
      "reference_ids": ["selected-video-id"]
    }
  ],
  "sections": [
    {
      "title": "Formulas to test",
      "items": [
        {
          "title": "Named mechanism",
          "text": "Evidence, visual execution, dispersion and caveat.",
          "formula": "[original-language formula]",
          "reference_ids": ["selected-video-id"],
          "adaptation": "A new test idea, clearly distinct from the source quote."
        }
      ]
    }
  ]
}
```

When no user product is specified, give a reusable test for an unspecified product. Only make product-specific recommendations when the product and audience are known. Do not copy sector-specific dimensions such as recipes, ingredients, health claims or a named company into the universal format. Include a dimension only when it is actually annotated across this cohort; don't create decorative empty charts.

Use cover evidence only for cover claims. A comment-keyword caption is an observed CTA, not evidence of sent messages, leads or sales. A newer post has had less time to accumulate views. The report should explicitly distinguish observed results from hypotheses and use comparable post age for any proposed follow-up test.

Before delivery, open the local HTML at desktop and narrow widths when possible. Check the map, summary, source links, expanders, filters and catalog; compare displayed numbers against `analysis.json`. If visual preview is unavailable, do not claim visual QA.
