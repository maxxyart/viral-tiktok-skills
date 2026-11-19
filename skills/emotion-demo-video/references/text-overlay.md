# Captions for emotion + demo videos

Captions are not part of the generated video. Each one is a transparent PNG at the video size, burned over its part at assembly. A typo or a new hook variant costs one re-render, never a new generation.

## Install the fonts first

- **TikTok Sans**, the font of TikTok's own captions: download from the [Google Fonts page](https://fonts.google.com/specimen/TikTok+Sans) (the [TikTok repository](https://github.com/tiktok/TikTokSans) links the same files), extract the ZIP and install the variable `.ttf`. macOS: open it in Font Book and select **Install** (file lands in `~/Library/Fonts/`). Windows: right-click → **Install**. Linux: copy it to `~/.local/share/fonts/` and run `fc-cache -f`. Pass the file path to `--font`.
- **Colour emoji** for a trailing emoji: Apple Color Emoji ships with macOS; on Linux install Noto Color Emoji; Windows has Segoe UI Emoji. If none is found the renderer stops and asks for `--emoji-font`. TikTok Sans has no emoji glyphs, so the renderer draws the trailing emoji separately in colour.

The renderer fails when the font file is missing instead of falling back to a bitmap font.

## Styles

| style | look | weight | where |
|---|---|---|---|
| `tiktok` | white, tight dark halo, no box (TikTok "Classic") | 600 | the hook, most references |
| `neon` | pink-white core, magenta glow (TikTok "Neon") | 700 | short phrase over the demo |
| `halo` | white with a soft wide shadow | font default | statements over busy frames |
| `plate` | dark text on white rounded plates | font default | references that use boxes |

Pick the style the reference uses for each part. `--weight` overrides the default on a variable font.

## Measure, then calibrate

Size and position come from the reference, not from a guess.

1. Measure: `media.py caption-lines FRAME --y0 A --y1 B [--mode neon]`. It finds the caption rows by colour inside the band and prints every line's top, bottom and width share, the block centre and the line pitch. Use the hook's first frame for the hook and a demo frame (`media.py frame ref.mp4 out.png --n <first demo frame + 20>`) for the demo phrase. Keep the band tight: white buttons and cards inside it count as text. Thin rows (UI edges) are dropped automatically.
2. Calibrate: pass the widest measured line's text as `--calib` and its share as `--calib-frac`. The font size is chosen so that this line would be exactly as wide in TikTok Sans as in the reference. Pass `--center-y` and `--line-pitch` from the same run.
3. Render at the video size (`--canvas 720x1280` for Wan 720P) with `--preview` on a frame of the new clip or the demo still, and read the printed block position and widest line.

In the test reference the hook measured 0.743 of the width at centre 0.29 and rendered at 46 px against 45 px picked by eye; the demo Neon phrase measured 0.669 at centre 0.739 and rendered at 37 px.

## Lines and placement

- Lines are balanced: the renderer keeps the greedy line count, then picks the breaks that make the widest line narrowest, so no word hangs alone. `\n` in `--text` forces a break.
- The trailing emoji sits at the end of the last line, centred on the letters, and counts toward that line's width. Emoji in the middle of the text is rejected.
- Never cover the eyes. On a close selfie the hook usually sits on the forehead or above the head, where the reference had it.
- Safe zone: the block must stay between 6 % and 86 % of the height and inside 6 % side margins (TikTok's top bar, buttons and description cover the rest). The renderer rejects a block outside it. The demo phrase fits around 0.70–0.80.
- On the demo, put the phrase on an empty part of the screen. If it covers app text, re-render the demo screen with that area clear rather than moving the caption out of the reference's place.

## Hook over the demo?

Default: the hook caption is shown over the hook only, and the demo gets its own short phrase. Keep the hook over the demo (`assemble --hook-overlay-on-demo`) only when the reference does that and it does not collide with the demo's text.

## Visual check

Look at both previews and at the final at phone size: exact spelling and punctuation, line breaks by meaning, the emoji in colour (not an empty box), eyes and mouth visible, nothing under TikTok UI, the caption readable on the brightest and darkest frame.
