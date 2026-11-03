#!/usr/bin/env python3
"""Cheap OCR mode (2026-10-28): the top-N carousels by views get the full slide-by-slide OCR, the rest only
slide 1. Needs fetch_top5.py output (acc/<h>/full/<id>_01.jpg).

Usage: python3 hooks.py OUT_DIR --accounts h1,h2,... [--full-top 10]
Writes OUT_DIR/hooks/<h>.jpg (numbered first slides of the account's other carousels), OUT_DIR/hooks/<h>.json
([{"n", "id", "views"}] in tile order) and prints the ids picked for full OCR (also OUT_DIR/hooks/full_ids.json,
{h: [ids]}). Agents: references/hook_prompt.md for the sheets, references/ocr_prompt.md for the full ones."""
import argparse
import json
import os

from PIL import Image, ImageDraw

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--accounts", required=True)
ap.add_argument("--full-top", type=int, default=10)
args = ap.parse_args()
OUT = args.out
os.makedirs(os.path.join(OUT, "hooks"), exist_ok=True)
TW, TH = 300, 400
items = []
for h in [x for x in args.accounts.split(",") if x]:
    for c in json.load(open(os.path.join(OUT, "acc", h, "brief.json")))["top5"]:
        items.append((h, c["id"], c["views"]))
full = sorted(items, key=lambda t: -t[2])[:args.full_top]
full_ids = {}
for h, i, _ in full:
    full_ids.setdefault(h, []).append(i)
json.dump(full_ids, open(os.path.join(OUT, "hooks", "full_ids.json"), "w"), indent=1)
by_acc = {}
for h, i, v in items:
    if i not in full_ids.get(h, []):
        by_acc.setdefault(h, []).append((i, v))
for h, lst in by_acc.items():
    tiles = []
    for i, v in lst:
        p = os.path.join(OUT, "acc", h, "full", f"{i}_01.jpg")
        if os.path.exists(p):
            im = Image.open(p).convert("RGB")
            im.thumbnail((TW, TH))
            tiles.append((i, v, im))
    if not tiles:
        continue
    cols = 4
    sheet = Image.new("RGB", (cols * TW, ((len(tiles) + cols - 1) // cols) * TH), "white")
    d = ImageDraw.Draw(sheet)
    for k, (_, _, im) in enumerate(tiles):
        x, y = (k % cols) * TW, (k // cols) * TH
        sheet.paste(im, (x + (TW - im.width) // 2, y + (TH - im.height) // 2))
        d.rectangle([x, y, x + 34, y + 30], fill="red")
        d.text((x + 8, y + 8), str(k + 1), fill="white")
    sheet.save(os.path.join(OUT, "hooks", f"{h}.jpg"), quality=85)
    json.dump([{"n": k + 1, "id": i, "views": v} for k, (i, v, _) in enumerate(tiles)],
              open(os.path.join(OUT, "hooks", f"{h}.json"), "w"), indent=1)
print(f"full OCR: {len(full)} carousels on {len(full_ids)} accounts; slide-1 only: "
      f"{sum(len(v) for v in by_acc.values())} carousels on {len(by_acc)} accounts")
print(json.dumps(full_ids))
