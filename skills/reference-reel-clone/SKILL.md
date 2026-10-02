---
name: reference-reel-clone
description: Clone a talking-creator TikTok/Instagram reel one-to-one with the user's own AI avatar – same scenes, timing, frame layouts, motion graphics, subtitles and script – with native speech in every on-camera clip and a cloned voice only for faceless voice-over. Runs on kie.ai (Nano Banana Pro first frames, Omni 1.1 clips with lip-sync) or on the user's own generation platform, with motion graphics rendered as code. Stops for approval after every stage. Use to learn a complex reel format before adapting it; product swaps and new scripts are a later, separate step.
---

# Clone a reference reel with your avatar

Goal: a faithful copy of a performing reel where only the **person and the room** change. Keep the reference's structure, timing, layouts, motion graphics, subtitle rhythm and words. Do not swap products, rewrite the script or "improve" the design: a clean clone is the benchmark that later adaptations are compared against.

## Hard rules

- **Voice.** Every clip where the avatar is on camera is generated **with native speech and lip-sync** (Omni). A cloned voice (ElevenLabs, Fish Audio, Inworld) is used **only** for segments where the avatar is not on screen (full-screen graphics). Never re-voice an on-camera clip, never lay a cloned track over it, never use voice changers. A clip with bad speech is regenerated.
- **Stops.** After stage 1, after the first frame, after the first voiced clip and after the assembled video, stop and wait for the user's OK.
- **No invention.** Never invent the avatar, the user's accounts or keys. Ask for what is missing. Do not create accounts or log in to sites for screen recordings.
- **Native look.** Ordinary people in ordinary rooms. Keep phone-video imperfection: slightly off-centre framing, natural light, visible texture, 720p–1080p rather than hyper-detailed renders. When unsure, match the reference, not an ideal.
- **Unknown outcomes.** Every paid task is logged before polling. If polling breaks, recover it with `kie.py resume --task <id>`; never resubmit a task whose result is unknown.

## 0. Ask for the inputs

Ask once for everything missing, then wait:

