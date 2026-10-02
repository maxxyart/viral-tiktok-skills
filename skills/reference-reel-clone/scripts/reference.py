#!/usr/bin/env python3
"""Stage 1 helpers for cloning a reference reel. Needs ffmpeg/ffprobe; yt-dlp only as a fallback.

Subcommands:
  fetch URL OUT.mp4                 download a TikTok/Instagram video: ScrapeCreators first, yt-dlp fallback
  prepare VIDEO OUTDIR [--fps 5]    frames at --fps, scene-change keyframes in full size, 1 s contact
                                    sheets, 16 kHz audio and a word-timestamped transcript when Whisper
                                    (faster-whisper or openai-whisper) is installed

Whisper model: WHISPER_MODEL (default small; base or tiny are faster).
ScrapeCreators key: SCRAPE_CREATORS_API_KEY or SCRAPECREATORS_API_KEY in the environment, or --env-file.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.scrapecreators.com"


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


def api_key(env_file: str | None) -> str | None:
    if env_file:
        for line in Path(env_file).expanduser().read_text(encoding="utf-8").splitlines():
            k, _, v = line.partition("=")
            if k.strip() in ("SCRAPE_CREATORS_API_KEY", "SCRAPECREATORS_API_KEY") and v.strip():
                return v.strip().strip('"').strip("'")
    return os.environ.get("SCRAPE_CREATORS_API_KEY") or os.environ.get("SCRAPECREATORS_API_KEY")


def sc_get(path: str, params: dict, key: str) -> dict:
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"x-api-key": key})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # retry 5xx/network; the API returns intermittent 500s
            last = e
            code = getattr(e, "code", 500)
            if 400 <= code < 500 and code != 429:
                break
            time.sleep(3 ** attempt)
    raise RuntimeError(f"ScrapeCreators {path} failed: {last}")


def video_url_from(payload: dict) -> str | None:
    """Pick a downloadable video URL from a ScrapeCreators TikTok or Instagram post payload."""
    aweme = payload.get("aweme_detail") or {}
    video = aweme.get("video") or {}
    for field in ("download_no_watermark_addr", "play_addr", "download_addr"):
        urls = (video.get(field) or {}).get("url_list") or []
        if urls:
            return urls[0]
    media = (payload.get("data") or {}).get("xdt_shortcode_media") or payload.get("xdt_shortcode_media") or {}
    return media.get("video_url") or payload.get("video_url")


def fetch(url: str, out: Path, env_file: str | None) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    key = api_key(env_file)
    if key:
        path = "/v2/tiktok/video" if "tiktok.com" in url else "/v1/instagram/post"
        try:
            payload = sc_get(path, {"url": url}, key)
            (out.with_suffix(".meta.json")).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
            src = video_url_from(payload)
            if src:
                req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0", "Referer": url})
                with urllib.request.urlopen(req, timeout=180) as r, open(out, "wb") as fh:
                    shutil.copyfileobj(r, fh)
                print(f"saved {out} via ScrapeCreators")
                return out
            print("ScrapeCreators returned no video URL; trying yt-dlp", file=sys.stderr)
        except Exception as e:
            print(f"ScrapeCreators failed ({e}); trying yt-dlp", file=sys.stderr)
    else:
        print("No ScrapeCreators key; using yt-dlp", file=sys.stderr)
    need("yt-dlp")
    run(["yt-dlp", "-q", "-f", "bv*+ba/b", "--merge-output-format", "mp4",
         "-o", str(out.with_suffix("")) + ".%(ext)s", url])
    print(f"saved {out} via yt-dlp")
    return out


def load_wav16k(path: Path):
    """16 kHz mono PCM WAV -> float32 numpy array (numpy ships with faster-whisper)."""
    import wave
    import numpy as np  # type: ignore
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def transcribe(audio: Path, outdir: Path) -> bool:
    """Word-level transcript with faster-whisper or openai-whisper, whichever is installed."""
    words = []
    try:
        from faster_whisper import WhisperModel  # type: ignore
        model = WhisperModel(os.environ.get("WHISPER_MODEL", "small"), compute_type="int8")
        # Pass samples, not a path: some PyAV builds break faster-whisper's own decoder
        segments, _ = model.transcribe(load_wav16k(audio), word_timestamps=True)
        for seg in segments:
            for w in seg.words or []:
                words.append({"word": w.word.strip(), "start": round(w.start, 2), "end": round(w.end, 2)})
    except ImportError:
        try:
            import whisper  # type: ignore
            res = whisper.load_model(os.environ.get("WHISPER_MODEL", "small")).transcribe(str(audio), word_timestamps=True)
            for seg in res["segments"]:
                for w in seg.get("words", []):
                    words.append({"word": w["word"].strip(), "start": round(w["start"], 2), "end": round(w["end"], 2)})
        except ImportError:
            return False
    (outdir / "transcript.json").write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")
    (outdir / "transcript.txt").write_text(
        "\n".join(f"{w['start']:6.2f}–{w['end']:6.2f}  {w['word']}" for w in words), encoding="utf-8")
    return True


def prepare(video: Path, outdir: Path, fps: float) -> None:
    need("ffmpeg")
    need("ffprobe")
    outdir.mkdir(parents=True, exist_ok=True)
    meta = json.loads(run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height,r_frame_rate",
                           "-of", "json", str(video)]))
    duration = float(meta["format"]["duration"])
    frames = outdir / f"frames{int(fps)}"
    frames.mkdir(exist_ok=True)
    run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-vf", f"fps={fps},scale=360:-2",
         "-q:v", "3", str(frames / "f_%04d.jpg")])
    key = outdir / "key"
    key.mkdir(exist_ok=True)
    run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-vf", r"select='eq(n\,0)+gt(scene\,0.25)'",
         "-fps_mode", "vfr", "-q:v", "2", str(key / "k_%03d.jpg")])
    sheets = outdir / "sheets"
    sheets.mkdir(exist_ok=True)
    per_sheet = int(fps * 4)  # 4 seconds per sheet, one row per second
    run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-vf",
         f"fps={fps},scale=200:-2,tile={int(fps)}x4", "-q:v", "3", str(sheets / "s_%03d.jpg")])
    audio = outdir / "audio16k.wav"
    has_audio = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-vn", "-ac", "1",
                                "-ar", "16000", str(audio)], capture_output=True).returncode == 0
    words = transcribe(audio, outdir) if has_audio else False
    print(json.dumps({
        "duration_s": round(duration, 2),
        "frames": len(list(frames.glob("*.jpg"))),
        "keyframes_scene_changes": len(list(key.glob("*.jpg"))),
        "contact_sheets": len(list(sheets.glob("*.jpg"))),
        "seconds_per_sheet": per_sheet / fps,
        "audio": str(audio) if has_audio else None,
        "transcript": str(outdir / "transcript.txt") if words else
        "not created: pip install faster-whisper (or openai-whisper), then rerun prepare",
    }, ensure_ascii=False, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env-file")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch"); f.add_argument("url"); f.add_argument("out", type=Path)
    p = sub.add_parser("prepare"); p.add_argument("video", type=Path); p.add_argument("outdir", type=Path)
    p.add_argument("--fps", type=float, default=5)
    a = ap.parse_args()
    if a.cmd == "fetch":
        fetch(a.url, a.out, a.env_file)
    else:
        prepare(a.video, a.outdir, a.fps)


if __name__ == "__main__":
    main()
