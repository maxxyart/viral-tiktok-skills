#!/usr/bin/env python3
"""Facebook Ads deep analysis — enrich facebook-ads-short-analysis CSV with Gemini hook/script data.

Routes each row by media_type:
  - video    → download MP4 (video_sd_url, fallback video_hd_url), ffmpeg-trim to
               N seconds, send to Gemini with VIDEO_PROMPT
  - image    → download JPG/PNG, send raw to Gemini with IMAGE_PROMPT (no ffmpeg)
  - carousel → up to 3 card images in ONE model call with CAROUSEL_PROMPT (cards
               come from the <prefix>_ads_full.json sidecar when it sits next to
               the input CSV; otherwise falls back to the CSV's first-card
               image/video)

Output columns (7):
  hook_text_overlay, visual_hook  — all types
  script                          — video: timestamped spoken script;
                                    carousel: card-by-card flow
  emotion                         — image + carousel
  cta                             — all types
  product_moment                  — video only (when the product/app first appears)
  analysis_status                 — ok / ok:grok / skip:* / stale_url / error:*

Results stream into <out-csv>.jsonl as they finish; --resume re-runs only rows
that aren't ok yet. Provider is probed once at start: if Gemini is unavailable
(e.g. VPN geo-block "User location is not supported") and XAI_API_KEY exists,
image/carousel rows fall back to Grok; video rows get error:gemini_unavailable
(Grok has no video input).
"""
import os, sys, json, csv, time, re, base64, asyncio, subprocess, tempfile, argparse
from collections import Counter
from pathlib import Path
import httpx
from google import genai
from google.genai import types

DEFAULT_MODEL = "gemini-3.1-flash-lite"
GROK_MODEL = os.environ.get("XAI_MODEL", "grok-4.20-0309-non-reasoning")
GROK_URL = "https://api.x.ai/v1/chat/completions"
OUT_COLS = ("hook_text_overlay", "visual_hook", "script", "emotion",
            "cta", "product_moment", "analysis_status")
ENV_FILES = []  # filled only by an explicit --env-file; no automatic key search

VIDEO_PROMPT = """Analyze this Facebook ad video (first ~10 seconds). Return STRICT JSON only, no markdown fences:
{
  "hook_text_overlay": "exact on-screen text on FIRST FRAME (0s). Empty string if none.",
  "visual_hook": "what viewer sees in first 2s — subject, setting, camera, emotion. 1-2 sentences.",
  "script": "timestamped spoken script [0:00] ... [0:03] ... . Under 800 chars. If no speech, describe audio.",
  "cta": "call to action, spoken or on-screen. Empty string if none.",
  "product_moment": "when and how the product/app first appears, e.g. '0:04 app UI screen recording'. Empty string if not shown."
}"""

IMAGE_PROMPT = """Analyze this Facebook ad image. Return STRICT JSON only, no markdown fences:
{
  "hook_text_overlay": "exact text overlaid on the image. Empty string if none.",
  "visual_hook": "what is depicted — subject, setting, mood, composition, style (photo/illustration/stock/UGC). 1-2 sentences.",
  "emotion": "dominant emotional tone (e.g. despair, exhaustion, loneliness, hope, tenderness). 1-3 words.",
  "cta": "call-to-action text visible on the image (button/badge/caption). Empty string if none."
}"""

CAROUSEL_PROMPT = """These images are the first cards of a Facebook carousel ad, in order. Return STRICT JSON only, no markdown fences:
{
  "hook_text_overlay": "exact text overlaid on CARD 1. Empty string if none.",
  "visual_hook": "card 1 visual + the shared visual style across cards (product shot/lifestyle/UGC/render). 1-2 sentences.",
  "script": "card-by-card flow: [card 1] ... [card 2] ... — what each card shows and the sequence logic. Under 600 chars.",
  "emotion": "dominant emotional tone. 1-3 words.",
  "cta": "call-to-action text on any card. Empty string if none."
}"""