1. **Reference** – TikTok/Instagram URL and which part to clone (whole reel or e.g. the first 20 s).
2. **Avatar** – a portrait and a character sheet (face front and profile, full body). No avatar yet: suggest making one first and stop.
3. **Voice** – a short description (age, accent, energy, pace) or permission to propose one. It is repeated word for word in every clip prompt.
4. **Generation access** – `KIE_API_KEY` from [kie.ai](https://kie.ai/api-key) by default. If the user works on another platform (Higgsfield, their own API), ask which one and use its equivalents for Nano Banana Pro and Omni 1.1.
5. **Voice clone access** – only if the reel has faceless voice-over: an API key for ElevenLabs (clone from the Starter plan), Fish Audio or Inworld (both have free API tiers).
6. **Tools** – `SCRAPE_CREATORS_API_KEY` ([scrapecreators.com](https://scrapecreators.com)) for downloading; `ffmpeg`; Python 3.9+; `pip install faster-whisper` for word-level checks; Node with Playwright for rendering motion graphics and screen recordings.

Project layout:

```
<project>/reference/            source.mp4, metadata, analysis/ (frames, keyframes, sheets, transcript)
<project>/storyboard.html       the stage 1 plan
<project>/avatar/               portrait, sheet, <name>_locks.md (face, voice, no-text blocks)
<project>/frames/               first-frame variants and plates, kie_jobs.jsonl
<project>/clips/                voiced clips K1, K2 … and QA notes
<project>/vo/                   voice clone samples and faceless voice-over
<project>/motion/               motion-graphics code, rendered layers, screen recordings
<project>/final/                final.mp4, compare.mp4
```

## 1. Analyse the reference (no generations)

```bash
python3 scripts/reference.py fetch <url> <project>/reference/source.mp4
python3 scripts/reference.py prepare <project>/reference/source.mp4 <project>/reference/analysis
```

`prepare` writes frames at 5 fps (fast graphics are missed at 1 fps), full-size keyframes at every cut, 4-second contact sheets and a word-timestamped transcript. Read the sheets and keyframes yourself.

Build `storyboard.html` as described in [storyboard.md](references/storyboard.md): avatar on top, then per scene the reference frames, layout, every motion element with timecodes, creator text, subtitle chunks, the **source of each piece** (Omni with native voice / cloned voice-over / code / screen recording) and the location plan. Verify facts the reel states only to flag them; keep the script as is. End with the open questions (e.g. hand-held mic vs lavalier when the creator gestures with both hands). **Stop.**

## 2. First frame

- Describe the new room in a detailed location prompt: same mood, light and palette as the reference, different objects and layout. Templates: [prompts.md](references/prompts.md).
- Generate 2 variants with Nano Banana Pro, references = portrait + sheet:
  `python3 scripts/kie.py edit-image --image avatar/portrait.jpg --image avatar/sheet.jpg --prompt "<prompt>" --out frames/A_v1.png`
- If the reel has split screens, show each variant full frame and cropped into the split next to the original. If a laptop or phone appears, make a plate of the same room with a pure black screen for compositing.
- Check the face against the sheet, no text, both hands free if the creator gestures. **Stop for the choice.**

## 3. Voiced clips

1. Write `avatar/<name>_locks.md` with FACE, VOICE, NO_TEXT and CAMERA blocks ([prompts.md](references/prompts.md)). Paste them **verbatim** into every clip prompt.
2. Map on-camera segments to clips. Duration = segment rounded up to kie's 4/6/8/10 s.
3. Generate the first on-camera clip from the approved frame:
   `python3 scripts/kie.py video --image frames/A_v1.png --prompt "<prompt>" --duration 4 --out clips/K1.mp4`
   - Gestures are tied to seconds ("at 1.5 s raises two fingers"). Tying them to words makes the model burn those words in as captions.
   - Omni stretches speech over the whole clip. To hit the reference pace, append the **next line of the script** as a "tail" and cut it off at assembly.
4. QA before showing (checklist in [prompts.md](references/prompts.md)): decodes fully, has audio, words match the script and timing (`reference.py prepare` on the clip), contact sheet shows no burned-in text, same face and room. **Stop: the user listens.** The approved clip becomes the voice reference.
5. Generate the remaining on-camera clips with the same locks and check each against the voice reference. Mismatch: regenerate.
6. Omni sometimes refuses a realistic face or a detail it reads as sensitive (e.g. a see-through top). Change that detail in the frame and prompt, or, with the user's OK, try another image-to-video model they have (Kling 3.0, MiniMax). Do not loop on the same failing request.

## 4. Faceless voice-over (only if the reel has it)

- Clone the voice from 15–40 s of clean speech cut from the approved clips of **this** project.
- Generate only the lines spoken over full-screen graphics. Put clone and native clip back to back in one audio file and let the user compare by ear before continuing.

## 5. Motion graphics, screens, assembly

Follow [motion-graphics.md](references/motion-graphics.md):
- Motion graphics are code (HTML/Canvas animated by time, rendered frame by frame), never generated video. Match elements, colours, fonts, easing and order from the storyboard; compare with reference frames at the key timecodes.
- Screens are recordings of the real public sites the reference shows. Hide cookie banners with CSS; do not sign in.
- When the reference puts graphics behind the creator, cut the avatar out frame by frame.
- Assemble at the reference cut points; subtitles in the reference style; loudness about −14 LUFS; sound effects clearly below the voice; short fades at every audio cut so there are no clicks or swallowed words.
- `python3 scripts/media.py check final/final.mp4` and `python3 scripts/media.py compare reference/source.mp4 final/final.mp4 final/compare.mp4`. **Stop: the user reviews the side-by-side.** Fix remarks narrowly (one element at a time).

## 6. Deliver

Give links to `final.mp4`, `compare.mp4` and `storyboard.html`, list the differences from the reference honestly, and report the kie credits spent. Offer to save the accepted avatar, locks, prompts and motion code as a project skill. Replacing a product or rewriting the script is the next step, done on top of this clone.
