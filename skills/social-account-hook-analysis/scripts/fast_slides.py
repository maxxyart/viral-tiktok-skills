#!/usr/bin/env python3
"""Every carousel slide into one table. Main path: Haiku subagents read text and picture of
each slide (read -> table), Apple Vision OCR is the free draft and cross-check (ocr), the
main session reads slices of the table (show). Cheaper visual-only variant: Vision text +
Haiku over contact sheets (sheets -> merge -> fix).

  fast_slides.py read WORK_DIR [--per-agent 40] [--hint] [--out-dir DIR]
      One prompt per Haiku subagent (template references/haiku_slide_prompt.md) over the
      slides in slides_ocr.jsonl: WORK_DIR/read/prompt-K.md -> read/slides-part-K.jsonl.
      --hint adds the Vision draft under each slide (measured: no accuracy gain).
  fast_slides.py table WORK_DIR [--read-dir DIR] [--min-agree 0.6] [--min-words 5] [--force]
      slides_table.jsonl/.csv (a row per slide: post, post_id, url, metric, slide_no, text,
      words, role, people, background, art_style, text_style, product_mention, unreadable,
      visual, source, ocr_text, ocr_agree, check), posts_table.csv (a row per post) and
      carousels/NN/slides.json; read/needs_sonnet.json lists slides for a Sonnet re-read.
      Rows in read/fix-*.jsonl (same keys, written by a Sonnet subagent) override Haiku.
  fast_slides.py show WORK_DIR [--posts 3,7 | --hits | --top N] [--fields ...]
      Compact slices of the table for the main session (one line per slide).
  fast_slides.py ocr WORK_DIR [--indexes 3,7 | --top N] [--jobs 8] [--lang en-US] [--force]
      Downloads the missing slides of the chosen carousels (all carousels by default) into
      carousels/NN/slideK.jpg (no comments, unlike fetch_slides.py), OCRs them and writes
      WORK_DIR/slides_ocr.jsonl plus carousels/NN/slides.json with "source": "ocr".
      A slides.json that Claude or a subagent wrote (any slide without "source": "ocr") is
      never overwritten unless --force.
  fast_slides.py ocr --dir DIR --out FILE.jsonl [--jobs 8] [--lang en-US]
      Any folder laid out as DIR/<post>/<images>: OCR only, nothing else is written.
  fast_slides.py sheets WORK_DIR [--cols 7] [--tile 200] [--max-mpx 1.6] [--per-agent 6]
      Contact sheets for the visual pass: every slide in slides_ocr.jsonl as a tile labelled
      "post.slide" (label colour flips per post), sheets kept under the Read tool's
      1568 px edge. Writes WORK_DIR/sheets/sheet_NNN.jpg, sheets/index.json, and one
      sheets/prompt-K.md per Haiku subagent (template: references/haiku_visual_prompt.md).
  fast_slides.py merge WORK_DIR
      Reads WORK_DIR/sheets/visual-part-*.jsonl written by the Haiku subagents, puts the
      visual fields into carousels/NN/slides.json, writes WORK_DIR/slides_fast.jsonl and
      WORK_DIR/needs_read.json: the slides for the old path (a model reads the slide),
      where OCR lost part of the headline Haiku sees (word pairs < 0.8), returned
      garbage, or found no text on a slide with text.
  fast_slides.py fix WORK_DIR FILE.jsonl
      Writes the model's readings ({"post", "slide", "text"[, "visual"]} per line) over the
      OCR text in slides.json ("source": "model") and slides_fast.jsonl.

slides_ocr.jsonl row: {"index", "id", "slide", "file", "text", "aside", "noise", "words",
"conf", "flags", "fixes"}. "index" is the meta.json index (null in --dir mode); "text" is
the slide text in reading order (XY-cut, so two columns stay apart), line breaks as \\n;
"aside" holds small isolated lines (props and labels inside the picture, watermarks) joined
with " / "; "noise" the lines Vision itself doubts (tally marks, scribbles); "fixes" the
OCR slips undone, [[read, fixed], ...]: l/1/| for the pronoun I, missing spaces and
apostrophes, look-alike letters (only spell-checker guesses of that shape, so author typos
stay). flags: "empty" (no text), "low_conf" (mean confidence < 0.5), "garbage" (> 40% of
the words unknown to the spell checker), "unreadable" (image failed to open).
"""
import argparse, glob, json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
SWIFT_SRC = os.path.join(HERE, "ocr_vision.swift")
OCR_BIN = os.path.expanduser("~/.cache/social-account-hook-analysis/ocr_vision")
IMG_RE = re.compile(r"\.(jpe?g|png|webp|heic)$", re.I)


# ---------- OCR binary ----------

