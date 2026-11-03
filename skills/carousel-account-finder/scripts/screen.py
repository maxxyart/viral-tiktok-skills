#!/usr/bin/env python3
"""Screen TikTok accounts over a time window: carousels vs single photos vs videos, carousel metrics, bio.

Usage:
  python3 screen.py OUT_DIR --since YYYY-MM-DD (--pool OUT_DIR/pool.txt | handle ...) \
      [--min-share 0.4] [--min-median 2000] [--min-total 100000] [--min-carousels 5] \
      [--max-pages 5] [--workers 8]

Definitions:
  carousel = photo-mode post with >= 2 slides; single photo = photo post with 1 slide (not a carousel).
  tier: "карусельный" share > 0.5, "пограничный" min_share..0.5, else "видео-аккаунт"/"фото-аккаунт".
  pass = share >= min_share AND median >= min_median AND total >= min_total AND carousels >= min_carousels
  (all metrics on carousels only, inside the window).
Writes OUT_DIR/accounts/<handle>.json (metrics + every post in window) and merges OUT_DIR/screening.json.
Prints only passing accounts plus totals.
"""
import argparse
import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from common import api, credits_remaining

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("handles", nargs="*")
ap.add_argument("--pool")
ap.add_argument("--since", required=True)
ap.add_argument("--min-share", type=float, default=0.4)
ap.add_argument("--min-median", type=int, default=2000)
ap.add_argument("--min-total", type=int, default=100_000)
ap.add_argument("--min-carousels", type=int, default=5)
ap.add_argument("--max-pages", type=int, default=5)
ap.add_argument("--workers", type=int, default=8)
args = ap.parse_args()

handles = list(args.handles)
if args.pool:
    handles += [h.strip() for h in open(args.pool) if h.strip()]
