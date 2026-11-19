#!/usr/bin/env python3
"""Minimal kie.ai client for the emotion + demo pipeline (standard library only).

Subcommands:
  credits                                   show the kie credit balance
  upload FILE [FILE ...]                    upload local images or videos, print one public URL per line
  swap-frame --image FRAME --image FACE [--image SHEET] --prompt-file P --out swapped.png
                                            GPT Image 2.6 image-to-image: image 1 = the reference's first
                                            frame, the next images = the character (face, sheet)
  wan-edit   --ref-video HOOK.mp4 --ref-image swapped.png --ref-image face.jpg --prompt-file P --out raw.mp4
                                            Wan 3.0 video edit: puts the character into the reference hook
                                            clip and keeps its motion, timing and framing
  resume     --task TASK_ID --out FILE      poll an already created task instead of paying again

API key: KIE_API_KEY in the environment, or --env-file path/to/.env with KIE_API_KEY=...
Every created task is appended to kie_jobs.jsonl next to --out BEFORE polling, and its credits are
appended after success. If polling breaks, run `resume` with that task id. Never create a second task
for an unknown outcome, and never start a duplicate run to "race" a slow one: both are billed.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

API = "https://api.kie.ai/api/v1"
UPLOAD = "https://kieai.redpandaai.co/api/file-stream-upload"  # multipart, works for big PNG and MP4
USD_PER_CREDIT = 0.005  # kie.ai/pricing; check before quoting a price
GPT_IMAGE = "gpt-image-2-6/sunburst-image-to-image"
WAN = "wan/3-0-video"


def api_key(env_file: str | None) -> str:
    if env_file:
        for line in Path(env_file).expanduser().read_text(encoding="utf-8").splitlines():
            line = line.strip().removeprefix("export ").strip()
            if line.startswith("KIE_API_KEY="):
                return line.split("=", 1)[1].strip().strip("\"'")
    key = os.environ.get("KIE_API_KEY", "").strip()
    if not key:
        sys.exit("KIE_API_KEY is not set. Get a key at https://kie.ai/api-key and export it, or pass --env-file.")
    return key


def call(key: str, url: str, body: dict | None = None, retries: int = 4, timeout: int = 120) -> dict:
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, data=json.dumps(body).encode() if body is not None else None,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            return json.load(urllib.request.urlopen(req, timeout=timeout))
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                raise RuntimeError(f"{url.split('?')[0]}: HTTP {exc.code} {exc.read().decode(errors='ignore')[:300]}")
            last = exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            last = exc
        print(f"  network retry {attempt + 1}/{retries}: {last}", file=sys.stderr)
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Request failed after {retries} attempts: {url.split('?')[0]}: {last}")


def upload(key: str, path: Path) -> str:
    """Multipart stream upload, one file at a time (parallel uploads were flaky).
    Returns a public URL that kie keeps for about 24 hours."""
    if not path.is_file():
        sys.exit(f"File not found: {path}")
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    boundary = uuid.uuid4().hex
    parts = [f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
             for k, v in (("uploadPath", "emotion-demo"), ("fileName", f"{uuid.uuid4().hex[:8]}-{path.name}"))]
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
                 f"Content-Type: {mime}\r\n\r\n".encode() + path.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    last = None
    for attempt in range(4):
        req = urllib.request.Request(UPLOAD, data=body, method="POST", headers={
            "Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                data = (json.load(r).get("data") or {})
            url = data.get("downloadUrl") or data.get("fileUrl")
            if url:
                print(f"uploaded {path.name}", file=sys.stderr)
                return url
            last = data
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:  # SSL resets happen
            last = exc
        print(f"  upload retry {attempt + 1}/4 for {path.name}: {last}", file=sys.stderr)
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Upload failed for {path}: {last}")


def as_url(key: str, ref: str) -> str:
    return ref if ref.startswith(("http://", "https://")) else upload(key, Path(ref).expanduser())


def ledger_write(ledger: Path, row: dict) -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def create(key: str, model: str, inp: dict, ledger: Path, label: str) -> str:
    res = call(key, f"{API}/jobs/createTask", {"model": model, "input": inp}, retries=1)
    task = (res.get("data") or {}).get("taskId")
    if res.get("code") not in (200, None) or not task:
        raise RuntimeError(f"createTask failed: {json.dumps(res)[:400]}")
    ledger_write(ledger, {"task": task, "model": model, "label": label, "created": int(time.time()),
                          "input": {k: v for k, v in inp.items() if k != "prompt"}})
    print(f"task {task} ({model}) logged to {ledger}", file=sys.stderr)
    return task


def poll(key: str, task: str, timeout_s: int) -> tuple[str, dict]:
    t0, last = time.time(), None
    while time.time() - t0 < timeout_s:
        time.sleep(8)
        try:
            data = call(key, f"{API}/jobs/recordInfo?taskId={task}", retries=2).get("data") or {}
        except RuntimeError as exc:
            print(f"  poll error, keep waiting: {exc}", file=sys.stderr)
            continue
        state = data.get("state")
        if state != last:
            print(f"  {task}: {state} ({time.time() - t0:.0f}s)", file=sys.stderr)
            last = state
        if state == "success":
            urls = json.loads(data.get("resultJson") or "{}").get("resultUrls") or []
            if not urls:
                raise RuntimeError(f"{task}: success without resultUrls")
            return urls[0], data
        if state == "fail":
            raise RuntimeError(f"{task} failed: {data.get('failMsg') or data.get('failCode')}")
    raise TimeoutError(f"{task} still running after {timeout_s}s. Run `resume --task {task}` later.")


def finish(key: str, task: str, out: Path, timeout_s: int) -> None:
    t0 = time.time()
    url, data = poll(key, task, timeout_s)
    out.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=300) as r:
        out.write_bytes(r.read())
    credits = data.get("creditsConsumed")
    usd = round(float(credits) * USD_PER_CREDIT, 3) if credits not in (None, "") else None
    ledger_write(out.parent / "kie_jobs.jsonl", {"task": task, "state": "success", "out": out.name,
                                                 "credits": credits, "usd": usd, "seconds": round(time.time() - t0)})
    print(f"saved {out} ({out.stat().st_size // 1024} KB), credits {credits} (~${usd}), {time.time() - t0:.0f}s")


def read_prompt(a: argparse.Namespace) -> str:
    text = a.prompt if a.prompt else Path(a.prompt_file).read_text(encoding="utf-8")
    if not text.strip():
        sys.exit("Empty prompt")
    return text.strip()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env-file")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("credits")
    up = sub.add_parser("upload")
    up.add_argument("files", nargs="+")

    sw = sub.add_parser("swap-frame", help="GPT Image 2.6 image-to-image")
    sw.add_argument("--image", action="append", required=True,
                    help="URL or local path; repeat. Image 1 = reference first frame, then the character.")
    sp = sw.add_mutually_exclusive_group(required=True)
    sp.add_argument("--prompt")
    sp.add_argument("--prompt-file")
    sw.add_argument("--out", type=Path, required=True)
    sw.add_argument("--aspect-ratio", default="9:16")
    sw.add_argument("--resolution", default="2K", choices=["1K", "2K", "4K"])
    sw.add_argument("--quality", default="high")
    sw.add_argument("--model", default=GPT_IMAGE)

    we = sub.add_parser("wan-edit", help="Wan 3.0 video edit with reference video and images")
    we.add_argument("--ref-video", action="append", required=True, help="The cut hook clip (1-15 s); repeatable")
    we.add_argument("--ref-image", action="append", required=True,
                    help="Swapped first frame first, then the character's face/sheet; repeatable")
    wp = we.add_mutually_exclusive_group(required=True)
    wp.add_argument("--prompt")
    wp.add_argument("--prompt-file")
    we.add_argument("--out", type=Path, required=True)
    we.add_argument("--resolution", default="720P", choices=["480P", "720P", "1080P"])
    we.add_argument("--duration", type=int, default=-1, help="-1 keeps the reference clip length")
    we.add_argument("--aspect-ratio", default="adaptive")
    we.add_argument("--audio", action="store_true", help="Let Wan generate audio (default off: mux the original)")
    we.add_argument("--seed", type=int)
    we.add_argument("--model", default=WAN)

    rs = sub.add_parser("resume")
    rs.add_argument("--task", required=True)
    rs.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    key = api_key(a.env_file)

    if a.cmd == "credits":
        print(json.dumps(call(key, f"{API}/chat/credit"), ensure_ascii=False))
    elif a.cmd == "upload":
        for f in a.files:
            print(upload(key, Path(f).expanduser()))
    elif a.cmd == "swap-frame":
        prompt = read_prompt(a)
        urls = [as_url(key, i) for i in a.image]
        inp = {"prompt": prompt, "input_urls": urls, "aspect_ratio": a.aspect_ratio,
               "resolution": a.resolution, "quality": a.quality, "output_format": "png"}
        task = create(key, a.model, inp, a.out.parent / "kie_jobs.jsonl", a.out.name)
        finish(key, task, a.out, timeout_s=900)
    elif a.cmd == "wan-edit":
        prompt = read_prompt(a)
        inp = {"prompt": prompt, "resolution": a.resolution, "aspect_ratio": a.aspect_ratio,
               "duration": a.duration, "audio": a.audio,
               "reference_video_urls": [as_url(key, v) for v in a.ref_video],
               "reference_image_urls": [as_url(key, i) for i in a.ref_image]}
        if a.seed is not None:
            inp["seed"] = a.seed
        task = create(key, a.model, inp, a.out.parent / "kie_jobs.jsonl", a.out.name)
        finish(key, task, a.out, timeout_s=2400)
    elif a.cmd == "resume":
        finish(key, a.task, a.out, timeout_s=2400)


if __name__ == "__main__":
    main()
