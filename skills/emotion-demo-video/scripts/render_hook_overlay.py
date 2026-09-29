#!/usr/bin/env python3
"""Render a TikTok-style hook caption as a transparent 1080x1920 PNG.

The PNG is burned over the animated hook clip by `media.py assemble`, so a
text change never needs a new video generation.

Usage:
  python3 render_hook_overlay.py --text "Ur telling me ..." --font /path/TikTokSans.ttf \
      --out overlay_hook1.png [--style halo|plate] [--center-y 0.155] [--preview frame.png]
"""

from __future__ import annotations

import argparse
import itertools
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

W, H = 1080, 1920
SAFE_TOP, SAFE_BOTTOM = 0.06, 0.86  # keep clear of TikTok top bar and bottom UI/caption
SAFE_X = 0.06


def size_for_length(chars: int) -> int:
    """Length-aware cap height: short hook = big, long statement = smaller."""
    for limit, frac in ((20, 0.0185), (55, 0.0165), (110, 0.015), (180, 0.0135), (260, 0.0125)):
        if chars <= limit:
            break
    else:
        frac = 0.0115
    cap = frac * H / 0.475  # letter height -> font size
    return int(max(0.020 * H, min(0.040 * H, cap)))


def load_font(path: Path, size: int, weight: int | None) -> ImageFont.FreeTypeFont:
    if not path.is_file():
        raise FileNotFoundError(f"Font file missing: {path}. Install the font and pass its file path.")
    font = ImageFont.truetype(str(path), size)
    if weight is not None:
        try:
            axes = font.get_variation_axes()
        except OSError as exc:
            raise ValueError(f"{path} is not a variable font; drop --weight or use a static bold file") from exc
        values = [axis["default"] for axis in axes]
        idx = next((i for i, a in enumerate(axes)
                    if a["name"].decode("utf-8", errors="ignore").lower() == "weight"), None)
        if idx is None:
            raise ValueError(f"{path} has no Weight axis")
        if not axes[idx]["minimum"] <= weight <= axes[idx]["maximum"]:
            raise ValueError(f"Weight {weight} outside {axes[idx]['minimum']}-{axes[idx]['maximum']}")
        values[idx] = weight
        font.set_variation_by_axes(values)
    return font


def wrap_balanced(text: str, font: ImageFont.FreeTypeFont, max_w: float, forced: list[str] | None = None) -> list[str]:
    """Greedy wrap to find the line count, then pick breaks that minimise the widest line
    (no orphan last word). Explicit line breaks in the text are kept as-is."""
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
        n = len(lines)
        if 1 < n <= 6 and len(words) <= 40:
            best = None
            for cuts in itertools.combinations(range(1, len(words)), n - 1):
                b = [0, *cuts, len(words)]
                cand = [" ".join(words[b[i]:b[i + 1]]) for i in range(n)]
                w = max(font.getlength(c) for c in cand)
                if w <= max_w and (best is None or w < best[0]):
                    best = (w, cand)
            if best:
                lines = best[1]
    for line in lines:
        if font.getlength(line) > max_w:
            raise ValueError(f"Line too wide even after wrapping: {line!r}. Shorten the hook or lower --size.")
    return lines


