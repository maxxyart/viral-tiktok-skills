# Prompt templates

Fill the brackets from the user's assets and the reference analysis. Keep the English wording: the models follow it more reliably than a translation. Describe what you **see** in the donor frame (room, camera angle, pose); do not ask the model to guess.

## 1. Character into the donor frame (Nano Banana 2)

Image order matters: image 1 = donor first frame (scene), image 2 = character sheet or reference photo.

```text
Edit image 1. Replace the person in image 1 with the person from image 2: keep their exact face,
skin tone, age and [hair: style, colour, length], [accessories]. Keep EVERYTHING else from image 1
identical: the same [room / background], the same camera angle ([handheld front-camera selfie,
slightly low angle]), the same framing and crop, the same lighting and colours. Same pose:
[pose from the frame, e.g. one hand at the temple, head turned, eyes looking sideways],
[emotion, e.g. worried, stunned "wait, what?" expression], lips closed.
They wear [outfit: from image 2 or described]. REMOVE all on-screen text, captions and emoji
completely; the area behind them must be clean and continuous. Photorealistic raw iPhone selfie
video frame, natural skin texture, no text, no watermark.
```

- **Change one thing at a time.** For an outfit variant, edit the already approved still: "Change ONLY the clothing to …; keep everything else pixel-identical." A full re-swap tends to change the face and the room.
- The donor's details can leak through (nail colour, jewellery, hand props). Name them in the prompt if they matter.
- Respect the user's brand rules for modesty, age and setting. Ask when unknown.

## 2. Emotion clip (Omni 1.1 on kie, `gemini-omni-video`)

```text
The [woman/man] just found out something that makes them feel they wasted years, disbelief like
"you're telling me I never knew this?!". [Beat 1: e.g. slowly turns from the side to stare into
the camera, eyes wide]. [Beat 2: e.g. presses a palm on the forehead, drags it down over the eyes].
[Beat 3: e.g. slow head shake]. Their lips stay CLOSED the entire time, they do NOT open their mouth
or speak, no talking, no mouthing words. Raw handheld iPhone front-camera selfie video, slight natural
hand shake, keep the face, hair, outfit and the room exactly as in the image. Silent, no music,
no captions, no text on screen.
```

- Take the beats from the reference's hook (watch its contact sheet). Two or three beats fit 5 seconds.
- Omni treats the image as a strong reference, not a pixel-exact first frame. Generate **6 s** and cut the first second at assembly: the clip no longer starts on the identical still, which also makes series variants look different.
- The lips-closed block is mandatory for a silent hook. Check the mouth in the contact sheet; a breath with parted lips is fine, words are not.
- For a series, vary the beats per clip (peek through fingers, frozen stare, facepalm) instead of repeating one prompt.

## 3. Hook variants

Keep the reference's formula and rhythm; change only the life detail and the number:

```text
Ur telling me I [everyday action tied to the pain] for [N] YEARS and never knew this?!?!?!
Ur telling me I've been [action]-ing for [N] YEARS and this existed the whole time?!?!?!
Ur telling me I [action] for [N] YEARS and nobody told me about this?!?!?!
```

Vary N across a series. The action must point at the exact situation the demo solves, so the viewer understands the product in the first second of the demo.
