#!/usr/bin/env python3
"""Fetch the posts of a TikTok or Instagram account via ScrapeCreators
and download all cover images (HEIC auto-converted to JPEG via sips).

Usage:
  python3 fetch_covers.py HANDLE --platform tiktok|instagram --out-dir DIR \
      [--count N | --all | --since YYYY-MM-DD] [--auto-max 150] [--ig-source reels|posts] \
      [--slides-top 6] [--slides-for 37,48]

Sample: --count N = latest N; --all = the whole feed; --since = posts on/after the date
(combine with --count to cap). With none of them the whole account is fetched when the
profile has ≤ --auto-max posts, otherwise the latest 50. Early hits sit at the bottom of
the feed: on an 86-post account the latest 50 lost 7 of the top-10 posts.

Instagram: --ig-source reels (default) = /v1/instagram/user/reels, views available.
posts = the whole grid (reels, carousels, photos) via /v2/instagram/user/posts with
carousel slides; Instagram shows no views for carousels and photos, so this mode ranks
by likes (meta.metric = "likes").

Output:
  DIR/meta.json          — sample, metric, profile + per-video metrics + cover paths (index-aligned)
  DIR/slide_urls.json    — carousel slide URLs by post id (for fetch_slides.py)
  DIR/covers/NN_ID.jpg   — cover images, NN = index in meta.json
  DIR/carousels/NN/      — only with --slides-top/--slides-for: all slides + top comments
  stdout                 — SAMPLE line, then one digest line per video:
                           index | views | date | slides | pin | id

Per video: id, desc, views, likes, comments, shares, saves, date, duration,
slides (0 = video/photo), isCarousel, isPinned, kind (video/carousel/reel/photo), music,
link (/photo/ for TikTok carousels), coverUrl, coverFile.

Env: SCRAPE_CREATORS_API_KEY (or SCRAPECREATORS_API_KEY), or a KEY=value / export line in a file
     passed with --env-file. Shell configs are never searched automatically.
"""
import argparse, json, os, re, shutil, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENV_FILES = []  # only files passed with --env-file: no automatic search of shell configs
ALIASES = {"SCRAPE_CREATORS_API_KEY": "SCRAPECREATORS_API_KEY", "GOOGLE_API_KEY": "GEMINI_API_KEY"}
ALL = 10 ** 9
PIN_SLOTS = 3  # TikTok and Instagram pin at most 3 posts, always at the top of the feed

def env_key(name):
    for n in (name, ALIASES.get(name)):
        if n and os.environ.get(n):
            return os.environ[n]
    for path in ENV_FILES:
        if not os.path.exists(path):
            continue
        for line in open(path, encoding="utf-8", errors="ignore"):
            m = re.match(rf'^(?:export\s+)?{name}\s*=\s*"?([^"\s#]+)"?', line.strip())
            if m:
                return m.group(1)
    sys.exit(f"ERROR: {name} is not set: export it or pass --env-file FILE")

def api_get(path, params, key, attempts=5):
    """GET with exponential backoff: ScrapeCreators returns sporadic 500s, and a
    silently failed page would truncate the sample."""
    qs = urlencode({k: v for k, v in params.items() if v is not None})
    req = Request(f"https://api.scrapecreators.com{path}?{qs}", headers={"x-api-key": key})
    for att in range(attempts):
        try:
            with urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if att == attempts - 1:
                raise
            wait = 2 ** att
            print(f"  retry {att + 1}/{attempts - 1} {path} in {wait}s: {str(e)[:80]}", file=sys.stderr)
            time.sleep(wait)

def to_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None

def fetch_profile(platform, handle, key):
    """Account totals for the report header, the completeness check and the auto sample size.
    Never fatal."""
    try:
        if platform == "tiktok":
            p = api_get("/v1/tiktok/profile", {"handle": handle}, key)
            st = p.get("stats") or p.get("statsV2") or {}
            u = p.get("user") or {}
            return {"followers": to_int(st.get("followerCount")),
                    "totalPosts": to_int(st.get("videoCount")),
                    "likes": to_int(st.get("heartCount") or st.get("heart")),
                    "nickname": u.get("nickname"), "bio": u.get("signature")}
        p = api_get("/v1/instagram/profile", {"handle": handle}, key)
        u = (p.get("data") or {}).get("user") or {}
        return {"followers": to_int((u.get("edge_followed_by") or {}).get("count")),
                "totalPosts": to_int((u.get("edge_owner_to_timeline_media") or {}).get("count")),
                "likes": None, "nickname": u.get("full_name"), "bio": u.get("biography")}
    except Exception as e:
        print(f"  profile fetch failed, continuing without: {str(e)[:80]}", file=sys.stderr)
        return None

