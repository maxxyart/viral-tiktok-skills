# Cover annotation and pattern discovery

Create one card for every `videos.json` ID. Use IDs, not row positions, to join cards to metrics. Contact-sheet rank is only a navigation label.

```json
[
  {
    "id": "platform-video-id-from-videos.json",
    "hook_text_exact": "I'm sorry since WHEN did Instagram get this update????",
    "hook_status": "legible",
    "text_formula": "I'm sorry since WHEN did [platform] get this [feature]????",
    "visual_format": "extreme close-up + shocked expression + translucent text bar",
    "character_role": "recurring creator",
    "evidence_scope": "cover_only",
    "embedded_text_exact": null,
    "framing": "face fills frame",
    "expression": "wide eyes, open mouth, hand on head",
    "text_treatment": "white text, black translucent rectangle",
    "setting": "indoor everyday background",
    "identity_evidence": "same recurring face; identity not independently verified",
    "transcription_notes": "",
    "opening_evidence": null
  }
]
```

Allowed `hook_status`: `legible`, `partial`, `no_text`, `unreadable`, `missing_cover`.
Allowed `evidence_scope`: `cover_only`, `opening_frames`, `full_video`.
Text/visual/character labels must be nonempty; use `unassigned` or `unknown` explicitly.

Exact quotes preserve case, punctuation, typos and visible emoji. If an emoji is unclear, mark `[illegible emoji]` and partial status; don't silently omit it and call the result verbatim. Store original line breaks when meaningful. Quotes copied from a caption are caption evidence, not cover text. A tiny automatic subtitle may be only a partial sentence, not the main hook.

Embedded screenshot text may itself be the attention hook. Record both the dominant headline and embedded text, then interpret their role from composition. Do not mechanically exclude all embedded text from hook analysis.

Annotate before inspecting performance where practical to reduce winner-driven labeling. Use the same abstraction level for high and low performers. Cluster formulas by mechanism rather than arbitrary exact-word groups, while retaining exact wording for repeat analysis. Keep broad axis labels consistent; use auxiliary fields for finer details instead of creating a new category for each winner.

## Opening-video requests

To analyze a spoken/first-second hook, inspect actual footage or timestamped frames/transcripts. At minimum record sampled time ranges, spoken text, on-screen text, action, cut and reveal timestamps separately. A transcript establishes speech, not the pictured action; a cover establishes neither timing nor audio. Do not use a thumbnail to claim the creator “cuts after 0.5 seconds”.

## Recommendations and formula library

Tie every priority to a measured pattern and 1–2 reference posts (ideally peak and typical). Keep source formulas English when references are English, Spanish when Spanish, etc. Write commentary in the user's language. Adaptations are new copy, clearly labeled, and need truthful experience/source claims.

Match the user's actual product, audience, production ability and goal from available project context. An app referenced in the source account is not automatically the user's app. A hook associated with creator-software views does not prove it will work for wellness. If the source evidence is cover-only, visual sequencing suggestions are hypotheses for a test.

Prefer a small factorial test: for example 2 text formulas × 2 visuals × 3 executions = 12 videos, matched topics and similar publishing conditions. This enables comparing one axis while holding the other constant. Define a consistent observation age (e.g. seven days), account-relative view median, CR, and any actually available downstream metric. Don't invent a retention/CTR baseline when public data cannot expose it.

For a saved library, include source quote, source URL/cover, generalized formula, view/CR snapshot, n/evidence strength, product adaptations and test result fields. The report and library should preserve the difference between observed winners and untested suggestions.
