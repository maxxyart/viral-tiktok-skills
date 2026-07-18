#!/usr/bin/env python3
"""FAST mode: extract a structured card from every cover image with a cheap
vision model. Clustering is NOT done here — Claude clusters the cards itself.

Usage:
  python3 ocr_covers.py META.json [--out cards.json] [--provider auto|gemini|grok]
                        [--concurrency 8]

Providers:
  gemini — gemini-3.1-flash-lite (override: GEMINI_MODEL env). Needs GOOGLE_API_KEY.
  grok   — grok non-reasoning (override: XAI_MODEL env). Needs XAI_API_KEY.
  auto   — probe Gemini once; on geo-block/error fall back to Grok.

Output cards.json: index-aligned array of
  {index, hook_text, has_text, visual_format, embedded_context,
   has_creator_face, ocr_failed}
Failed covers get ocr_failed=true → the caller should Read those images manually.
"""
import argparse, base64, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

ENV_FILES = [os.path.expanduser("~/.zshenv"), os.path.expanduser("~/.zshrc")]
if os.environ.get("TIKTOK_SKILLS_ROOT"):
    ENV_FILES.append(os.path.join(os.environ["TIKTOK_SKILLS_ROOT"], ".env"))
ENV_FILES.append(os.path.join(os.getcwd(), ".env"))

def env_key(name, required=True):
    if os.environ.get(name):
        return os.environ[name]
    for path in ENV_FILES:
        if not os.path.exists(path):
            continue
        for line in open(path, encoding="utf-8", errors="ignore"):
            m = re.match(rf'^(?:export\s+)?{name}\s*=\s*"?([^"\s#]+)"?', line.strip())
            if m:
                return m.group(1)
    if required:
        sys.exit(f"ERROR: {name} not found in env or {ENV_FILES}")
    return None

CARD_PROMPT = """You analyze a short-video cover/thumbnail image for marketing research.

Return strictly one JSON object:
{
  "hook_text": "<ALL text visible on the image VERBATIM — preserve original language, typos, casing, emoji; join lines with ' | '; empty string if none>",
  "has_text": <true/false>,
  "visual_format": "<one of: talking_head | face_plus_screenshot | designed_promo | meme_reaction | pov_lifestyle | ui_screen_only | diagram_scheme | comparison_grid | other>",
  "embedded_context": "<if the cover CONTAINS an embedded screenshot/photo/video (a tweet, article, app UI, someone else's viral video, a celebrity photo) — describe in one short sentence WHAT it is and whose; empty string if none>",
  "has_creator_face": <true if the creator's own face/figure is visible>
}

Rules:
- hook_text must be verbatim: do NOT fix typos, do NOT translate, do NOT reorder lines.
- Text INSIDE an embedded screenshot is NOT the hook — put its essence into embedded_context instead (still include big overlay captions in hook_text).
- visual_format describes the COMPOSITION, not the topic.
- Return ONLY the JSON object."""

def call_gemini(b64, key, model):
    body = json.dumps({
        "contents": [{"role": "user", "parts": [
            {"text": CARD_PROMPT},
            {"inlineData": {"mimeType": "image/jpeg", "data": b64}}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }).encode()
    req = Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                  data=body, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=120) as r:
        resp = json.loads(r.read().decode())
    return resp["candidates"][0]["content"]["parts"][0]["text"]

def call_grok(b64, key, model):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text", "text": CARD_PROMPT}]}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }).encode()
    req = Request("https://api.x.ai/v1/chat/completions", data=body,
                  headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urlopen(req, timeout=120) as r:
        resp = json.loads(r.read().decode())
    return resp["choices"][0]["message"]["content"]

def pick_provider(requested):
    gem_model = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
    grok_model = os.environ.get("XAI_MODEL", "grok-4.20-0309-non-reasoning")
    if requested in ("gemini", "auto"):
        gkey = env_key("GOOGLE_API_KEY", required=(requested == "gemini"))
        if gkey:
            try:  # 1x1 white jpeg probe
                probe = base64.b64encode(base64.b64decode(
                    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAj/2wBDAQj/wAARCAABAAEDASIAAhEBAxEB/8QAFA"
                    "ABAAAAAAAAAAAAAAAAAAAACv/EABQQAQAAAAAAAAAAAAAAAAAAAAD/xAAUAQEAAAAAAAAAAAAA"
                    "AAAAAAAA/8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAwDAQACEQMRAD8AfwD/2Q==")).decode()
                call_gemini(probe, gkey, gem_model)
                return "gemini", gkey, gem_model
            except Exception as e:
                msg = str(e)[:120]
                if requested == "gemini":
                    sys.exit(f"ERROR: Gemini unavailable ({msg})")
                print(f"  Gemini unavailable ({msg}) → falling back to Grok", file=sys.stderr)
    xkey = env_key("XAI_API_KEY")
    return "grok", xkey, grok_model

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("meta")
    ap.add_argument("--out")
    ap.add_argument("--provider", choices=["auto", "gemini", "grok"], default="auto")
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args()

    meta = json.load(open(args.meta, encoding="utf-8"))
    videos = meta["videos"]
    provider, key, model = pick_provider(args.provider)
    print(f"provider: {provider} ({model})", file=sys.stderr)
    call = call_gemini if provider == "gemini" else call_grok

    done = [0]
    def one(iv):
        i, v = iv
        card = {"index": i, "hook_text": "", "has_text": False, "visual_format": "",
                "embedded_context": "", "has_creator_face": None, "ocr_failed": False}
        if not v.get("coverFile") or not os.path.exists(v["coverFile"]):
            card["ocr_failed"] = True
            return card
        b64 = base64.b64encode(open(v["coverFile"], "rb").read()).decode()
        for att in range(3):
            try:
                parsed = json.loads(call(b64, key, model))
                card.update({k: parsed.get(k, card[k]) for k in
                             ("hook_text", "has_text", "visual_format",
                              "embedded_context", "has_creator_face")})
                break
            except Exception as e:
                if att == 2:
                    card["ocr_failed"] = True
                    print(f"  fail #{i}: {str(e)[:100]}", file=sys.stderr)
                else:
                    time.sleep(2 * (att + 1))
        done[0] += 1
        print(f"  [{done[0]}/{len(videos)}]", file=sys.stderr)
        return card

    t0 = time.time()
    with ThreadPoolExecutor(args.concurrency) as ex:
        cards = sorted(ex.map(one, enumerate(videos)), key=lambda c: c["index"])
    failed = [c["index"] for c in cards if c["ocr_failed"]]
    print(f"done in {time.time()-t0:.1f}s | failed: {failed or 'none'}", file=sys.stderr)

    text = json.dumps(cards, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"cards written to {args.out}", file=sys.stderr)
    else:
        print(text)

if __name__ == "__main__":
    main()
