#!/usr/bin/env python3
"""
Download the slides of the max-views carousel from a carousels_ocr.json into <dest>.
Prints one JSON line with the top post's metadata + local slide paths.

Usage: download_slides.py <carousels_ocr.json> <dest_dir> [--id ID]
"""
import os, sys, json, glob, urllib.request, subprocess

def main():
    ocr_path = sys.argv[1]
    dest = sys.argv[2]
    force_id = None
    if "--id" in sys.argv:
        force_id = sys.argv[sys.argv.index("--id") + 1]
    cs = json.load(open(ocr_path))
    if not cs:
        print(json.dumps({"ok": False, "reason": "no carousels"}))
        return
    if force_id:
        top = next((c for c in cs if str(c["id"]) == str(force_id)), None) or max(cs, key=lambda c: c["views"])
    else:
        top = max(cs, key=lambda c: c["views"])
    os.makedirs(dest, exist_ok=True)
    # clear any stale slides from a previous run (avoids .jpg/.webp doubling on re-download)
    for old in glob.glob(os.path.join(dest, "slide_*")):
        try: os.remove(old)
        except OSError: pass
    paths = []
    for i, u in enumerate(top.get("slides", [])):
        p = os.path.join(dest, f"slide_{i}.webp")
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            open(p, "wb").write(data)
            # TikTok sometimes serves HEIC/HEIF under a .webp name — browsers can't render it.
            if b"ftyp" in data[:16] and any(b in data[:24] for b in (b"heic", b"heif", b"hevc", b"mif1", b"msf1")):
                jp = p[:-5] + ".jpg"
                try:
                    subprocess.run(["sips", "-s", "format", "jpeg", p, "--out", jp],
                                   capture_output=True, timeout=30)
                    if os.path.exists(jp) and os.path.getsize(jp) > 0:
                        os.remove(p); p = jp
                except Exception:
                    pass
            paths.append(p)
        except Exception as e:
            paths.append(f"[ERR {e}]")
    st = top.get("slide_text") or []
    print(json.dumps({
        "ok": True,
        "id": top["id"],
        "url": top.get("url", ""),
        "date": top.get("date", "")[:10],
        "views": top["views"],
        "likes": top["likes"],
        "saves": top["saves"],
        "comments": top["comments"],
        "shares": top.get("shares", 0),
        "nslides": top["nslides"],
        "hook": (st[0] if st else "").replace("\n", " / "),
        "slide_texts": st,
        "local_paths": paths,
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
