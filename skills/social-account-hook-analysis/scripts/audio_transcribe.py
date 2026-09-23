#!/usr/bin/env python3
"""Transcribe selected TikTok/Instagram videos from saved ScrapeCreators pages.

Each video and its first three seconds are sent as separate audio requests to
Gemini. Successful per-video results are cached so reruns do not repeat calls.
Run this only when the user requested audio transcription.
"""

import argparse
import base64
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from social import load, normalize, page_data, write_json


DEFAULT_MODEL = "gemini-2.5-flash-lite"
MAX_VIDEO_BYTES = 60 * 1024 * 1024
FULL_PROMPT = """Listen only to the attached audio from one short social video.
Return JSON with exactly these fields: status (speech/no_speech/uncertain),
language (spoken language name or null), transcript (audible spoken words in
the original language or empty string), non_speech_notes (short description
of music or sound effects, or empty string). Do not translate, complete
unclear words, infer speech from the caption or visuals, or treat song lyrics
as spoken narration. Preserve repetitions. When speech is unclear, mark
uncertain and omit doubtful words."""
OPENING_PROMPT = """This file contains ONLY the first three seconds of one
social video. Return JSON with exactly these fields: status
(speech/no_speech/uncertain), language, transcript and non_speech_notes.
Transcribe only words audible in this short file. Do not continue a sentence
past the end, translate, or infer words from context. Omit doubtful words."""


def selected_source_items(out, snapshot):
    """Join raw feed media to selected stable IDs without another API request."""
    items = {}
    for page_number, page in enumerate(sorted((out / "raw").glob("page-*.json")), 1):
        entries, _, _ = page_data(load(page), snapshot["platform"])
        for item in entries:
            row = normalize(item, snapshot["platform"], snapshot["handle"], snapshot["fetched_at_utc"], page_number)
            if row:
                items[row["id"]] = item
    return items


def _https_urls(values):
    return [value for value in values if isinstance(value, str) and urlparse(value).scheme == "https"]


def media_urls(item, platform):
    media = item.get("media", item)
    if platform == "tiktok":
        video = media.get("video") or {}
        urls = []
        for key in ("play_addr_h264", "play_addr", "download_addr"):
            urls.extend((video.get(key) or {}).get("url_list") or [])
        for variant in video.get("bit_rate") or []:
            urls.extend((variant.get("play_addr") or {}).get("url_list") or [])
    else:
        versions = media.get("video_versions") or []
        versions = sorted(versions, key=lambda v: (v.get("width") or 0) * (v.get("height") or 0), reverse=True)
        urls = [v.get("url") for v in versions]
        urls.extend([media.get("video_url"), media.get("progressive_download_url")])
    return list(dict.fromkeys(_https_urls(urls)))


def download_video(urls, target):
    if target.is_file() and target.stat().st_size > 1024:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    last_error = "no HTTPS video URL in saved feed"
    for url in urls:
        try:
            request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(request, timeout=45) as response:
                data = response.read(MAX_VIDEO_BYTES + 1)
            if len(data) > MAX_VIDEO_BYTES or len(data) < 1024 or b"ftyp" not in data[:32]:
                raise ValueError("invalid or oversized MP4")
            temporary = target.with_suffix(".part")
            temporary.write_bytes(data)
            temporary.replace(target)
            return
        except (OSError, URLError, ValueError) as error:
            last_error = f"{type(error).__name__}: {str(error)[:180]}"
    raise RuntimeError(last_error)


def extract_media(video, audio, opening_audio, frame):
    for path in (audio, opening_audio, frame):
        path.parent.mkdir(parents=True, exist_ok=True)
    commands = [
        (frame, ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-ss", "0.35", "-i", str(video), "-frames:v", "1", "-q:v", "3", str(frame)]),
        (audio, ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "32k", str(audio)]),
        (opening_audio, ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), "-t", "3", "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "32k", str(opening_audio)]),
    ]
    for path, command in commands:
        if not path.is_file() or path.stat().st_size == 0:
            subprocess.run(command, check=True, capture_output=True, timeout=120)


def ask_gemini(audio, key, prompt, model):
    body = {"contents": [{"role": "user", "parts": [
        {"text": prompt},
        {"inline_data": {"mime_type": "audio/mpeg", "data": base64.b64encode(audio.read_bytes()).decode("ascii")}},
    ]}], "generationConfig": {"temperature": 0, "maxOutputTokens": 2048,
                            "responseMimeType": "application/json", "thinkingConfig": {"thinkingBudget": 0}}}
    request = Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                      data=json.dumps(body).encode("utf-8"),
                      headers={"Content-Type": "application/json", "x-goog-api-key": key})
    for attempt in range(5):
        try:
            with urlopen(request, timeout=120) as response:
                data = json.load(response)
            answer = json.loads("".join(part.get("text", "") for part in data["candidates"][0]["content"]["parts"]))
            if answer.get("status") not in {"speech", "no_speech", "uncertain"}:
                raise ValueError("Gemini returned an invalid transcription status")
            return answer, data.get("usageMetadata", {})
        except HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == 4:
                raise RuntimeError(f"Gemini HTTP {error.code}: {error.read(300).decode('utf-8', errors='replace')}") from None
        except (URLError, TimeoutError):
            if attempt == 4:
                raise
        time.sleep(min(30, 3 * 2 ** attempt))
    raise RuntimeError("Gemini retry limit reached")


