# Prompt templates

Fill the brackets from the storyboard and the user's avatar. Keep prompts in English: the models follow it more reliably. Describe what you see; do not ask the model to guess.

## Locks file (`avatar/<name>_locks.md`)

Write once per project, then paste the blocks **word for word** into every clip prompt. Changing a single word changes the face or the voice.

```text
FACE_LOCK
The [man/woman] is exactly the person in the supplied first frame and stays identical in every frame:
[age], [ethnicity if visible], [hair: length, colour, parting, fringe], [glasses / facial hair / marks],
[jewellery], [outfit: plain, no print]. [Mic: tiny black clip-on lavalier on the collar | handheld mic].
Both hands are free and visible.

VOICE_LOCK
Voice: the same [young man's / woman's] voice in every clip – [age], [accent], [timbre: warm mid-low],
[mood: relaxed, slight smile], quick confident social-media pace of about [3.5] words per second,
upbeat but never shouty, close dry lavalier recording in a small furnished room, no echo, no reverb,
no music, no sound effects, no background noise.

NO_TEXT
Clean video frame: absolutely no on-screen text, no captions, no subtitles, no words, letters or
numbers anywhere in the image, no logos, no watermarks, no graphic overlays.

CAMERA (end of every prompt)
Raw, unedited original camera footage, vertical 9:16 phone video, camera at eye level, natural
micro-movements only, no cuts, no zoom.
```

If the user gave no voice description, propose one that fits the avatar's look (the model already infers age and gender from the face) and ask for approval.

## Location prompt (first frame)

```text
LOCATION – keeps the reference mood and palette, changes the layout and objects.
Mood & palette: [time of day], lit by [light sources], dominant colours [hex from the storyboard],
exposure [low-key / bright], background about [N] stops under the face.
Framing: [waist-up / chest-up], top of head at [~30%] of frame height, eyes at [~38%], hands in the
lower third, camera at eye level about [90 cm] away, [24 mm] phone lens, background softly out of
focus but readable. Slightly imperfect handheld composition, not perfectly centred.
Wall: [new material and colour, same tone family].
Light sources: [new practicals: lantern, table lamp … positions].
Props: [2–4 new objects; none copied from the reference].
Foreground: [desk edge, laptop, mug …].
Look: iPhone video still, slight sensor noise in shadows, natural vignetting, ordinary room,
no text, no logos.
```

First-frame request to Nano Banana Pro (image 1 = portrait, image 2 = character sheet):

```text
The person from image 1 and image 2 (same face, hair, glasses, build) sits in the room described
below, facing the camera, [pose and hands from the reference keyframe]. [LOCATION prompt]. Ordinary,
real-looking person and room. Vertical 9:16 phone video frame, photoreal, no text, no watermark.
```

Plate for split screens: same room and light, no person, an open [laptop/phone] whose screen is a flat pure black (#000000) rectangle facing the camera squarely, top [20%] of the frame dark wall for the title.

## Clip prompt (Omni 1.1, image-to-video with speech)

```text
[FACE_LOCK]
[VOICE_LOCK]
He/She says, clearly and naturally, in one take: "[exact line from the script] [NEXT line = tail]"
Gestures: at 0.0 s [gesture], at [1.5] s [gesture], at [3.0] s [gesture]. Natural facial expression,
eye contact with the lens.
[NO_TEXT]
[CAMERA]
```

- **Tail.** Omni spreads the words over the whole clip (minimum 4 s). Appending the next script line makes the needed part land at the reference pace; cut the tail at assembly.
- **Gestures by seconds only.** "On the word *thousands*" makes the model print *thousands* on screen.
- For a split-screen clip the avatar sits lower in frame; describe that framing.

## QA

For each clip before showing it:

1. Plays to the end; has an audio stream (`media.py check`).
2. `reference.py prepare clips/K1.mp4 clips/K1_qa` – the transcript matches the script word for word; the needed line ends where the plan says.
3. Contact sheet (`media.py sheet`): no burned-in text or captions, the same face as the sheet, the same room and outfit, hands look right.
4. Voice matches the approved reference clip by ear (pitch, timbre, accent, pace). A different voice is a retake, not post-processing.

Record each attempt (task id, duration, what failed) in `clips/qa.md`.
