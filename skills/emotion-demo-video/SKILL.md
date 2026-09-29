---
name: emotion-demo-video
description: Make short vertical "emotion hook + product demo" videos from a TikTok/Instagram reference. The user's AI character is placed into real donor first frames (Nano Banana 2 on kie.ai), animated with a silent emotion (Omni 1.1 on kie.ai), given a TikTok-native hook text overlay and joined with the user's product demo. Asks for the character, backgrounds and demo; never invents them. Use for "emotion + demo", "Ur telling me…" style hooks and series of variants; use reference-carousel-adapter for photo carousels.
---

# Emotion hook + demo video

Format: 4–5 s of a person reacting silently (shock, "wait, what?", facepalm) with a hook caption, then a screen recording of the product that answers the hook. Keep the reference's **structure and emotion**; the face, scenes, product and words are the user's.

## 0. Ask for the inputs (never assume)

Ask for everything missing in one message, then wait. Use nothing from other projects.

1. **Reference video** – TikTok/Instagram URL of an emotion + demo post that performed.
2. **Character** – 1–3 images of the user's AI character: a character sheet (face close-up, profile, full body) is best. If they have none, suggest making one first (e.g. with a portrait-clone style skill) and stop here. Ask whether outfit variants exist.
3. **Backgrounds** – 1–3 donor video URLs or photos whose first frame is a real, imperfect scene (kitchen, hallway, car) with a similar selfie framing. Real scenes sell the native look; do not generate rooms from scratch.
4. **Demo** – the user's own screen recording of the product (mp4/mov, 5–15 s) that shows the moment the hook promises. Never fake UI.
5. **Product and audience** – read `CLAUDE.md` / `AGENTS.md` / a brief; ask for the pain the demo solves and any brand rules (modesty, age, language).
6. **Access** – `KIE_API_KEY` (https://kie.ai/api-key) in the environment or an `.env` path; `ffmpeg`, `yt-dlp`, Python 3.9+ with Pillow; a font file for captions (see step 4).

Save assets in the user's project so they are reused for every future video:

```
assets/characters/<name>/   sheets and approved stills per outfit
assets/backgrounds/         donor first frames (frame0 jpg)
assets/demos/               product screen recordings
emotion-demo/<series>/      hooks, overlays, raw clips, finals, kie_jobs.jsonl
```

## 1. Read the reference

- `python3 scripts/media.py fetch <url> emotion-demo/<series>/ref.mp4`, then `media.py sheet` on it. Note: hook length (where the demo starts), the emotion beats, silent or talking, caption text, style, position, and whether the caption stays over the demo.
- Separate the **hook formula** (e.g. "Ur telling me I … for N YEARS and never knew this?!?!?!") from the visual formula.

## 2. Hooks → the user picks

Offer 3 hooks in the reference's formula, each pointing at the exact situation the demo shows (templates in [prompts.md](references/prompts.md)). Say which one you recommend and why. Wait for the choice. For a series, write close variants with different numbers and actions.

## 3. Stills: character into the donor frames

- Extract backgrounds: `python3 scripts/media.py first-frame <donor-url> assets/backgrounds/<id>_frame0.jpg`.
- Swap in the character and remove the donor's text: `python3 scripts/kie.py edit-image --image <frame0.jpg> --image <character-sheet.jpg> --prompt "<prompt>" --out emotion-demo/<series>/still1.png`. Local paths are uploaded automatically (sequentially, as JPEG under 1 MB).
- **Checkpoint A:** show all stills side by side. Check face match, no leftover text, pose and emotion, hands, modesty rules. Fix with a narrow edit of the approved still ("change ONLY …") rather than a full redo.

## 4. Hook overlay

Read [text-overlay.md](references/text-overlay.md) (font install, halo vs plate, size, safe zone, eyes rule). Render one PNG per hook and preview it on its still:

```bash
python3 scripts/render_hook_overlay.py --text "<hook>" --font /path/TikTokSans.ttf --weight 600 \
  --out emotion-demo/<series>/overlay1.png --preview emotion-demo/<series>/still1.png
```

## 5. Animate the emotion

`python3 scripts/kie.py video --image emotion-demo/<series>/still1.png --prompt "<emotion prompt>" --duration 6 --out emotion-demo/<series>/raw1.mp4`

- Model: Omni 1.1 (`gemini-omni-video` on kie). Durations 4/6/8/10 s only: generate 6 s, the first second is cut at assembly. State the cost before a batch and check `kie.py credits` (about 84 credits per 6 s 1080p clip on 29.09.2026; check the current kie price).
- Lips closed, no speech, no music: use the template in [prompts.md](references/prompts.md). Review `media.py sheet raw1.mp4` for mouth, face drift and hands.
- **Never resubmit a task with an unknown outcome.** Every task id is logged in `kie_jobs.jsonl` before polling; recover with `kie.py resume --task <id> --out <file>`. Other models (Kling 3.0, Seedance, MiniMax) work the same way through their own APIs; ask before switching.

## 6. Assemble

```bash
python3 scripts/media.py assemble --hook raw1.mp4 --overlay overlay1.png --demo assets/demos/<demo>.mp4 \
  --out emotion-demo/<series>/final1.mp4 --trim-start 1 --hook-seconds 5 [--overlay-on-demo]
```

Output: 1080×1920, 30 fps, H.264, **silent** AAC track (music is added inside TikTok). Keep the demo's own on-screen text readable; use `--overlay-on-demo` only if the hook does not collide with it.

## 7. Check and deliver

- For every final: `media.py sheet` + `media.py check`. Verify spelling, eyes clear of text, lips closed, the cut from hook to demo, demo not badly cropped, peak volume = silence.
- For a series, build a side-by-side control grid so the user can compare variants at once.
- Deliver links to finals, stills and overlays; list known flaws honestly (leaked details, motion blur, a start that differs from the still). Publishing is manual.
- Once one series works, offer to save the user's accepted choices (character, backgrounds, demo, hook formula, prompts, overlay settings) into a project skill so the next series is one request.
