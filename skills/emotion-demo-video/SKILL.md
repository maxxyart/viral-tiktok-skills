---
name: emotion-demo-video
description: Make a short vertical "emotion hook + product demo" video from a TikTok/Instagram reference. Cuts the reference's emotional hook frame-accurately, puts the user's AI character into its first frame (GPT Image 2.6 on kie.ai), re-renders the hook with the reference's exact motion and timing (Wan 3.0 video edit on kie.ai), adds TikTok-native captions measured from the reference, and joins the user's product demo under the reference sound. Asks for the character and the demo; never invents them. Use for "emotion + demo", "shock face + app screen" and "сделай видео эмоции как в референсе"; use reference-reel-clone for talking reels and reference-carousel-adapter for photo carousels.
---

# Emotion hook + demo video

Format: 3–6 s of a person reacting (shock, "wait, what?", facepalm, open mouth) with a hook caption, then the product screen that answers the hook, often with its own short caption. The reference gives the **motion, timing, framing, caption layout and sound**. The face, product and words are the user's.

How it works: the reference itself is the scene. Its hook clip is the motion source, its first frame gets the user's character, and Wan 3.0 re-renders the clip with the new person and the same movements. No donor backgrounds and no free-form animation prompt.

**Video is made at 720p.** Wan renders the hook at 720P (720×1280), and the captions, the demo and both finals are 720×1280 at 30 fps. Do not switch to 1080P unless the user asks for it.

## 0. Ask for the inputs (never assume)

Ask for everything missing in one message, then wait. Use nothing from other projects.

