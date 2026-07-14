#!/usr/bin/env python3
"""
Render an iOS-Notes-style screenshot slide — the "payload" slide of a
hook+notes carousel. Deterministic Pillow render: real-looking status bar,
"< Notes" nav bar, centered date header, bold title, numbered list with
hanging indent, optional CTA line with a color-emoji.

Usage:
  python3 render_notes.py --content notes.json --out final/slide_2.png
                          [--width 1152] [--height 2048]

Content JSON fields:
  date         "July 8, 2026 at 7:12 AM"      (required)
  clock        "7:12"                          (optional; derived from `date`)
  title        bold note title                 (required)
  items        list of 3-6 numbered strings    (required)
  cta          footer line                     (optional)
  cta_emoji    single emoji after the CTA      (optional)
  theme        "light" | "dark"                (default light)
  smart_quotes true/false                      (default true)

Exit codes: 0 = ok, 2 = content overflows even at minimum font size.
Only dependency: Pillow.
"""
import argparse
import json
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------- fonts ----

FONT_SETS = [
    {"kind": "ttc", "path": "/System/Library/Fonts/HelveticaNeue.ttc"},          # macOS
    {"kind": "files",
     "reg": "/System/Library/Fonts/Supplemental/Arial.ttf",
     "bold": "/System/Library/Fonts/Supplemental/Arial Bold.ttf"},                 # macOS fallback
    {"kind": "files",
     "reg": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"},              # Linux
    {"kind": "files",
     "reg": "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "bold": "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"},      # Linux
    {"kind": "files",
     "reg": "C:/Windows/Fonts/segoeui.ttf",
     "med": "C:/Windows/Fonts/seguisb.ttf",
     "bold": "C:/Windows/Fonts/segoeuib.ttf"},                                     # Windows
    {"kind": "files",
     "reg": "C:/Windows/Fonts/arial.ttf",
     "bold": "C:/Windows/Fonts/arialbd.ttf"},                                      # Windows
]

EMOJI_FONTS = [
    os.environ.get("HNC_FONT_EMOJI", ""),
    "/System/Library/Fonts/Apple Color Emoji.ttc",       # macOS (fixed strikes!)
    "C:/Windows/Fonts/seguiemj.ttf",                      # Windows (scalable)
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",  # Linux (fixed strike)
]
EMOJI_STRIKES = [160, 137, 128, 109, 96, 64, 48, 32]  # first that loads wins

_resolved = None


def _resolve_fonts():
    """Return dict weight -> (path, index). Honors HNC_FONT_* env overrides."""
    global _resolved
    if _resolved is not None:
        return _resolved
    env = {w: os.environ.get(f"HNC_FONT_{w.upper()}") for w in ("regular", "bold", "medium")}
    if env["regular"]:
        reg = (env["regular"], 0)
        bold = (env["bold"] or env["regular"], 0)
        med = (env["medium"] or env["bold"] or env["regular"], 0)
        _resolved = {"reg": reg, "bold": bold, "med": med}
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

            _resolved = {
                "reg": (spec["path"], pick("Regular", "Roman", "Book")),
                "med": (spec["path"], pick("Medium", "Regular")),
                "bold": (spec["path"], pick("Bold", "Medium")),
            }
            return _resolved
        if spec["kind"] == "files" and os.path.exists(spec["reg"]):
            reg = (spec["reg"], 0)
            bold = (spec.get("bold", spec["reg"]), 0)
            med = (spec.get("med", spec.get("bold", spec["reg"])), 0)
            _resolved = {"reg": reg, "med": med, "bold": bold}
            return _resolved
    print("WARNING: no system font found, using Pillow default (ugly).", file=sys.stderr)
    _resolved = {}
    return _resolved


def font(size, weight="reg"):
    r = _resolve_fonts()
    if not r:
        return ImageFont.load_default()
    path, idx = r[weight]
    return ImageFont.truetype(path, size, index=idx)


def emoji_img(ch, px):
    """Render one emoji via a color font. Fixed-strike fonts (Apple, Noto) only
    accept specific sizes — probe them and downscale. Returns RGBA or None."""
    for path in EMOJI_FONTS:
        if not path or not os.path.exists(path):
            continue
        for strike in EMOJI_STRIKES:
            try:
                f = ImageFont.truetype(path, strike)
            except OSError:
                continue  # invalid pixel size for this fixed-strike font
            try:
                pad = strike + 16
                tmp = Image.new("RGBA", (pad, pad), (0, 0, 0, 0))
                ImageDraw.Draw(tmp).text((pad // 2, pad // 2), ch, font=f,
                                         anchor="mm", embedded_color=True)
                bb = tmp.getbbox()
                if not bb:
                    break  # glyph missing in this font
                tmp = tmp.crop(bb)
                w, h = tmp.size
                k = px / max(w, h)
                return tmp.resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS)
            except Exception:
                continue
    return None


# ---------------------------------------------------------------- text -----

def smartify(s):
    """Straight quotes -> curly, like iOS keyboard would produce."""
    s = s.replace("'", "’")
    out, opened = [], False
    for i, ch in enumerate(s):
        if ch == '"':
            prev = s[i - 1] if i else " "
            if prev in " \n(—–-[{" or i == 0:
                out.append("“"); opened = True
            else:
                out.append("”"); opened = False
        else:
            out.append(ch)
    return "".join(out)


def wrap(draw, text, fnt, max_w):
    lines = []
    for seg in text.split("\n"):
        if seg == "":
            lines.append("")
            continue
        cur = ""
        for w in seg.split(" "):
            t = (cur + " " + w).strip()
            if draw.textlength(t, font=fnt) > max_w and cur:
                lines.append(cur)
                cur = w
            else:
                cur = t
        lines.append(cur)
    return lines


def derive_clock(date_str):
    m = re.search(r"\bat\s+(\d{1,2}:\d{2})", date_str)
    return m.group(1) if m else "9:41"


# ---------------------------------------------------------------- render ---

THEMES = {
    "light": {"bg": (253, 252, 249), "ink": (28, 28, 30), "date": (142, 142, 147),
              "accent": (255, 179, 0), "chrome": (28, 28, 30), "chip": (238, 238, 236)},
    "dark": {"bg": (28, 28, 30), "ink": (229, 229, 234), "date": (152, 152, 157),
             "accent": (255, 214, 10), "chrome": (229, 229, 234), "chip": (44, 44, 46)},
}


def draw_chrome(img, d, W, clock, th):
    """Status bar + '< Notes' nav bar."""
    C = th["chrome"]; Y = th["accent"]
    sb = 46
    d.text((70, sb), clock, font=font(38, "bold"), fill=C, anchor="lm")
    rx = W - 66
    bw, bh = 46, 22
    by, bx = sb - bh // 2, rx - 46
    d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=6, outline=C, width=3)
    d.rectangle([bx + 4, by + 4, bx + int(bw * 0.72), by + bh - 4], fill=C)
    d.rounded_rectangle([bx + bw + 2, by + 6, bx + bw + 6, by + bh - 6], radius=2, fill=C)
    wx, wy = bx - 34, sb + 6
    for r in (16, 11, 6):
        d.arc([wx - r, wy - r, wx + r, wy + r], start=225, end=315, fill=C, width=3)
    d.ellipse([wx - 2, wy - 2, wx + 2, wy + 2], fill=C)
    sx = wx - 58
    for i in range(4):
        h = 8 + i * 6
        d.rounded_rectangle([sx + i * 12, sb + 12 - h, sx + i * 12 + 8, sb + 12], radius=2, fill=C)

    nav = 128
    d.line([(74, nav - 13), (60, nav), (74, nav + 13)], fill=Y, width=5, joint="curve")
    d.text((86, nav), "Notes", font=font(41, "reg"), fill=Y, anchor="lm")
    sh = W - 150
    d.rounded_rectangle([sh - 15, nav - 6, sh + 15, nav + 22], radius=5, outline=Y, width=4)
    d.line([(sh, nav - 26), (sh, nav + 6)], fill=Y, width=4)
    d.line([(sh - 9, nav - 17), (sh, nav - 27), (sh + 9, nav - 17)], fill=Y, width=4, joint="curve")
    mc = W - 78
    d.ellipse([mc - 22, nav - 22, mc + 22, nav + 22], fill=th["chip"])
    for dx in (-9, 0, 9):
        d.ellipse([mc + dx - 2, nav - 2, mc + dx + 2, nav + 2], fill=Y)


def body_height(d, c, W, ML, ts, bs):
    """Dry-run measure of the note body below the date header."""
    content_w = W - ML * 2
    tlh, blh = round(ts * 1.27), round(bs * 1.4)
    gap, num = round(bs * 0.7), round(bs * 1.2)
    y = len(wrap(d, c["title"], font(ts, "bold"), content_w)) * tlh + 30
    bf = font(bs, "reg")
    for it in c["items"]:
        y += len(wrap(d, it, bf, content_w - num)) * blh + gap
    if c.get("cta"):
        y += 16 + blh
    return y


def render(c, out, W, H):
    theme = THEMES[c.get("theme", "light")]
    if c.get("smart_quotes", True):
        c = dict(c)
        c["title"] = smartify(c["title"])
        c["items"] = [smartify(i) for i in c["items"]]
        if c.get("cta"):
            c["cta"] = smartify(c["cta"])

    img = Image.new("RGB", (W, H), theme["bg"])
    d = ImageDraw.Draw(img)
    draw_chrome(img, d, W, c.get("clock") or derive_clock(c["date"]), theme)

    ML = 74
    content_w = W - ML * 2
    top = 250

    # font ladder: shrink until the body fits above H*0.94
    ladder = [(52, 43), (52, 41), (50, 39), (48, 37), (46, 35)]
    ts, bs = ladder[-1]
    fitted = False
    for t, b in ladder:
        if top + 74 + body_height(d, c, W, ML, t, b) <= H * 0.94:
            ts, bs = t, b
            fitted = True
            break
    if not fitted:
        print("WARNING: content overflows even at minimum size — trim item wording.",
              file=sys.stderr)

    d.text((W // 2, top), c["date"], font=font(31, "reg"), fill=theme["date"], anchor="mm")
    y = top + 74

    tf = font(ts, "bold")
    tlh = round(ts * 1.27)
    for line in wrap(d, c["title"], tf, content_w):
        d.text((ML, y), line, font=tf, fill=theme["ink"], anchor="la")
        y += tlh
    y += 30

    bf, nf = font(bs, "reg"), font(bs, "med")
    blh, gap, num = round(bs * 1.4), round(bs * 0.7), round(bs * 1.2)
    for i, it in enumerate(c["items"], 1):
        d.text((ML, y), f"{i}.", font=nf, fill=theme["ink"], anchor="la")
        for line in wrap(d, it, bf, content_w - num):
            d.text((ML + num, y), line, font=bf, fill=theme["ink"], anchor="la")
            y += blh
        y += gap

    if c.get("cta"):
        y += 16
        cf = font(bs, "med")
        d.text((ML, y), c["cta"], font=cf, fill=theme["ink"], anchor="la")
        if c.get("cta_emoji"):
            cw = d.textlength(c["cta"], font=cf)
            em = emoji_img(c["cta_emoji"], bs + 4)
            if em:
                img.paste(em, (int(ML + cw + 12), int(y - 2)), em)
            else:
                print("NOTE: no color-emoji font found; CTA emoji skipped.", file=sys.stderr)

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    img.save(out)
    print(f"saved {out} {img.size} title={ts}px body={bs}px")
    return 0 if fitted else 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--content", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--width", type=int, default=1152)
    ap.add_argument("--height", type=int, default=2048)
    a = ap.parse_args()
    with open(a.content) as f:
        c = json.load(f)
    sys.exit(render(c, a.out, a.width, a.height))


if __name__ == "__main__":
    main()