# ---- keys / provider ----

def env_key(name):
    if os.environ.get(name):
        return os.environ[name]
    for path in ENV_FILES:
        if not os.path.exists(path): continue
        for line in open(path, errors="ignore"):
            m = re.match(rf'\s*(?:export\s+)?{name}=["\']?([^"\'\n ]+)', line)
            if m: return m.group(1)
    return ""

def pick_provider(model):
    """Probe Gemini once; fall back to Grok (images/carousels only) if unavailable."""
    g_key = env_key("GOOGLE_API_KEY")
    x_key = env_key("XAI_API_KEY")
    if g_key:
        client = genai.Client(api_key=g_key,
                              http_options=types.HttpOptions(timeout=120_000))
        try:
            client.models.generate_content(model=model, contents="hi")
            return {"mode": "gemini", "client": client, "grok_key": x_key}
        except Exception as e:
            print(f"[WARN] Gemini unavailable: {str(e)[:100]}", file=sys.stderr)
            if not x_key:
                sys.exit("ERROR: Gemini unavailable and XAI_API_KEY not found — no usable provider "
                         "(if this is the VPN geo-block, switch the exit node or add XAI_API_KEY)")
            print("[WARN] falling back to Grok — image/carousel rows only; "
                  "VIDEO rows will be marked error:gemini_unavailable", file=sys.stderr)
            return {"mode": "grok", "client": None, "grok_key": x_key}
    if x_key:
        print("[WARN] GOOGLE_API_KEY not found — Grok fallback, image/carousel rows only; "
              "VIDEO rows will be marked error:gemini_unavailable", file=sys.stderr)
        return {"mode": "grok", "client": None, "grok_key": x_key}
    sys.exit("ERROR: neither GOOGLE_API_KEY nor XAI_API_KEY found")

# ---- model calls (sync, run in threads) ----

def _retriable(e):
    code = getattr(e, "code", None)
    if isinstance(code, int) and code in (429, 500, 502, 503, 504): return True
    if isinstance(e, httpx.HTTPStatusError):
        return e.response.status_code in (429, 500, 502, 503, 504)
    if isinstance(e, (httpx.TransportError, TimeoutError)): return True
    s = str(e)
    return any(k in s for k in ("UNAVAILABLE", "INTERNAL", "RESOURCE_EXHAUSTED",
                                "overloaded", "Deadline"))

def model_call(fn, retries=3):
    delay = 2.0
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as e:
            if attempt == retries or not _retriable(e):
                raise
            time.sleep(delay); delay *= 2

