#!/usr/bin/env python3
"""
Fetch last N TikTok carousels of an account (direct ScrapeCreators REST, cursor loop)
+ threaded download+OCR of every slide via Gemini Flash Lite.

Usage:
  python3 fetch_and_ocr.py <handle_or_url> --out <dir> [--limit 50] [--max-pages 15] [--workers 15]

Output files in <dir>:
  carousels_ocr.json  - full dataset (metrics + slide URLs + slide_text[])
  DIGEST.txt          - human-readable, ranked by views (HOOK/BODY per carousel)

Env: SCRAPE_CREATORS_API_KEY, GOOGLE_API_KEY
Only a short summary is printed to stdout - keep context clean.
"""
import os, sys, json, re, time, base64, argparse, urllib.request, urllib.error, concurrent.futures
import subprocess, tempfile

SC_BASE = "https://api.scrapecreators.com/v3/tiktok/profile/videos"
GEMINI_MODEL = "gemini-3.1-flash-lite"
OCR_PROMPT = ("Extract ALL text visible in this TikTok carousel slide EXACTLY as written, "
              "preserving line breaks and order (top to bottom). Keep emojis. Do NOT add "
              "commentary, labels, or quotes. If the slide has no text, output exactly: NONE")


def parse_handle(s):
    m = re.search(r"tiktok\.com/@([\w.\-]+)", s)
    return m.group(1) if m else s.lstrip("@").strip()


def http_json(url, headers=None, data=None, timeout=90, retries=3):
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers or {})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            if attempt == retries:
                raise
            time.sleep(2 * (attempt + 1))


def fetch_carousels(handle, sc_key, limit, max_pages):
    """Paginate profile feed, collect carousel posts only."""
    seen, out, cursor = set(), [], None
    for page in range(1, max_pages + 1):
        url = f"{SC_BASE}?handle={handle}&sort_by=latest&trim=true"
        if cursor:
            url += f"&max_cursor={cursor}"
        resp = http_json(url, headers={"x-api-key": sc_key})
        items = resp.get("aweme_list") or []
        for it in items:
            ipi = it.get("image_post_info")
            if not ipi or it["aweme_id"] in seen:
                continue
            seen.add(it["aweme_id"])
            slides = []
            for img in ipi.get("images", []):
                di = img.get("display_image") or img.get("thumbnail") or {}
                urls = di.get("url_list") or []
                if urls:
                    slides.append(urls[0])
            st = it.get("statistics", {})
            out.append({
                "id": it["aweme_id"],
                "date": it.get("create_time_utc", ""),
                "ct": it.get("create_time", 0),
                "desc": it.get("desc", ""),
                "views": st.get("play_count", 0),
                "likes": st.get("digg_count", 0),
                "saves": st.get("collect_count", 0),
                "comments": st.get("comment_count", 0),
                "shares": st.get("share_count", 0),
                "nslides": len(slides),
                "slides": slides,
                "url": it.get("url", ""),
            })
        # sort by recency and check if we already hold N *latest* carousels
        out.sort(key=lambda c: c["ct"], reverse=True)
        print(f"  page {page}: +{len(items)} posts -> {len(out)} carousels", flush=True)
        if len(out) >= limit or not resp.get("has_more") or not items:
            break
        cursor = resp.get("max_cursor")
    return out[:limit]


