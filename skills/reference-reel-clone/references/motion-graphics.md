# Motion graphics, screens and assembly

## Motion graphics as code

- Build each graphics scene as an HTML page (DOM, Canvas or SVG) whose state is a pure function of time `t`. No CSS animations driven by the wall clock: rendering must be deterministic.
- Render frame by frame with Playwright at 30 fps (set `t`, take a screenshot), then join the frames with ffmpeg. Render transparent layers (PNG sequence or ProRes 4444) when graphics sit over video.
- Take every value from the storyboard: palette, fonts, sizes measured on reference frames, easing (usually ease-out cubic, 3–10 frame entrances), stagger between items, order of appearance.
- Compare with the reference at the key timecodes: put reference and render frames side by side and fix size, position and timing differences. Look for small motion: rotating icons, lines that draw in, items that fade up with a slight rise, blurred or pixelated teasers.
- Logos and product names stay as in the reference (this skill clones; it does not swap products).

## Screen recordings

- Record the real public pages the reference shows with Playwright: scroll by a fixed step per frame and screenshot at 30 fps; crop small UI with `clip` and `deviceScaleFactor: 2`.
- Hide cookie banners and pop-ups with injected CSS instead of clicking them. Never sign in or create accounts; if the reference shows a logged-in console, use the closest public page and tell the user.
- If the reference shows a list or table that is not a public page, build a simple HTML page with the same look and record it.
- Composite the recording into the black screen of the laptop or phone plate (four-corner fit), adding a soft screen glow.

## Avatar in front of graphics

When the creator's head overlaps graphics in the reference, render the graphics, then put the avatar back on top with a per-frame person mask (macOS: Apple Vision person segmentation; elsewhere: rembg or a similar matting model). Check hair and fingers on the contact sheet.

## Assembly

- Cut at the reference timecodes. Trim tails and dead air by the clip transcripts, not by eye.
- Subtitles: same chunking, position and style as the reference (white bold over the creator, plate over graphics if the reference does so).
- Audio: voice first. Sound effects clearly quieter than speech; add 5–15 ms fades at every audio cut so there are no clicks or swallowed syllables. Normalise to about −14 LUFS, true peak below −1 dBFS.
- Use the ffmpeg concat **filter** (with `settb`/`setpts`), not the concat demuxer, so durations and audio stay in sync. The final video length must equal the audio length.
- Review: `media.py check final.mp4`, then `media.py compare source.mp4 final.mp4 compare.mp4` and watch them together. Fix one remark at a time and re-render only what changed.
