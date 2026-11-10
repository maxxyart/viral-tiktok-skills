# Read carousel slides: text and picture, one JSON line per slide

You read carousel slides for a hook analysis of a social account. The main model will
find the patterns from your table alone and never sees the images, so the text has to be
verbatim and the description concrete.

Slides (label = post.slide, then the image path):

{slides}
{hint_rules}
Read the images with the Read tool in the order listed, up to 8 per message (several Read
calls in one message). For EVERY label write one JSON object with exactly these keys:

{"post": "12", "slide": 3,
 "text": "every word on the slide, verbatim, lines joined with \n",
 "role": "hook | point | integration | cta | other",
 "people": "count, gender, rough age, face shown or hidden, what they do; or none",
 "background": "setting or backdrop, 2-6 words",
 "art_style": "photo | stock_photo | ai_illustration | illustration | comic | sketch | painting | 3d | text_only | screenshot | meme, then 2-5 words of detail",
 "text_style": "font kind, case, weight, colour, outline / shadow / box, size on the slide",
 "product_mention": "",
 "unreadable": false,
 "visual": "one sentence: what the picture shows"}

text:
- Every word printed or written on the slide, exactly as it stands: keep the author's
  typos, casing, punctuation, emoji, list numbers and circled numbers. Do not correct
  spelling or grammar.
- One line on the slide = one line in `text`, joined with \n. Order: top to bottom, left
  to right; speech bubbles in the order a reader follows them.
- Add nothing that is not on the slide: no speaker names (no "HE:", "SHE:"), no
  "Slide 2", no descriptions in brackets.
- A word you cannot make out: write [?] in its place.
- Readable text inside the picture (signs, sticky notes, labels on objects) counts.
- Leave out the platform UI and a small brand watermark or @handle in a corner; name it in
  `product_mention` instead.

role: hook = the title slide or the line that promises the payoff (usually slide 1);
point = a list item, step, rule, story beat or line of dialogue; integration = a product,
app, book, course or brand placed inside the content; cta = asks to follow, save, comment,
share, tap the profile or a link; other = anything else.

text_style: font kind (serif / sans / handwritten / hand-lettered / typewriter / marker),
case (CAPS / Title / lower), weight, colour, effects (outline, shadow, highlight box),
how big on the slide. Example: "hand-lettered CAPS, black crayon, no outline, large".

product_mention: "" when nothing is named or shown; else what (book, app, brand, service,
@handle) and how (cover photo, text line, "link in bio", corner watermark).

unreadable: true when a substantial part of the text could not be read.

Write all lines to {out} with the Write tool: one JSON object per line, no array, no code
fences, nothing else in the file. Then reply with ONE line only:
"<N> slides written, <M> unreadable". Never put the slide texts in the reply.
