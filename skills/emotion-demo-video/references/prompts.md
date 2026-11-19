# Prompt templates

Fill the brackets from the reference's hook frame, its contact sheet and the character files. Keep the English wording: both models follow it more reliably than a translation. Describe what you **see** (angle, distance, pose, hands, light, props); do not make the model guess. Name the character's features as concrete shapes and colours, never "beautiful" or "attractive".

## 1. First-frame swap (GPT Image 2.6)

Image order: image 1 = the reference's first frame (the scene), image 2 = the character's selfie, image 3 = the character sheet.

```text
Face and hair swap on a real phone selfie video frame.

Image 1 is the SCENE: a vertical 9:16 front-camera selfie frame of [who, where: a young woman sitting
in a car], shot [angle and distance: from a low angle and very close, face filling the lower two thirds,
chin cut off by the bottom edge]. Keep everything about Image 1 exactly as it is: the camera angle,
distance and framing, [head pose], [gaze], [mouth], [hands: which hand, where, how the fingers point],
[nails, jewellery], [light: direction, hard or soft, the shadows it casts], [background details],
the colour grade and the phone-camera grain and softness.

Image 2 and Image 3 are the IDENTITY: both show the same woman. Image 2 is a casual selfie of her,
Image 3 is her reference sheet; use Image 3 only for her features, not for its layout or white
background. Replace the woman's face and hair in Image 1 with this woman. Her face must be clearly the
same person as Images 2 and 3, with their exact proportions: [face shape, cheeks, forehead, jaw, chin,
nose, eye colour and shape, brows, lips, skin tone]. Her hair becomes her hair from Images 2 and 3:
[length, texture, one exact colour, parting]. Keep the facial expression, head pose, gaze direction,
[open mouth] and the lighting and shadows from Image 1, rendered on her face. Keep Image 1's hand,
nails and earring.

Remove the [white caption text and the emoji] in [where] of Image 1 ("[the caption text]") and restore
the [background surface] behind it, continuing the existing lighting. No text, no captions, no emoji,
no stickers, no UI anywhere in the image.

Photoreal, unretouched iPhone front-camera look, natural skin texture with visible pores and fine peach
fuzz, no beauty filter, no smoothing, no added makeup, no extra fingers, hand anatomically correct with
five fingers.
```

- Quoting the caption text helps the model find and remove all of it.
- Check the result against the frame: GPT Image may zoom out a little and lighten the hair. A small zoom is fine, Wan follows the reference video framing; a different hair colour carries into the video, so redo it.
- Settings in `kie.py swap-frame`: 9:16, 2K, quality high, PNG.

## 2. Hook re-render (Wan 3.0 edit)

Inputs: Video 1 = the cut hook clip; Image 1 = the swapped first frame; Image 2 = the character's selfie (add Image 3 = the sheet when the outfit changes).

**Reference outfit (default, the safer choice):**

```text
Edit Video 1: replace the woman in Video 1 with the woman from Image 1 and Image 2. Image 1 shows how
she must look in the first frame of Video 1; Image 2 is a selfie of the same woman showing her face and
hair clearly. She has [face shape, cheeks, chin, jaw], [skin tone with only a light natural flush],
[eyes], [brows], [nose], [lips], [earrings], and [hair length and texture with a centre part]. The hair
is one even [colour] from the roots to the very ends, exactly like Image 2: no ombre, no lighter,
copper or blonde ends, no highlights.

Keep everything else from Video 1 unchanged: her exact movements and timing ([beat 1], then [beat 2],
then [beat 3]), every facial expression and lip movement, the handheld front-camera selfie framing and
natural camera shake, [the outfit as seen in Video 1, with its prints and colours], [seatbelt, nails,
rings], [the location and its details], and [the light and its shadows on her face].

Remove the [white caption text and the emoji] in [where] of Video 1 so the [surface] behind it is clean
in every frame. No text, no subtitles, no emoji, no stickers anywhere. Photoreal iPhone front-camera
footage, natural skin texture, no sunburn, no beauty filter, hands anatomically correct with five
fingers.
```

**Character's own outfit:** start with "Edit Video 1: replace the woman in Video 1 with the woman from Image 1, Image 2 and Image 3, and dress her in her own outfit from Image 2 and Image 3", add `Image 3 is her reference sheet (front close-up, left profile, full body)`, then a clothing paragraph: "Clothing: replace the [reference outfit] from Video 1 with her [garment] from Image 2 and Image 3: [colour, fabric, neckline, sleeves, no print, no logo]. The [seatbelt] still runs [where] over the [new top]." Keep the rest of the template.

Pitfalls seen in tests:

- A hair description with two tones ("warmer reddish-brown lengths") produced copper ombre ends. Name one colour and add the no-ombre line.
- A "natural pink flush" on bright sun became sunburn-red cheeks by the end of the clip. Ask for a light flush and add "no sunburn".
- The own-outfit run kept the clothes right but cut the long hair to shoulder length. Put the hair length into the prompt and check it at checkpoint B.
- Beats copied from the contact sheet keep lips and hands in sync with the original; leave out beats you did not see.

## 3. Hook and demo phrase

The hook keeps the reference's formula, length and rhythm; only the situation changes so it points at what the demo shows. Lower case and a trailing emoji if the reference has them.

```text
i could literally KISS the [person/place] who showed me this🥹
[Any / Every] [audience] whose [pain] [this week]? 😭
POV: [situation the demo solves] and it's day [N]
```

The demo phrase is 4–9 words in capitals (if the reference uses capitals): what the app just showed, said like a friend, ending in an emoji when the reference does.

```text
IT SHOWED US WE KEEP HAVING THE SAME FIGHT 💀
EVEN MY [THING] [DID X] 💀
```

Offer 3 hooks and 2–3 demo phrases with different numbers and verbs, never the same template three times. Write them in the target audience's language and check them with the user before rendering.
