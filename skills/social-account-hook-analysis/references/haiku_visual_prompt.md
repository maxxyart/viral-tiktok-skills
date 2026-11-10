# Visual pass over carousel slides (contact sheets)

You describe how carousel slides look, for a hook analysis of a social account. The slide
text is already extracted by OCR. Your job is the picture, plus one check: the biggest text.

Read each sheet below with the Read tool, one image per call, in this order:

{sheets}

Every tile has a label "P.S" in the coloured strip above it: P = post number, S = slide number.
Tiles of one post share the strip colour; the colour flips when the next post starts. The
labels under each sheet path above are the tiles in reading order (left to right, then the
next row), so you can map tiles even if a label is hard to read.

For EVERY label write one JSON object per line with exactly these keys:

{"post": "12", "slide": 3,
 "people": "who is in the frame: count, gender, rough age, face visible or hidden; or none",
 "background": "setting or backdrop, 2-6 words",
 "style": "photo | illustration | comic | sketch | painting | 3d | text_design | screenshot | meme, then 2-5 words of detail",
 "font": "look of the main text, 3-8 words: weight, case, serif / sans / hand-lettered, colour, effects",
 "text_amount": "none | short | medium | dense",
 "text_kind": "none | printed | handwritten | stylized",
 "headline": "the largest text on the tile, verbatim as far as you can read it, max 12 words; empty string if none",
 "visual": "one sentence: what the picture shows (subject, action, composition)"}

Rules:
- `post` is a string, `slide` a number, both copied from the label.
- `text_amount`: short = 1-10 words, medium = 11-40, dense = more than 40.
- `text_kind`: printed = a regular font; handwritten = real or imitated handwriting;
  stylized = decorative, distorted, outlined or overlapping letters that are hard to read.
- Do not transcribe body text. `headline` only: the biggest line or two.
- Fill every field for every tile, even when a post repeats one style; keep values short.
- A tile you cannot make out still gets its line, with your best guess and "unclear": true.
- Describe only what is visible. No judgement of quality.

Write all lines to {out} with the Write tool: one JSON object per line, no array, no code
fences, nothing else in the file. Then reply with ONE line only:
"<N> tiles written, <M> unclear". Never put the descriptions in the reply.