def sniff_mime(data):
    """TikTok serves slides as webp, jpeg or heic regardless of the URL extension."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:8] == b"ftyp":
        return "image/heic"
    return "image/webp"


def prep_image(data):
    """Return (mime, bytes) Gemini accepts. HEIC/HEIF -> JPEG via sips (macOS);
    Gemini rejects image/heic with HTTP 400, so convert before sending."""
    mime = sniff_mime(data)
    if mime == "image/heic":
        try:
            with tempfile.NamedTemporaryFile(suffix=".heic", delete=False) as fi:
                fi.write(data); src = fi.name
            dst = src[:-5] + ".jpg"
            subprocess.run(["sips", "-s", "format", "jpeg", src, "--out", dst],
                           capture_output=True, timeout=30)
            if os.path.exists(dst) and os.path.getsize(dst) > 0:
                data = open(dst, "rb").read(); mime = "image/jpeg"
            for p in (src, dst):
                try: os.remove(p)
                except OSError: pass
        except Exception:
            pass
    return mime, data


def ocr_all(carousels, g_key, workers):
    """Download + OCR every slide in one threaded pool."""
    # key goes in a header, not the URL, so it can never leak via logged/printed URLs
    gemini_url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                  f"{GEMINI_MODEL}:generateContent")
    tasks = [(i, j, url) for i, c in enumerate(carousels) for j, url in enumerate(c["slides"])]

    def worker(t):
        i, j, url = t
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                img = r.read()
        except Exception as e:
            return (i, j, f"[DL-ERR: {e}]")
        mime, img = prep_image(img)
        body = json.dumps({
            "contents": [{"parts": [
                {"inline_data": {"mime_type": mime,
                                 "data": base64.b64encode(img).decode()}},
                {"text": OCR_PROMPT},
            ]}],
            "generationConfig": {"temperature": 0},
        }).encode()
        try:
            resp = http_json(gemini_url, headers={"Content-Type": "application/json",
                                                  "x-goog-api-key": g_key},
                             data=body, retries=3)
            return (i, j, resp["candidates"][0]["content"]["parts"][0]["text"].strip())
        except Exception as e:
            return (i, j, f"[OCR-ERR: {e}]")

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for i, j, txt in ex.map(worker, tasks):
            results.setdefault(i, {})[j] = txt
    for i, c in enumerate(carousels):
        c["slide_text"] = [results.get(i, {}).get(j, "[MISSING]")
                           for j in range(len(c["slides"]))]
    errs = sum(1 for c in carousels for t in c["slide_text"]
               if t.startswith(("[DL-ERR", "[OCR-ERR")) or t == "[MISSING]")
    return len(tasks), errs


def write_digest(carousels, path):
    def sr(c):
        return 100 * c["saves"] / c["views"] if c["views"] else 0
    cs = sorted(carousels, key=lambda c: c["views"], reverse=True)
    tv = sum(c["views"] for c in cs)
    med = sorted(c["views"] for c in cs)[len(cs) // 2] if cs else 0
    lines = [
        f"{len(cs)} carousels | total {tv:,} views | avg {tv // max(len(cs),1):,} | median {med:,}",
        f"date range: {cs and max(c['date'] for c in cs)} -> {cs and min(c['date'] for c in cs)}",
        f"avg save-rate: {sum(sr(c) for c in cs) / max(len(cs),1):.2f}%", "",
    ]
    for rank, c in enumerate(cs, 1):
        st = c["slide_text"]
        hook = st[0].replace("\n", " / ") if st else ""
        body = " || ".join(s.replace("\n", " / ") for s in st[1:])
        lines.append(f"#{rank} | id={c['id']} | {c['views']:,}v {c['likes']:,}l "
                     f"{c['saves']:,}s {c['comments']:,}c | save%={sr(c):.1f} | "
                     f"{c['nslides']}sl | {c['date'][:10]}")
        if c.get("url"):
            lines.append(f"   URL:  {c['url']}")
        lines.append(f"   HOOK: {hook}")
        if body:
            lines.append(f"   BODY: {body}")
        lines.append("")
    open(path, "w").write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("handle")
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--max-pages", type=int, default=15)
    ap.add_argument("--workers", type=int, default=15)
    a = ap.parse_args()

    sc_key = os.environ.get("SCRAPE_CREATORS_API_KEY")
    g_key = os.environ.get("GOOGLE_API_KEY")
    if not sc_key or not g_key:
        sys.exit("ERROR: need SCRAPE_CREATORS_API_KEY and GOOGLE_API_KEY in env")

    handle = parse_handle(a.handle)
    os.makedirs(a.out, exist_ok=True)
    print(f"fetching carousels for @{handle} (target {a.limit}, max {a.max_pages} pages)...")
    t0 = time.time()
    carousels = fetch_carousels(handle, sc_key, a.limit, a.max_pages)
    if not carousels:
        sys.exit(f"ERROR: no carousels found for @{handle}")
    if len(carousels) < a.limit:
        print(f"WARNING: only {len(carousels)} carousels available (asked {a.limit})")
    print(f"fetched {len(carousels)} carousels in {time.time()-t0:.0f}s; OCR starting...")

    t1 = time.time()
    n_slides, errs = ocr_all(carousels, g_key, a.workers)
    print(f"OCR: {n_slides} slides, {errs} errors, {time.time()-t1:.0f}s")

    json.dump(carousels, open(os.path.join(a.out, "carousels_ocr.json"), "w"),
              ensure_ascii=False, indent=2)
    write_digest(carousels, os.path.join(a.out, "DIGEST.txt"))
    print(f"done in {time.time()-t0:.0f}s -> {a.out}/carousels_ocr.json + DIGEST.txt")


if __name__ == "__main__":
    main()
