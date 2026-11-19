#!/usr/bin/env python3
"""ffmpeg + Pillow helpers for the emotion + demo pipeline. Needs ffmpeg/ffprobe and Pillow;
yt-dlp only as a download fallback.

Subcommands:
  fetch URL OUT.mp4                       download a TikTok/Instagram video. TikTok goes through ScrapeCreators
                                          (no watermark, metrics in OUT.meta.json) when SCRAPE_CREATORS_API_KEY
                                          is set; otherwise, and for Instagram, yt-dlp
  find-cut VIDEO OUT_DIR                  scene cuts (hook -> demo candidates) + a labelled strip of the frames
                                          around each cut, to pick the last hook frame by eye
  cut-hook VIDEO --frames N --out HOOK.mp4 [--first-frame FRAME.jpg]
                                          frame-accurate cut of frames 0..N-1 (re-encoded, audio kept)
  first-frame SOURCE OUT.jpg              frame 0 of a URL or local video
  frame VIDEO OUT.png (--n N | --t SECONDS)
                                          one frame by index or time, e.g. a demo frame to measure its caption
  sheet VIDEO OUT.jpg [--fps 4] [--cols 8]
                                          labelled contact sheet to review motion, lips, hands and text
  caption-lines FRAME [--y0 0.15 --y1 0.5] [--mode white|neon]
                                          measure a caption in a reference frame: line tops, width share,
                                          line pitch and block centre, ready for render_hook_overlay.py
  compare ORIGINAL RESULT OUT.jpg [--times 0.1 1 2 3 4]
                                          2-row grid: original on top, result below, same timestamps.
                                          Two images (frame vs swapped frame) are put side by side
  side-by-side LEFT RIGHT OUT.mp4 [--labels Reference Result] [--audio-from FILE]
                                          both clips playing at once, for the user's review
  mux-audio VIDEO AUDIO_SOURCE OUT.mp4    copy the video, take the audio from another file
  assemble --hook RAW.mp4 --hook-overlay PNG --demo DEMO(.mp4|.png|.jpg) [--demo-overlay PNG]
           [--audio-from REF.mp4] [--demo-seconds S] [--hook-overlay-on-demo] --out FINAL.mp4
                                          hook + its caption, then the demo + its caption. Writes
                                          FINAL_silent.mp4 (no audio) and FINAL.mp4 (reference sound)
  check VIDEO                             duration, frames, size, fps, peak volume
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

FPS = 30


def need(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        sys.exit(f"{tool} not found. Install it first (macOS: brew install {tool}).")
    return path


def run(cmd: list[str]) -> str:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode:
        sys.exit(f"Command failed: {' '.join(cmd[:4])} ...\n{res.stderr[-1500:]}")
    return res.stdout + res.stderr


def probe(video: Path) -> dict:
    need("ffprobe")
    res = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
                          "format=duration:stream=codec_type,width,height,r_frame_rate,nb_read_frames",
                          "-of", "json", str(video)], capture_output=True, text=True)
    if res.returncode:
        sys.exit(f"ffprobe failed on {video}: {res.stderr[-500:]}")
    meta = json.loads(res.stdout or "{}")
    v = next((s for s in meta.get("streams", []) if s["codec_type"] == "video"), {})
    num, den = (v.get("r_frame_rate") or "30/1").split("/")
    return {"duration": float(meta.get("format", {}).get("duration", 0)), "width": v.get("width"),
            "height": v.get("height"), "fps": float(num) / float(den or 1),
            "frames": int(v.get("nb_read_frames") or 0),
            "audio": any(s["codec_type"] == "audio" for s in meta.get("streams", []))}


# ---------- download ----------

def sc_key(env_file: str | None) -> str | None:
    if env_file:
        for line in Path(env_file).expanduser().read_text(encoding="utf-8").splitlines():
            line = line.strip().removeprefix("export ").strip()
            if line.startswith("SCRAPE_CREATORS_API_KEY="):
                return line.split("=", 1)[1].strip().strip("\"'")
    return os.environ.get("SCRAPE_CREATORS_API_KEY") or None


def fetch_scrapecreators(url: str, out: Path, key: str) -> bool:
    api = "https://api.scrapecreators.com/v2/tiktok/video?" + urllib.parse.urlencode({"url": url.split("?")[0]})
    data = None
    for attempt in range(4):  # the API returns 500 now and then
        try:
            req = urllib.request.Request(api, headers={"x-api-key": key, "User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
            break
        except Exception as exc:  # noqa: BLE001
            print(f"  ScrapeCreators retry {attempt + 1}/4: {exc}", file=sys.stderr)
            time.sleep(2 ** attempt)
    a = (data or {}).get("aweme_detail") or {}
    v, st, mu = a.get("video") or {}, a.get("statistics") or {}, a.get("music") or {}
    candidates = []
    for k in ("download_no_watermark_addr", "play_addr", "download_addr"):
        candidates += (v.get(k) or {}).get("url_list", [])
    for c in candidates:
        try:
            with urllib.request.urlopen(urllib.request.Request(c, headers={"User-Agent": "Mozilla/5.0"}), timeout=120) as r:
                body = r.read()
        except Exception:  # noqa: BLE001
            continue
        if len(body) > 10_000:
            out.write_bytes(body)
            mid = mu.get("id_str") or mu.get("id")
            meta = {"url": url, "author": (a.get("author") or {}).get("unique_id"), "desc": a.get("desc"),
                    "views": st.get("play_count"), "likes": st.get("digg_count"), "comments": st.get("comment_count"),
                    "shares": st.get("share_count"), "saves": st.get("collect_count"),
                    "sound": mu.get("title"), "sound_author": mu.get("author"),
                    "sound_url": f"https://www.tiktok.com/music/original-sound-{mid}" if mid else None}
            out.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{out}: views {meta['views']}, saves {meta['saves']}, sound {meta['sound']!r} (ScrapeCreators)")
            return True
    return False


def fetch(url: str, out: Path, env_file: str | None = None) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    key = sc_key(env_file)
    if "tiktok.com" in url and key and fetch_scrapecreators(url, out, key):
        return out
    need("yt-dlp")
    run(["yt-dlp", "-q", "-f", "bv*+ba/b", "--merge-output-format", "mp4", "--write-info-json",
         "-o", str(out.with_suffix("")) + ".%(ext)s", url])
    info = out.with_suffix(".info.json")
    if info.exists():
        d = json.loads(info.read_text(encoding="utf-8"))
        print(f"{out}: {d.get('duration')}s, views {d.get('view_count')}, by @{d.get('uploader') or d.get('uploader_id')} (yt-dlp)")
    return out


def local_video(src: str, tmp: str) -> Path:
    return fetch(src, Path(tmp) / "src.mp4") if src.startswith(("http://", "https://")) else Path(src)


# ---------- frames ----------

def grab(video: Path, out: Path, *, frame: int | None = None, t: float | None = None) -> Path:
    need("ffmpeg")
    if frame is not None:
        run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-vf", f"select=eq(n\\,{frame})",
             "-fps_mode", "passthrough", "-frames:v", "1", str(out)])
    else:
        run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{t}", "-i", str(video), "-frames:v", "1", str(out)])
    return out


def label_font(size: int):
    from PIL import ImageFont
    for p in ("/System/Library/Fonts/Helvetica.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "C:/Windows/Fonts/arial.ttf"):
        if Path(p).is_file():
            return ImageFont.truetype(p, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def tile(images: list, labels: list[str], cols: int, cell_w: int, out: Path) -> Path:
    from PIL import Image, ImageDraw
    cells = []
    for im, lab in zip(images, labels):
        im = im.convert("RGB")
        im = im.resize((cell_w, round(im.height * cell_w / im.width)))
        d = ImageDraw.Draw(im)
        f = label_font(max(14, cell_w // 14))
        box = d.textbbox((6, 6), lab, font=f)
        d.rectangle((box[0] - 4, box[1] - 3, box[2] + 4, box[3] + 3), fill=(0, 0, 0))
        d.text((6, 6), lab, font=f, fill=(255, 220, 0))
        cells.append(im)
    rows = (len(cells) + cols - 1) // cols
    ch = max(c.height for c in cells)
    sheet = Image.new("RGB", (cols * cell_w, rows * ch), "black")
    for i, c in enumerate(cells):
        sheet.paste(c, ((i % cols) * cell_w, (i // cols) * ch))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=90)
    return out


def sheet(video: Path, out: Path, fps: float, cols: int) -> Path:
    from PIL import Image
    info = probe(video)
    with tempfile.TemporaryDirectory() as tmp:
        times, t = [], 0.0
        while t < info["duration"] - 0.02:
            times.append(round(t, 3)); t += 1 / fps
        ims = [Image.open(grab(video, Path(tmp) / f"{i}.png", t=x)) for i, x in enumerate(times)]
        tile(ims, [f"{x:.2f}s" for x in times], cols, 200, out)
    print(f"saved {out} ({len(times)} frames)")
    return out


def find_cut(video: Path, out_dir: Path, threshold: float) -> list[int]:
    from PIL import Image
    need("ffmpeg")
    info = probe(video)
    log = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-vf", f"select='gt(scene,{threshold})',showinfo",
                          "-an", "-f", "null", "-"], capture_output=True, text=True).stderr
    cuts = sorted({round(float(m) * info["fps"]) for m in re.findall(r"pts_time:([\d.]+)", log)})
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"{video}: {info['duration']:.2f}s, {info['frames']} frames, {info['fps']:.0f} fps")
    if not cuts:
        print(f"no scene cut above {threshold}; lower --threshold or read the contact sheet")
    with tempfile.TemporaryDirectory() as tmp:
        for c in cuts[:4]:
            nums = [n for n in range(c - 3, c + 2) if 0 <= n < (info["frames"] or c + 2)]
            ims = [Image.open(grab(video, Path(tmp) / f"{n}.png", frame=n)) for n in nums]
            strip = tile(ims, [f"n={n}" for n in nums], len(nums), 240, out_dir / f"cut_{c}.jpg")
            print(f"cut at frame {c} ({c / info['fps']:.3f}s): first new-scene frame. Check {strip}; "
                  f"the hook is frames 0..{c - 1} -> cut-hook --frames {c}")
    return cuts


def cut_hook(video: Path, frames: int, out: Path, first: Path | None) -> Path:
    need("ffmpeg")
    info = probe(video)
    out.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-frames:v", str(frames),
         "-t", f"{frames / info['fps']:.4f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])
    if first:
        run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-frames:v", "1", "-q:v", "1", str(first)])
        print(f"saved {first}")
    check(out)
    return out


def first_frame(src: str, out: Path) -> Path:
    need("ffmpeg")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(local_video(src, tmp)), "-frames:v", "1", "-q:v", "1", str(out)])
    print(f"saved {out}")
    return out


# ---------- captions ----------

def caption_lines(frame: Path, y0: float, y1: float, mode: str) -> dict:
    """Find caption rows by colour inside a horizontal band. white = classic caption core,
    neon = the pink-white core of TikTok's Neon style. Keep the band tight around the caption:
    white UI (buttons, cards) inside the band is counted too."""
    from PIL import Image
    im = Image.open(frame).convert("RGB")
    W, H = im.size
    px = im.load()
    if mode == "white":
        hit = lambda p: min(p) > 235  # noqa: E731
    else:  # pink-white core; pure white UI (buttons, cards) has g close to r and is skipped
        hit = lambda p: p[0] > 235 and p[2] > 205 and 170 < p[1] <= p[0] - 12  # noqa: E731
    rows = {}
    for y in range(int(y0 * H), int(y1 * H)):
        xs = [x for x in range(W) if hit(px[x, y])]
        if len(xs) > 3:
            rows[y] = (xs[0], xs[-1])
    if not rows:
        sys.exit("No caption pixels in that band; widen --y0/--y1 or switch --mode")
    ys, lines, cur = sorted(rows), [], []
    for y in ys:
        if cur and y - cur[-1] > 3:
            lines.append(cur); cur = []
        cur.append(y)
    lines.append(cur)
    tallest = max(ln[-1] - ln[0] for ln in lines)
    lines = [ln for ln in lines if ln[-1] - ln[0] >= 0.4 * tallest]  # drop thin UI edges and noise
    res = []
    for ln in lines:
        x0, x1 = min(rows[y][0] for y in ln), max(rows[y][1] for y in ln)
        res.append({"top": ln[0], "bottom": ln[-1], "x0": x0, "x1": x1, "width_frac": round((x1 - x0) / W, 3)})
    tops = [r["top"] for r in res]
    pitch = round((tops[-1] - tops[0]) / (len(tops) - 1) / H, 4) if len(tops) > 1 else None
    out = {"frame": f"{W}x{H}", "lines": res, "line_pitch_frac": pitch,
           "center_y": round((res[0]["top"] + res[-1]["bottom"]) / 2 / H, 3)}
    for r in res:
        print(f"line y={r['top']}..{r['bottom']} x={r['x0']}..{r['x1']} width {r['width_frac']}")
    widest = max(res, key=lambda r: r["width_frac"])
    print(f"centre {out['center_y']}, line pitch {pitch} of height. Calibrate with the text of the widest line: "
          f"--calib '<that line>' --calib-frac {widest['width_frac']} --center-y {out['center_y']}"
          + (f" --line-pitch {pitch}" if pitch else ""))
    return out


# ---------- review ----------

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")


def compare(original: Path, result: Path, out: Path, times: list[float]) -> Path:
    from PIL import Image
    if original.suffix.lower() in IMAGE_EXT and result.suffix.lower() in IMAGE_EXT:
        ims = [Image.open(original), Image.open(result)]
        ims[1] = ims[1].resize((ims[0].width, round(ims[1].height * ims[0].width / ims[1].width)))
        tile(ims, ["reference", "result"], 2, 480, out)
        print(f"saved {out}")
        return out
    with tempfile.TemporaryDirectory() as tmp:
        top = [Image.open(grab(original, Path(tmp) / f"o{i}.png", t=t)) for i, t in enumerate(times)]
        bot = [Image.open(grab(result, Path(tmp) / f"r{i}.png", t=t)) for i, t in enumerate(times)]
        tile(top + bot, [f"ref {t}s" for t in times] + [f"new {t}s" for t in times], len(times), 240, out)
    print(f"saved {out}")
    return out


def label_png(text: str, w: int, path: Path) -> Path:
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (w, 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = label_font(max(20, w // 16))
    box = d.textbbox((0, 0), text, font=f)
    x = (w - (box[2] - box[0])) // 2
    d.rounded_rectangle((x - 14, 30 - 10, x + box[2] - box[0] + 14, 30 + box[3] - box[1] + 14), 8, fill=(0, 0, 0, 150))
    d.text((x, 30 - box[1] + 2), text, font=f, fill=(255, 255, 255, 255))
    im.save(path)
    return path


def side_by_side(left: Path, right: Path, out: Path, labels: list[str], audio_from: Path | None) -> Path:
    need("ffmpeg")
    a, b = probe(left), probe(right)
    W, H = a["width"] or 720, a["height"] or 1280
    with tempfile.TemporaryDirectory() as tmp:
        l1, l2 = label_png(labels[0], W, Path(tmp) / "l1.png"), label_png(labels[1], W, Path(tmp) / "l2.png")
        aud = audio_from or (right if b["audio"] else left if a["audio"] else None)
        cmd = ["ffmpeg", "-loglevel", "error", "-y", "-i", str(left), "-i", str(right), "-i", str(l1), "-i", str(l2)]
        if aud:
            cmd += ["-i", str(aud)]
        graph = (f"[0:v]scale={W}:{H},setsar=1,fps={FPS}[a0];[a0][2:v]overlay=0:0[a];"
                 f"[1:v]scale={W}:{H},setsar=1,fps={FPS}[b0];[b0][3:v]overlay=0:0[b];"
                 f"[a][b]hstack=inputs=2:shortest=1,format=yuv420p[v]")
        cmd += ["-filter_complex", graph, "-map", "[v]"]
        cmd += (["-map", "4:a", "-c:a", "aac", "-b:a", "192k"] if aud else ["-an"])
        cmd += ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-movflags", "+faststart", str(out)]
        run(cmd)
    check(out)
    return out


def mux_audio(video: Path, audio_src: Path, out: Path) -> Path:
    need("ffmpeg")
    run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-i", str(audio_src), "-map", "0:v", "-map", "1:a",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)])
    check(out)
    return out


# ---------- final ----------

def assemble(hook: Path, hook_overlay: Path | None, demo: Path, demo_overlay: Path | None, out: Path,
             audio_from: Path | None, demo_seconds: float | None, hook_overlay_on_demo: bool,
             size: str | None) -> tuple[Path, Path | None]:
    """Hook clip + its caption, then the demo (+ its own caption). The demo fills the reference's
    remaining length by default, so the reference sound runs to the end."""
    need("ffmpeg")
    h = probe(hook)
    W, H = (int(x) for x in size.split("x")) if size else (h["width"], h["height"])
    hook_frames = h["frames"] or round(h["duration"] * FPS)
    is_image = demo.suffix.lower() in IMAGE_EXT
    if demo_seconds is not None:
        demo_frames = round(demo_seconds * FPS)
    elif audio_from:
        demo_frames = round(probe(audio_from)["duration"] * FPS) - hook_frames
    elif not is_image:
        demo_frames = probe(demo)["frames"] or round(probe(demo)["duration"] * FPS)
    else:
        sys.exit("An image demo needs --demo-seconds or --audio-from (to fill the reference length)")
    if demo_frames < FPS // 2:
        sys.exit(f"Demo would last {demo_frames} frames; pass --demo-seconds")
    fit = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS},format=yuv420p"
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-i", str(hook)]
    cmd += (["-loop", "1", "-framerate", str(FPS), "-i", str(demo)] if is_image else ["-i", str(demo)])
    graph, n = [f"[0:v]{fit}[h0]", f"[1:v]{fit},trim=end_frame={demo_frames},setpts=PTS-STARTPTS[d0]"], 2
    hv, dv = "h0", "d0"
    if hook_overlay:
        cmd += ["-i", str(hook_overlay)]
        if hook_overlay_on_demo:
            graph.append(f"[{n}:v]scale={W}:{H},split=2[ho1][ho2]")
            graph.append(f"[{dv}][ho2]overlay=0:0:format=auto,format=yuv420p[d1]"); dv = "d1"
        else:
            graph.append(f"[{n}:v]scale={W}:{H}[ho1]")
        graph.append(f"[{hv}][ho1]overlay=0:0:format=auto,format=yuv420p[h1]"); hv = "h1"
        n += 1
    if demo_overlay:
        cmd += ["-i", str(demo_overlay)]
        graph.append(f"[{n}:v]scale={W}:{H}[do]")
        graph.append(f"[{dv}][do]overlay=0:0:format=auto,format=yuv420p[d2]"); dv = "d2"
        n += 1
    graph.append(f"[{hv}][{dv}]concat=n=2:v=1:a=0[v]")
    silent = out.with_name(out.stem + "_silent.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    run(cmd + ["-filter_complex", ";".join(graph), "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "medium",
               "-crf", "18", "-r", str(FPS), "-movflags", "+faststart", str(silent)])
    check(silent)
    if not audio_from:
        print("no --audio-from: only the silent version was written")
        return silent, None
    mux_audio(silent, audio_from, out)
    print(f"hook {hook_frames} frames ({hook_frames / FPS:.2f}s) + demo {demo_frames} frames ({demo_frames / FPS:.2f}s)")
    return silent, out


def check(video: Path) -> None:
    info = probe(video)
    vol = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True).stderr if info["audio"] else ""
    peak = next((ln.split("max_volume:")[1].strip() for ln in vol.splitlines() if "max_volume" in ln), "no audio")
    print(f"{video}: {info['duration']:.2f}s, {info['frames']} frames, {info['width']}x{info['height']}, "
          f"{info['fps']:.0f} fps, peak {peak}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env-file", help=".env with SCRAPE_CREATORS_API_KEY (optional)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch"); f.add_argument("url"); f.add_argument("out", type=Path)
    fc = sub.add_parser("find-cut"); fc.add_argument("video", type=Path); fc.add_argument("out_dir", type=Path)
    fc.add_argument("--threshold", type=float, default=0.25)
    ch = sub.add_parser("cut-hook"); ch.add_argument("video", type=Path)
    ch.add_argument("--frames", type=int, required=True, help="Number of hook frames = first demo frame index")
    ch.add_argument("--out", type=Path, required=True); ch.add_argument("--first-frame", type=Path)
    ff = sub.add_parser("first-frame"); ff.add_argument("source"); ff.add_argument("out", type=Path)
    fr = sub.add_parser("frame"); fr.add_argument("video", type=Path); fr.add_argument("out", type=Path)
    fw = fr.add_mutually_exclusive_group(required=True)
    fw.add_argument("--n", type=int, help="Frame index (0 = first)"); fw.add_argument("--t", type=float, help="Seconds")
    s = sub.add_parser("sheet"); s.add_argument("video", type=Path); s.add_argument("out", type=Path)
    s.add_argument("--fps", type=float, default=4); s.add_argument("--cols", type=int, default=8)
    cl = sub.add_parser("caption-lines"); cl.add_argument("frame", type=Path)
    cl.add_argument("--y0", type=float, default=0.0); cl.add_argument("--y1", type=float, default=1.0)
    cl.add_argument("--mode", choices=["white", "neon"], default="white")
    cp = sub.add_parser("compare"); cp.add_argument("original", type=Path); cp.add_argument("result", type=Path)
    cp.add_argument("out", type=Path); cp.add_argument("--times", type=float, nargs="+", default=[0.1, 1.0, 1.7, 2.3, 3.2, 4.5])
    sb = sub.add_parser("side-by-side"); sb.add_argument("left", type=Path); sb.add_argument("right", type=Path)
    sb.add_argument("out", type=Path); sb.add_argument("--labels", nargs=2, default=["Reference", "Result"])
    sb.add_argument("--audio-from", type=Path)
    mx = sub.add_parser("mux-audio"); mx.add_argument("video", type=Path); mx.add_argument("audio_source", type=Path)
    mx.add_argument("out", type=Path)
    a_ = sub.add_parser("assemble")
    a_.add_argument("--hook", type=Path, required=True); a_.add_argument("--hook-overlay", type=Path)
    a_.add_argument("--demo", type=Path, required=True); a_.add_argument("--demo-overlay", type=Path)
    a_.add_argument("--out", type=Path, required=True); a_.add_argument("--audio-from", type=Path)
    a_.add_argument("--demo-seconds", type=float); a_.add_argument("--size", help="e.g. 720x1280 (default: hook size)")
    a_.add_argument("--hook-overlay-on-demo", action="store_true", help="Keep the hook caption over the demo too")
    c = sub.add_parser("check"); c.add_argument("video", type=Path)
    a = ap.parse_args()
    if a.cmd == "fetch":
        fetch(a.url, a.out, a.env_file)
    elif a.cmd == "find-cut":
        find_cut(a.video, a.out_dir, a.threshold)
    elif a.cmd == "cut-hook":
        cut_hook(a.video, a.frames, a.out, a.first_frame)
    elif a.cmd == "first-frame":
        first_frame(a.source, a.out)
    elif a.cmd == "frame":
        a.out.parent.mkdir(parents=True, exist_ok=True)
        print(f"saved {grab(a.video, a.out, frame=a.n, t=a.t)}")
    elif a.cmd == "sheet":
        sheet(a.video, a.out, a.fps, a.cols)
    elif a.cmd == "caption-lines":
        caption_lines(a.frame, a.y0, a.y1, a.mode)
    elif a.cmd == "compare":
        compare(a.original, a.result, a.out, a.times)
    elif a.cmd == "side-by-side":
        side_by_side(a.left, a.right, a.out, a.labels, a.audio_from)
    elif a.cmd == "mux-audio":
        mux_audio(a.video, a.audio_source, a.out)
    elif a.cmd == "assemble":
        assemble(a.hook, a.hook_overlay, a.demo, a.demo_overlay, a.out, a.audio_from, a.demo_seconds,
                 a.hook_overlay_on_demo, a.size)
    elif a.cmd == "check":
        check(a.video)


if __name__ == "__main__":
    main()
