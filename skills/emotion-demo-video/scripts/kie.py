#!/usr/bin/env python3
"""Minimal kie.ai client for the emotion + demo pipeline (standard library + optional Pillow).

Subcommands:
  credits                                   show the kie credit balance
  upload FILE [FILE ...]                    upload local images, print one public URL per line
  edit-image  --image A --image B --prompt P --out still.png
                                            Nano Banana 2 edit (image 1 = scene, image 2 = character)
  video       --image still.png --prompt P --out raw.mp4 [--duration 6] [--resolution 1080p]
                                            Omni 1.1 image-to-video (kie model `gemini-omni-video`)
  resume      --task TASK_ID --out FILE     poll an already created task instead of paying again

API key: KIE_API_KEY in the environment, or --env-file path/to/.env with KIE_API_KEY=...
Every created task is appended to kie_jobs.jsonl next to --out BEFORE polling. If polling breaks,
run `resume` with that task id. Never create a second task for an unknown outcome.
"""

from __future__ import annotations

import argparse
import base64
import io
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
UPLOAD = "https://kieai.redpandaai.co/api/file-base64-upload"
MAX_UPLOAD_BYTES = 900_000  # large PNGs break the base64 upload; send JPEG under ~1 MB


def api_key(env_file: str | None) -> str:
    if env_file:
        for line in Path(env_file).expanduser().read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("KIE_API_KEY="):
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
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last = exc
            print(f"  network retry {attempt + 1}/{retries}: {exc}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Request failed after {retries} attempts: {url}: {last}")


def _jpeg_bytes(path: Path) -> tuple[bytes, str]:
    data = path.read_bytes()
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    if len(data) <= MAX_UPLOAD_BYTES and mime in ("image/jpeg", "image/png"):
        return data, mime
    try:
        from PIL import Image
    except ImportError:
        sys.exit(f"{path} is {len(data) // 1024} KB. Install Pillow (python3 -m pip install Pillow) "
                 "or convert it to a JPEG under 1 MB first.")
    img = Image.open(path).convert("RGB")
    for quality in (92, 85, 78, 70):
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        if buf.tell() <= MAX_UPLOAD_BYTES:
            break
        img = img.resize((int(img.width * 0.85), int(img.height * 0.85)))
    return buf.getvalue(), "image/jpeg"


def upload(key: str, path: Path) -> str:
    """Upload sequentially (parallel uploads were flaky). Returns a temporary public URL."""
    data, mime = _jpeg_bytes(path)
    ext = ".jpg" if mime == "image/jpeg" else ".png"
    body = {"base64Data": f"data:{mime};base64,{base64.b64encode(data).decode()}",
            "uploadPath": "emotion-demo", "fileName": uuid.uuid4().hex + ext}
    res = call(key, UPLOAD, body, retries=4, timeout=90)
    url = (res.get("data") or {}).get("downloadUrl")
    if not url:
        raise RuntimeError(f"Upload failed for {path}: {json.dumps(res)[:300]}")
    return url


def as_url(key: str, ref: str) -> str:
    return ref if ref.startswith(("http://", "https://")) else upload(key, Path(ref).expanduser())


def create(key: str, model: str, inp: dict, ledger: Path, label: str) -> str:
    res = call(key, f"{API}/jobs/createTask", {"model": model, "input": inp}, retries=1)
    task = (res.get("data") or {}).get("taskId")
    if res.get("code") not in (200, None) or not task:
        raise RuntimeError(f"createTask failed: {json.dumps(res)[:400]}")
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"task": task, "model": model, "label": label, "created": int(time.time()),
                             "input": {k: v for k, v in inp.items() if k != "prompt"}}) + "\n")
    print(f"task {task} ({model}) logged to {ledger}", file=sys.stderr)
    return task


def poll(key: str, task: str, timeout_s: int = 1500) -> str:
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
            return urls[0]
        if state == "fail":
            raise RuntimeError(f"{task} failed: {data.get('failMsg') or data.get('failCode')}")
    raise TimeoutError(f"{task} still running after {timeout_s}s. Run `resume --task {task}` later.")


def download(url: str, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=300) as r:
        out.write_bytes(r.read())
    print(f"saved {out} ({out.stat().st_size // 1024} KB)")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env-file")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("credits")
    up = sub.add_parser("upload")
    up.add_argument("files", nargs="+")
    ed = sub.add_parser("edit-image")
    ed.add_argument("--image", action="append", required=True, help="URL or local path; repeat. Order matters.")
    ed.add_argument("--prompt", required=True)
    ed.add_argument("--out", type=Path, required=True)
    ed.add_argument("--aspect-ratio", default="9:16")
    ed.add_argument("--resolution", default="2K", choices=["1K", "2K", "4K"])
    vd = sub.add_parser("video")
    vd.add_argument("--image", required=True, help="Still with the character already in the scene")
    vd.add_argument("--prompt", required=True)
    vd.add_argument("--out", type=Path, required=True)
    vd.add_argument("--duration", default="6", choices=["4", "6", "8", "10"])
    vd.add_argument("--resolution", default="1080p", choices=["720p", "1080p", "4k"])
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
    elif a.cmd == "edit-image":
        urls = [as_url(key, i) for i in a.image]
        inp = {"prompt": a.prompt, "image_input": urls, "aspect_ratio": a.aspect_ratio,
               "resolution": a.resolution, "output_format": "png", "google_search": False}
        task = create(key, "nano-banana-2", inp, a.out.parent / "kie_jobs.jsonl", a.out.name)
        download(poll(key, task), a.out)
    elif a.cmd == "video":
        inp = {"prompt": a.prompt, "image_urls": [as_url(key, a.image)], "duration": a.duration,
               "aspect_ratio": "9:16", "resolution": a.resolution}
        task = create(key, "gemini-omni-video", inp, a.out.parent / "kie_jobs.jsonl", a.out.name)
        download(poll(key, task), a.out)
    elif a.cmd == "resume":
        download(poll(key, a.task), a.out)


if __name__ == "__main__":
    main()
