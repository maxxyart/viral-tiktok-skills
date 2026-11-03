"""Shared helpers: ScrapeCreators key from the environment, GET with retries/backoff, image -> JPEG."""
import json
import os
import shutil
import subprocess
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

KEY_VARS = ("SCRAPE_CREATORS_API_KEY", "SCRAPECREATORS_API_KEY")
_state = {"key": None, "credits": None}


def api_key():
    """The key comes only from the environment; no shell config or .env files are searched."""
    for var in KEY_VARS:
        if os.environ.get(var):
            return os.environ[var]
    sys.exit(f"ERROR: set {KEY_VARS[0]} in the environment (get a key at https://scrapecreators.com)")


def api(path, params, tries=5):
    """GET https://api.scrapecreators.com{path}; retries with exponential backoff (API returns sporadic 500s)."""
    _state["key"] = _state["key"] or api_key()
    url = f"https://api.scrapecreators.com{path}?{urlencode(params)}"
    for att in range(tries):
        try:
            with urlopen(Request(url, headers={"x-api-key": _state["key"]}), timeout=90) as r:
                d = json.loads(r.read().decode())
            if isinstance(d, dict) and d.get("credits_remaining") is not None:
                _state["credits"] = d["credits_remaining"]
            return d
        except Exception:
            if att == tries - 1:
                raise
            time.sleep(2 ** att * 2)


def credits_remaining():
    return _state["credits"]


def to_jpeg(src, dst, side, quality=85):
    """Convert a downloaded slide (JPEG, WebP or HEIC) to JPEG with the longest side <= side.
    macOS: `sips`. Elsewhere: Pillow; HEIC then needs `pip install pillow-heif`."""
    if shutil.which("sips"):
        res = subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", str(quality), "-Z", str(side),
                              src, "--out", dst], capture_output=True, timeout=60)
        return res.returncode == 0 and os.path.exists(dst)
    from PIL import Image
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass
    im = Image.open(src).convert("RGB")
    im.thumbnail((side, side))
    im.save(dst, "JPEG", quality=quality)
    return True