def in_window(v, pos, since):
    """keep / skip / stop for a --since window. Pinned posts are older than the rest of the
    feed, so an old post ends the feed only after the pin slots."""
    if not since or v["date"] >= since:
        return "keep"
    return "skip" if v["isPinned"] or pos < PIN_SLOTS else "stop"

def fetch_tiktok(handle, count, key, since=None):
    videos, slide_urls, cursor, page, pos, skipped = [], {}, None, 0, 0, 0
    while len(videos) < count:
        page += 1
        print(f"  page {page} (cursor={cursor or 'start'})...", file=sys.stderr)
        resp = api_get("/v3/tiktok/profile/videos",
                       {"handle": handle, "max_cursor": cursor, "sort_by": "latest", "trim": False}, key)
        items = resp.get("aweme_list") or []
        if not items:
            break
        stop = False
        for it in items:
            if len(videos) >= count:
                break
            vid = it.get("video") or {}
            cover = None
            for field in ("origin_cover", "cover_large", "cover", "dynamic_cover", "ai_dynamic_cover"):
                urls = ((vid.get(field) or {}).get("url_list")) or []
                if urls:
                    cover = urls[0]
                    break
            st = it.get("statistics") or {}
            vid_id = str(it.get("aweme_id") or it.get("id") or "unknown")
            images = (it.get("image_post_info") or {}).get("images") or []
            v = {
                "id": vid_id,
                "desc": (it.get("desc") or "")[:200],
                "views": st.get("play_count") or 0,
                "likes": st.get("digg_count") or 0,
                "comments": st.get("comment_count") or 0,
                "shares": st.get("share_count") or 0,
                "saves": st.get("collect_count") or 0,
                "date": time.strftime("%Y-%m-%d", time.gmtime(it["create_time"])) if it.get("create_time") else "unknown",
                "duration": vid.get("duration") or 0,
                "slides": len(images),
                "isCarousel": bool(images),
                "isPinned": bool(it.get("is_top")),
                "kind": "carousel" if images else "video",
                "music": ((it.get("music") or {}).get("title") or "")[:80],
                "link": f"https://www.tiktok.com/@{handle}/{'photo' if images else 'video'}/{vid_id}",
                "coverUrl": cover,
                "videoUrl": None if images else next(
                    (u for f in ("play_addr", "download_addr")
                     for u in ((vid.get(f) or {}).get("url_list") or [])[:1]), None),
            }
            verdict = in_window(v, pos, since)
            pos += 1
            if verdict == "stop":
                stop = True
                break
            if verdict == "skip":
                skipped += 1
                continue
            if images:
                slide_urls[vid_id] = [
                    (((img.get("display_image") or img.get("thumbnail") or {}).get("url_list")) or [None])[0]
                    for img in images]
            videos.append(v)
        cursor = resp.get("max_cursor")
        if stop or not int(resp.get("has_more") or 0) or cursor is None:
            break
    return videos, slide_urls, skipped