def process(row, item, platform, out, key, model):
    ident = row["id"]
    stem = f'{row["recent_rank"]:03d}-{ident}'
    result_path = out / "transcripts" / f"{stem}.json"
    previous = load(result_path) if result_path.is_file() else None
    if previous and previous.get("model") == model and previous.get("status") in {"speech", "no_speech", "uncertain"} and previous.get("opening_verified"):
        return previous
    video = out / "video_media" / f"{stem}.mp4"
    audio = out / "audio_media" / f"{stem}.mp3"
    opening_audio = out / "audio_media" / f"{stem}-opening.mp3"
    frame = out / "opening_frames" / f"{stem}.jpg"
    result = previous if previous and previous.get("model") == model else None
    result = result or {"id": ident, "recent_rank": row["recent_rank"], "source_url": row["url"],
                        "model": model, "status": "error", "language": None, "transcript": "",
                        "opening_0_3s": "", "non_speech_notes": "", "usage": {}}
    try:
        download_video(media_urls(item, platform), video)
        extract_media(video, audio, opening_audio, frame)
        result["audio_file"] = audio.relative_to(out).as_posix()
        result["opening_frame_file"] = frame.relative_to(out).as_posix()
        if result["status"] not in {"speech", "no_speech", "uncertain"}:
            answer, usage = ask_gemini(audio, key, FULL_PROMPT, model)
            result.update({field: answer.get(field) for field in ("status", "language", "transcript", "non_speech_notes")})
            result["usage"] = usage
        opening, opening_usage = ask_gemini(opening_audio, key, OPENING_PROMPT, model)
        result["opening_0_3s"] = opening.get("transcript") or ""
        result["opening_status"] = opening["status"]
        result["opening_usage"] = opening_usage
        result["opening_verified"] = True
        result.pop("error", None)
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {str(error)[:300]}"
    write_json(result_path, result)
    return result


def cached_complete(out, row, model):
    path = out / "transcripts" / f'{row["recent_rank"]:03d}-{row["id"]}.json'
    if not path.is_file():
        return False
    item = load(path)
    return item.get("model") == model and item.get("status") in {"speech", "no_speech", "uncertain"} and bool(item.get("opening_verified"))


def usage_summary(results):
    counts = Counter()
    for item in results:
        for key in ("usage", "opening_usage"):
            usage = item.get(key) or {}
            counts["input_tokens"] += usage.get("promptTokenCount", 0)
            counts["output_tokens"] += usage.get("candidatesTokenCount", 0)
            for detail in usage.get("promptTokensDetails") or []:
                counts[f'input_{str(detail.get("modality", "unknown")).lower()}_tokens'] += detail.get("tokenCount", 0)
    return dict(counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int, help="Only the first N selected videos; default: all")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true", help="Check saved media URLs and scope without downloads or Gemini calls")
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    snapshot = load(args.out / "snapshot.json")
    rows = load(args.out / "videos.json")
    chosen = rows[:args.limit]
    source = selected_source_items(args.out, snapshot)
    resolvable = [row for row in chosen if row["id"] in source and media_urls(source[row["id"]], snapshot["platform"])]
    resolvable_ids = {row["id"] for row in resolvable}
    uncached = [row for row in chosen if not cached_complete(args.out, row, args.model)]
    if args.dry_run:
        print(json.dumps({"selected": len(chosen), "media_urls_found": len(resolvable),
                          "missing_media_ids": [row["id"] for row in chosen if row["id"] not in resolvable_ids],
                          "cached_complete": len(chosen) - len(uncached),
                          "duration_seconds_known": sum(row.get("duration_seconds") or 0 for row in chosen),
                          "max_new_gemini_calls": 2 * sum(row["id"] in resolvable_ids for row in uncached),
                          "model": args.model}, indent=2))
        return
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key and any(row["id"] in resolvable_ids for row in uncached):
        parser.error("Set GOOGLE_API_KEY or GEMINI_API_KEY for uncached transcription")
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 5))) as pool:
        futures = {pool.submit(process, row, source.get(row["id"], {}), snapshot["platform"], args.out, key, args.model): row for row in chosen}
        for future in as_completed(futures):
            item = future.result()
            print(f'#{item["recent_rank"]} {item["status"]}: {item.get("error", "")[:90]}', flush=True)
    results = []
    for row in rows:
        path = args.out / "transcripts" / f'{row["recent_rank"]:03d}-{row["id"]}.json'
        if path.is_file():
            results.append(load(path))
    write_json(args.out / "transcripts.json", results)
    write_json(args.out / "audio_usage.json", {"models_in_saved_results": sorted({item.get("model") or "unknown" for item in results}),
                                                 "selected_in_run": len(chosen), "saved_results": len(results),
                                                 "tokens_from_saved_responses": usage_summary(results)})
    by_id = {item["id"]: item for item in results}
    changed = False
    for row in rows:
        frame = by_id.get(row["id"], {}).get("opening_frame_file")
        if not row.get("cover_file") and frame and (args.out / frame).is_file():
            row["cover_file"] = frame
            row["cover_status"] = "opening_frame_fallback"
            changed = True
    if changed:
        write_json(args.out / "videos.json", rows)
    print(f'Transcripts: {sum(item.get("status") in {"speech", "no_speech", "uncertain"} for item in results)}/{len(chosen)}')


if __name__ == "__main__":
    main()