def render(text: str, font_path: Path, out: Path, *, style: str = "halo", center_y: float = 0.155,
           wrap: float = 0.88, size: int | None = None, weight: int | None = None,
           halo_alpha: int = 160, halo_blur: float = 6.0, halo_stroke: int | None = None) -> dict:
    forced = [ln.strip() for ln in text.splitlines() if ln.strip()] if "\n" in text.strip() else None
    flat = " ".join(text.split())
    size = size or size_for_length(len(flat))
    font = load_font(font_path, size, weight)
    max_w = W * wrap
    if max_w > W * (1 - 2 * SAFE_X):
        raise ValueError(f"--wrap {wrap} leaves the horizontal safe zone (max {1 - 2 * SAFE_X:.2f})")
    lines = wrap_balanced(flat, font, max_w, forced)

    top_b, bot_b = font.getbbox("H")[1], font.getbbox("H")[3]
    cap = bot_b - top_b
    step = int(cap * 1.14 / 0.72)
    block_h = step * (len(lines) - 1) + cap
    top = int(center_y * H - block_h / 2)
    if top < SAFE_TOP * H or top + block_h > SAFE_BOTTOM * H:
        raise ValueError(f"Text block {top}..{top + block_h}px leaves the safe zone "
                         f"({int(SAFE_TOP * H)}..{int(SAFE_BOTTOM * H)}px). Move --center-y or shorten the text.")

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if style == "halo":
        stroke = halo_stroke if halo_stroke is not None else max(2, int(0.03 * cap))
        halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dh, dt = ImageDraw.Draw(halo), ImageDraw.Draw(canvas)
        for i, ln in enumerate(lines):
            x, y = (W - font.getlength(ln)) / 2, top + i * step - top_b
            dh.text((x, y), ln, font=font, fill=(0, 0, 0, halo_alpha), stroke_width=stroke, stroke_fill=(0, 0, 0, halo_alpha))
        halo = halo.filter(ImageFilter.GaussianBlur(halo_blur))
        for i, ln in enumerate(lines):
            x, y = (W - font.getlength(ln)) / 2, top + i * step - top_b
            dt.text((x, y), ln, font=font, fill=(255, 255, 255, 255))
        canvas = Image.alpha_composite(halo, canvas)
    elif style == "plate":
        d = ImageDraw.Draw(canvas)
        px, py, r = int(0.45 * cap), int(0.25 * cap) + cap // 3, int(0.4 * cap)
        for i, ln in enumerate(lines):
            lw = font.getlength(ln)
            x, y = (W - lw) / 2, top + i * step
            d.rounded_rectangle((x - px, y - py, x + lw + px, y + cap + py), radius=r, fill=(255, 255, 255, 255))
        for i, ln in enumerate(lines):
            x, y = (W - font.getlength(ln)) / 2, top + i * step - top_b
            d.text((x, y), ln, font=font, fill=(17, 17, 17, 255))
    else:
        raise ValueError("--style must be halo or plate")

    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return {"lines": lines, "font_size": size, "cap_px": cap, "block": [top, top + block_h]}


def preview(overlay: Path, background: Path, out: Path) -> None:
    """Composite the overlay on a still (cover-fit 1080x1920) to check face and eye clearance."""
    bg = ImageOps.fit(Image.open(background).convert("RGBA"), (W, H), Image.LANCZOS)
    Image.alpha_composite(bg, Image.open(overlay).convert("RGBA")).convert("RGB").save(out, quality=90)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--text", help="Hook text. Use \\n in a text file for manual line breaks.")
    src.add_argument("--text-file", type=Path)
    ap.add_argument("--font", type=Path, required=True, help="Path to the installed .ttf/.otf (e.g. TikTok Sans)")
    ap.add_argument("--weight", type=int, help="Weight for a variable font, e.g. 600")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--style", choices=["halo", "plate"], default="halo")
    ap.add_argument("--center-y", type=float, default=0.155, help="Block centre as a fraction of height (0.155 = above the face)")
    ap.add_argument("--wrap", type=float, default=0.88, help="Max line width as a fraction of 1080")
    ap.add_argument("--size", type=int, help="Font size in px (default: length-aware)")
    ap.add_argument("--halo-alpha", type=int, default=160, help="150 on dark backgrounds, 170 on bright")
    ap.add_argument("--halo-blur", type=float, default=6.0)
    ap.add_argument("--halo-stroke", type=int)
    ap.add_argument("--preview", type=Path, help="Background still to composite a preview JPEG next to --out")
    a = ap.parse_args()
    text = a.text if a.text is not None else a.text_file.read_text(encoding="utf-8")
    info = render(text, a.font, a.out, style=a.style, center_y=a.center_y, wrap=a.wrap, size=a.size,
                  weight=a.weight, halo_alpha=a.halo_alpha, halo_blur=a.halo_blur, halo_stroke=a.halo_stroke)
    print(f"{a.out}: {len(info['lines'])} lines, size {info['font_size']}px, block {info['block']}")
    for ln in info["lines"]:
        print("  |", ln)
    if a.preview:
        p = a.out.with_name(a.out.stem + "_preview.jpg")
        preview(a.out, a.preview, p)
        print(f"preview: {p}")


if __name__ == "__main__":
    main()