def gemini_generate(client, model, media_parts, prompt):
    resp = client.models.generate_content(
        model=model,
        contents=media_parts + [prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json", temperature=0.2),
    )
    return resp.text

def grok_generate(grok_key, images, prompt):
    """images: list of (mime, bytes). OpenAI-compatible vision call."""
    content = [{"type": "image_url",
                "image_url": {"url": f"data:{m};base64,{base64.b64encode(b).decode()}"}}
               for m, b in images]
    content.append({"type": "text", "text": prompt})
    r = httpx.post(GROK_URL,
                   headers={"Content-Type": "application/json",
                            "Authorization": f"Bearer {grok_key}"},
                   json={"model": GROK_MODEL,
                         "messages": [{"role": "user", "content": content}],
                         "temperature": 0.2},
                   timeout=120.0)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def parse_json(txt: str) -> dict:
    txt = txt.strip()
    try: return json.loads(txt)
    except Exception:
        s = txt.find("{"); depth = 0; end = -1
        for i, ch in enumerate(txt[s:], s):
            if ch == "{": depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0: end = i+1; break
        return json.loads(txt[s:end])

# ---- media helpers ----

class StaleURL(Exception): pass

async def dl(http, url):
    """Download with retry/backoff. 403/410 on signed CDN URLs = expired, no retry."""
    delay = 1.0
    for attempt in range(4):
        try:
            r = await http.get(url, timeout=60.0)
            if r.status_code in (403, 410):
                raise StaleURL(f"HTTP {r.status_code} — signed CDN URL expired; "
                               "re-run fb-ads-short-analysis for fresh URLs")
            r.raise_for_status()
            return r.content
        except StaleURL:
            raise
        except httpx.HTTPStatusError as e:
            if e.response.status_code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
        except httpx.HTTPError:
            if attempt == 3: raise
        await asyncio.sleep(delay); delay *= 2

def sniff_mime(raw: bytes) -> str:
    if raw[:8] == b"\x89PNG\r\n\x1a\n": return "image/png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP": return "image/webp"
    return "image/jpeg"

def trim_video(raw: bytes, seconds: int) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=True) as out:
        r = subprocess.run(
            ["ffmpeg","-y","-loglevel","error","-i","pipe:0",
             "-t",str(seconds),"-c","copy","-movflags","+faststart", out.name],
            input=raw, capture_output=True
        )
        if r.returncode != 0 or os.path.getsize(out.name) < 1000:
            subprocess.run(
                ["ffmpeg","-y","-loglevel","error","-i","pipe:0",
                 "-t",str(seconds),"-c:v","libx264","-preset","ultrafast",
                 "-crf","28","-c:a","aac","-b:a","96k","-movflags","+faststart", out.name],
                input=raw, capture_output=True, check=True
            )
        return open(out.name, "rb").read()

# ---- per-row analysis ----

def result_row(row, idx, kind, status, **fields):
    base = {"ad_archive_id": row["ad_archive_id"],
            **{c: "" for c in OUT_COLS},
            "analysis_status": status,
            "_t": {"idx": idx, "kind": kind}}
    base.update(fields)
    return base

def fill(data, res, keys):
    for k in keys:
        res[k] = data.get(k, "") or ""

async def analyze_video(ctx, http, row, idx, clip_seconds, kind="video"):
    if ctx["mode"] != "gemini":
        return result_row(row, idx, kind, "error:gemini_unavailable")
    t = {"idx": idx, "kind": kind}
    t0 = time.time()
    url = row.get("video_sd_url") or row.get("video_hd_url")
    raw = await dl(http, url)
    t["dl_s"] = round(time.time()-t0, 2); t["raw_kb"] = len(raw)//1024

    t1 = time.time()
    trimmed = await asyncio.to_thread(trim_video, raw, clip_seconds)
    t["trim_s"] = round(time.time()-t1, 2); t["clip_kb"] = len(trimmed)//1024

    t2 = time.time()
    txt = await asyncio.to_thread(
        model_call,
        lambda: gemini_generate(ctx["client"], ctx["model"],
                                [types.Part.from_bytes(data=trimmed, mime_type="video/mp4")],
                                VIDEO_PROMPT))
    t["gem_s"] = round(time.time()-t2, 2)
    data = parse_json(txt)
    t["total_s"] = round(time.time()-t0, 2)
    print(f"  [{idx:03}] VIDEO dl={t['dl_s']}s trim={t['trim_s']}s gem={t['gem_s']}s total={t['total_s']}s ({t['raw_kb']}→{t['clip_kb']}KB)")
    res = result_row(row, idx, kind, "ok", _t=t)
    fill(data, res, ("hook_text_overlay", "visual_hook", "script", "cta", "product_moment"))
    return res

