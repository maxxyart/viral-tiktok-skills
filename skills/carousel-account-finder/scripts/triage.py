#!/usr/bin/env python3
"""Triage sheets (2026-10-28): one image per job account with the first slide of up to 8 of its job carousels
(biggest first), numbered, plus triage/<h>.txt with bio and captions. A cheap Haiku pass reads them and drops
off-niche accounts before the full OCR (references/triage_prompt.md). CDN only, no ScrapeCreators credits.

Usage: python3 triage.py OUT_DIR [--per 8] [--workers 16]
Writes OUT_DIR/triage/<h>.jpg, OUT_DIR/triage/<h>.txt, OUT_DIR/triage/index.json ({h: n_tiles})."""
import argparse
import io
import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw

from common import to_jpeg

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--per", type=int, default=8)
ap.add_argument("--workers", type=int, default=16)
ap.add_argument("--only-missing", action="store_true")
args = ap.parse_args()
OUT = args.out
cand = json.load(open(os.path.join(OUT, "candidates.json")))
scr = json.load(open(os.path.join(OUT, "screening.json")))
os.makedirs(os.path.join(OUT, "triage"), exist_ok=True)
TW, TH = 300, 400


def get(u):
    try:
        with urlopen(Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as r:
            b = r.read()
    except Exception:
        return None
    try:
        return Image.open(io.BytesIO(b)).convert("RGB")
    except Exception:  # HEIC / WebP: common.to_jpeg, as in fetch_top5.py
        with tempfile.TemporaryDirectory() as td:
            src, dst = os.path.join(td, "in.heic"), os.path.join(td, "out.jpg")
            open(src, "wb").write(b)
            try:
                return Image.open(dst).convert("RGB") if to_jpeg(src, dst, 600) else None
            except Exception:
                return None


def one(h):
    posts = {p["id"]: p for p in json.load(open(os.path.join(OUT, "accounts", f"{h}.json")))["posts"]}
    ps = sorted([posts[i] for i in cand["jobs"][h]["ids"] if i in posts], key=lambda p: -p["views"])[:args.per]
    tiles = []
    for p in ps:
        u = next((x for x in p.get("image_urls") or [] if x), None)
        im = get(u) if u else None
        if im:
            im.thumbnail((TW, TH))
            tiles.append(im)
    if not tiles:
        return h, 0
    cols = 4
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * TW, rows * TH), "white")
    d = ImageDraw.Draw(sheet)
    for k, im in enumerate(tiles):
        x, y = (k % cols) * TW, (k // cols) * TH
        sheet.paste(im, (x + (TW - im.width) // 2, y + (TH - im.height) // 2))
        d.rectangle([x, y, x + 34, y + 30], fill="red")
        d.text((x + 8, y + 8), str(k + 1), fill="white")
    sheet.save(os.path.join(OUT, "triage", f"{h}.jpg"), quality=80)
    m = scr.get(h, {})
    lines = [f"@{h}  followers {m.get('followers')}  roles {','.join(cand['jobs'][h]['roles'])}",
             f"bio: {(m.get('bio') or '').replace(chr(10), ' ')}"]
    for k, p in enumerate(ps[:len(tiles)], 1):
        lines.append(f"{k}. views {p['views']:,} slides {p['n_slides']} caption: {(p.get('desc') or '')[:160]}")
    open(os.path.join(OUT, "triage", f"{h}.txt"), "w").write("\n".join(lines))
    return h, len(tiles)


with ThreadPoolExecutor(args.workers) as ex:
    idx = os.path.join(OUT, "triage", "index.json")
    prev = json.load(open(idx)) if args.only_missing and os.path.exists(idx) else {}
    todo = [h for h in cand["jobs"] if not prev.get(h)]
    res = {**prev, **dict(ex.map(one, todo))}
json.dump(res, open(os.path.join(OUT, "triage", "index.json"), "w"), indent=1)
print(f"triage sheets: {sum(1 for v in res.values() if v)} of {len(res)} accounts; empty: "
      f"{[h for h, v in res.items() if not v][:20]}")
