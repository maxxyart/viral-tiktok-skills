#!/usr/bin/env python3
"""Shrink slide strips before publishing so artifact uploads don't drop.

Usage: python3 shrink.py OUT_DIR [--scale 0.6] [--quality 70] [--min-height 1000]

Re-encodes every acc/<h>/strips/*.jpg: strips taller than --min-height are scaled by --scale,
all are saved as progressive JPEG at --quality. build.py takes slide counts from the feed and the
aspect ratio from the strip itself, so scaled strips render correctly. Run once, right before build.py.
"""
import argparse
import glob
import os

from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--scale", type=float, default=0.6)
ap.add_argument("--quality", type=int, default=70)
ap.add_argument("--min-height", type=int, default=1000)
args = ap.parse_args()

paths = glob.glob(os.path.join(args.out, "acc", "*", "strips", "*.jpg"))
before = sum(os.path.getsize(p) for p in paths)
for p in paths:
    im = Image.open(p).convert("RGB")
    if im.size[1] > args.min_height:
        im = im.resize((round(im.size[0] * args.scale), round(im.size[1] * args.scale)), Image.LANCZOS)
    im.save(p, "JPEG", quality=args.quality, optimize=True, progressive=True)
after = sum(os.path.getsize(p) for p in paths)
print(f"{len(paths)} strips: {before / 1e6:.1f} MB -> {after / 1e6:.1f} MB")
