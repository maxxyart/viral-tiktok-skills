# Text overlay for emotion + demo videos

The hook text is **not** part of the generated video. It is rendered as a transparent 1080 × 1920 PNG and burned over the animated clip at assembly. A typo or a new hook variant therefore costs one re-render, not a new generation. The same rules as the carousel guide apply: measure the reference, install the font first, write final words before drawing, check every frame.

## Install the font first

For TikTok-native captions, download **TikTok Sans** from the [official Google Fonts page](https://fonts.google.com/specimen/TikTok+Sans) (the [TikTok source repository](https://github.com/tiktok/TikTokSans) links to the same download). Extract the ZIP and install the `.ttf`:

- macOS: open the `.ttf` in Font Book and select **Install**.
- Windows: right-click the `.ttf` and select **Install**.
- Linux: copy the `.ttf` into `~/.local/share/fonts/`, then run `fc-cache -f`.

Pass the **actual font file path** to `--font`. TikTok Sans ships as a **variable font**; pick the weight with `--weight` (600 is close to the in-app caption, 700 for a heavier look). The in-app "Classic" caption font many creators use is Proxima Nova Semibold; it is commercial, so use it only with a licence. If the reference visibly uses another face, match that licensed font instead. Never let Pillow fall back to its default bitmap font: the renderer fails when the font file is missing. TikTok Sans covers Latin, Greek and Cyrillic.

## Measure the reference

Open the reference's first second full size and write down: font and weight, colour, halo or box, position (fraction of frame height), line count, and whether the caption stays over the demo part. Two looks cover almost every emotion hook:

| style | look | use for |
|---|---|---|
| `halo` | white text, soft blurred dark halo, no box | default hook: "Ur telling me…", "POV:", statements |
| `plate` | black text on a white rounded box per line | punchy labels, when the reference uses boxes |

## Size, lines, placement

- **Size follows length.** Short hook = big, long statement = smaller. The renderer picks the size from character count (clamped to 2–4 % of frame height); override with `--size` only to match a measured reference.
- **Balanced lines.** The renderer keeps the line count of a greedy wrap and then chooses breaks that make the widest line as narrow as possible, so no single word hangs on the last line. For a deliberate break, put `\n` in a `--text-file`. Break by meaning when you have a choice.
- **Never cover the eyes.** Text must clear the eyes and upper face. A short hook sits **above the face** (`--center-y 0.155` is a good start for a selfie framing). A longer statement may sit centred over the chin and neck. Check with `--preview still.png`.
- **Safe zone.** The block must stay between 6 % and 86 % of the height and inside 6 % side margins: TikTok's bottom caption, buttons and top bar cover the rest. The renderer rejects a block that leaves it. Shorten or move the text; do not squeeze it.
- **Halo strength.** Match the reference's contrast, not WCAG. Bright background: `--halo-alpha 170`; dark: `150`. The halo is soft, never a hard outline.
- **Emoji** only if the reference has them. Colour emoji need a colour-emoji font; if the output shows empty boxes, drop the emoji.

## Render

```bash
python3 -m pip install Pillow
python3 scripts/render_hook_overlay.py --text "Ur telling me I ... for 6 YEARS and never knew this?!?!?!" \
  --font "/absolute/path/TikTokSans.ttf" --weight 600 \
  --out work/overlay_hook1.png --preview work/still1.png
```

The script prints the final lines and writes `overlay_hook1_preview.jpg` with the text over your still.

## Hook over the demo?

In many references the hook stays on screen for the whole video. Keep it over the demo (`media.py assemble --overlay-on-demo`) only if it does not collide with text inside the demo recording. Otherwise show it on the hook part only.

## Visual check

Look at every preview and every final at phone size. Check: exact spelling and punctuation; no orphan word; eyes and mouth visible; nothing hidden by TikTok UI zones; the same position across the variants of one series; text readable on the brightest and darkest frame of the clip.