handles = list(dict.fromkeys(h.lstrip("@") for h in handles))
CUTOFF = int(datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
os.makedirs(os.path.join(args.out, "accounts"), exist_ok=True)


def screen(handle):
    try:
        prof = api("/v1/tiktok/profile", {"handle": handle})
    except Exception:
        prof = {}
    user = prof.get("user") or {}
    stats = prof.get("stats") or prof.get("statsV2") or {}

    posts, seen, cursor, pages, early = [], set(), None, 0, False
    while pages < args.max_pages:
        params = {"handle": handle, "sort_by": "latest"}
        if cursor:
            params["max_cursor"] = cursor
        d = api("/v3/tiktok/profile/videos", params)
        pages += 1
        al = d.get("aweme_list") or []
        stop = False
        for a in al:
            if a.get("aweme_id") in seen:
                continue
            seen.add(a["aweme_id"])
            ct = a.get("create_time") or 0
            pinned = bool(a.get("is_top"))
            if ct < CUTOFF:
                if not pinned:  # feed is newest-first; pinned posts come first regardless of date
                    stop = True
                continue
            st = a.get("statistics") or {}
            imgs = (a.get("image_post_info") or {}).get("images") or []
            urls = []
            for im in imgs:
                ul = ((im.get("display_image") or im.get("thumbnail") or {}).get("url_list")) or []
                jpg = [u for u in ul if ".jpeg" in u or ".jpg" in u]
                urls.append((jpg or ul or [None])[0])
            is_photo = a.get("aweme_type") == 150 or bool(imgs)
            kind = "carousel" if is_photo and len(imgs) >= 2 else "photo" if is_photo else "video"
            posts.append({
                "id": a["aweme_id"], "type": kind,
                "url": f"https://www.tiktok.com/@{handle}/{'photo' if is_photo else 'video'}/{a['aweme_id']}",
                "date": time.strftime("%Y-%m-%d", time.gmtime(ct)), "pinned": pinned,
                "views": st.get("play_count", 0) or 0, "likes": st.get("digg_count", 0) or 0,
                "comments": st.get("comment_count", 0) or 0, "saves": st.get("collect_count", 0) or 0,
                "shares": st.get("share_count", 0) or 0, "n_slides": len(imgs), "image_urls": urls,
                "desc": a.get("desc", ""), "music": ((a.get("music") or {}).get("title") or ""),
                "anchors": [x.get("keyword") or x.get("title") for x in (a.get("anchors") or [])],
            })
        if not user and al:
            au = al[0].get("author") or {}
            user = {"signature": au.get("signature"), "nickname": au.get("nickname"),
                    "follower_count": au.get("follower_count"), "aweme_count": au.get("aweme_count")}
        if stop or not d.get("has_more") or not al:
            break
        if len(posts) >= 30 and not any(p["type"] == "carousel" for p in posts):
            early = True  # clearly not a carousel account; save credits
            break
        cursor = d.get("max_cursor")

    car = [p for p in posts if p["type"] == "carousel"]
    single = [p for p in posts if p["type"] == "photo"]
    vid = [p for p in posts if p["type"] == "video"]
    cv = [p["views"] for p in car]
    share = round(len(car) / len(posts), 2) if posts else 0
    m = {
        "handle": handle, "url": f"https://www.tiktok.com/@{handle}",
        "nickname": user.get("nickname") or "", "bio": user.get("signature") or "",
        "bio_link": ((user.get("bioLink") or {}).get("link")) or "",
        "followers": stats.get("followerCount", user.get("follower_count")),
        "total_likes": stats.get("heartCount") or stats.get("heart"),
        "all_time_posts": stats.get("videoCount", user.get("aweme_count")),
        "pages": pages, "early_stop": early, "capped": pages >= args.max_pages,
        "posts_win": len(posts), "carousels_win": len(car), "single_photos_win": len(single), "videos_win": len(vid),
        "carousel_share": share,
        "car_total_views": sum(cv), "car_median_views": int(statistics.median(cv)) if cv else 0,
        "car_avg_views": int(statistics.mean(cv)) if cv else 0, "car_max_views": max(cv) if cv else 0,
        "car_total_comments": sum(p["comments"] for p in car), "car_total_saves": sum(p["saves"] for p in car),
        "vid_total_views": sum(p["views"] for p in vid), "single_total_views": sum(p["views"] for p in single),
    }
    m["tier"] = ("карусельный" if share > 0.5 else "пограничный" if share >= args.min_share
                 else "фото-аккаунт" if len(single) > len(vid) else "видео-аккаунт")
    r = []
    if share < args.min_share:
        r.append(f"карусели {len(car)}/{len(posts)}" + (f", одиночных фото {len(single)}" if single else ""))
    if m["car_median_views"] < args.min_median:
        r.append(f"медиана {m['car_median_views']}")
    if m["car_total_views"] < args.min_total:
        r.append(f"total {m['car_total_views']}")
    if len(car) < args.min_carousels:
        r.append(f"всего {len(car)} карусел.")
    m["reasons"], m["pass"] = r, not r
    json.dump({"metrics": m, "posts": posts}, open(os.path.join(args.out, "accounts", f"{handle}.json"), "w"),
              ensure_ascii=False, indent=1)
    return m


def safe(h):
    try:
        return screen(h)
    except Exception as e:
        return {"handle": h, "url": f"https://www.tiktok.com/@{h}", "error": str(e)[:200], "pass": False, "reasons": []}


with ThreadPoolExecutor(args.workers) as ex:
    results = list(ex.map(safe, handles))

spath = os.path.join(args.out, "screening.json")
scr = json.load(open(spath)) if os.path.exists(spath) else {}
for r in results:
    scr[r["handle"]] = r
json.dump(scr, open(spath, "w"), ensure_ascii=False, indent=1)
json.dump({k: getattr(args, k) for k in ("since", "min_share", "min_median", "min_total", "min_carousels")},
          open(os.path.join(args.out, "screen_params.json"), "w"), indent=1)

passed = [r for r in results if r.get("pass")]
print(f"screened {len(results)}: pass {len(passed)}, errors {sum(1 for r in results if 'error' in r)}, "
      f"credits left: {credits_remaining()}")
for r in sorted(passed, key=lambda r: -r["car_median_views"]):
    print(f"PASS [{r['tier']}] @{r['handle']}: posts {r['posts_win']} car {r['carousels_win']} "
          f"({int(r['carousel_share'] * 100)}%) single {r['single_photos_win']} vid {r['videos_win']} | "
          f"total {r['car_total_views']:,} med {r['car_median_views']:,} avg {r['car_avg_views']:,} "
          f"com {r['car_total_comments']:,}{' CAPPED' if r['capped'] else ''}")
