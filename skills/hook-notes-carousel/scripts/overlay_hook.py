#!/usr/bin/env python3
"""
Overlay a TikTok-style hook (white bold text + dark halo) on carousel
backgrounds. Auto-darkens bright tops with a gradient scrim (luminance-based),
auto-wraps and auto-shrinks long titles, supports an emoji at the end of the
title. Classic "raw creator text" look — no boxes, no design.

Usage:
  python3 overlay_hook.py --config slides_config.json --input-dir DIR --output-dir DIR

Config = JSON list, one object per slide:
  filename          input background                     (required)
  out_name          output file name                     (default slide_1.png)
  title_lines       list of manual lines  — OR —
  title             one string, auto-wrapped (shrinks if > 4 lines)
  body_text         smaller block under the title        (optional)
  title_emoji       emoji appended after last title line (optional)
  text_y_start_pct  top offset 0-1                       (default 0.05)
  title_size        px                                   (default 56)
  body_size         px                                   (default 40)
  outline_width     dark halo width                      (default 3)
  scrim             "auto" | "none" | 0-255              (default "auto")
  scrim_height_pct  gradient depth 0-1                   (default 0.45)

Only dependency: Pillow.
"""
import argparse
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

# ---- font resolution (same chain as render_notes.py, kept self-contained) ----

FONT_SETS = [
    {"kind": "ttc", "path": "/System/Library/Fonts/HelveticaNeue.ttc"},
    {"kind": "files",
     "reg": "/System/Library/Fonts/Supplemental/Arial.ttf",
     "bold": "/System/Library/Fonts/Supplemental/Arial Bold.ttf"},
    {"kind": "files",
     "reg": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"},
    {"kind": "files",
     "reg": "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "bold": "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"},
    {"kind": "files",
     "reg": "C:/Windows/Fonts/segoeui.ttf",
     "med": "C:/Windows/Fonts/seguisb.ttf",
     "bold": "C:/Windows/Fonts/segoeuib.ttf"},
    {"kind": "files",
     "reg": "C:/Windows/Fonts/arial.ttf",
     "bold": "C:/Windows/Fonts/arialbd.ttf"},
]
EMOJI_FONTS = [
    os.environ.get("HNC_FONT_EMOJI", ""),
    "/System/Library/Fonts/Apple Color Emoji.ttc",
    "C:/Windows/Fonts/seguiemj.ttf",
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
]
EMOJI_STRIKES = [160, 137, 128, 109, 96, 64, 48, 32]
_resolved = None


def _resolve_fonts():
    global _resolved
    if _resolved is not None:
        return _resolved
    env = {w: os.environ.get(f"HNC_FONT_{w.upper()}") for w in ("regular", "bold", "medium")}
    if env["regular"]:
        _resolved = {"reg": (env["regular"], 0),
                     "bold": (env["bold"] or env["regular"], 0),
                     "med": (env["medium"] or env["bold"] or env["regular"], 0)}
        return _resolved
    for spec in FONT_SETS:
        if spec["kind"] == "ttc" and os.path.exists(spec["path"]):
            faces = {}
            for i in range(18):
                try:
                    faces[ImageFont.truetype(spec["path"], 40, index=i).getname()[1]] = i
                except Exception:
                    break
            if not faces:
                continue

            def pick(*names):
                for n in names:
                    if n in faces:
                        return faces[n]
                return 0

            _resolved = {"reg": (spec["path"], pick("Regular", "Roman")),
                         "med": (spec["path"], pick("Medium", "Regular")),
                         "bold": (spec["path"], pick("Bold", "Medium"))}
            return _resolved
        if spec["kind"] == "files" and os.path.exists(spec["reg"]):
            _resolved = {"reg": (spec["reg"], 0),
                         "med": (spec.get("med", spec.get("bold", spec["reg"])), 0),
                         "bold": (spec.get("bold", spec["reg"]), 0)}
            return _resolved
    print("WARNING: no system font found, using Pillow default.", file=sys.stderr)
    _resolved = {}
    return _resolved


def font(size, weight="reg"):
    r = _resolve_fonts()
    if not r:
        return ImageFont.load_default()
    path, idx = r[weight]
    return ImageFont.truetype(path, size, index=idx)


def emoji_img(ch, px):
    for path in EMOJI_FONTS:
        if not path or not os.path.exists(path):
            continue
        for strike in EMOJI_STRIKES:
            try:
                f = ImageFont.truetype(path, strike)
            except OSError:
                continue
            try:
                pad = strike + 16
                tmp = Image.new("RGBA", (pad, pad), (0, 0, 0, 0))
                ImageDraw.Draw(tmp).text((pad // 2, pad // 2), ch, font=f,
                                         anchor="mm", embedded_color=True)
                bb = tmp.getbbox()
                if not bb:
                    break
                tmp = tmp.crop(bb)
                w, h = tmp.size
                k = px / max(w, h)
                return tmp.resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS)
            except Exception:
                continue
    return None


# ------------------------------------------------------------- helpers -----

def wrap_text(draw, text, fnt, max_w):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=fnt) > max_w and cur:
            lines.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


def text_outline(draw, xy, text, fnt, ow, anchor="mt", fill="white",
                 halo=(0, 0, 0, 160)):
    x, y = xy
    for dx in range(-ow, ow + 1):
        for dy in range(-ow, ow + 1):
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=fnt, fill=halo, anchor=anchor)
    draw.text((x, y), text, font=fnt, fill=fill, anchor=anchor)