async def analyze_image(ctx, http, row, idx, kind="image"):
    t = {"idx": idx, "kind": kind}
    t0 = time.time()
    url = row.get("image_url") or row.get("video_preview_image_url")
    raw = await dl(http, url)
    t["dl_s"] = round(time.time()-t0, 2); t["raw_kb"] = len(raw)//1024
    mime = sniff_mime(raw)

    t2 = time.time()
    if ctx["mode"] == "gemini":
        txt = await asyncio.to_thread(
            model_call,
            lambda: gemini_generate(ctx["client"], ctx["model"],
                                    [types.Part.from_bytes(data=raw, mime_type=mime)],
                                    IMAGE_PROMPT))
        status = "ok"
    else:
        txt = await asyncio.to_thread(
            model_call, lambda: grok_generate(ctx["grok_key"], [(mime, raw)], IMAGE_PROMPT))
        status = "ok:grok"
    t["gem_s"] = round(time.time()-t2, 2)
    data = parse_json(txt)
    t["total_s"] = round(time.time()-t0, 2)
    print(f"  [{idx:03}] IMAGE dl={t['dl_s']}s gem={t['gem_s']}s total={t['total_s']}s ({t['raw_kb']}KB)")
    res = result_row(row, idx, kind, status, _t=t)
    fill(data, res, ("hook_text_overlay", "visual_hook", "emotion", "cta"))
    return res

async def analyze_carousel_cards(ctx, http, row, idx, card_urls):
    t = {"idx": idx, "kind": "carousel", "cards": len(card_urls)}
    t0 = time.time()
    imgs = []
    for u in card_urls:
        raw = await dl(http, u)
        imgs.append((sniff_mime(raw), raw))
    t["dl_s"] = round(time.time()-t0, 2); t["raw_kb"] = sum(len(b) for _, b in imgs)//1024

    t2 = time.time()
    if ctx["mode"] == "gemini":
        parts = [types.Part.from_bytes(data=b, mime_type=m) for m, b in imgs]
        txt = await asyncio.to_thread(
            model_call,
            lambda: gemini_generate(ctx["client"], ctx["model"], parts, CAROUSEL_PROMPT))
        status = "ok"
    else:
        txt = await asyncio.to_thread(
            model_call, lambda: grok_generate(ctx["grok_key"], imgs, CAROUSEL_PROMPT))
        status = "ok:grok"
    t["gem_s"] = round(time.time()-t2, 2)
    data = parse_json(txt)
    t["total_s"] = round(time.time()-t0, 2)
    print(f"  [{idx:03}] CAROUSEL×{len(imgs)} dl={t['dl_s']}s gem={t['gem_s']}s total={t['total_s']}s ({t['raw_kb']}KB)")
    res = result_row(row, idx, "carousel", status, _t=t)
    fill(data, res, ("hook_text_overlay", "visual_hook", "script", "emotion", "cta"))
    return res

async def analyze_one(ctx, http, sem, row, idx, clip_seconds, cards_map):
    async with sem:
        kind = (row.get("media_type") or "").lower()
        try:
            if kind == "video" and (row.get("video_sd_url") or row.get("video_hd_url")):
                return await analyze_video(ctx, http, row, idx, clip_seconds)
            if kind == "carousel":
                cards = (cards_map.get(row["ad_archive_id"]) or [])[:3]
                if len(cards) >= 2:
                    return await analyze_carousel_cards(ctx, http, row, idx, cards)
                if row.get("video_sd_url") or row.get("video_hd_url"):
                    return await analyze_video(ctx, http, row, idx, clip_seconds, kind="carousel")
                if row.get("image_url") or row.get("video_preview_image_url"):
                    return await analyze_image(ctx, http, row, idx, kind="carousel")
                return result_row(row, idx, "carousel", "skip:no_media")
            if kind == "image" and (row.get("image_url") or row.get("video_preview_image_url")):
                return await analyze_image(ctx, http, row, idx)
            return result_row(row, idx, kind or "unknown", f"skip:{kind or 'unknown'}")
        except StaleURL as e:
            print(f"  [{idx:03}] STALE URL ({kind}): {e}", file=sys.stderr)
            return result_row(row, idx, kind, "stale_url", _t={"idx": idx, "kind": kind, "error": str(e)})
        except Exception as e:
            print(f"  [{idx:03}] ERROR ({kind}): {str(e)[:160]}", file=sys.stderr)
            return result_row(row, idx, kind, f"error:{type(e).__name__}",
                              _t={"idx": idx, "kind": kind, "error": str(e)[:500]})

