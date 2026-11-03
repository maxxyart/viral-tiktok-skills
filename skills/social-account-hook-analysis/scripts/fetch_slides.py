#!/usr/bin/env python3
"""Download every slide + top comments for chosen carousels of a fetched account
(TikTok, or Instagram fetched with --ig-source posts).
Reuses meta.json + slide_urls.json from fetch_covers.py, so the feed is not re-fetched;
expired TikTok slide URLs are refreshed with one /v2/tiktok/video call per post.

Usage:
  python3 fetch_slides.py WORK_DIR [--top 6] [--indexes 37,48] [--comments 20]

--top N picks the N best carousels by meta.metric (views, or likes for Instagram posts);
--indexes adds explicit meta.json indexes.
Writes WORK_DIR/carousels/NN/slideK.jpg and WORK_DIR/carousels/NN/post.json
({index, id, link, views, likes, saves, shares, comments, slides, slide_files, top_comments}).
Claude adds WORK_DIR/carousels/NN/slides.json after reading the slides:
[{"slide": 1, "text": "verbatim, line breaks as \\n", "visual": "short description"}].
Stdout: one line per carousel: index | slides ok/total | comments | top comment.
"""
import argparse, json, os, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_covers import ENV_FILES, api_get, env_key

def pick_indexes(meta, top, extra):
    metric = meta.get("metric") or "views"
    cars = sorted((i for i, v in enumerate(meta["videos"]) if v.get("isCarousel")),
                  key=lambda i: -(meta["videos"][i].get(metric) or 0))
    chosen = cars[:top] if top else []
    for i in extra:
        if i not in chosen:
            chosen.append(i)
    return chosen

def to_jpeg(data, dst):
    """Write image bytes as JPEG; convert HEIC/WebP via sips when needed."""
    if data[:3] == b"\xff\xd8\xff":
        with open(dst, "wb") as f:
            f.write(data)
        return True
    suffix = ".heic" if data[4:8] == b"ftyp" else ".webp"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(data)
        src = f.name
    res = subprocess.run(["sips", "-s", "format", "jpeg", src, "--out", dst],
                         capture_output=True, timeout=30)
    os.remove(src)
    return res.returncode == 0 and os.path.exists(dst)

def download(url, dst):
    if not url:
        return False
    try:
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
            return to_jpeg(r.read(), dst)
    except Exception:
        return False

def fresh_urls(link, key):
    det = (api_get("/v2/tiktok/video", {"url": link, "trim": "true"}, key) or {}).get("aweme_detail") or {}
    images = (det.get("image_post_info") or {}).get("images") or []
    return [(((img.get("display_image") or img.get("thumbnail") or {}).get("url_list")) or [None])[0]
            for img in images]

def top_comments(platform, link, key, n):
    if platform == "instagram":
        raw = (api_get("/v2/instagram/post/comments", {"url": link}, key) or {}).get("comments") or []
        likes = "comment_like_count"
    else:
        raw = (api_get("/v1/tiktok/video/comments", {"url": link, "trim": "true"}, key) or {}).get("comments") or []
        likes = "digg_count"
    return sorted(({"text": c.get("text", "").strip(), "likes": c.get(likes) or 0} for c in raw
                   if (c.get("text") or "").strip()),  # sticker/GIF comments have no text
                  key=lambda c: -c["likes"])[:n]

def one_carousel(work_dir, platform, i, v, urls, key, n_comments):
    out = os.path.join(work_dir, "carousels", f"{i:02d}")
    os.makedirs(out, exist_ok=True)
    dsts = [os.path.join(out, f"slide{k}.jpg") for k in range(1, len(urls) + 1)]
    with ThreadPoolExecutor(8) as ex:
        ok = list(ex.map(download, urls, dsts))
    if not all(ok) and platform == "tiktok":
        try:  # signed URLs expire; refresh once
            urls = fresh_urls(v["link"], key)
            dsts = [os.path.join(out, f"slide{k}.jpg") for k in range(1, len(urls) + 1)]
            with ThreadPoolExecutor(8) as ex:
                ok = list(ex.map(download, urls, dsts))
        except Exception as e:
            print(f"  {i:02d}: slide refresh failed: {str(e)[:80]}", file=sys.stderr)
    try:
        comments = top_comments(platform, v["link"], key, n_comments)
    except Exception as e:
        print(f"  {i:02d}: comments failed, continuing without: {str(e)[:80]}", file=sys.stderr)
        comments = []
    post = {"index": i, "id": v["id"], "link": v["link"], "views": v["views"], "likes": v.get("likes"),
            "saves": v["saves"], "shares": v["shares"], "comments": v["comments"], "slides": len(urls),
            "slide_files": [d for d, good in zip(dsts, ok) if good], "top_comments": comments}
    with open(os.path.join(out, "post.json"), "w", encoding="utf-8") as f:
        json.dump(post, f, ensure_ascii=False, indent=1)
    top = comments[0] if comments else {"text": "", "likes": 0}
    return f"{i:02d} | slides {sum(ok)}/{len(urls)} | comments {len(comments)} | {top['likes']}♥ {top['text'][:70]}"

def fetch_carousels(work_dir, indexes, key, n_comments=20):
    meta = json.load(open(os.path.join(work_dir, "meta.json"), encoding="utf-8"))
    platform = meta.get("platform") or "tiktok"
    path = os.path.join(work_dir, "slide_urls.json")
    slide_urls = json.load(open(path)) if os.path.exists(path) else {}
    jobs = []
    for i in indexes:
        v = meta["videos"][i]
        if not v.get("isCarousel"):
            print(f"  {i:02d}: not a carousel, skipped", file=sys.stderr)
            continue
        jobs.append((i, v, slide_urls.get(v["id"]) or []))
    print(f"Downloading slides + comments for {len(jobs)} carousels: {[j[0] for j in jobs]}", file=sys.stderr)
    with ThreadPoolExecutor(4) as ex:
        lines = list(ex.map(lambda j: one_carousel(work_dir, platform, j[0], j[1], j[2], key, n_comments), jobs))
    for line in lines:
        print(line)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir")
    ap.add_argument("--top", type=int, default=0)
    ap.add_argument("--indexes", default="")
    ap.add_argument("--comments", type=int, default=20)
    ap.add_argument("--env-file", action="append", default=[], help="file with KEY=value lines (repeatable)")
    args = ap.parse_args()
    ENV_FILES[:] = [os.path.expanduser(p) for p in args.env_file]
    meta = json.load(open(os.path.join(args.work_dir, "meta.json"), encoding="utf-8"))
    extra = [int(x) for x in args.indexes.split(",") if x.strip()]
    if not args.top and not extra:
        sys.exit("ERROR: pass --top N and/or --indexes")
    fetch_carousels(args.work_dir, pick_indexes(meta, args.top, extra),
                    env_key("SCRAPE_CREATORS_API_KEY"), args.comments)

if __name__ == "__main__":
    main()
