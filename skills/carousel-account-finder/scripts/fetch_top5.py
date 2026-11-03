#!/usr/bin/env python3
"""Download every slide of each passing account's top-5 carousels and prepare page + analysis assets.

Usage: python3 fetch_top5.py OUT_DIR [handle ...]     (default: all accounts with pass=true)
       python3 fetch_top5.py OUT_DIR --jobs             (2026-10-27: every account and carousel in candidates.json
                                                          "jobs": mono top-5, super carousels, repeat candidates)

Per account, under OUT_DIR/acc/<handle>/:
  full/<id>_NN.jpg    slides as JPEG (<=1080px)
  thumbs/<id>.jpg     cover thumbnail for the page rail
  strips/<id>.jpg     all slides side by side (720px cells) – the page shows slides from one strip,
                      which keeps the artifact under its 511-files-per-version limit
  sheets/<id>.jpg     numbered contact sheet of all slides – read by the analysis agents
Also writes acc/<handle>/brief.json (bio, metrics, top-5 with captions + sheet paths, product signals).
Needs Pillow; HEIC/WebP -> JPEG via macOS `sips`, elsewhere Pillow (+ `pillow-heif` for HEIC).
"""
import json
import os
import re
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw

from common import to_jpeg

OUT = sys.argv[1]
scr = json.load(open(os.path.join(OUT, "screening.json")))
JOBS, MED = {}, {}
if "--jobs" in sys.argv:
    cand = json.load(open(os.path.join(OUT, "candidates.json")))
    JOBS, MED = cand["jobs"], cand["median_all"]
handles = [a for a in sys.argv[2:] if a != "--jobs"] or (list(JOBS) if JOBS else [h for h, m in scr.items() if m.get("pass")])
KW = re.compile(r"link in (my )?bio|linkinbio|shop|discount|\bcode\b|% ?off|course|e-?book|workbook|\bbook\b|coaching|"
                r"\bapp\b|download|subscribe|newsletter|program|free guide|\bguide\b|journal|affiliate|#ad\b|"
                r"sponsored|gifted|\border\b|\bbuy\b|patreon|stan\.store|linktr", re.I)


def fetch(url, dst):
    for att in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
                data = r.read()
            with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as f:
                f.write(data)
                src = f.name
            try:
                if to_jpeg(src, dst, 1080):
                    return True
            finally:
                os.remove(src)
        except Exception as e:
            print(f"  fail {os.path.basename(dst)} try {att + 1}: {str(e)[:70]}", file=sys.stderr)
            time.sleep(2 * (att + 1))
    return False


def make_sheet(paths, dst, label):
    ims = [Image.open(p).convert("RGB") for p in paths]
    cols, W = min(6, len(ims)), 300
    H = max(int(W * im.height / im.width) for im in ims)
    rows = (len(ims) + cols - 1) // cols
    sh = Image.new("RGB", (cols * W, rows * H + 30), "white")
    d = ImageDraw.Draw(sh)
    d.text((6, 8), label, fill="black")
    for i, im in enumerate(ims):
        im.thumbnail((W, H))
        x, y = (i % cols) * W, 30 + (i // cols) * H
        sh.paste(im, (x, y))
        d.rectangle([x, y, x + 26, y + 18], fill="red")
        d.text((x + 4, y + 3), str(i + 1), fill="white")
    sh.save(dst, quality=82)


def make_strip(paths, dst):
    first = Image.open(paths[0])
    cw, ch = 720, round(720 * first.height / first.width)
    st = Image.new("RGB", (cw * len(paths), ch), "black")
    for k, p in enumerate(paths):
        im = Image.open(p).convert("RGB")
        im.thumbnail((cw, ch))
        st.paste(im, (k * cw + (cw - im.width) // 2, (ch - im.height) // 2))
    st.save(dst, "JPEG", quality=78, optimize=True, progressive=True)


for h in handles:
    acc = json.load(open(os.path.join(OUT, "accounts", f"{h}.json")))
    m = {**acc["metrics"], **scr.get(h, {})}
    posts = acc["posts"]
    top5 = sorted([p for p in posts if p["type"] == "carousel" and p["n_slides"] >= 2], key=lambda p: -p["views"])[:5]
    if h in JOBS:
        top5 = sorted([p for p in posts if p["id"] in JOBS[h]["ids"]], key=lambda p: -p["views"])
    base = os.path.join(OUT, "acc", h)
    for sub in ("full", "thumbs", "strips", "sheets"):
        os.makedirs(os.path.join(base, sub), exist_ok=True)
    jobs = [(u, os.path.join(base, "full", f"{p['id']}_{n:02d}.jpg"))
            for p in top5 for n, u in enumerate(p["image_urls"], 1) if u]
    with ThreadPoolExecutor(8) as ex:
        ok = list(ex.map(lambda j: os.path.exists(j[1]) or fetch(*j), jobs))
    for p in top5:
        full = [os.path.join(base, "full", f"{p['id']}_{n:02d}.jpg") for n in range(1, len(p["image_urls"]) + 1)]
        full = [f for f in full if os.path.exists(f)]
        p["slides_ok"] = len(full)
        if not full:
            continue
        im = Image.open(full[0]).convert("RGB")
        im.thumbnail((200, 300))
        im.save(os.path.join(base, "thumbs", f"{p['id']}.jpg"), "JPEG", quality=78)
        make_strip(full, os.path.join(base, "strips", f"{p['id']}.jpg"))
        make_sheet(full, os.path.join(base, "sheets", f"{p['id']}.jpg"),
                   f"@{h} {p['date']} views {p['views']:,} saves {p['saves']:,} slides {len(full)}")

    sig = [p for p in posts if p.get("anchors") or KW.search(p.get("desc") or "")]
    brief = {
        "handle": h, "url": m["url"], "roles": JOBS.get(h, {}).get("roles", ["mono"]), "median_all_posts": MED.get(h), "nickname": m.get("nickname"), "bio": m.get("bio"),
        "bio_link": m.get("bio_link"), "followers": m.get("followers"),
        "metrics": {k: m.get(k) for k in ("posts_win", "carousels_win", "single_photos_win", "videos_win",
                                          "carousel_share", "car_total_views", "car_median_views", "car_avg_views",
                                          "car_total_comments", "vid_total_views")},
        "top5": [{"id": p["id"], "url": p["url"], "date": p["date"], "views": p["views"], "saves": p["saves"],
                  "comments": p["comments"], "n_slides": p["n_slides"], "caption": p["desc"], "music": p["music"],
                  "x": round(p["views"] / MED[h], 1) if MED.get(h) else None,
                  "sheet": os.path.abspath(os.path.join(base, "sheets", f"{p['id']}.jpg"))}
                 for p in top5 if p.get("slides_ok")],
        "product_signals": {"posts_with_anchor_or_keyword": len(sig),
                            "examples": [{"type": p["type"], "date": p["date"], "views": p["views"],
                                          "anchors": p.get("anchors"), "caption": (p["desc"] or "")[:220]}
                                         for p in sig[:14]]},
        "video_caption_samples": [{"date": p["date"], "views": p["views"], "caption": (p["desc"] or "")[:160]}
                                  for p in posts if p["type"] == "video"][:10],
        "recent_carousel_captions": [(p["desc"] or "")[:160] for p in posts if p["type"] == "carousel"][:12],
    }
    json.dump(brief, open(os.path.join(base, "brief.json"), "w"), ensure_ascii=False, indent=1)
    print(f"@{h}: slides {sum(ok)}/{len(jobs)}; top5 " +
          ", ".join(f"{p['views']:,}({p.get('slides_ok', 0)}sl)" for p in top5))
