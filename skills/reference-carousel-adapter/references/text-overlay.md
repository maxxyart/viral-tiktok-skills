# Text overlay: from reference to finished slides

The source session used clean 3:4 photos plus a separate Pillow render for colored, stepped text stickers. Its 1200 × 1600 output used Arial Regular for pink headings and Arial Bold for white body stickers. The first draft felt cramped, so horizontal/vertical sticker padding was increased. The white text felt too heavy, so an extra glyph stroke was removed. Treat those measurements as a case study, **not** universal defaults.

## Install the font first

For TikTok-native text, download **TikTok Sans** from the [official Google Fonts page](https://fonts.google.com/specimen/TikTok+Sans) (the [TikTok source repository](https://github.com/tiktok/TikTokSans) links to the same download). Extract the ZIP and install the `.ttf` font file in your operating system. The official family includes a **variable font**: this one file can render both regular and bold weights.

- macOS: open the `.ttf` in Font Book and select **Install**.
- Windows: right-click the `.ttf` and select **Install**.
- Linux: copy the `.ttf` into `~/.local/share/fonts/`, then run `fc-cache -f`.

Pass the **actual font file path** to both `--font-regular` and `--font-bold`. The sample config sets `weight: 400` and `weight: 700`; the renderer applies those values through the variable font's Weight axis. Alternatively, use two separate static files and remove `weight` from the styles. The sample `fonts/TikTokSans.ttf` path is illustrative: copy the downloaded file there or replace that path with its actual name. Do not let Pillow silently substitute its default bitmap font. TikTok Sans covers Latin, Greek and Cyrillic; for another script, select a font that supports the language. If the reference uses a different face (the source session used Arial), use the closest licensed match instead of forcing TikTok Sans.

## Measure the overlay, then set the parameters

Record for each text layer: font family and weight, size, text color, background color, stroke and width, alignment, top position, line spacing, horizontal/vertical padding, corner radius, and maximum width. Use the reference's **relative** proportions when its resolution differs from the output. Start with a consistent canvas (the source session used 1200 × 1600, 3:4); adapt to the target platform or supplied brief.

For a stepped sticker, each line gets its own rounded rectangle. Adjacent rectangles slightly overlap to make one readable shape. Leave visible air between the glyphs and the box edges. The background should support contrast without covering the main subject. A text stroke changes perceived weight: use it only if the reference actually has one. In the source session, removing the body-text stroke corrected an overly bold appearance.

Write the **final words** before drawing. Break lines by meaning, not merely by pixel width; check punctuation and product names. The renderer rejects lines that exceed `max_width` and blocks that cross the canvas edge. Fix the wording or style instead of hiding overflow with an automatic tiny font. Never render AI-generated words into a background and then cover them: request a clean background.

## Render

Install Pillow: `python3 -m pip install Pillow`. Copy `assets/example-config.json` into the project, set background paths and exact text, and edit styles to match the reference. The configuration's paths are relative to the JSON file. Then run:

```bash
python3 scripts/render_overlay.py path/to/carousel.json \
  --font-regular /absolute/path/to/TikTokSans.ttf \
  --font-bold /absolute/path/to/TikTokSans.ttf
```

`--font-regular` and `--font-bold` can be omitted only when `font_files` in the JSON points to valid files. Backgrounds must already have the target aspect ratio; set `allow_crop: true` on a slide only after checking the crop. Output PNGs go to each slide's `output` path. The script makes no image-generation API calls.

For a real product image or app screenshot, add an optional `asset_layers` array to that slide. The renderer places these assets **before** the text stickers, with no invented UI:

```json
"asset_layers": [{
  "path": "assets/real-product-screen.png",
  "width": 850,
  "top": 1050,
  "align": "center",
  "corner_radius": 24
}]
```

Use only an image supplied by the user or taken from their verified product. Inspect the crop and make sure the asset remains readable on a phone.

## Visual check

View the contact sheet to catch inconsistent hierarchy, then open every PNG at 100% and at approximate phone size. Check that the first slide reads in a glance; pink/white boxes have enough interior space; repeated titles occupy similar positions; no face, hand, screenshot, or product is hidden; all copy is spelled correctly; and the last slide delivers the promised payoff. If a line is too long, rewrite or rebreak it before shrinking the type. If the text feels heavy, compare font **weight** and stroke separately.
