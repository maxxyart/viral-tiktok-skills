#!/usr/bin/env python3
"""Render a TikTok caption as a transparent PNG, to burn over the hook clip or the demo.

Styles:
  tiktok  white SemiBold with a tight dark halo, TikTok's "Classic" caption (the hook text)
  neon    pink-white Bold with a magenta glow, TikTok's "Neon" caption (the short demo phrase)
  halo    white with a soft wide shadow
  plate   dark text on white rounded plates

Match the reference instead of guessing: `media.py caption-lines FRAME` measures the caption in a
reference frame and prints --calib-frac, --center-y and --line-pitch for this script. --calib is the
text of the widest measured line, so the font size makes that line exactly as wide as in the reference.
A trailing emoji is drawn with the system colour emoji font (TikTok Sans has no emoji glyphs).
"\\n" in --text is a line break.

Usage:
  python3 render_hook_overlay.py --style tiktok --font ~/Library/Fonts/TikTokSans-Variable.ttf \\
      --canvas 720x1280 --text "i could literally KISS the mom\\nat pickup who showed me this🥹" \\
      --calib "everyone's July period late??" --calib-frac 0.73 --center-y 0.165 \\
      --out hook_caption.png --preview hook_frame1.jpg
  python3 render_hook_overlay.py --style neon --font ~/Library/Fonts/TikTokSans-Variable.ttf \\
      --canvas 720x1280 --text "IT SHOWED US WE KEEP\\nHAVING THE SAME FIGHT 💀" \\
      --calib "Not really late yet?" --calib-frac 0.49 --center-y 0.74 --out demo_caption.png
"""

from __future__ import annotations

import argparse
import itertools
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

W, H = 1080, 1920
SAFE_TOP, SAFE_BOTTOM = 0.06, 0.86  # keep clear of TikTok top bar and bottom UI/caption
SAFE_X = 0.06
STYLES = ("tiktok", "neon", "halo", "plate")
STYLE_WEIGHT = {"tiktok": 600, "neon": 700, "halo": None, "plate": None}
EMOJI_FONTS = (  # (path, a size the font has a bitmap strike for)
    ("/System/Library/Fonts/Apple Color Emoji.ttc", 160),
    ("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", 109),
    ("/usr/share/fonts/noto/NotoColorEmoji.ttf", 109),
    ("C:/Windows/Fonts/seguiemj.ttf", 128),
)


def is_emoji(ch: str) -> bool:
    cp = ord(ch)
    return (cp in (0x200D, 0xFE0F, 0x2B50, 0x2B55) or 0x1F000 <= cp <= 0x1FAFF
            or 0x2600 <= cp <= 0x27BF or 0x231A <= cp <= 0x23FF)


def split_emoji(text: str) -> tuple[str, str]:
    """'who showed me this🥹' -> ('who showed me this', '🥹'). Emoji elsewhere in the text is an error:
    the caption font cannot draw it, and TikTok captions put it at the end anyway."""
    i = len(text)
    while i and (is_emoji(text[i - 1]) or (text[i - 1] == " " and i < len(text))):
        i -= 1
    body, tail = text[:i].rstrip(), text[i:].replace(" ", "")
    if any(is_emoji(c) for c in body):
        raise ValueError("Emoji is supported only at the end of the caption; move it there or drop it")
    return body, tail


def size_for_length(chars: int, height: int = H) -> int:
    """Length-aware size when there is no reference to calibrate from."""
    for limit, frac in ((20, 0.0185), (55, 0.0165), (110, 0.015), (180, 0.0135), (260, 0.0125)):
        if chars <= limit:
            break
    else:
        frac = 0.0115
    cap = frac * height / 0.475  # letter height -> font size
    return int(max(0.020 * height, min(0.040 * height, cap)))