async def run(ctx, rows, concurrency, clip_seconds, cards_map, jsonl_f):
    sem = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    async with httpx.AsyncClient(follow_redirects=True) as http:
        async def one(row, idx):
            res = await analyze_one(ctx, http, sem, row, idx, clip_seconds, cards_map)
            async with lock:
                jsonl_f.write(json.dumps(res, ensure_ascii=False) + "\n")
                jsonl_f.flush()
            return res
        return await asyncio.gather(*(one(r, i+1) for i, r in enumerate(rows)))

# ---- sidecar cards ----

def find_full_json(input_csv, explicit):
    if explicit:
        return explicit if os.path.exists(explicit) else ""
    p = Path(input_csv)
    for suf in ("_ads.csv", "_by_impressions.csv", "_inactive.csv"):
        if p.name.endswith(suf):
            cand = p.with_name(p.name[:-len(suf)] + "_ads_full.json")
            if cand.exists(): return str(cand)
    return ""

def load_cards_map(full_json_path):
    """ad_archive_id -> [card image urls] from the short-analysis raw dump."""
    out = {}
    try:
        ads = json.load(open(full_json_path))
    except Exception as e:
        print(f"[WARN] could not read sidecar {full_json_path}: {e}", file=sys.stderr)
        return out
    for a in ads:
        cards = (a.get("snapshot") or {}).get("cards") or []
        urls = []
        for c in cards:
            if not isinstance(c, dict): continue
            u = c.get("original_image_url") or c.get("resized_image_url")
            if u: urls.append(u)
        if urls:
            out[a.get("ad_archive_id") or ""] = urls
    return out

