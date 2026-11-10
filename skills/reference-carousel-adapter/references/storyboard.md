# Storyboard with ticks

The storyboard is where the user picks hooks and a visual style. The block order is in SKILL.md; this file covers how the ticks are kept and read.

## Saving ticks

- Publish with `capabilities: {db: {}}` and load the `artifact-capabilities` skill before writing the page script.
- One collection, `approvals`, one document per option: `{ok, kind, hook, at}`. `kind` is `"topic"` for hooks and `"visual"` for styles. Visual ids get a prefix (`visual-aura`), so they never clash with hook ids.
- Each checkbox carries `data-id` and `data-kind` and starts `disabled` until the database answers.
- `const db = await window.claude?.use?.('db')`. When it is `null`, enable the boxes anyway and say on the page that ticks are not saved here.
- Subscribe once with `onSnapshot`; a 10 s timer shows "not loaded yet" and is cleared on the first server snapshot or an error.
- One write at a time per document: keep a `wanted` and a `writing` map and loop until they match, so fast clicking does not race. On `invalid_argument` say the viewer has no right to save.
- Count hooks and styles separately (`Ticked: N of 12`, `Ticked: N of 3`).

## Reading them back

- `ArtifactData` (load it with ToolSearch), `action: "list"`, `collection: "approvals"`. Keep documents with `ok: true` and split them by `kind`.
- An empty collection means nothing is ticked yet: ask, do not guess.
- No ticked style: ask which one before rendering. Several ticked styles: render the first hook in each and let the user choose.

## Before publishing

- Render the page at 390 px width in headless Chrome: no horizontal scroll, every image path resolves, no template placeholders left.
- Publish only the images the page references (`grep -o 'img/[^"]*'`), with `root` set to the storyboard folder.