def load_font(path: Path, size: int, weight: int | None, strict: bool = True) -> ImageFont.FreeTypeFont:
    """strict=False: a style's default weight is skipped quietly on a static font."""
    if not Path(path).is_file():
        raise FileNotFoundError(f"Font file missing: {path}. Install the font and pass its file path.")
    font = ImageFont.truetype(str(path), size)
    if weight is None:
        return font
    try:
        axes = font.get_variation_axes()
    except OSError as exc:
        if not strict:
            return font
        raise ValueError(f"{path} is not a variable font; drop --weight or use a static bold file") from exc
    idx = next((i for i, a in enumerate(axes)
                if a["name"].decode("utf-8", errors="ignore").lower() == "weight"), None)
    if idx is None:
        if not strict:
            return font
        raise ValueError(f"{path} has no Weight axis")
    if not axes[idx]["minimum"] <= weight <= axes[idx]["maximum"]:
        raise ValueError(f"Weight {weight} outside {axes[idx]['minimum']}-{axes[idx]['maximum']}")
    values = [axis["default"] for axis in axes]
    values[idx] = weight
    font.set_variation_by_axes(values)
    return font


def calibrate(font_path: Path, weight: int | None, strict: bool, text: str, frac: float, width: int) -> int:
    """Font size at which `text` spans `frac` of the frame width."""
    text = "".join(c for c in text if not is_emoji(c)).strip()
    if not text or not 0 < frac < 1:
        raise ValueError("--calib needs reference text and --calib-frac between 0 and 1")
    lo, hi = 8, 400
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if load_font(font_path, mid, weight, strict).getlength(text) <= frac * width:
            lo = mid
        else:
            hi = mid - 1
    return lo


def emoji_image(chars: str, height: int, font_path: Path | None = None) -> Image.Image:
    cands = [(str(font_path), 160)] if font_path else list(EMOJI_FONTS)
    for path, strike in cands:
        if not Path(path).is_file():
            continue
        for sz in dict.fromkeys((strike, 160, 109, 128, 96, 64)):
            try:
                font = ImageFont.truetype(path, sz)
            except OSError:
                continue
            im = Image.new("RGBA", (sz * 2 * len(chars) + 40, sz * 2), (0, 0, 0, 0))
            ImageDraw.Draw(im).text((20, 20), chars, font=font, embedded_color=True)
            box = im.getbbox()
            if box:
                im = im.crop(box)
                return im.resize((max(1, round(im.width * height / im.height)), height), Image.LANCZOS)
    raise FileNotFoundError("No colour emoji font found (Apple Color Emoji / Noto Color Emoji). "
                            "Pass --emoji-font or drop the emoji.")


def wrap_balanced(text: str, font: ImageFont.FreeTypeFont, max_w: float, forced: list[str] | None = None,
                  tail: float = 0) -> list[str]:
    """Greedy wrap to find the line count, then pick breaks that minimise the widest line
    (no orphan last word). Explicit line breaks are kept. `tail` = emoji width on the last line."""
    def widths(cand: list[str]) -> list[float]:
        return [font.getlength(c) + (tail if i == len(cand) - 1 else 0) for i, c in enumerate(cand)]

    if forced:
        lines = forced
    else:
        words = text.split()
        lines, cur = [], ""
        for word in words:
            trial = f"{cur} {word}".strip()
            if font.getlength(trial) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
        if widths(lines)[-1] > max_w and len(lines[-1].split()) > 1:
            *head, last = lines[-1].split()
            lines[-1:] = [" ".join(head), last]
        n = len(lines)
        if 1 < n <= 6 and len(words) <= 40:
            best = None
            for cuts in itertools.combinations(range(1, len(words)), n - 1):
                b = [0, *cuts, len(words)]
                cand = [" ".join(words[b[i]:b[i + 1]]) for i in range(n)]
                w = max(widths(cand))
                if w <= max_w and (best is None or w < best[0]):
                    best = (w, cand)
            if best:
                lines = best[1]
    for line, w in zip(lines, widths(lines)):
        if w > max_w:
            raise ValueError(f"Line too wide even after wrapping: {line!r}. Shorten the text, add a line break "
                             f"or lower the size.")
    return lines