1. **Reference** – TikTok/Instagram URL of an emotion + demo post. The hook should be one continuous selfie shot with no cuts inside it.
2. **Character** – a clear selfie or face close-up of the user's AI character plus a character sheet (front close-up, profile, full body). With no sheet, suggest making one first and stop. Ask whether the video should keep the reference's outfit (safer, see step 5) or the character's own.
3. **Demo** – the user's real product: a screen recording (mp4/mov) or a screenshot or rendered app screen at 9:16 that shows what the hook promises. Never fake UI.
4. **Product and audience** – read `CLAUDE.md` / `AGENTS.md` / a brief: the pain the demo solves, audience, brand rules.
5. **Access and tools** – `KIE_API_KEY` ([kie.ai/api-key](https://kie.ai/api-key)) in the environment or an `.env` path; optional `SCRAPE_CREATORS_API_KEY` ([ScrapeCreators](https://scrapecreators.com)) for watermark-free TikTok downloads with metrics, otherwise `yt-dlp`; `ffmpeg`; Python 3.9+ with Pillow; [TikTok Sans](https://fonts.google.com/specimen/TikTok+Sans) and a colour emoji font for captions ([text-overlay.md](references/text-overlay.md)).

Work in the user's project:

```
assets/characters/<name>/      selfie, sheet, outfit variants
assets/demos/                  screen recordings and app screens
emotion-demo/<slug>/           reference, hook, swapped frame, Wan clips, captions, finals, kie_jobs.jsonl
```

Scripts: `scripts/media.py` (ffmpeg + Pillow), `scripts/kie.py` (kie.ai, standard library), `scripts/render_hook_overlay.py` (captions). Run each with `--help` for every option. Below, `W=emotion-demo/<slug>`.

## 1. Fetch and cut the reference

```bash
python3 scripts/media.py --env-file .env fetch "<url>" $W/ref.mp4          # + ref.meta.json: views, saves, sound link
python3 scripts/media.py find-cut $W/ref.mp4 $W/cut                         # scene cuts + labelled frame strips
python3 scripts/media.py cut-hook $W/ref.mp4 --frames <N> --out $W/hook.mp4 --first-frame $W/hook_frame1.jpg
python3 scripts/media.py sheet $W/hook.mp4 $W/hook_sheet.jpg
```

- `find-cut` prints the first frame of the new scene. Open its strip and confirm by eye: `N` is the first demo frame, so the hook is frames `0..N-1`. If no cut is found, lower `--threshold` or read the contact sheet.
- From the hook sheet write down the beats (e.g. hand on forehead, eyes down → pulls the phone back, mouth open in shock → points up → salute), the outfit, nails, jewellery, light and props. They go into both prompts.
- Note the caption: text, lines, position, style (white Classic or Neon), emoji, and whether it stays over the demo. Note the demo length (`ref` duration minus the hook) and its caption.

## 2. Measure both captions

```bash
python3 scripts/media.py caption-lines $W/hook_frame1.jpg --y0 0.15 --y1 0.45
python3 scripts/media.py frame $W/ref.mp4 $W/ref_demo.png --n <N+20>
python3 scripts/media.py caption-lines $W/ref_demo.png --mode neon --y0 0.6 --y1 0.86
```

Keep the band (`--y0/--y1`) tight around the caption: white UI inside it counts as text. Each run prints `--calib-frac`, `--center-y` and `--line-pitch` for step 6; `--calib` is the text of the widest measured line.

## 3. Texts → the user picks

Offer 3 hooks in the reference's formula and 2–3 short demo phrases (what the app shows, in plain words, in the reference's caption tone). Vary the numbers and verbs between options. Say which you recommend and why, then wait. Templates: [prompts.md](references/prompts.md#3-hook-and-demo-phrase).

## 4. Character into the first frame (GPT Image 2.6)

Write `$W/swap_prompt.txt` from the template in [prompts.md](references/prompts.md#1-first-frame-swap-gpt-image-26): describe the frame as you see it, the character's exact features, and remove the caption.

```bash
python3 scripts/kie.py --env-file .env swap-frame --image $W/hook_frame1.jpg \
  --image assets/characters/<name>/selfie.jpg --image assets/characters/<name>/sheet.jpg \
  --prompt-file $W/swap_prompt.txt --out $W/swapped.png
python3 scripts/media.py compare $W/hook_frame1.jpg $W/swapped.png $W/swap_compare.jpg
```

About 12–14 credits (~$0.07) and 1–5 min. **Checkpoint A** (show the compare image): same person as the sheet, hair colour and length, framing scale (GPT Image sometimes zooms out a little), caption gone, hand and nails intact. Fix with a narrower prompt, not by accepting a wrong face.

## 5. Re-render the hook (Wan 3.0 video edit)

Write `$W/wan_prompt.txt` from the template in [prompts.md](references/prompts.md#2-hook-re-render-wan-30-edit): the beats from step 1, the character's features, the outfit choice, caption removal. Say the price and the wait, then run:

```bash
python3 scripts/kie.py --env-file .env wan-edit --ref-video $W/hook.mp4 \
  --ref-image $W/swapped.png --ref-image assets/characters/<name>/selfie.jpg \
  --prompt-file $W/wan_prompt.txt --out $W/wan.mp4
python3 scripts/media.py compare $W/hook.mp4 $W/wan.mp4 $W/wan_compare.jpg
python3 scripts/media.py mux-audio $W/wan.mp4 $W/ref.mp4 $W/wan_sound.mp4
python3 scripts/media.py side-by-side $W/hook.mp4 $W/wan_sound.mp4 $W/side_by_side.mp4 --audio-from $W/ref.mp4
```

- Resolution is always 720P (720×1280, the `kie.py` default). Length = the hook clip (`--duration -1`), no generated audio, the reference sound goes on later. Model `wan/3-0-video`; `--ref-video` takes 1–15 s.
- Price: billed seconds = output + reference video, so a 4.8 s hook cost 160 credits ($0.80) on 18.11.2026. Typical wait 3–4 min, once 21 min. Check `kie.py credits` before a batch.
- **One task per variant.** Every task id goes to `kie_jobs.jsonl` before polling. If polling breaks, `kie.py resume --task <id> --out <file>`. Never start a duplicate or a faster tier to race a slow task: both are billed. Wait and check.
- The output can be one frame shorter than the hook (144 of 145). That is fine: the demo fills the rest.
- **Checkpoint B** (show the compare grid and the side-by-side): movements and timing match, lips follow the original, the same face in every frame, one even hair colour, no sunburn-red cheeks, caption gone, five fingers. Offer the second outfit variant only after the first one is reviewed.

## 6. Captions

```bash
python3 scripts/media.py frame $W/wan.mp4 $W/wan_frame1.jpg --n 0
python3 scripts/render_hook_overlay.py --style tiktok --font ~/Library/Fonts/TikTokSans-Variable.ttf \
  --canvas 720x1280 --text "<hook>" --calib "<widest reference line>" --calib-frac <w> --center-y <c> \
  --line-pitch <p> --out $W/hook_caption.png --preview $W/wan_frame1.jpg
python3 scripts/render_hook_overlay.py --style neon --font ~/Library/Fonts/TikTokSans-Variable.ttf \
  --canvas 720x1280 --text "<demo phrase>" --calib "<widest reference line>" --calib-frac <w> \
  --center-y <c> --line-pitch <p> --out $W/demo_caption.png --preview <demo still>
```

`--canvas` = the Wan output size. Use the reference's style for each part: in the tested reference the hook was white Classic and the demo phrase Neon. Look at both previews: spelling, line breaks, eyes clear, the demo caption on an empty part of the screen. Details: [text-overlay.md](references/text-overlay.md).

## 7. Assemble

```bash
python3 scripts/media.py assemble --hook $W/wan.mp4 --hook-overlay $W/hook_caption.png \
  --demo assets/demos/<demo>.(mp4|png) --demo-overlay $W/demo_caption.png \
  --audio-from $W/ref.mp4 --out $W/final.mp4
```

- Writes `final.mp4` with the reference sound and `final_silent.mp4` without audio, both 720×1280 at 30 fps (the size of the 720P hook).
- The demo fills the reference's remaining length, so the sound ends with the video. Override with `--demo-seconds`.
- The hook caption stays on the hook only. Add `--hook-overlay-on-demo` only when the reference keeps it over the demo.
- A demo still is cover-fit to the frame: render app screens at 9:16 so nothing important is cropped.

## 8. Check and deliver

- `media.py check` on both finals (frames, size, peak volume), `media.py sheet $W/final.mp4 $W/final_sheet.jpg`, and `media.py frame` on the last hook frame and the first demo frame to see the cut and both captions.
- Deliver links to the finals, the side-by-side and the compare images, the costs from `kie_jobs.jsonl`, and known flaws in plain words (hair tone shift, a frame that drifts, cheeks too red).
- The sound link from `ref.meta.json` lets the user post with the original TikTok sound. Publishing is not part of this skill.
- Once one video works, offer to save the accepted choices (character files, outfit, prompts, caption settings, demo screens) into a project skill so the next video is one request.
