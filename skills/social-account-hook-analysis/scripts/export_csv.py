#!/usr/bin/env python3
"""Export a finished analysis to one CSV and optionally copy the work dir into the project.

Usage:
  python3 export_csv.py WORK_DIR [--out FILE.csv] [--save-to DIR]

One row per post, sorted by meta.metric (views, or likes in Instagram posts mode):
rank, metrics, × account median, save/share rate, ER, kind, hook_text, pattern + formula,
every cards.json and labels.json field, top comment and the verbatim slide texts of the
carousels that were read (carousels/NN/slides.json), caption, cover file.
utf-8-sig, so Excel and Numbers open the Cyrillic correctly.

--save-to DIR copies the whole work dir (meta/cards/labels/clusters/report/insights json,
covers/, thumbs/, carousels/, report/ without report/_check) into DIR, points the file
paths inside meta.json and carousels/*/post.json at the copy, and writes the CSV there.
Default CSV name: <handle>_posts.csv.
"""
import argparse, csv, json, os, shutil, sys, time
from datetime import date

def load(path, default=None):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else default

def by_index(raw):
    """cards.json / labels.json: a list, an {index: card} dict, or {"names":…, "labels":[…]}."""
    if isinstance(raw, dict) and "labels" in raw:
        raw = raw["labels"]
    if isinstance(raw, dict):
        return {int(k): v for k, v in raw.items()}
    return {int(c.get("index", k)): c for k, c in enumerate(raw or [])}

def cell(x):
    if isinstance(x, (list, tuple)):
        return "; ".join(str(i) for i in x)
    if isinstance(x, dict):
        return json.dumps(x, ensure_ascii=False)
    if isinstance(x, bool):
        return "true" if x else "false"
    return "" if x is None else x

def pct(a, b):
    return round(100 * a / b, 2) if b else None

def build_rows(W):
    meta, rep = load(os.path.join(W, "meta.json")), load(os.path.join(W, "report.json"))
    if not meta or not rep:
        sys.exit("ERROR: WORK_DIR needs meta.json and report.json")
    videos, handle = meta["videos"], meta["handle"]
    platform = meta.get("platform", "tiktok")
    metric = rep.get("metric") or meta.get("metric") or "views"
    med = rep.get("accountMedianViews") or 0
    cards = by_index(load(os.path.join(W, "cards.json"), []))
    labels = by_index(load(os.path.join(W, "labels.json"), []))
    clusters = load(os.path.join(W, "clusters.json"), {"patterns": []})
    pattern_of = {}
    for p in clusters.get("patterns", []):
        for i in p.get("indexes", []):
            pattern_of[i] = (p.get("patternName", ""), p.get("formula", ""))
    young = set((rep.get("young") or {}).get("indexes") or [])
    excluded = set((rep.get("window") or {}).get("excluded") or [])
    fetched = (meta.get("fetchedAt") or time.strftime("%Y-%m-%d"))[:10]
    owner = f"https://www.tiktok.com/@{handle}" if platform == "tiktok" else f"https://www.instagram.com/{handle}/"

    card_keys, label_keys = [], []
    for c in cards.values():
        card_keys += [k for k in c if k not in ("index", "hook_text") and k not in card_keys]
    for c in labels.values():
        label_keys += [k for k in c if k != "index" and k not in label_keys]
    label_cols = {k: (f"label_{k}" if k in card_keys else k) for k in label_keys}

    order = sorted(range(len(videos)), key=lambda i: -(videos[i].get(metric) or 0))
    rows = []
    for rank, i in enumerate(order, 1):
        v = videos[i]
        val, views = v.get(metric) or 0, v.get("views") or 0
        try:
            age = (date.fromisoformat(fetched) - date.fromisoformat(v["date"])).days
        except (ValueError, KeyError):
            age = None
        cdir = os.path.join(W, "carousels", f"{i:02d}")
        post = load(os.path.join(cdir, "post.json"), {})
        top = (post.get("top_comments") or [None])[0]
        texts = load(os.path.join(cdir, "slides.json"), []) or []
        eng = sum(v.get(k) or 0 for k in ("likes", "comments", "shares", "saves"))
        cover = v.get("coverFile") or ""
        row = {
            "rank": rank, "index": i, "date": v.get("date"), "age_days": age,
            "young": i in young, "in_window": i not in excluded,
            "url": v.get("link"), "owner_url": owner,
            "views": views, "likes": v.get("likes"), "comments": v.get("comments"),
            "shares": v.get("shares"), "saves": v.get("saves"),
            "x_median": round(val / med, 2) if med else None,
            "save_rate": pct(v.get("saves") or 0, views), "share_rate": pct(v.get("shares") or 0, views),
            "er": pct(eng, views) if metric == "views" else None,
            "slides": v.get("slides"), "kind": v.get("kind") or ("carousel" if v.get("isCarousel") else "video"),
            "is_pinned": v.get("isPinned"),
            "hook_text": (cards.get(i) or {}).get("hook_text", ""),
            "pattern": pattern_of.get(i, ("unassigned", ""))[0], "formula": pattern_of.get(i, ("", ""))[1],
        }
        for k in card_keys:
            row[k] = (cards.get(i) or {}).get(k)
        for k, col in label_cols.items():
            row[col] = (labels.get(i) or {}).get(k)
        row.update({
            "top_comment": f'{top["text"]} ({top["likes"]}♥)' if top else "",
            "slide_texts": " | ".join(f'{t.get("slide", n)}: {t.get("text", "")}'.replace("\n", " / ")
                                      for n, t in enumerate(texts, 1)),
            "caption": v.get("desc", ""),
            "cover_file": os.path.relpath(cover, W) if cover.startswith(os.path.abspath(W)) else cover,
            "cover_source": v.get("coverSource", ""),
        })
        rows.append({k: cell(x) for k, x in row.items()})
    return handle, rows

def write_csv(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

def save_to(W, dst):
    src, dst = os.path.abspath(W), os.path.abspath(dst)
    shutil.copytree(src, dst, dirs_exist_ok=True,
                    ignore=lambda d, names: [n for n in names if n == "_check" or n.endswith((".mp4", ".mov"))])

    def moved(p):
        return p.replace(src, dst, 1) if isinstance(p, str) and p.startswith(src) else p

    meta_path = os.path.join(dst, "meta.json")
    meta = load(meta_path)
    for v in meta["videos"]:
        for k in ("coverFile", "thumbFile"):
            if v.get(k):
                v[k] = moved(v[k])
    json.dump(meta, open(meta_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    cdir = os.path.join(dst, "carousels")
    for sub in sorted(os.listdir(cdir)) if os.path.isdir(cdir) else []:
        pp = os.path.join(cdir, sub, "post.json")
        post = load(pp)
        if post and post.get("slide_files"):
            post["slide_files"] = [moved(p) for p in post["slide_files"]]
            json.dump(post, open(pp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return dst

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir")
    ap.add_argument("--out")
    ap.add_argument("--save-to")
    args = ap.parse_args()
    W = save_to(args.work_dir, args.save_to) if args.save_to else args.work_dir
    handle, rows = build_rows(W)
    out = args.out or os.path.join(W, f"{handle}_posts.csv")
    write_csv(out, rows)
    print(f"CSV: {out} ({len(rows)} rows, {len(rows[0])} columns)")
    if args.save_to:
        print(f"Saved work dir: {W}")

if __name__ == "__main__":
    main()