def fetch_instagram(handle, count, key, since=None):
    videos, max_id, page, pos, skipped = [], None, 0, 0, 0
    while len(videos) < count:
        page += 1
        print(f"  page {page} (cursor={max_id or 'start'})...", file=sys.stderr)
        resp = api_get("/v1/instagram/user/reels", {"handle": handle, "max_id": max_id}, key)
        items = resp.get("items") or []
        if not items:
            break
        stop = False
        for it in items:
            if len(videos) >= count:
                break
            m = it.get("media") or it
            cands = ((m.get("image_versions2") or {}).get("candidates")) or []
            cap = m.get("caption")
            code = m.get("code", "")
            v = {
                "id": str(m.get("pk") or m.get("id")),
                "desc": ((cap.get("text", "") if isinstance(cap, dict) else "") or "")[:200],
                "views": m.get("play_count") or m.get("ig_play_count") or 0,
                "likes": m.get("like_count") or 0,
                "comments": m.get("comment_count") or 0,
                "shares": m.get("reshare_count") or 0,
                "saves": m.get("save_count") or 0,
                "date": time.strftime("%Y-%m-%d", time.gmtime(m["taken_at"])) if m.get("taken_at") else "unknown",
                "duration": m.get("video_duration") or 0,
                "slides": 0,
                "isCarousel": False,
                "isPinned": bool(m.get("clips_tab_pinned_user_ids") or m.get("timeline_pinned_user_ids")),
                "kind": "reel",
                "music": "",
                "link": f"https://www.instagram.com/reel/{code}/" if code else "",
                "coverUrl": cands[0]["url"] if cands else None,
                "videoUrl": ((m.get("video_versions") or [{}])[0]).get("url"),
            }
            verdict = in_window(v, pos, since)
            pos += 1
            if verdict == "stop":
                stop = True
                break
            if verdict == "skip":
                skipped += 1
                continue
            videos.append(v)
        pi = resp.get("paging_info") or {}
        nxt = pi.get("max_id") or resp.get("max_id")
        if stop or pi.get("more_available") is False or not nxt or nxt == max_id:
            break
        max_id = nxt
    return videos, {}, skipped

def ig_image(m):
    return m.get("display_uri") or ((((m.get("image_versions2") or {}).get("candidates")) or [{}])[0].get("url"))

def fetch_instagram_posts(handle, count, key, since=None):
    """Whole grid: media_type 1 = photo, 2 = reel, 8 = carousel. No views for 1 and 8."""
    videos, slide_urls, cursor, page, pos, skipped = [], {}, None, 0, 0, 0
    while len(videos) < count:
        page += 1
        print(f"  page {page} (cursor={(cursor or 'start')[:20]})...", file=sys.stderr)
        resp = api_get("/v2/instagram/user/posts", {"handle": handle, "next_max_id": cursor}, key)
        items = resp.get("items") or []
        if not items:
            break
        stop = False
        for m in items:
            if len(videos) >= count:
                break
            mt = m.get("media_type")
            kids = m.get("carousel_media") or []
            cap = m.get("caption")
            code = m.get("code", "")
            vid_id = str(m.get("pk") or m.get("id"))
            reel = mt == 2
            v = {
                "id": vid_id,
                "desc": ((cap.get("text", "") if isinstance(cap, dict) else "") or "")[:200],
                "views": m.get("play_count") or m.get("ig_play_count") or 0,
                "likes": m.get("like_count") or 0,
                "comments": m.get("comment_count") or 0,
                "shares": 0,
                "saves": 0,
                "date": time.strftime("%Y-%m-%d", time.gmtime(m["taken_at"])) if m.get("taken_at") else "unknown",
                "duration": m.get("video_duration") or 0,
                "slides": (m.get("carousel_media_count") or len(kids)) if mt == 8 else 0,
                "isCarousel": mt == 8,
                "isPinned": bool(m.get("timeline_pinned_user_ids")),
                "kind": "reel" if reel else "carousel" if mt == 8 else "photo",
                "music": "",
                "link": f"https://www.instagram.com/{'reel' if reel else 'p'}/{code}/" if code else (m.get("url") or ""),
                "coverUrl": ig_image(m) or (ig_image(kids[0]) if kids else None),
            }
            verdict = in_window(v, pos, since)
            pos += 1
            if verdict == "stop":
                stop = True
                break
            if verdict == "skip":
                skipped += 1
                continue
            if kids:
                slide_urls[vid_id] = [ig_image(k) for k in kids]
            videos.append(v)
        cursor = resp.get("next_max_id")
        if stop or not resp.get("more_available") or not cursor:
            break
    return videos, slide_urls, skipped

