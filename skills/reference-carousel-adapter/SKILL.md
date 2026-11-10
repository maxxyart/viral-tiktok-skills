---
name: reference-carousel-adapter
description: Adapt one TikTok photo post or Instagram carousel to the user's own product. Analyze its slide sequence and visual language, write original hooks and slide copy, integrate the real product naturally, then produce reviewable HTML and finished image slides with accurate text overlays. Use for a reference-based carousel; use carousel-account-patterns for account-wide research or hook-notes-carousel for its fixed two-slide Notes format.
---

# Adapt a reference carousel

Make a new carousel that serves the user's product and audience while preserving the reference's useful **structure and visual logic**. Do not carry over the original creator's personal claims, exact copy, brand assets, or product facts.

## 1. Collect the reference and product facts

- For a TikTok or Instagram post URL, fetch post data and all carousel images with **ScrapeCreators first**. Save the source URL, capture date, metrics if returned, and original images. If it is unavailable, say so before another source. Restore slide order from post metadata and visual continuity when the provider's media array is shuffled.
- Read every slide at full size, including its text. Separate the **semantic formula** (hook → progression/payoff → product/CTA) from the **visual formula** (photo type, crop, lighting, font, boxes, color, placement). Note what each slide does, rather than copying its words.
- Read the user's product brief, site, store listing, or project files. Extract audience, specific pain, real features, proof, available screenshots/photos, and target language. Mark anything unknown; never invent product UI, results, testimonials, or statistics.
- If a source image is unavailable, use only the visible evidence and label that limit. Do not treat a schematic preview as the final reference.

## 2. Adapt the story

- Write several distinct hook options for the user to pick from, grouped by the reference's format when a series has more than one. Each one points to the user's audience and an actual benefit. Keep the reference's emotional or informational move, but write fresh lines in the audience's language.
- Plan each slide as `{job, exact on-slide text, visual brief, source or new asset}`. Keep the number of slides that best completes this story; the reference count is evidence, not a rule. Deliver useful content before the product appears.
- Integrate the product through a real moment of use, an authentic screenshot/photo, or a verified feature. The transition should read as part of the story, not a sudden ad. Include an appropriate final action only if it fits the user's goal.
- Make the storyboard one self-contained HTML page with these blocks, in this order:
  1. **Series**: a title and one line of facts (account, number of posts, views against the account median, save rate).
  2. **References**: the cover of each reference post, linked to the post, with views and saves.
  3. **Semantic formula**: the slide chain as short text blocks (slide range, job, pattern), integration slide highlighted. Text only, no renders.
  4. **Hooks to choose**: every hook option with a checkbox, plus what it covers, the product feature it leads to and the persona. A drafted carousel sits collapsed under its hook as a swipeable strip with its caption. To compare, show the original and the adaptation as two whole strips, never slide-by-slide pairs.
  5. **Visual formula**: short text blocks for background, hook type, body type, color, rhythm and the integration slide.
  6. **Visual options to choose**: two or three styles, each rendered on the same two slides (hook and first body slide), each with a checkbox.
- Keep the page lean: no decision cards, transfer tables, per-slide notes or explanations of why a hook works. Read [storyboard.md](references/storyboard.md) for saving the ticks and reading them back.
- When the Artifact tool is available, publish the storyboard as an Artifact so the user can tick and comment beside the chat; apply feedback and republish to the same URL. Read the ticks before final slides, and render only the ticked hooks in the ticked style. Do not start paid image generation until then, unless the request already authorizes it.

## 3. Produce images and text

- Obtain or generate clean backgrounds **without baked-in words**. Generate realistic or complex backgrounds with GPT Image or Nano Banana; draw simple slides (typography, cards, Notes or chat screenshots) directly in code without an image model. Generate the first slide, show it, then the rest. Match the reference's photo realism, framing, and empty space for text. Keep background assets separate from final slides so edits do not require new image generations.
- Place all copy as editable, deterministic text overlay. When the reference uses TikTok-native typography, install **TikTok Sans** from the [official Google Fonts page](https://fonts.google.com/specimen/TikTok+Sans) before rendering. When it visibly uses another font, match that font instead. Read [text-overlay.md](references/text-overlay.md) for installation, layer measurements, line wrapping, sticker padding, stroke, safe areas, and visual QA.
- For stepped caption stickers like the source session, use [render_overlay.py](scripts/render_overlay.py) with a copied [example config](assets/example-config.json). The script supports per-slide text, styles, font files, positions, and explicit overflow errors. Other visual styles can use an equivalent editor or renderer; keep the overlay principles.

## 4. Check and deliver

- Inspect **every** finished slide at full size and as a contact sheet or mobile preview. Check slide order, exact spelling, font weight, box padding, contrast, line breaks, face/product occlusion, product accuracy, and cropping. Revise the overlay config before regenerating backgrounds for a text-only issue.
- Save the storyboard, source/provenance note, clean backgrounds, text/config, and numbered final PNGs. Give the user a link to the preview and final assets; when the Artifact tool is available, show the final slides, caption and sound suggestion in one Artifact the user can open on a phone. Post to social networks only when requested.