def render(text: str, font_path: Path, out: Path, *, style: str = "tiktok", center_y: float = 0.155,
           wrap: float = 0.88, size: int | None = None, weight: int | None = None,
           canvas: tuple[int, int] = (W, H), calib: str | None = None, calib_frac: float | None = None,
           line_pitch: float | None = None, emoji: str | None = None, emoji_font: Path | None = None,
           emoji_scale: float = 0.92, halo_alpha: int = 160, halo_blur: float | None = None,
           halo_stroke: int | None = None) -> dict:
    if style not in STYLES:
        raise ValueError(f"--style must be one of {', '.join(STYLES)}")
    cw, ch = canvas
    text = text.replace("\\n", "\n")
    body, emo = split_emoji("\n".join(ln.strip() for ln in text.strip().splitlines() if ln.strip()))
    emo = emo + (emoji or "")
    forced = body.split("\n") if "\n" in body else None
    flat = " ".join(body.split())
    if not flat:
        raise ValueError("Empty caption")

    strict = weight is not None
    wt = weight if weight is not None else STYLE_WEIGHT[style]
    if size is None and calib:
        if calib_frac is None:
            raise ValueError("--calib needs --calib-frac")
        size = calibrate(font_path, wt, strict, calib, calib_frac, cw)
    size = size or size_for_length(len(flat), ch)
    font = load_font(font_path, size, wt, strict)
    max_w = cw * wrap
    if max_w > cw * (1 - 2 * SAFE_X):
        raise ValueError(f"--wrap {wrap} leaves the horizontal safe zone (max {1 - 2 * SAFE_X:.2f})")
    emo_img = emoji_image(emo, round(size * emoji_scale), emoji_font) if emo else None
    gap = round(size * 0.22)
    tail = emo_img.width + gap if emo_img else 0
    lines = wrap_balanced(flat, font, max_w, forced, tail)

    top_b, bot_b = font.getbbox("H")[1], font.getbbox("H")[3]
    cap = bot_b - top_b
    step = round(line_pitch * ch) if line_pitch else int(cap * 1.14 / 0.72)
    block_h = step * (len(lines) - 1) + cap
    top = int(center_y * ch - block_h / 2)
    if top < SAFE_TOP * ch or top + block_h > SAFE_BOTTOM * ch:
        raise ValueError(f"Text block {top}..{top + block_h}px leaves the safe zone "
                         f"({int(SAFE_TOP * ch)}..{int(SAFE_BOTTOM * ch)}px). Move --center-y or shorten the text.")
    pos = []  # (x, y for draw, cap top, line, line width incl. emoji)
    for i, ln in enumerate(lines):
        lw = font.getlength(ln) + (tail if i == len(lines) - 1 else 0)
        pos.append(((cw - lw) / 2, top + i * step - top_b, top + i * step, ln, lw))

    layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    if style == "plate":
        px, py, r = int(0.45 * cap), int(0.25 * cap) + cap // 3, int(0.4 * cap)
        for x, _, y, _, lw in pos:
            d.rounded_rectangle((x - px, y - py, x + lw + px, y + cap + py), radius=r, fill=(255, 255, 255, 255))
        for x, y, _, ln, _ in pos:
            d.text((x, y), ln, font=font, fill=(17, 17, 17, 255))
        result = layer
    else:
        shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ds = ImageDraw.Draw(shadow)
        if style == "neon":
            for x, y, _, ln, _ in pos:
                ds.text((x, y), ln, font=font, fill=(255, 30, 185, 255), stroke_width=max(2, size // 14),
                        stroke_fill=(255, 30, 185, 255))
            passes = ((size * 0.55, 2), (size * 0.22, 2), (size * 0.08, 1))
            fill, stroke, stroke_fill = (255, 226, 248, 255), max(1, size // 28), (255, 120, 215, 255)
        else:
            s = cw / 720
            alpha = 255 if style == "tiktok" else halo_alpha
            sw = halo_stroke if halo_stroke is not None else (max(1, round(s)) if style == "tiktok" else max(2, int(0.03 * cap)))
            for x, y, _, ln, _ in pos:
                ds.text((x, y), ln, font=font, fill=(0, 0, 0, alpha), stroke_width=sw, stroke_fill=(0, 0, 0, alpha))
            blur = halo_blur if halo_blur is not None else (1.6 * s if style == "tiktok" else 6.0)
            passes = ((blur, 3 if style == "tiktok" else 1),)
            fill, stroke, stroke_fill = (255, 255, 255, 255), 0, None
        result = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        for radius, times in passes:
            glow = shadow.filter(ImageFilter.GaussianBlur(radius))
            for _ in range(times):
                result = Image.alpha_composite(result, glow)
        for x, y, _, ln, _ in pos:
            d.text((x, y), ln, font=font, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
        result = Image.alpha_composite(result, layer)
    if emo_img:
        x, _, y_cap, ln, _ = pos[-1]
        result.alpha_composite(emo_img, (round(x + font.getlength(ln) + gap), round(y_cap + cap / 2 - emo_img.height / 2)))

    out.parent.mkdir(parents=True, exist_ok=True)
    result.save(out)
    return {"lines": lines, "font_size": size, "cap_px": cap, "step": step, "block": [top, top + block_h],
            "block_frac": [round(top / ch, 3), round((top + block_h) / ch, 3)], "canvas": [cw, ch], "emoji": emo,
            "max_line_frac": round(max(p[4] for p in pos) / cw, 3)}


def preview(overlay: Path, background: Path, out: Path) -> None:
    """Composite the overlay on a still (cover-fit to the overlay size) to check face and UI clearance."""
    ov = Image.open(overlay).convert("RGBA")
    bg = ImageOps.fit(Image.open(background).convert("RGBA"), ov.size, Image.LANCZOS)
    Image.alpha_composite(bg, ov).convert("RGB").save(out, quality=90)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--text", help="Caption text; \\n = line break, a trailing emoji is drawn in colour")
    src.add_argument("--text-file", type=Path)
    ap.add_argument("--font", type=Path, required=True, help="Path to the installed .ttf/.otf (TikTok Sans)")
    ap.add_argument("--weight", type=int, help="Variable-font weight (default: tiktok 600, neon 700)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--style", choices=STYLES, default="tiktok")
    ap.add_argument("--canvas", default="1080x1920", help="Overlay size = the video size, e.g. 720x1280")
    ap.add_argument("--center-y", type=float, default=0.155, help="Block centre as a fraction of height")
    ap.add_argument("--wrap", type=float, default=0.88, help="Max line width as a fraction of the width")
    ap.add_argument("--size", type=int, help="Font size in px (skips calibration)")
    ap.add_argument("--calib", help="Text of a reference caption line (from caption-lines)")
    ap.add_argument("--calib-frac", type=float, help="Share of the frame width that line occupies")
    ap.add_argument("--line-pitch", type=float, help="Distance between line tops as a fraction of height")
    ap.add_argument("--emoji", help="Extra emoji after the last word")
    ap.add_argument("--emoji-font", type=Path, help="Colour emoji font if the system one is not found")
    ap.add_argument("--emoji-scale", type=float, default=0.92, help="Emoji height x font size")
    ap.add_argument("--halo-alpha", type=int, default=160, help="halo style: 150 on dark backgrounds, 170 on bright")
    ap.add_argument("--halo-blur", type=float)
    ap.add_argument("--halo-stroke", type=int)
    ap.add_argument("--preview", type=Path, help="Background still to composite a preview JPEG next to --out")
    a = ap.parse_args()
    text = a.text if a.text is not None else a.text_file.read_text(encoding="utf-8")
    cw, ch = (int(v) for v in a.canvas.lower().split("x"))
    info = render(text, a.font.expanduser(), a.out, style=a.style, center_y=a.center_y, wrap=a.wrap, size=a.size,
                  weight=a.weight, canvas=(cw, ch), calib=a.calib, calib_frac=a.calib_frac, line_pitch=a.line_pitch,
                  emoji=a.emoji, emoji_font=a.emoji_font, emoji_scale=a.emoji_scale, halo_alpha=a.halo_alpha,
                  halo_blur=a.halo_blur, halo_stroke=a.halo_stroke)
    print(f"{a.out}: {a.style}, {len(info['lines'])} lines, size {info['font_size']}px, block "
          f"{info['block_frac'][0]}..{info['block_frac'][1]} of height, widest line {info['max_line_frac']} of width"
          + (f", emoji {info['emoji']}" if info["emoji"] else ""))
    for ln in info["lines"]:
        print("  |", ln)
    if a.preview:
        p = a.out.with_name(a.out.stem + "_preview.jpg")
        preview(a.out, a.preview, p)
        print(f"preview: {p}")


if __name__ == "__main__":
    main()
