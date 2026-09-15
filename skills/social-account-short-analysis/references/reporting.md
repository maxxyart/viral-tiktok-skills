# Report and delivery contract

The bundled HTML renderer creates a data report without requiring a web service. Covers and contact sheets are embedded as data URIs so a moved/copied `report.html` still displays them. No external fonts or scripts. Use local output links in the final answer, and real source post URLs inside the report. Do not publish private project recommendations or downloaded media without user authorization.

## Agent-authored insights

The renderer deliberately does not invent qualitative findings. Write `insights.json` in the user's language:

```json
{
  "sections": [
    {
      "title": "Best-supported formula",
      "items": [
        {
          "title": "Unexpected discovery",
          "text": "State sample size, observed result, visual details and caveats here.",
          "formula": "I'm sorry since WHEN did [platform] get this [feature]????",
          "reference_ids": ["actual-id-from-videos.json", "second-actual-id"],
          "adaptation": "Proposed product-specific hook; not a source quote."
        }
      ]
    },
    {
      "title": "What the account promotes",
      "items": [{"text": "Ground this in profile/caption/video evidence. State what remains inferred.", "reference_ids": []}]
    }
  ]
}
```

`formula` requires 1–2 selected reference IDs. IDs are resolved to original URLs, exact quotes, metrics and covers. No raw HTML is accepted in narrative fields. If only one example exists, cite it and label the formula exploratory; don't invent a second source. Without insights the renderer displays DATA DRAFT. To localize table headings or change layout, edit the report/template as needed; `--lang` sets document language only, it is not automatic translation.

## Short report

Scope/source/capture date → metrics → publication-month table → top five → topic and offer → data limits. No need for cover downloads unless requested. Main summary should fit a brief reading; detailed CSV can be separate.

## Hook report

Scope/source/capture date → summary → top five → text-axis, visual-axis, character-axis and cross-axis tables → original-language formulas with 1–2 references each → exceptions and uncertainty → product priorities and controlled test → contact sheets (20 per batch) → full selected-video catalog → methodology.

Show source quotes separately from formulas and proposed adaptations. Put cover evidence beside formula references, not just in a final gallery. Keep unavailable covers and unreadable text visible in coverage counts. If only one recurring person appears, say the cohort cannot compare different identities; expressions/framing may still vary.

## Validation before handoff

- CSV and HTML derive from the same selected IDs and unrounded baseline; all rows and formulas have matching references.
- Original-language strings remain intact; no fabricated emoji/words or post IDs.
- Report has insights, not only the data-draft skeleton. Numbers in narrative agree with analysis.json.
- Downloaded assets are inside the output, missing-image tiles are explicit, and media is truly decoded rather than renamed `.jpg` bytes.
- Open permitted preview and inspect desktop plus narrow layout: top-five table, formula reference blocks, contact sheet and catalog. If blocked or unavailable, do static checks and disclose visual review was not completed. Never work around a browser policy denial.
- The final answer links HTML and CSV, reports key findings and any material scope limitation. Retain raw files locally for repeatability. Do not promise automatic future recall merely because a Markdown library was saved.