def is_heic(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return b"ftypheic" in head or b"ftypheix" in head or b"ftypmif1" in head or b"ftypavif" in head

def is_blank(path):
    """Flat single-colour frame (fade-in start). Needs Pillow; without it never blank."""
    try:
        from PIL import Image, ImageStat
        return ImageStat.Stat(Image.open(path).convert("L").resize((64, 114))).stddev[0] < 12  # fade-in 7.9, real blurry frame 22.5
    except Exception:
        return False

def download_cover(args):
    i, v, covers_dir = args
    if not v.get("coverUrl"):
        v["coverFile"] = None
        return f"{i:02d}: no cover URL"
    dst = os.path.join(covers_dir, f"{i:02d}_{v['id']}.jpg")
    tmp = dst + ".tmp"
    try:
        req = Request(v["coverUrl"], headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=45) as r, open(tmp, "wb") as f:
            f.write(r.read())
        if is_heic(tmp):
            res = subprocess.run(["sips", "-s", "format", "jpeg", tmp, "--out", dst],
                                 capture_output=True)
            os.remove(tmp)
            if res.returncode != 0:
                v["coverFile"] = None
                return f"{i:02d}: HEIC convert failed"
        else:
            os.replace(tmp, dst)
        v["coverFile"], v["coverSource"] = dst, "thumbnail"
        # Video: the grid thumbnail is any frame or an uploaded image the creator picked; the feed
        # starts the video at frame 0, so frame 0 is the hook viewers see. It replaces coverFile.
        if v.get("videoUrl"):
            thumbs = os.path.join(os.path.dirname(covers_dir), "thumbs")
            os.makedirs(thumbs, exist_ok=True)
            thumb = os.path.join(thumbs, os.path.basename(dst))
            os.replace(dst, thumb)
            v["thumbFile"] = thumb
            ff = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-user_agent", "Mozilla/5.0",
                                 "-headers", "Referer: https://www.tiktok.com/\r\n", "-i", v["videoUrl"],
                                 "-frames:v", "1", "-q:v", "2", dst], capture_output=True, timeout=120)
            if ff.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 0:
                v["coverSource"] = "first_frame"
                if is_blank(dst):  # fade-in from a flat colour: the hook appears a moment later
                    ff2 = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-user_agent", "Mozilla/5.0",
                                          "-headers", "Referer: https://www.tiktok.com/\r\n", "-ss", "0.5",
                                          "-i", v["videoUrl"], "-frames:v", "1", "-q:v", "2", dst],
                                         capture_output=True, timeout=120)
                    if ff2.returncode == 0:
                        v["coverSource"] = "frame_0.5s"
            else:
                shutil.copyfile(thumb, dst)
                return f"{i:02d}: first frame failed, kept thumbnail ({ff.stderr.decode()[:60].strip()})"
        return None
    except Exception as e:
        v["coverFile"] = None
        if os.path.exists(tmp):
            os.remove(tmp)
        return f"{i:02d}: {str(e)[:80]}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("handle")
    ap.add_argument("--platform", choices=["tiktok", "instagram"], required=True)
    ap.add_argument("--count", type=int, help="latest N posts (default: auto, see --auto-max)")
    ap.add_argument("--all", action="store_true", help="the whole feed")
    ap.add_argument("--since", help="only posts published on/after YYYY-MM-DD")
    ap.add_argument("--auto-max", type=int, default=150,
                    help="without --count/--all/--since: fetch everything when the account has ≤ this many posts")
    ap.add_argument("--ig-source", choices=["reels", "posts"], default="reels")
    ap.add_argument("--env-file", action="append", default=[], help="file with KEY=value lines (repeatable)")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--slides-top", type=int, default=0,
                    help="also download all slides + top comments of the N best carousels")
    ap.add_argument("--slides-for", default="",
                    help="comma-separated extra indexes to download slides for")
    args = ap.parse_args()
    if args.since and not re.match(r"^\d{4}-\d{2}-\d{2}$", args.since):
        sys.exit("ERROR: --since must be YYYY-MM-DD")

    handle = args.handle.lstrip("@").rstrip("/").split("/")[-1]
    covers_dir = os.path.join(args.out_dir, "covers")
    os.makedirs(covers_dir, exist_ok=True)
    ENV_FILES[:] = [os.path.expanduser(p) for p in args.env_file]
    key = env_key("SCRAPE_CREATORS_API_KEY")

    # profile first: its post counter decides the sample size
    profile = fetch_profile(args.platform, handle, key)
    total = (profile or {}).get("totalPosts")
    if args.since:
        count, mode = args.count or ALL, "since"
    elif args.count:
        count, mode = args.count, "latest"
    elif args.all or (total is not None and total <= args.auto_max):
        count, mode = ALL, "all"
    else:
        count, mode = 50, "latest"
    posts_mode = args.platform == "instagram" and args.ig_source == "posts"
    metric = "likes" if posts_mode else "views"

    label = "all" if count == ALL else str(count)
    print(f"Fetching {label} {args.platform} posts for @{handle} (mode {mode}, account total "
          f"{total if total is not None else 'unknown'})...", file=sys.stderr)
    fetch = fetch_tiktok if args.platform == "tiktok" else fetch_instagram_posts if posts_mode else fetch_instagram
    videos, slide_urls, skipped = fetch(handle, count, key, args.since)
    if not videos:
        sys.exit(f"ERROR: no videos found for @{handle} on {args.platform}")
    print(f"  fetched {len(videos)} posts, downloading covers...", file=sys.stderr)

    with ThreadPoolExecutor(10) as ex:
        errs = [e for e in ex.map(download_cover, [(i, v, covers_dir) for i, v in enumerate(videos)]) if e]
    for e in errs:
        print(f"  cover fail {e}", file=sys.stderr)

    n = len(videos)
    meta = {"platform": args.platform, "handle": handle, "fetchedAt": time.strftime("%Y-%m-%d"),
            "requested": args.count, "metric": metric,
            "igSource": args.ig_source if args.platform == "instagram" else None,
            "sample": {"mode": mode, "since": args.since, "fetched": n, "accountTotal": total,
                       "skippedPinned": skipped, "autoMax": args.auto_max},
            "profile": profile, "videos": videos}
    meta_path = os.path.join(args.out_dir, "meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    with open(os.path.join(args.out_dir, "slide_urls.json"), "w", encoding="utf-8") as f:
        json.dump(slide_urls, f)

    ok = sum(1 for v in videos if v.get("coverFile"))
    print(f"  covers: {ok}/{n} | meta: {meta_path}", file=sys.stderr)
    nvid = sum(1 for v in videos if v.get("videoUrl"))
    if nvid:
        nff = sum(1 for v in videos if v.get("coverSource") in ("first_frame", "frame_0.5s"))
        print(f"FIRST FRAMES: {nff}/{nvid} videos use frame 0 as cover (grid thumbnails in thumbs/)"
              + ("" if nff == nvid else " – the rest fell back to the thumbnail, see 'first frame failed'"))

    reels_only = args.platform == "instagram" and not posts_mode
    tot = total if total is not None else "unknown"
    share = f" ({100 * n / total:.0f}% of the account)" if total and not reels_only else ""
    if mode == "all":
        head = f"SAMPLE: all {n} posts fetched; account total {tot}"
        if total and not reels_only and n < 0.95 * total:
            head += " (feed returned fewer than the profile counter: deleted, private or unavailable posts)"
    elif mode == "since":
        head = (f"SAMPLE: {n} posts since {args.since}{share}; {skipped} older pinned post(s) skipped; "
                f"account total {tot}")
    else:
        head = f"SAMPLE: latest {n} of {tot}{share}"
        if n < count:
            head += " (feed ended before the requested count)"
        elif total is None or n < total:
            head += "; older posts, including possible hits, are outside the sample: rerun with --all or --since"
    if reels_only:
        head += " (account total counts all media types; only reels were fetched)"
    cars = sum(1 for v in videos if v["isCarousel"])
    photos = sum(1 for v in videos if v.get("kind") == "photo")
    kinds = f"carousels {cars}, videos {n - cars - photos}" + (f", photos {photos}" if photos else "")
    print(f"{head}; {kinds}; followers {(profile or {}).get('followers', 'unknown')}"
          + ("; metric = likes (Instagram shows no views for carousels and photos)" if posts_mode else ""))
    for i, v in enumerate(videos):
        kind = f"{v['slides']}sl" if v["isCarousel"] else v.get("kind", "video")
        print(f"{i:02d} | {v[metric]:>9} | {v['date']} | {kind:>5} | {'PIN' if v['isPinned'] else '   '} | {v['id']}")

    extra = [int(x) for x in args.slides_for.split(",") if x.strip()]
    if args.slides_top or extra:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from fetch_slides import fetch_carousels, pick_indexes
        fetch_carousels(args.out_dir, pick_indexes(meta, args.slides_top, extra), key)

if __name__ == "__main__":
    main()
