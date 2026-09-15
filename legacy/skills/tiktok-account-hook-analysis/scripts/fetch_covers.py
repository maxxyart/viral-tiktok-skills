#!/usr/bin/env python3
"""Fetch last N videos of a TikTok or Instagram account via ScrapeCreators
and download all cover images (HEIC auto-converted to JPEG via sips).

Usage:
  python3 fetch_covers.py HANDLE --platform tiktok|instagram --count 50 --out-dir DIR

Output:
  DIR/meta.json          — per-video metrics + cover file paths (index-aligned)
  DIR/covers/NN_ID.jpg   — cover images, NN = index in meta.json
  stdout                 — one digest line per video: index | views | date | id

Env: SCRAPE_CREATORS_API_KEY (also searched in ~/.zshenv, ~/.zshrc,
     the repo .env (via TIKTOK_SKILLS_ROOT) or ./.env).
"""
import argparse, json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENV_FILES = [os.path.expanduser("~/.zshenv"), os.path.expanduser("~/.zshrc")]
if os.environ.get("TIKTOK_SKILLS_ROOT"):
    ENV_FILES.append(os.path.join(os.environ["TIKTOK_SKILLS_ROOT"], ".env"))
ENV_FILES.append(os.path.join(os.getcwd(), ".env"))

def env_key(name):
    if os.environ.get(name):
        return os.environ[name]
    for path in ENV_FILES:
        if not os.path.exists(path):
            continue
        for line in open(path, encoding="utf-8", errors="ignore"):
            m = re.match(rf'^(?:export\s+)?{name}\s*=\s*"?([^"\s#]+)"?', line.strip())
            if m:
                return m.group(1)
    sys.exit(f"ERROR: {name} not found in env or {ENV_FILES}")

def api_get(path, params, key):
    qs = urlencode({k: v for k, v in params.items() if v is not None})
    req = Request(f"https://api.scrapecreators.com{path}?{qs}", headers={"x-api-key": key})
    for att in range(3):
        try:
            with urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if att == 2:
                raise
            print(f"  retry {path}: {e}", file=sys.stderr)
            time.sleep(2 * (att + 1))

def fetch_tiktok(handle, count, key):
    videos, cursor, page = [], None, 0
    while len(videos) < count:
        page += 1
        print(f"  page {page} (cursor={cursor or 'start'})...", file=sys.stderr)
        resp = api_get("/v3/tiktok/profile/videos",
                       {"handle": handle, "max_cursor": cursor, "sort_by": "latest", "trim": False}, key)
        items = resp.get("aweme_list") or []
        if not items:
            break
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
            videos.append({
                "id": vid_id,
                "desc": (it.get("desc") or "")[:200],
                "views": st.get("play_count") or 0,
                "likes": st.get("digg_count") or 0,
                "comments": st.get("comment_count") or 0,
                "shares": st.get("share_count") or 0,
                "saves": st.get("collect_count") or 0,
                "date": time.strftime("%Y-%m-%d", time.gmtime(it["create_time"])) if it.get("create_time") else "unknown",
                "duration": vid.get("duration") or 0,
                "link": f"https://www.tiktok.com/@{handle}/video/{vid_id}",
                "coverUrl": cover,
            })
        cursor = resp.get("max_cursor")
        if not int(resp.get("has_more") or 0) or cursor is None:
            break
    return videos

def fetch_instagram(handle, count, key):
    videos, max_id, page = [], None, 0
    while len(videos) < count:
        page += 1
        print(f"  page {page} (cursor={max_id or 'start'})...", file=sys.stderr)
        resp = api_get("/v1/instagram/user/reels", {"handle": handle, "max_id": max_id}, key)
        items = resp.get("items") or []
        if not items:
            break
        for it in items:
            if len(videos) >= count:
                break
            m = it.get("media") or it
            cands = ((m.get("image_versions2") or {}).get("candidates")) or []
            cap = m.get("caption")
            code = m.get("code", "")
            videos.append({
                "id": str(m.get("pk") or m.get("id")),
                "desc": ((cap.get("text", "") if isinstance(cap, dict) else "") or "")[:200],
                "views": m.get("play_count") or m.get("ig_play_count") or 0,
                "likes": m.get("like_count") or 0,
                "comments": m.get("comment_count") or 0,
                "shares": m.get("reshare_count") or 0,
                "saves": m.get("save_count") or 0,
                "date": time.strftime("%Y-%m-%d", time.gmtime(m["taken_at"])) if m.get("taken_at") else "unknown",
                "duration": m.get("video_duration") or 0,
                "link": f"https://www.instagram.com/reel/{code}/" if code else "",
                "coverUrl": cands[0]["url"] if cands else None,
            })
        pi = resp.get("paging_info") or {}
        nxt = pi.get("max_id") or resp.get("max_id")
        if pi.get("more_available") is False or not nxt or nxt == max_id:
            break
        max_id = nxt
    return videos

def is_heic(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return b"ftypheic" in head or b"ftypheix" in head or b"ftypmif1" in head or b"ftypavif" in head

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
        v["coverFile"] = dst
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
    ap.add_argument("--count", type=int, default=50)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    handle = args.handle.lstrip("@").rstrip("/").split("/")[-1]
    covers_dir = os.path.join(args.out_dir, "covers")
    os.makedirs(covers_dir, exist_ok=True)
    key = env_key("SCRAPE_CREATORS_API_KEY")

    print(f"Fetching {args.count} {args.platform} videos for @{handle}...", file=sys.stderr)
    fetch = fetch_tiktok if args.platform == "tiktok" else fetch_instagram
    videos = fetch(handle, args.count, key)
    if not videos:
        sys.exit(f"ERROR: no videos found for @{handle} on {args.platform}")
    print(f"  fetched {len(videos)} videos, downloading covers...", file=sys.stderr)

    with ThreadPoolExecutor(10) as ex:
        errs = [e for e in ex.map(download_cover, [(i, v, covers_dir) for i, v in enumerate(videos)]) if e]
    for e in errs:
        print(f"  cover fail {e}", file=sys.stderr)

    meta = {"platform": args.platform, "handle": handle, "videos": videos}
    meta_path = os.path.join(args.out_dir, "meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)

    ok = sum(1 for v in videos if v.get("coverFile"))
    print(f"  covers: {ok}/{len(videos)} | meta: {meta_path}", file=sys.stderr)
    for i, v in enumerate(videos):
        print(f"{i:02d} | {v['views']:>9} | {v['date']} | {v['id']}")

if __name__ == "__main__":
    main()
