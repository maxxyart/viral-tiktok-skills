#!/usr/bin/env python3
"""ffmpeg helpers for the emotion + demo pipeline. Needs ffmpeg/ffprobe; yt-dlp for URLs.

Subcommands:
  fetch URL OUT.mp4                         download a TikTok/Instagram video (reference or donor)
  first-frame SOURCE OUT.jpg                frame 0 of a URL or local video -> background asset
  sheet VIDEO OUT.jpg [--fps 2] [--cols 6]  contact sheet to review motion, lips and text
  assemble --hook RAW --overlay PNG --demo DEMO --out FINAL [--trim-start 1] [--hook-seconds 5]
           [--overlay-on-demo]              hook clip + text overlay, then the demo; silent audio
  check VIDEO                               duration, size, fps, peak volume
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FIT = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setsar=1"


def need(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        sys.exit(f"{tool} not found. Install it first (macOS: brew install {tool}).")
    return path


def run(cmd: list[str]) -> str:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode:
        sys.exit(f"Command failed: {' '.join(cmd[:4])} ...\n{res.stderr[-1500:]}")
    return res.stdout


def fetch(url: str, out: Path) -> Path:
    need("yt-dlp")
    out.parent.mkdir(parents=True, exist_ok=True)
    run(["yt-dlp", "-q", "-f", "bv*+ba/b", "--merge-output-format", "mp4", "--write-info-json",
         "-o", str(out.with_suffix("")) + ".%(ext)s", url])
    info = out.with_suffix(".info.json")
    if info.exists():
        d = json.loads(info.read_text(encoding="utf-8"))
        print(f"{out}: {d.get('duration')}s, views {d.get('view_count')}, by @{d.get('uploader') or d.get('uploader_id')}")
    return out


def first_frame(src: str, out: Path) -> Path:
    need("ffmpeg")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        video = fetch(src, Path(tmp) / "src.mp4") if src.startswith(("http://", "https://")) else Path(src)
        run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-vf", r"select=eq(n\,0)",
             "-frames:v", "1", "-q:v", "1", str(out)])
    print(f"saved {out}")
    return out


def sheet(video: Path, out: Path, fps: float, cols: int) -> Path:
    need("ffmpeg")
    run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-vf",
         f"fps={fps},scale=240:-1,tile={cols}x2", "-frames:v", "1", str(out)])
    print(f"saved {out}")
    return out


def assemble(hook: Path, overlay: Path, demo: Path, out: Path, trim_start: float, hook_s: float,
             overlay_on_demo: bool) -> Path:
    """Trimming the first second makes each clip start away from the still (variations stop
    looking identical). Audio is replaced by silence: music is added inside TikTok."""
    need("ffmpeg")
    out.parent.mkdir(parents=True, exist_ok=True)
    if overlay_on_demo:
        ov = "[1:v]split=2[o1][o2];"
        demo_chain = f"[2:v]{FIT},format=yuv420p[d0];[d0][o2]overlay=0:0,format=yuv420p[d]"
    else:
        ov = "[1:v]null[o1];"
        demo_chain = f"[2:v]{FIT},format=yuv420p[d]"
    graph = (f"{ov}[0:v]{FIT},setpts=PTS-STARTPTS[h0];[h0][o1]overlay=0:0,format=yuv420p[h];"
             f"{demo_chain};[h][d]concat=n=2:v=1:a=0[v]")
    run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(trim_start), "-t", str(hook_s), "-i", str(hook),
         "-i", str(overlay), "-i", str(demo),
         "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
         "-filter_complex", graph, "-map", "[v]", "-map", "3:a", "-shortest",
         "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-c:a", "aac", "-movflags", "+faststart", str(out)])
    check(out)
    return out


def check(video: Path) -> None:
    need("ffprobe")
    meta = json.loads(run(["ffprobe", "-v", "error", "-show_entries",
                           "format=duration:stream=codec_type,width,height,r_frame_rate", "-of", "json", str(video)]))
    v = next((s for s in meta["streams"] if s["codec_type"] == "video"), {})
    vol = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    peak = next((ln.split("max_volume:")[1].strip() for ln in vol.splitlines() if "max_volume" in ln), "no audio")
    print(f"{video}: {float(meta['format']['duration']):.2f}s, {v.get('width')}x{v.get('height')}, "
          f"{v.get('r_frame_rate')} fps, peak {peak}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch"); f.add_argument("url"); f.add_argument("out", type=Path)
    ff = sub.add_parser("first-frame"); ff.add_argument("source"); ff.add_argument("out", type=Path)
    s = sub.add_parser("sheet"); s.add_argument("video", type=Path); s.add_argument("out", type=Path)
    s.add_argument("--fps", type=float, default=2); s.add_argument("--cols", type=int, default=6)
    a_ = sub.add_parser("assemble")
    a_.add_argument("--hook", type=Path, required=True); a_.add_argument("--overlay", type=Path, required=True)
    a_.add_argument("--demo", type=Path, required=True); a_.add_argument("--out", type=Path, required=True)
    a_.add_argument("--trim-start", type=float, default=1.0); a_.add_argument("--hook-seconds", type=float, default=5.0)
    a_.add_argument("--overlay-on-demo", action="store_true", help="Keep the hook text over the demo too")
    c = sub.add_parser("check"); c.add_argument("video", type=Path)
    a = ap.parse_args()
    if a.cmd == "fetch":
        fetch(a.url, a.out)
    elif a.cmd == "first-frame":
        first_frame(a.source, a.out)
    elif a.cmd == "sheet":
        sheet(a.video, a.out, a.fps, a.cols)
    elif a.cmd == "assemble":
        assemble(a.hook, a.overlay, a.demo, a.out, a.trim_start, a.hook_seconds, a.overlay_on_demo)
    elif a.cmd == "check":
        check(a.video)


if __name__ == "__main__":
    main()