def ocr_binary():
    """Compile ocr_vision.swift on first use (or when the source changed)."""
    if os.path.exists(OCR_BIN) and os.path.getmtime(OCR_BIN) >= os.path.getmtime(SWIFT_SRC):
        return OCR_BIN
    os.makedirs(os.path.dirname(OCR_BIN), exist_ok=True)
    res = subprocess.run(["swiftc", "-O", SWIFT_SRC, "-o", OCR_BIN], capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit("ERROR: swiftc failed (needs macOS with Xcode command line tools); read the slides "
                 "with a model instead.\n" + res.stderr[-2000:])
    return OCR_BIN


def run_ocr(files, jobs, lang):
    """OCR files in `jobs` parallel processes; returns {file: raw swift record}."""
    binary = ocr_binary()
    chunks = [files[i::jobs] for i in range(jobs) if files[i::jobs]]

    def run(chunk):
        res = subprocess.run([binary, "--lang", lang, *chunk], capture_output=True, text=True)
        return [json.loads(l) for l in res.stdout.splitlines() if l.strip()]

    with ThreadPoolExecutor(max(1, len(chunks))) as ex:
        return {r["file"]: r for part in ex.map(run, chunks) for r in part}


# ---------- text layout ----------

def xy_order(items, W, H):
    """Reading order by recursive XY-cut: split at the widest empty band, columns or rows,
    whichever gap is wider in pixels. Keeps two-column layouts (he/she bubbles, comparison
    slides) column by column instead of interleaving their lines."""
    if len(items) <= 1:
        return items

    def split(axis):
        lo, size, scale = ("x", "w", W) if axis == "x" else ("y", "h", H)
        iv = sorted(items, key=lambda i: i[lo])
        best, at, end = 0, None, iv[0][lo] + iv[0][size]
        for k in range(1, len(iv)):
            gap = (iv[k][lo] - end) * scale
            if gap > best:
                best, at = gap, k
            end = max(end, iv[k][lo] + iv[k][size])
        return best, (iv[:at], iv[at:]) if at else None

    gx, parts_x = split("x")
    gy, parts_y = split("y")
    if parts_x and gx >= 0.02 * W and gx > gy:
        parts = parts_x
    elif parts_y:
        parts = parts_y
    else:
        return sorted(items, key=lambda i: (i["y"], i["x"]))
    return xy_order(parts[0], W, H) + xy_order(parts[1], W, H)


def dedupe(lines):
    """Vision sometimes returns one heading twice ('2.DESIRE IS NOT' + 'DESIRE IS NOT' in the
    same box): drop a line whose text sits inside an overlapping line's text."""
    def key(l):
        return re.sub(r"[^a-z0-9]", "", l["t"].lower())

    out = []
    for l in lines:
        dup = False
        for o in lines:
            if o is l or not key(l) or key(l) not in key(o) or (key(l) == key(o) and lines.index(o) > lines.index(l)):
                continue
            iw = min(l["x"] + l["w"], o["x"] + o["w"]) - max(l["x"], o["x"])
            ih = min(l["y"] + l["h"], o["y"] + o["h"]) - max(l["y"], o["y"])
            if iw > 0 and ih > 0 and iw * ih > 0.5 * l["w"] * l["h"]:
                dup = True
                break
        if not dup:
            out.append(l)
    return out


def split_lines(lines):
    """main / aside / noise. noise = Vision confidence < 0.6 (tally marks, scribbles).
    aside = small (< 0.6 of the main text height) lines of <= 3 words that do not continue
    a paragraph: labels and props inside the picture, watermarks."""
    lines = dedupe(lines)
    noise = [l for l in lines if l["c"] < 0.6]
    rest = [l for l in lines if l["c"] >= 0.6]
    if not rest:
        return [], [], noise
    hs = sorted(h for l in rest for h in [l["h"]] * max(1, len(l["t"].split())))
    med = hs[len(hs) // 2]  # word-weighted: the height most of the text is set in
    small = [l for l in rest if l["h"] < 0.6 * med and len(l["t"].split()) <= 3]

    def in_paragraph(l):
        for o in rest:
            if o is l or o in small:
                continue
            gap = max(o["y"] - (l["y"] + l["h"]), l["y"] - (o["y"] + o["h"]))
            overlap = min(l["x"] + l["w"], o["x"] + o["w"]) - max(l["x"], o["x"])
            if gap < 1.2 * o["h"] and overlap > 0:
                return True
        return False

    aside = [l for l in small if not in_paragraph(l)]
    return [l for l in rest if l not in aside], aside, noise


# ---------- OCR fixes ----------

I_VERBS = {"am", "was", "have", "had", "will", "would", "can", "could", "do", "did", "don't",
           "didn't", "love", "need", "want", "know", "knew", "think", "feel", "felt", "just", "never",
           "always", "still", "really", "said", "say", "told", "see", "saw", "wish", "hope", "mean",
           "miss", "guess", "swear", "promise", "get", "got", "went", "made", "like", "should",
           "shouldn't", "can't", "won't", "wasn't", "haven't", "realized", "realised", "realize",
           "used", "thought", "tried", "try", "also", "only", "even", "finally", "cannot", "care",
           "hate", "ask", "asked", "explain", "wake", "met", "found", "truly", "choose", "chose",
           "remember", "forgot", "believe", "understand", "appreciate", "deserve", "lost", "let"}
I_NOT_AFTER = {"number", "no", "no.", "#", "top", "day", "part", "step", "chapter", "page", "level",
               "rule", "tip", "reason", "sign", "of", "out", "x", "to", "only", "just", "the", "a",
               "plus", "minus", "and", "or", "than", "every", "per", "by", "at", "under", "over"}


def fix_pronoun_i(text, listicle):
    """'l' / '|' / '1' read for the pronoun I. Vision does this a lot on serif and handwriting-like
    fonts (@infinite.quotes: l've, l'll, l want, | love, 1 know). A line-start 1 stays a number
    when the carousel numbers its points (listicle)."""
    text = re.sub(r"(?<![\w'’])[1l|](?=['’](m|ve|ll|d)\b)", "I", text)
    out = []
    for line in text.split("\n"):
        toks = line.split(" ")
        for k, tok in enumerate(toks):
            m = re.fullmatch(r"([\"'\u201c\u2018(*]*)([1l|])([,.!?\u2026:;\"'\u201d\u2019)]*)", tok)
            if not m:
                continue
            t = m.group(2)
            prev = toks[k - 1].lower() if k else ""
            nxt = toks[k + 1] if k + 1 < len(toks) else ""
            nl = nxt.lower().strip(",.!?;:")
            is_i = False
            if k == 0 and listicle and not m.group(1) and t in ("l", "|") and nxt[:1].isupper():
                toks[k] = "1" + m.group(3)  # 'l He Makes You Think' on a numbered carousel
                continue
            if t in ("l", "|") and (prev or nxt):
                is_i = True  # a lone l or bar next to words is never an English word
            elif t == "1":
                if k == 0 and not m.group(1):  # "1." / "1)" opening a line is a point number
                    is_i = not m.group(3) and nl in I_VERBS and not listicle and \
                        not (nxt[:1].isupper() and nxt[1:2].islower())
                else:
                    is_i = prev not in I_NOT_AFTER and not re.search(r"\d", prev) and \
                        bool(nl in I_VERBS or (not nxt and re.fullmatch(r"[a-z,]+", prev)))
            if is_i:
                toks[k] = m.group(1) + "I" + m.group(3)
        out.append(" ".join(toks))
    return "\n".join(out)


HOMOGLYPHS = str.maketrans("АВЕКМНОРСТХаеорсухк", "ABEKMHOPCTXaeopcyxk")


def fix_homoglyphs(text):
    """Vision with en-US sometimes returns Cyrillic look-alikes inside Latin words ('Нe',
    'BACKРАСК'); words that mix the two scripts are turned back into Latin."""
    return re.sub(r"\S+", lambda m: m.group(0).translate(HOMOGLYPHS)
                  if re.search(r"[A-Za-z]", m.group(0)) and re.search(r"[\u0400-\u04ff]", m.group(0))
                  else m.group(0), text)


CONFUSABLE = {("t", "f"): 1, ("f", "t"): 1, ("l", "i"): 1, ("i", "l"): 1, ("c", "e"): 2,
              ("e", "c"): 2, ("u", "o"): 2, ("o", "u"): 2, ("0", "o"): 1, ("5", "s"): 2}
CORE_RE = re.compile(r"^([^\w']*)([\w'’]+?)([^\w']*)$")


def ocr_shaped(word, guesses, spell):
    """The spell checker's guess that an OCR slip explains: a missing space ('beforethe'), a
    missing apostrophe ('doesnt'), or look-alike letters ('peacetul', 'gooty'). Author typos
    ('awkvarable', 'celabrate') have no such guess and stay as written."""
    w = word.lower()
    if any(g.lower() == w for g in guesses):
        return None  # only the case was off: 'jesus' -> 'Jesus'; keep the author's casing
    if w[:1] == "i" and len(w) > 3 and spell.get(w[1:], (False,))[0]:
        return "I " + w[1:]  # 'Itold', 'Ifell': the checker would offer 'It old', 'If ell'
    best, best_cost = None, 9
    for g in guesses:
        gl = g.lower()
        if " " in gl and gl.replace(" ", "") == w and gl.count(" ") == 1:
            return g
        if "'" in gl.strip("'") and gl.replace("'", "") == w:
            return g
        if len(gl) == len(w) >= 5:  # shorter ones are mostly labels in the picture: THU, TUE, KCAL
            diff = [(a, b) for a, b in zip(w, gl) if a != b]
            if 0 < len(diff) <= 2 and all(d in CONFUSABLE for d in diff):
                cost = sum(CONFUSABLE[d] for d in diff)
                if cost < best_cost:
                    best, best_cost = g, cost
    return best


def match_case(src, dst):
    if src.isupper() and len(src) > 1:
        return dst.upper()
    if src[:1].isupper():
        return dst[:1].upper() + dst[1:]
    return dst


def spell_check(words, lang):
    """{word: (ok, guesses)} from the macOS spell checker (one process for all words)."""
    if not words or not lang.startswith(("en", "auto")):
        return {}
    res = subprocess.run([ocr_binary(), "--spell", "--lang", "en"], input="\n".join(words) + "\n",
                         capture_output=True, text=True)
    out = {}
    for l in res.stdout.splitlines():
        r = json.loads(l)
        out[r["w"]] = (r["ok"], r["g"])
    return out


def cores(text):
    for tok in text.split():
        m = CORE_RE.match(tok.replace("’", "'"))
        if m and re.fullmatch(r"[A-Za-z']{2,}", m.group(2)):
            yield tok, m


def apply_fixes(text, spell):
    fixes, out = [], []
    for line in text.split("\n"):
        toks = line.split(" ")
        for k, tok in enumerate(toks):
            g = re.fullmatch(r"(\d{1,2}[.)]?)([A-Za-z\"'\u201c\u2018][\w'\u2019\"\u201d.,!?]*)", tok)
            if g and len(re.sub(r"[^A-Za-z]", "", g.group(2))) >= 3 and g.group(2).lower() not in UNITS:
                toks[k] = g.group(1) + " " + g.group(2)  # '3DON'T', '2.DESIRE': the point number glued on
                fixes.append([tok, toks[k]])
                continue
            for _, m in cores(tok):
                ok, guesses = spell.get(m.group(2).lower(), (True, []))
                g = None if ok else ocr_shaped(m.group(2), guesses, spell)
                if g:
                    toks[k] = m.group(1) + match_case(m.group(2), g) + m.group(3)
                    fixes.append([tok, toks[k]])
        out.append(" ".join(toks))
    return "\n".join(out), fixes


def junk_line(line, spell):
    """Tally marks and scribbles read as letters ('HH #H', 'HHt'): every token a short
    non-word. Digits, real words and the one-letter words a / I / O keep a line."""
    if not line.split() or len(line.split()) > 5 or line.rstrip().endswith("-"):
        return False  # 'REQU-' is half of a hyphenated word
    toks = [re.sub(r"[^\w']", "", t) for t in line.split()]
    for t in toks:
        if not t:
            continue
        if re.search(r"\d", t) or len(t) > 4 or t.lower() in ("a", "i", "o"):
            return False
        if len(t) > 1 and spell.get(t.lower(), (True, []))[0]:
            return False
    return True


def unknown_share(text, spell):
    words = [m.group(2).lower() for _, m in cores(text)]
    if len(words) < 3:
        return 0
    return sum(not spell.get(w, (True, []))[0] for w in words) / len(words)


def lead_number(lines):
    """A big point numeral overlaps the heading lines, so XY-cut can put it between them
    ('DON'T EXPOSE HER | 1 | PRIVATE WORDS'); a line that is only a number leads the slide."""
    for k, l in enumerate(lines):
        if k and re.fullmatch(r"\d{1,2}[.)]?", l.strip()):
            return [l] + lines[:k] + lines[k + 1:]
    return lines


UNITS = {"min", "mins", "hrs", "sec", "secs", "kcal", "lbs", "mph", "kms", "yrs", "days", "sets", "reps"}


def token_changes(before, after):
    a, b = before.split(), after.split()
    return [[x, y] for x, y in zip(a, b) if x != y] if len(a) == len(b) else []


def build_records(raws, groups, lang):
    """raws: {file: swift record}; groups: [[file, ...] per carousel] -> {file: record}."""
    en = lang.startswith(("en", "auto"))
    pre = {}
    for files in groups:
        texts = {}
        for f in files:
            raw = raws.get(f)
            if not raw or raw.get("error"):
                continue
            main, aside, noise = split_lines(raw.get("lines") or [])
            W, H = raw.get("w") or 1080, raw.get("h") or 1920
            texts[f] = (lead_number([l["t"] for l in xy_order(main, W, H)]), [l["t"] for l in xy_order(aside, W, H)],
                        [l["t"] for l in noise], [l["c"] for l in raw.get("lines") or []])
        firsts = [t[0][0] for t in texts.values() if t[0]]
        listicle = sum(bool(re.match(r"\d{1,2}\b", s)) for s in firsts) >= 2
        if listicle and not any(re.match(r"1\b", s) for s in firsts) and any(re.match(r"2\b", s) for s in firsts):
            for f, t in texts.items():  # point 1 read as I / l / | ('I He Makes You Think')
                if t[0] and re.match(r"[Il|] \S", t[0][0]):
                    t[0][0] = "1" + t[0][0][1:]
                    break
        for f, (main, aside, noise, confs) in texts.items():
            main, aside = "\n".join(main), " / ".join(aside)
            if en:
                main, aside = (fix_pronoun_i(fix_homoglyphs(t), listicle) for t in (main, aside))
            pre[f] = (main, aside, noise, confs, token_changes("\n".join(texts[f][0]), main)
                      + token_changes(" / ".join(texts[f][1]), aside))
    vocab = {m.group(2).lower() for t in pre.values() for s in t[:2] for _, m in cores(s)}
    vocab |= {w.lower() for t in pre.values() for line in t[0].split("\n") if len(line.split()) <= 5
              for w in re.findall(r"[A-Za-z]{2,4}", line)}  # for junk_line
    vocab = sorted(vocab | {w[1:] for w in vocab if w[:1] == "i" and len(w) > 3})  # 'Ifell' -> 'fell'?
    spell = spell_check(vocab, lang)
    recs = {}
    for f in (f for files in groups for f in files):
        if f not in pre:
            recs[f] = {"text": "", "aside": "", "noise": "", "words": 0, "conf": None, "flags": ["unreadable"],
                       "fixes": []}
            continue
        main, aside, noise, confs, fx0 = pre[f]
        text, fx1 = apply_fixes(main, spell)
        noise = noise + [l for l in text.split("\n") if junk_line(l, spell)]
        text = "\n".join(l for l in text.split("\n") if not junk_line(l, spell))
        aside, fx2 = apply_fixes(aside, spell)
        flags = []
        if not text.split():
            flags.append("empty")
        if confs and sum(confs) / len(confs) < 0.5:
            flags.append("low_conf")
        if unknown_share(text, spell) > 0.4:
            flags.append("garbage")
        recs[f] = {"text": text, "aside": aside, "noise": " / ".join(noise), "words": len(text.split()),
                   "conf": round(sum(confs) / len(confs), 2) if confs else None, "flags": flags,
                   "fixes": fx0 + fx1 + fx2}
    return recs


# ---------- slide download (WORK_DIR mode) ----------

def slide_files(cdir):
    return sorted((os.path.join(cdir, f) for f in os.listdir(cdir) if re.match(r"slide\d+\.jpg$", f)),
                  key=lambda p: int(re.search(r"(\d+)\.jpg$", p).group(1))) if os.path.isdir(cdir) else []


def download_slides(work_dir, meta, indexes, env_files):
    """carousels/NN/slideK.jpg for every chosen carousel; refresh expired TikTok URLs once."""
    from fetch_covers import ENV_FILES, env_key
    from fetch_slides import download, fresh_urls
    ENV_FILES[:] = env_files
    path = os.path.join(work_dir, "slide_urls.json")
    urls = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    videos = meta["videos"]

    def jobs_for(i, us):
        cdir = os.path.join(work_dir, "carousels", f"{i:02d}")
        os.makedirs(cdir, exist_ok=True)
        return [(i, u, os.path.join(cdir, f"slide{k}.jpg")) for k, u in enumerate(us, 1)
                if not (os.path.exists(os.path.join(cdir, f"slide{k}.jpg"))
                        and os.path.getsize(os.path.join(cdir, f"slide{k}.jpg")) > 0)]

    todo = [j for i in indexes for j in jobs_for(i, urls.get(videos[i]["id"]) or [])]
    with ThreadPoolExecutor(16) as ex:
        ok = list(ex.map(lambda j: download(j[1], j[2]), todo))
    failed = sorted({j[0] for j, good in zip(todo, ok) if not good})
    no_urls = [i for i in indexes if not urls.get(videos[i]["id"])
               and not slide_files(os.path.join(work_dir, "carousels", f"{i:02d}"))]
    retry = sorted(set(failed) | set(no_urls)) if meta.get("platform", "tiktok") == "tiktok" else []
    if retry:
        key = env_key("SCRAPE_CREATORS_API_KEY")
        for i in retry:  # signed URLs expire; one /v2/tiktok/video call per post
            try:
                fresh = fresh_urls(videos[i]["link"], key)
            except Exception as e:
                print(f"  {i:02d}: slide refresh failed: {str(e)[:80]}", file=sys.stderr)
                continue
            for _, u, dst in jobs_for(i, fresh):
                download(u, dst)
    return len(todo), retry


# ---------- subcommands ----------

def cmd_ocr(a):
    t0 = time.time()
    if a.dir:
        posts = sorted(d for d in os.listdir(a.dir) if os.path.isdir(os.path.join(a.dir, d)))
        items = []
        for p in posts:
            fs = sorted((f for f in os.listdir(os.path.join(a.dir, p)) if IMG_RE.search(f)),
                        key=lambda f: int((re.findall(r"\d+", f) or ["0"])[-1]))
            items += [(None, p, k, os.path.join(a.dir, p, f)) for k, f in enumerate(fs, 1)]
        out = a.out or os.path.join(a.dir, "slides_ocr.jsonl")
    else:
        if not a.work_dir:
            sys.exit("ERROR: pass WORK_DIR or --dir")
        meta = json.load(open(os.path.join(a.work_dir, "meta.json"), encoding="utf-8"))
        videos = meta["videos"]
        metric = meta.get("metric") or "views"
        cars = [i for i, v in enumerate(videos) if v.get("isCarousel")]
        if a.indexes:
            cars = [int(x) for x in a.indexes.split(",") if x.strip()]
        elif a.top:
            cars = sorted(cars, key=lambda i: -(videos[i].get(metric) or 0))[:a.top]
        n_dl, refreshed = download_slides(a.work_dir, meta, cars, [os.path.expanduser(p) for p in a.env_file])
        print(f"download: {n_dl} missing slides fetched for {len(cars)} carousels"
              + (f", URLs refreshed for {refreshed}" if refreshed else "") + f", {time.time() - t0:.0f}s",
              file=sys.stderr)
        items = [(i, videos[i]["id"], k, f) for i in cars
                 for k, f in enumerate(slide_files(os.path.join(a.work_dir, "carousels", f"{i:02d}")), 1)]
        out = os.path.join(a.work_dir, "slides_ocr.jsonl")

    t1 = time.time()
    raw = run_ocr([it[3] for it in items], a.jobs, a.lang)
    groups = {}
    for it in items:
        groups.setdefault(it[1], []).append(it[3])
    recs = build_records(raw, list(groups.values()), a.lang)
    rows = [{"index": i, "id": pid, "slide": k, "file": f, **recs[f]} for i, pid, k, f in items]
    with open(out, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    if a.raw:
        with open(a.raw, "w", encoding="utf-8") as fh:
            for it in items:
                fh.write(json.dumps(raw.get(it[3]) or {"file": it[3], "error": "missing"}, ensure_ascii=False) + "\n")

    kept = 0
    if not a.dir:  # carousels/NN/slides.json, never over a model-read file
        by_post = {}
        for r in rows:
            by_post.setdefault(r["index"], []).append(r)
        for i, rs in by_post.items():
            p = os.path.join(a.work_dir, "carousels", f"{i:02d}", "slides.json")
            old = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []
            if old and any(s.get("source") != "ocr" for s in old) and not a.force:
                kept += 1
                continue
            vis = {s.get("slide"): s for s in old}
            json.dump([{"slide": r["slide"], "text": r["text"],
                        **{k: v for k, v in (vis.get(r["slide"]) or {}).items() if k not in ("slide", "text")},
                        "aside": r["aside"], "source": "ocr", "ocr_conf": r["conf"], "ocr_flags": r["flags"]}
                       for r in rs],
                      open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    flagged = [r for r in rows if r["flags"]]
    print(f"ocr: {len(rows)} slides in {len({r['id'] for r in rows})} posts, {time.time() - t1:.1f}s "
          f"({a.jobs} processes), {sum(r['words'] for r in rows)} words, "
          f"{sum(len(r['fixes']) for r in rows)} OCR slips fixed -> {out}")
    if kept:
        print(f"kept {kept} slides.json written by a model (use --force to replace)")
    if flagged:
        print(f"flagged {len(flagged)}: " + ", ".join(
            f"{r['index'] if r['index'] is not None else r['id']}/{r['slide']} {'+'.join(r['flags'])}"
            for r in flagged[:40]) + (" …" if len(flagged) > 40 else ""))


PROMPT_TEMPLATE = os.path.join(os.path.dirname(HERE), "references", "haiku_visual_prompt.md")
LABEL_COLORS = [(230, 0, 70), (0, 90, 200)]


def open_rgb(path):
    from PIL import Image
    try:
        return Image.open(path).convert("RGB")
    except Exception:  # HEIC under another name: let sips convert it
        tmp = os.path.join("/tmp" if not os.environ.get("TMPDIR") else os.environ["TMPDIR"],
                           f"fs_{os.getpid()}_{os.path.basename(path)}.jpg")
        subprocess.run(["sips", "-s", "format", "jpeg", path, "--out", tmp], capture_output=True)
        im = Image.open(tmp).convert("RGB")
        os.remove(tmp)
        return im


def cmd_sheets(a):
    """Numbered contact sheets of every OCR'd slide + one prompt file per Haiku subagent."""
    from PIL import Image, ImageDraw, ImageFont
    W = a.work_dir
    rows = [json.loads(l) for l in open(os.path.join(W, "slides_ocr.jsonl"), encoding="utf-8")]
    out = os.path.join(W, "sheets")
    os.makedirs(out, exist_ok=True)
    for old in glob.glob(os.path.join(out, "sheet_*.jpg")) + glob.glob(os.path.join(out, "prompt-*.md")):
        os.remove(old)
    first = open_rgb(rows[0]["file"])
    th = round(a.tile * first.height / first.width)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", max(14, a.tile // 10))
    except OSError:
        font = ImageFont.load_default()
    gap, strip = 6, font.size + 6  # the label sits in a strip above the tile, never over the slide
    sw = a.cols * (a.tile + gap) + gap
    per_row_h = strip + th + gap
    n_rows = max(1, min((1568 - gap) // per_row_h, int(a.max_mpx * 1e6 // (sw * per_row_h))))
    per_sheet = a.cols * n_rows
    key = lambda r: str(r["index"]) if r["index"] is not None else r["id"]
    color_of, flip = {}, 0
    for r in rows:
        if key(r) not in color_of:
            color_of[key(r)] = LABEL_COLORS[flip % 2]
            flip += 1
    index = []
    for s in range(0, len(rows), per_sheet):
        chunk = rows[s:s + per_sheet]
        used_rows = (len(chunk) + a.cols - 1) // a.cols
        sheet = Image.new("RGB", (sw, used_rows * per_row_h + gap), (30, 30, 30))
        d = ImageDraw.Draw(sheet)
        tiles = []
        for k, r in enumerate(chunk):
            x, y = gap + (k % a.cols) * (a.tile + gap), gap + (k // a.cols) * per_row_h
            im = open_rgb(r["file"])
            im.thumbnail((a.tile, th))
            sheet.paste(im, (x + (a.tile - im.width) // 2, y + strip + (th - im.height) // 2))
            label = f"{key(r)}.{r['slide']}"
            d.rectangle([x, y, x + a.tile - 1, y + strip - 2], fill=color_of[key(r)])
            d.text((x + 5, y + 2), label, fill=(255, 255, 255), font=font)
            tiles.append({"label": label, "post": key(r), "id": r["id"], "slide": r["slide"], "file": r["file"]})
        path = os.path.join(out, f"sheet_{len(index) + 1:03d}.jpg")
        sheet.save(path, quality=85)
        index.append({"sheet": path, "size": list(sheet.size), "tiles": tiles})
    json.dump(index, open(os.path.join(out, "index.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    template = open(PROMPT_TEMPLATE, encoding="utf-8").read()
    jobs = []
    for k in range(0, len(index), a.per_agent):
        part = len(jobs) + 1
        sheets = index[k:k + a.per_agent]
        block = "\n".join(f"- {s['sheet']}\n  labels: {' '.join(t['label'] for t in s['tiles'])}" for s in sheets)
        dst = os.path.join(out, f"visual-part-{part}.jsonl")
        prompt = os.path.join(out, f"prompt-{part}.md")
        with open(prompt, "w", encoding="utf-8") as f:
            f.write(template.replace("{sheets}", block).replace("{out}", dst))
        jobs.append({"part": part, "prompt": prompt, "out": dst, "sheets": len(sheets),
                     "tiles": sum(len(s["tiles"]) for s in sheets)})
    json.dump(jobs, open(os.path.join(out, "jobs.json"), "w", encoding="utf-8"), indent=1)
    print(f"sheets: {len(index)} x up to {per_sheet} tiles ({a.cols}x{n_rows}, tile {a.tile}x{th}, "
          f"sheet {sw}px wide) for {len(rows)} slides -> {out}")
    print(f"haiku jobs: {len(jobs)}; launch all in ONE message, model haiku, prompt per job:")
    for j in jobs:
        print(f"  part {j['part']}: {j['tiles']} tiles on {j['sheets']} sheets | Read {j['prompt']} and follow it "
              f"exactly; reply with one line.")


def norm_words(s):
    s = (s or "").replace("’", "'").lower()
    return re.sub(r"[^\w\s']", " ", re.sub(r"[—–\-/]+", " ", s)).split()


def bigrams(words):
    return [tuple(words[i:i + 2]) for i in range(len(words) - 1)] if len(words) > 1 else [tuple(words)]


def headline_cover(headline, ocr_row):
    """Share of the Haiku headline's word pairs that OCR has in a row. Pairs, not words: the
    body text repeats 'is', 'not', 'your' and hid a lost 'YOUR BODY IS NOT' at 0.67 by words."""
    words = lambda t: [w for w in norm_words(t) if not w.isdigit()]  # point numerals move around
    hw = words(headline)
    if not hw:
        return None
    ow = words(" ".join(ocr_row.get(k, "") for k in ("text", "aside", "noise")))
    if len(hw) == 1:  # "BLOCKED." is one word, not a pair: a pair test flagged it as missed
        return float(hw[0] in ow)
    seen = set(bigrams(ow))
    head = bigrams(hw)
    return sum(b in seen for b in head) / len(head)


def cmd_merge(a):
    """Visual fields into carousels/NN/slides.json; list the slides that need a model read."""
    W = a.work_dir
    index = json.load(open(os.path.join(W, "sheets", "index.json"), encoding="utf-8"))
    tiles = {(t["post"], int(t["slide"])): t for s in index for t in s["tiles"]}
    vis = {}
    for f in sorted(glob.glob(os.path.join(W, "sheets", "visual-part-*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            line = line.strip().rstrip(",")
            if not line.startswith("{"):
                continue
            try:
                r = json.loads(line)
                vis[(str(r["post"]), int(r["slide"]))] = r
            except (ValueError, KeyError, TypeError):
                continue
    ocr = {(str(r["index"]) if r["index"] is not None else r["id"], int(r["slide"])): r
           for r in map(json.loads, open(os.path.join(W, "slides_ocr.jsonl"), encoding="utf-8"))}
    missing = sorted(set(tiles) - set(vis), key=lambda k: (k[0], k[1]))
    needs, merged = [], []
    for key in sorted(tiles, key=lambda k: (int(k[0]) if k[0].isdigit() else 0, k[0], k[1])):
        o, v = ocr.get(key) or {}, vis.get(key) or {}
        reasons = [f for f in o.get("flags") or [] if f in ("garbage", "low_conf", "unreadable")]
        cover = headline_cover(v.get("headline"), o)
        if cover is not None and cover < 0.8:
            # volatvio test: every slide under 0.8 had a real OCR loss (a big red numeral over
            # the first word, stylized letters); the 0.82-0.83 ones were bubble order only
            reasons.append("headline_missed" if cover < 0.6 else "headline_partial")
            if v.get("text_kind") in ("handwritten", "stylized"):
                reasons.append(v["text_kind"])
        if v.get("text_amount") not in (None, "none") and not o.get("words"):
            reasons.append("ocr_empty")
        if reasons:
            needs.append({"post": key[0], "slide": key[1], "file": tiles[key]["file"], "reasons": reasons,
                          "cover": None if cover is None else round(cover, 2),
                          "headline": v.get("headline", ""), "ocr_head": (o.get("text") or "").split("\n")[0]})
        merged.append({"post": key[0], "id": tiles[key]["id"], "slide": key[1], "text": o.get("text", ""),
                       **{k: v[k] for k in ("visual", "people", "background", "style", "font", "text_amount",
                                            "text_kind", "headline", "unclear") if k in v},
                       "needs_read": reasons})
    with open(os.path.join(W, "slides_fast.jsonl"), "w", encoding="utf-8") as f:
        for m in merged:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    json.dump(needs, open(os.path.join(W, "needs_read.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    updated = kept = 0
    by_post = {}
    for m in merged:
        by_post.setdefault(m["post"], []).append(m)
    for post, ms in by_post.items():
        p = os.path.join(W, "carousels", f"{int(post):02d}", "slides.json") if post.isdigit() else None
        if not p or not os.path.exists(p):
            continue
        cur = json.load(open(p, encoding="utf-8"))
        if any(s.get("source") != "ocr" for s in cur):
            kept += 1  # read by a model: its text and visual stay
            continue
        extra = {m["slide"]: m for m in ms}
        for s in cur:
            m = extra.get(s["slide"]) or {}
            s.update({k: m[k] for k in ("visual", "people", "background", "style", "font", "text_amount",
                                        "text_kind", "needs_read") if k in m})
        json.dump(cur, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        updated += 1
    print(f"merge: {len(vis)}/{len(tiles)} tiles described, {updated} slides.json updated"
          + (f", {kept} model-read kept" if kept else "") + f" -> {os.path.join(W, 'slides_fast.jsonl')}")
    if missing:
        print(f"MISSING {len(missing)} tiles (rerun that part): " + " ".join(f"{p}.{s}" for p, s in missing[:60]))
    print(f"needs a model read: {len(needs)} slides -> {os.path.join(W, 'needs_read.json')}")
    for n in needs[:30]:
        print(f"  {n['post']}.{n['slide']} {'+'.join(n['reasons'])} | haiku: {n['headline'][:50]!r} | "
              f"ocr: {n['ocr_head'][:50]!r}")


def cmd_fix(a):
    """Model-read texts (the old path) back into carousels/NN/slides.json and slides_fast.jsonl.
    FILE: JSONL {"post": "12", "slide": 3, "text": "verbatim", "visual": "optional"}."""
    W = a.work_dir
    fixes = {(str(r["post"]), int(r["slide"])): r for r in map(json.loads, open(a.file, encoding="utf-8"))
             if r.get("text") is not None}
    done = 0
    for post in sorted({k[0] for k in fixes}):
        p = os.path.join(W, "carousels", f"{int(post):02d}", "slides.json")
        if not os.path.exists(p):
            print(f"  {post}: no slides.json, skipped")
            continue
        cur = json.load(open(p, encoding="utf-8"))
        for s in cur:
            r = fixes.get((post, int(s["slide"])))
            if r:
                s.update({"text": r["text"], "source": "model", "needs_read": []})
                if r.get("visual"):
                    s["visual"] = r["visual"]
                done += 1
        json.dump(cur, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    fast = os.path.join(W, "slides_fast.jsonl")
    if os.path.exists(fast):
        rows = [json.loads(l) for l in open(fast, encoding="utf-8")]
        for m in rows:
            r = fixes.get((m["post"], int(m["slide"])))
            if r:
                m.update({"text": r["text"], "needs_read": [], "source": "model"})
        with open(fast, "w", encoding="utf-8") as f:
            for m in rows:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")
    print(f"fix: {done} slides replaced with the model's reading")


READ_TEMPLATE = os.path.join(os.path.dirname(HERE), "references", "haiku_slide_prompt.md")
HINT_RULES = """
An "OCR draft" follows some image paths: a machine reading of the slide. It can put lines
in the wrong order, miss hand-lettered or decorative words, misread letters and include
small labels from the picture. Use it to check the spelling of printed words; the image
wins: fix the order, add what it missed, drop what is not on the slide.
"""
TABLE_KEYS = ("text", "role", "people", "background", "art_style", "text_style", "product_mention",
              "unreadable", "visual")


def bow_f1(a, b):
    """Order-free word overlap of two texts, 0..1 (None when both are empty)."""
    import collections
    ca, cb = collections.Counter(norm_words(a)), collections.Counter(norm_words(b))
    if not ca and not cb:
        return None
    inter = sum((ca & cb).values())
    return 2 * inter / (sum(ca.values()) + sum(cb.values()))


def cmd_read(a):
    """One prompt per Haiku subagent: the slides it Reads and the JSONL it writes."""
    W = a.work_dir
    rows = [json.loads(l) for l in open(os.path.join(W, "slides_ocr.jsonl"), encoding="utf-8")]
    out = a.out_dir or os.path.join(W, "read")
    os.makedirs(out, exist_ok=True)
    for old in glob.glob(os.path.join(out, "prompt-*.md")):
        os.remove(old)
    template = open(READ_TEMPLATE, encoding="utf-8").read()
    key = lambda r: str(r["index"]) if r["index"] is not None else r["id"]
    jobs = []
    for k in range(0, len(rows), a.per_agent):
        part = len(jobs) + 1
        chunk = rows[k:k + a.per_agent]
        lines = []
        for r in chunk:
            lines.append(f"- {key(r)}.{r['slide']}: {r['file']}")
            if a.hint and r.get("text"):
                lines.append("  OCR draft: " + json.dumps(r["text"], ensure_ascii=False))
        dst = os.path.join(out, f"slides-part-{part}.jsonl")
        prompt = os.path.join(out, f"prompt-{part}.md")
        with open(prompt, "w", encoding="utf-8") as f:
            f.write(template.replace("{slides}", "\n".join(lines)).replace("{out}", dst)
                    .replace("{hint_rules}", HINT_RULES if a.hint else ""))
        jobs.append({"part": part, "prompt": prompt, "out": dst, "slides": len(chunk)})
    json.dump(jobs, open(os.path.join(out, "jobs.json"), "w", encoding="utf-8"), indent=1)
    print(f"read: {len(rows)} slides, {len(jobs)} Haiku subagents of up to {a.per_agent}"
          + (" (OCR draft in the prompt)" if a.hint else "") + f" -> {out}")
    print("launch all in ONE message: subagent_type general-purpose, model haiku, prompt per job:")
    for j in jobs:
        print(f"  part {j['part']}: {j['slides']} slides | Read {j['prompt']} and follow it exactly; "
              f"reply with one line.")


def read_jsonl_loose(paths):
    """Rows keyed by (post, slide) from model-written JSONL; tolerates stray lines and commas."""
    got = {}
    for f in paths:
        for line in open(f, encoding="utf-8"):
            line = line.strip().rstrip(",")
            if not line.startswith("{"):
                continue
            try:
                r = json.loads(line)
                got[(str(r["post"]), int(r["slide"]))] = r
            except (ValueError, KeyError, TypeError):
                continue
    return got


def cmd_table(a):
    """Haiku readings -> one table, a row per slide (+ a post-level table), checked against OCR."""
    import csv, statistics
    W = a.work_dir
    rd = a.read_dir or os.path.join(W, "read")
    meta = json.load(open(os.path.join(W, "meta.json"), encoding="utf-8"))
    videos, metric = meta["videos"], meta.get("metric") or "views"
    owner = f"https://www.tiktok.com/@{meta.get('handle')}" if meta.get("platform") == "tiktok" else \
        f"https://www.instagram.com/{meta.get('handle')}/"
    med = statistics.median([v.get(metric) or 0 for v in videos]) if videos else 0
    ocr = [json.loads(l) for l in open(os.path.join(W, "slides_ocr.jsonl"), encoding="utf-8")]
    haiku = read_jsonl_loose(sorted(glob.glob(os.path.join(rd, "slides-part-*.jsonl"))))
    fixes = read_jsonl_loose(sorted(glob.glob(os.path.join(rd, "fix-*.jsonl"))))
    key = lambda r: str(r["index"]) if r["index"] is not None else r["id"]

    rows, needs = [], []
    for o in ocr:
        k = (key(o), int(o["slide"]))
        h, src = fixes.get(k), "sonnet"
        if not h:
            h, src = haiku.get(k), "haiku"
        v = videos[o["index"]] if o["index"] is not None else {}
        ocr_text = " ".join(x for x in (o.get("text"), o.get("aside")) if x)
        text = (h or {}).get("text") or ""
        agree = bow_f1(text, ocr_text)
        reasons = []
        if not h:
            reasons, src = ["missing"], "ocr"
        elif src == "haiku":
            if h.get("unreadable"):
                reasons.append("unreadable")
            if "[?]" in text:
                reasons.append("partial")
            if o.get("words", 0) >= a.min_words and agree is not None and agree < a.min_agree:
                reasons.append("ocr_mismatch")
        rows.append({
            "post": k[0], "post_id": o["id"], "url": v.get("link", ""), metric: v.get(metric),
            "slide_no": k[1], "text": text if h else o.get("text", ""), "words": len(norm_words(text)),
            **{f: (h or {}).get(f, "") for f in TABLE_KEYS if f != "text"},
            "source": src, "ocr_text": o.get("text", ""),
            "ocr_agree": None if agree is None else round(agree, 2), "check": reasons, "file": o["file"]})
        if reasons:
            needs.append({"post": k[0], "slide": k[1], "file": o["file"], "reasons": reasons,
                          "ocr_agree": rows[-1]["ocr_agree"], "haiku": text[:80], "ocr": (o.get("text") or "")[:80]})

    base = os.path.join(W, "slides_table")
    with open(base + ".jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({k: v for k, v in r.items() if k != "file"}, ensure_ascii=False) + "\n")
    cols = [c for c in rows[0] if c not in ("file",)] if rows else []
    with open(base + ".csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "check": "+".join(r["check"]), "unreadable": bool(r["unreadable"])})
    json.dump(needs, open(os.path.join(rd, "needs_sonnet.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    by_post = {}
    for r in rows:
        by_post.setdefault(r["post"], []).append(r)
    with open(os.path.join(W, "posts_table.csv"), "w", encoding="utf-8-sig", newline="") as f:
        pcols = ["post", "post_id", "url", "owner_url", "date", "kind", "slides", "views", "likes", "comments",
                 "shares", "saves", "x_median", "caption", "hook", "integration_slides", "product_mentions"]
        w = csv.DictWriter(f, fieldnames=pcols)
        w.writeheader()
        for post, rs in by_post.items():
            v = videos[int(post)] if post.isdigit() and int(post) < len(videos) else {}
            w.writerow({"post": post, "post_id": rs[0]["post_id"], "url": v.get("link", ""), "owner_url": owner,
                        "date": v.get("date"), "kind": v.get("kind"), "slides": len(rs),
                        **{m: v.get(m) for m in ("views", "likes", "comments", "shares", "saves")},
                        "x_median": round((v.get(metric) or 0) / med, 2) if med else None,
                        "caption": v.get("desc") or v.get("caption") or v.get("title") or "",
                        "hook": next((r["text"] for r in rs if r["role"] == "hook"), rs[0]["text"]),
                        "integration_slides": " ".join(str(r["slide_no"]) for r in rs if r["role"] == "integration"),
                        "product_mentions": " | ".join(f"{r['slide_no']}: {r['product_mention']}"
                                                       for r in rs if r["product_mention"])})

    written = kept = 0  # carousels/NN/slides.json for the renderer and export_csv.py
    for post, rs in by_post.items():
        if not post.isdigit():
            continue
        p = os.path.join(W, "carousels", f"{int(post):02d}", "slides.json")
        cur = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []
        if any(s.get("source") == "model" for s in cur) and not a.force:
            kept += 1
            continue
        json.dump([{"slide": r["slide_no"], **{f: r[f] for f in TABLE_KEYS}, "source": r["source"]} for r in rs],
                  open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        written += 1

    n_h = sum(r["source"] == "haiku" for r in rows)
    print(f"table: {len(rows)} slides in {len(by_post)} posts ({n_h} haiku, "
          f"{sum(r['source'] == 'sonnet' for r in rows)} sonnet, {sum(r['source'] == 'ocr' for r in rows)} ocr only) "
          f"-> {base}.jsonl / .csv, {os.path.join(W, 'posts_table.csv')}; slides.json {written} written"
          + (f", {kept} model-read kept" if kept else ""))
    print(f"for a Sonnet re-read: {len(needs)} slides -> {os.path.join(rd, 'needs_sonnet.json')}")
    for n in needs[:30]:
        print(f"  {n['post']}.{n['slide']} {'+'.join(n['reasons'])} agree={n['ocr_agree']} | "
              f"haiku: {n['haiku'][:45]!r} | ocr: {n['ocr'][:45]!r}")


def cmd_show(a):
    """Slices of the slide table for the main session: the whole table of 1000 slides is
    ~330K tokens, so it reads posts_table.csv and prints only the posts it needs."""
    import csv
    W = a.work_dir
    posts = list(csv.DictReader(open(os.path.join(W, "posts_table.csv"), encoding="utf-8-sig")))
    rows = [json.loads(l) for l in open(os.path.join(W, "slides_table.jsonl"), encoding="utf-8")]
    xm = lambda p: float(p["x_median"] or 0)
    if a.posts:
        want = [x.strip() for x in a.posts.split(",") if x.strip()]
    elif a.hits:
        want = [p["post"] for p in sorted(posts, key=xm, reverse=True) if xm(p) >= 5]
    else:
        want = [p["post"] for p in sorted(posts, key=xm, reverse=True)[:a.top or len(posts)]]
    by_post = {}
    for r in rows:
        by_post.setdefault(r["post"], []).append(r)
    info = {p["post"]: p for p in posts}
    fields = [f for f in a.fields.split(",") if f]
    one = lambda s: re.sub(r"\s*\n\s*", " / ", str(s or "")).strip()
    for post in want:
        p = info.get(post, {})
        print(f"#{post} {p.get('views', '')} ({p.get('x_median', '')}x) {p.get('date', '')} {p.get('url', '')}")
        for r in by_post.get(post, []):
            extra = " | ".join(f"{f}: {one(r.get(f))[:a.max_chars]}" for f in fields if r.get(f) not in (None, ""))
            print(f"  {r['slide_no']} [{r.get('role', '')}] {one(r['text'])[:a.max_chars * 2]}" + (f" || {extra}" if extra else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("ocr")
    o.add_argument("work_dir", nargs="?")
    o.add_argument("--dir")
    o.add_argument("--out")
    o.add_argument("--raw", help="also save the raw Vision lines (boxes, confidence) as JSONL")
    o.add_argument("--indexes", default="")
    o.add_argument("--top", type=int, default=0)
    o.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 4))
    o.add_argument("--lang", default="en-US", help="Vision languages, e.g. en-US,ru-RU, or auto")
    o.add_argument("--force", action="store_true")
    o.add_argument("--env-file", action="append", default=[])
    o.set_defaults(fn=cmd_ocr)
    s = sub.add_parser("sheets")
    s.add_argument("work_dir")
    s.add_argument("--cols", type=int, default=7)
    s.add_argument("--tile", type=int, default=200, help="tile width, px")
    s.add_argument("--max-mpx", type=float, default=1.6, help="sheet size cap, megapixels")
    s.add_argument("--per-agent", type=int, default=6, help="sheets per Haiku subagent")
    s.set_defaults(fn=cmd_sheets)
    m = sub.add_parser("merge")
    m.add_argument("work_dir")
    m.set_defaults(fn=cmd_merge)
    x = sub.add_parser("fix")
    x.add_argument("work_dir")
    x.add_argument("file", help="JSONL of model-read slides: post, slide, text[, visual]")
    x.set_defaults(fn=cmd_fix)
    r = sub.add_parser("read")
    r.add_argument("work_dir")
    r.add_argument("--per-agent", type=int, default=40, help="slides per Haiku subagent")
    r.add_argument("--hint", action="store_true", help="put the OCR draft under each slide in the prompt")
    r.add_argument("--out-dir", help="default WORK_DIR/read")
    r.set_defaults(fn=cmd_read)
    t = sub.add_parser("table")
    t.add_argument("work_dir")
    t.add_argument("--read-dir", help="default WORK_DIR/read")
    t.add_argument("--min-agree", type=float, default=0.6, help="Haiku vs OCR word overlap below this -> check")
    t.add_argument("--min-words", type=int, default=5, help="only check slides where OCR found this many words")
    t.add_argument("--force", action="store_true")
    t.set_defaults(fn=cmd_table)
    sh = sub.add_parser("show")
    sh.add_argument("work_dir")
    sh.add_argument("--posts", default="", help="meta indexes, e.g. 3,7")
    sh.add_argument("--hits", action="store_true", help="posts at 5x the median or more")
    sh.add_argument("--top", type=int, default=0, help="top N posts by x_median")
    sh.add_argument("--fields", default="art_style,people,visual,product_mention")
    sh.add_argument("--max-chars", type=int, default=120)
    sh.set_defaults(fn=cmd_show)
    a = ap.parse_args()
    sys.path.insert(0, HERE)
    a.fn(a)


if __name__ == "__main__":
    main()