def top_luminance(img, y0_pct=0.02, y1_pct=0.22):
    """Mean luminance of the band where the hook text will sit."""
    W, H = img.size
    band = img.convert("L").crop((0, int(H * y0_pct), W, int(H * y1_pct)))
    hist = band.histogram()
    total = sum(hist)
    return sum(i * n for i, n in enumerate(hist)) / max(1, total)


def scrim_strength(cfg, img):
    s = cfg.get("scrim", "auto")
    if s == "none":
        return 0
    if isinstance(s, (int, float)):
        return max(0, min(255, int(s)))
    lum = top_luminance(img)
    if lum <= 60:
        return 0
    if lum <= 110:
        return 90
    if lum <= 155:
        return 150
    return 195


def apply_scrim(img, strength, hpct):
    if strength <= 0:
        return img
    W, H = img.size
    span = max(1, int(H * hpct))
    grad = Image.new("L", (1, span))
    grad.putdata([int(strength * (1 - y / span)) for y in range(span)])
    mask = grad.resize((W, span))
    img.paste(Image.new("RGB", (W, span), (0, 0, 0)), (0, 0), mask)
    return img


# ------------------------------------------------------------- render ------

def render_slide(input_dir, output_dir, cfg):
    img = Image.open(os.path.join(input_dir, cfg["filename"])).convert("RGB")
    W, H = img.size
    d = ImageDraw.Draw(img)
    max_w = int(W * 0.88)

    # resolve title lines (manual or auto-wrap with shrink)
    tsize = cfg.get("title_size", 56)
    if cfg.get("title_lines"):
        lines = cfg["title_lines"]
    else:
        while True:
            lines = wrap_text(d, cfg["title"], font(tsize, "bold"), max_w)
            if len(lines) <= 4 or tsize <= 44:
                break
            tsize -= 4

    strength = scrim_strength(cfg, img)
    apply_scrim(img, strength, cfg.get("scrim_height_pct", 0.45))
    d = ImageDraw.Draw(img)  # re-bind after paste

    tf = font(tsize, "bold")
    ow = cfg.get("outline_width", 3)
    cx = W // 2
    y = int(H * cfg.get("text_y_start_pct", 0.05))
    tlh = int(tsize * 1.3)

    emoji = cfg.get("title_emoji")
    for i, line in enumerate(lines):
        last = i == len(lines) - 1
        if last and emoji:
            em = emoji_img(emoji, tsize)
            tw = d.textlength(line, font=tf)
            ew = (em.size[0] + 14) if em else 0
            x0 = cx - (tw + ew) / 2
            text_outline(d, (x0, y), line, tf, ow, anchor="lt")
            if em:
                img.paste(em, (int(x0 + tw + 14), int(y + tsize * 0.05)), em)
        else:
            text_outline(d, (cx, y), line, tf, ow, anchor="mt")
        y += tlh

    if cfg.get("body_text"):
        bsize = cfg.get("body_size", 40)
        bf = font(bsize, "reg")
        y += int(bsize * 0.5)
        for line in wrap_text(d, cfg["body_text"], bf, max_w):
            text_outline(d, (cx, y), line, bf, max(1, ow - 1), anchor="mt",
                         halo=(0, 0, 0, 140))
            y += int(bsize * 1.35)

    if y > H * 0.45:
        print(f"  WARNING: text block ends at {y / H:.0%} of height — "
              "it may cover the subject.", file=sys.stderr)

    out_name = cfg.get("out_name", "slide_1.png")
    out_path = os.path.join(output_dir, out_name)
    os.makedirs(output_dir, exist_ok=True)
    img.save(out_path)
    print(f"  saved {out_path}  (scrim={strength}, title={tsize}px, {len(lines)} lines)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    a = ap.parse_args()
    with open(a.config) as f:
        slides = json.load(f)
    print(f"Overlaying {len(slides)} slide(s)...")
    for cfg in slides:
        render_slide(a.input_dir, a.output_dir, cfg)
    print("Done.")


if __name__ == "__main__":
    main()