# ---- main ----

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-csv", required=True,
                    help="CSV from fb-ads-short-analysis (catalog or *_by_impressions.csv)")
    ap.add_argument("--out-csv", required=True)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=None)
    ap.add_argument("--top", type=int, default=0,
                    help="Analyze only the N best rows by impression_rank (ranked rows first, "
                         "then CSV order). Applied before --start/--end.")
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--clip-seconds", type=int, default=10)
    ap.add_argument("--media", choices=["all","video","image","carousel"], default="all",
                    help="which creative types to analyze (default: all)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--full-json", default="",
                    help="Path to <prefix>_ads_full.json for carousel cards "
                         "(auto-detected next to the input CSV)")
    ap.add_argument("--env-file", default="",
                    help="explicit .env file with GOOGLE_API_KEY / XAI_API_KEY")
    ap.add_argument("--resume", action="store_true",
                    help="Skip rows already ok in <out-csv>.jsonl; re-run errors/stale/skips")
    args = ap.parse_args()
    if args.env_file:
        ENV_FILES.append(os.path.expanduser(args.env_file))

    all_rows = list(csv.DictReader(open(args.input_csv)))
    def keep(r):
        mt = (r.get("media_type") or "").lower()
        if args.media not in ("all", mt): return False
        if mt == "video":    return bool(r.get("video_sd_url") or r.get("video_hd_url"))
        if mt == "image":    return bool(r.get("image_url") or r.get("video_preview_image_url"))
        if mt == "carousel": return bool(r.get("image_url") or r.get("video_preview_image_url")
                                         or r.get("video_sd_url") or r.get("video_hd_url"))
        return False
    filtered = [r for r in all_rows if keep(r)]
    kept_ids = {id(r) for r in filtered}
    not_kept = Counter((r.get("media_type") or "unknown") for r in all_rows
                       if id(r) not in kept_ids)

    if args.top:
        def rank_key(r):
            try: return (0, int(r.get("impression_rank") or ""))
            except ValueError: return (1, 0)
        filtered = sorted(filtered, key=rank_key)[:args.top]

    sliced = filtered[args.start:args.end] if args.end else filtered[args.start:]

    # resume: skip rows already ok in the jsonl
    jsonl_path = args.out_csv + ".jsonl"
    done = {}
    if args.resume and os.path.exists(jsonl_path):
        for line in open(jsonl_path):
            try: d = json.loads(line)
            except Exception: continue
            if str(d.get("analysis_status", "")).startswith("ok"):
                done[d["ad_archive_id"]] = d
        before = len(sliced)
        sliced = [r for r in sliced if r["ad_archive_id"] not in done]
        print(f"Resume: {len(done)} rows already ok in {os.path.basename(jsonl_path)}, "
              f"{before - len(sliced)} of them in scope, {len(sliced)} to run")

    kinds = Counter((r.get("media_type") or "").lower() for r in sliced)
    print(f"Input: {len(all_rows)} rows | analyzing: {len(sliced)} "
          f"(video={kinds.get('video',0)}, image={kinds.get('image',0)}, carousel={kinds.get('carousel',0)})")
    if not_kept:
        print(f"Not eligible (no media url / filtered by --media): "
              + ", ".join(f"{k}={n}" for k, n in not_kept.most_common()))

    cards_map = {}
    if kinds.get("carousel"):
        fj = find_full_json(args.input_csv, args.full_json)
        if fj:
            cards_map = load_cards_map(fj)
            print(f"Carousel cards sidecar: {fj} ({len(cards_map)} ads with cards)")
        else:
            print("Carousel cards sidecar not found — carousels fall back to first card from the CSV")

    if not sliced and not done:
        print("Nothing to analyze."); return

    new_results = []
    if sliced:
        ctx = pick_provider(args.model)
        ctx["model"] = args.model
        print(f"Model: {args.model if ctx['mode']=='gemini' else GROK_MODEL + ' (fallback)'} "
              f"| concurrency: {args.concurrency} | clip: {args.clip_seconds}s")
        t_all = time.time()
        with open(jsonl_path, "a" if args.resume else "w", encoding="utf-8") as jf:
            new_results = asyncio.run(run(ctx, sliced, args.concurrency, args.clip_seconds,
                                          cards_map, jf))
        elapsed = time.time() - t_all
    else:
        elapsed = 0.0
        print("All rows already ok — rewriting CSV from jsonl.")

    results = list(done.values()) + list(new_results)

    by_id = {r["ad_archive_id"]: r for r in results}
    fields = list(all_rows[0].keys())
    for col in OUT_COLS:
        if col not in fields: fields.append(col)
    for r in all_rows:
        a = by_id.get(r["ad_archive_id"])
        for col in OUT_COLS:
            r[col] = a[col] if a else r.get(col, "")
    with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(all_rows)

    ts = [r["_t"] for r in new_results if "total_s" in r.get("_t", {})]
    statuses = Counter(r["analysis_status"] for r in results)
    print(f"\n=== TIMING ===")
    if sliced:
        print(f"Wall time: {elapsed:.1f}s | per-creative parallel: {elapsed/max(len(sliced),1):.2f}s")
    for label, kind in (("VIDEO", "video"), ("IMAGE", "image"), ("CAROUSEL", "carousel")):
        kts = [t for t in ts if t.get("kind") == kind]
        if not kts: continue
        avg = lambda k: round(sum(x.get(k, 0) for x in kts)/len(kts), 2)
        extra = f" trim={avg('trim_s')}s" if kind == "video" else ""
        print(f"{label} avg ({len(kts)}): dl={avg('dl_s')}s{extra} gem={avg('gem_s')}s total={avg('total_s')}s")
    print("Statuses: " + ", ".join(f"{s}={n}" for s, n in statuses.most_common()))
    stale = statuses.get("stale_url", 0)
    if stale:
        print(f"[WARN] {stale} rows had expired CDN URLs — re-run fb-ads-short-analysis "
              "for a fresh CSV, then re-run this with --resume", file=sys.stderr)
    print(f"\nCSV:   {args.out_csv}")
    print(f"JSONL: {jsonl_path}")

if __name__ == "__main__":
    main()
