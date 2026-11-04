#!/usr/bin/env python3
"""Compute per-pattern analytics from meta.json + Claude's clusters.json.

Usage:
  python3 pattern_stats.py META.json CLUSTERS.json [--cards CARDS.json] [--labels LABELS.json]
                           [--split-by has_creator_face,visual_format] [--since YYYY-MM-DD]
                           [--min-age-days 7] [--out REPORT.json]

clusters.json format (produced by Claude after reading covers):
{
  "patterns": [
    {"patternName": "...", "formula": "...", "visualFormat": "...", "indexes": [0, 7, 12]}
  ],
  "unassigned": [3, 41]        # optional; explicit bucket, never silent
}

cards.json: index-aligned array of cards (fan-out subagents, NATIVE, or ocr_covers.py).
labels.json: written by Claude after clustering, once the account's themes and the user's
product are known. Index-aligned array [{"index": 0, "theme": "learning",
"product_fit": "direct"}] (product_fit: direct / adjacent / off), or
{"names": {"theme": {"learning": "Знания"}}, "labels": [...]} with display names.
Labels merge into the cards. Every categorical field (bool or ≤12 distinct short values)
becomes a split; --split-by restricts the list. Free-text fields are never split.

Window: --since drops older posts from every number (they still must be clustered).
Young posts (published < --min-age-days before meta.fetchedAt, default 7) are still
collecting views, so every median leaves them out; hits (≥5× median) still include them.

Metric: meta.metric — "views", or "likes" for Instagram posts mode (no views for carousels
and photos). Keys keep their names (medianViews = median of the metric).
ER = (likes + comments + shares + saves) / views (social-account-short-analysis reports
comment rate instead); null when the metric is not views.

Validation is STRICT: every video index 0..N-1 must appear exactly once across
patterns + unassigned. Duplicates or missing indexes → exit 1 with the list,
so the caller must fix the assignment (no silent drops possible).

Output: report JSON with metric, window, young posts, account median + save/share rates
and ER, view concentration and hits, per-pattern stats sorted by median (count,
median/avg, virality, median likes/saves, save/share rate, ER, top-5, outlier &
small-sample flags) and splits: format, pinned, period (publication month) and every
categorical card/label field. Every split bucket carries belowMinimum (< 3 posts).
"""
import argparse, json, statistics, sys
from datetime import date

FREE_TEXT = {"index", "hook_text", "embedded_context", "notes", "desc", "ocr_failed", "series"}
ER_FORMULA = "(likes + comments + shares + saves) / views"
MIN_N = 3

def median(vals):
    return statistics.median(vals) if vals else 0

def rate(v, field):
    return 100 * v[field] / v["views"] if v.get("views") else 0

def slide_bucket(v):
    if not v.get("isCarousel"):
        return "photo" if v.get("kind") == "photo" else "video"
    n = v.get("slides") or 0
    return "1" if n <= 1 else "2-3" if n <= 3 else "4+"

def load_rows(path):
    raw = json.load(open(path, encoding="utf-8"))
    names = {}
    if isinstance(raw, dict) and "labels" in raw:
        names, raw = raw.get("names") or {}, raw["labels"]
    rows = {int(c.get("index", k)): c for k, c in
            (raw.items() if isinstance(raw, dict) else enumerate(raw))}
    return rows, names

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("meta")
    ap.add_argument("clusters")
    ap.add_argument("--cards")
    ap.add_argument("--labels")
    ap.add_argument("--split-by", default="")
    ap.add_argument("--since")
    ap.add_argument("--min-age-days", type=int, default=7)
    ap.add_argument("--out")
    args = ap.parse_args()

    meta = json.load(open(args.meta, encoding="utf-8"))
    clusters = json.load(open(args.clusters, encoding="utf-8"))
    videos = meta["videos"]
    n = len(videos)
    metric = meta.get("metric") or "views"

    # --- strict coverage validation ---
    seen = {}
    for p in clusters.get("patterns", []):
        for i in p.get("indexes", []):
            seen[i] = seen.get(i, 0) + 1
    for i in clusters.get("unassigned", []):
        seen[i] = seen.get(i, 0) + 1
    missing = [i for i in range(n) if i not in seen]
    dupes = sorted(i for i, c in seen.items() if c > 1)
    invalid = sorted(i for i in seen if i < 0 or i >= n)
    if missing or dupes or invalid:
        print(json.dumps({"error": "coverage validation failed",
                          "missing": missing, "duplicates": dupes,
                          "out_of_range": invalid, "total_videos": n},
                         ensure_ascii=False))
        sys.exit(1)

    # --- window and young posts ---
    def age(v):
        try:
            return (date.fromisoformat(meta.get("fetchedAt")) - date.fromisoformat(v["date"])).days
        except (TypeError, ValueError):
            return None

    out_set = {i for i in range(n) if args.since and videos[i]["date"] < args.since}
    inwin = [i for i in range(n) if i not in out_set]
    young = [i for i in inwin if (a := age(videos[i])) is not None and a < args.min_age_days]
    young_set = set(young)
    stat = [i for i in inwin if i not in young_set]
    young_fallback = not stat
    if young_fallback:  # every post is young: better a noisy median than none
        stat = list(inwin)
    stat_set = set(stat)

    def val(i):
        return videos[i].get(metric) or 0

    def er(v):
        if metric != "views" or not v.get("views"):
            return None
        return (v["likes"] + v["comments"] + v.get("shares", 0) + v.get("saves", 0)) / v["views"]

    acc_median = median([val(i) for i in stat])

    def group(idxs):
        med = median([val(i) for i in idxs])
        vids = [videos[i] for i in idxs]
        return {"count": len(idxs), "medianViews": round(med),
                "viralityRate": round(med / acc_median, 2) if acc_median else 0,
                "medianSaveRate": round(median([rate(v, "saves") for v in vids]), 2),
                "medianShareRate": round(median([rate(v, "shares") for v in vids]), 2),
                "belowMinimum": len(idxs) < MIN_N,
                "indexes": sorted(idxs, key=lambda i: -val(i))}

    def build(name, formula, visual, members):
        st_idx = [i for i in members if i in stat_set]
        shown = sorted((i for i in members if i not in out_set), key=lambda i: -val(i))
        vals = [val(i) for i in st_idx]
        med, av = median(vals), (sum(vals) / len(vals) if vals else 0)
        eng = [e for e in (er(videos[i]) for i in st_idx) if e is not None]
        g = group(st_idx)
        return {
            "patternName": name,
            "formula": formula,
            "visualFormat": visual,
            "count": len(st_idx),
            "medianViews": round(med),
            "avgViews": round(av),
            "viralityRate": round(med / acc_median, 2) if acc_median else 0,
            "medianLikes": round(median([videos[i]["likes"] for i in st_idx])),
            "medianSaves": round(median([videos[i]["saves"] for i in st_idx])),
            "medianSaveRate": g["medianSaveRate"],
            "medianShareRate": g["medianShareRate"],
            "medianEngagement": round(median(eng) * 100, 2) if eng else None,
            "outlierWarning": bool(vals) and av > 3 * med and len(vals) >= 2,
            "belowMinimum": len(st_idx) < MIN_N,
            "indexes": shown,
            "youngIndexes": [i for i in shown if i in young_set],
            "topVideos": [{"index": i, "id": videos[i]["id"], "views": videos[i]["views"],
                           "value": val(i), "likes": videos[i]["likes"], "saves": videos[i]["saves"],
                           "date": videos[i]["date"], "link": videos[i]["link"]} for i in shown[:5]],
        }

    out_patterns = [build(p["patternName"], p.get("formula", ""), p.get("visualFormat", ""),
                          p["indexes"]) for p in clusters.get("patterns", [])]
    out_patterns.sort(key=lambda p: -p["medianViews"])

    # --- splits: format, pinned, period from meta; categorical fields from cards + labels ---
    def split(values):
        buckets = {}
        for i in stat:
            v = values[i]
            buckets.setdefault("unknown" if v is None else str(v).lower(), []).append(i)
        return sorted(({"value": k} | group(ix) for k, ix in buckets.items()),
                      key=lambda g: -g["medianViews"])

    splits = {}
    if any("isCarousel" in v for v in videos):
        splits["format"] = split([slide_bucket(v) for v in videos])
    if any(v.get("isPinned") for v in videos):
        splits["pinned"] = split([bool(v.get("isPinned")) for v in videos])
    months = sorted({videos[i]["date"][:7] for i in stat if videos[i]["date"][:4].isdigit()})
    if len(months) >= 2:
        quarter = len(months) > 12
        def period(d):
            if not d[:4].isdigit():
                return None
            return f"{d[:4]}-Q{(int(d[5:7]) - 1) // 3 + 1}" if quarter else d[:7]
        splits["period"] = split([period(v["date"]) for v in videos])

    cards, names = {}, {}
    if args.cards:
        cards, _ = load_rows(args.cards)
        if len(cards) != n:
            print(f"WARNING: cards cover {len(cards)} of {n} videos", file=sys.stderr)
    if args.labels:
        labels, names = load_rows(args.labels)
        if len(labels) != n:
            print(f"WARNING: labels cover {len(labels)} of {n} videos", file=sys.stderr)
        for i, row in labels.items():
            cards[i] = {**cards.get(i, {}), **{k: v for k, v in row.items() if k != "index"}}
    if cards:
        fields = sorted({k for c in cards.values() for k in c} - FREE_TEXT)
        wanted = [f for f in args.split_by.split(",") if f.strip()]
        for f in wanted or fields:
            vals = [cards.get(i, {}).get(f) for i in range(n)]
            distinct = {str(v).lower() for v in vals if v is not None}
            short = all(len(str(v)) <= 40 for v in vals if v is not None)
            if wanted or (2 <= len(distinct) <= 12 and short):
                splits[f] = split(vals)

    total = sum(val(i) for i in inwin)
    by_val = sorted(inwin, key=lambda i: -val(i))
    hits = [i for i in by_val if acc_median and val(i) >= 5 * acc_median]
    acc_eng = [e for e in (er(videos[i]) for i in stat) if e is not None]

    un_all = clusters.get("unassigned", [])
    un_shown = sorted((i for i in un_all if i not in out_set), key=lambda i: -val(i))
    un_stat = [i for i in un_all if i in stat_set]
    report = {
        "platform": meta.get("platform"),
        "handle": meta.get("handle"),
        "metric": metric,
        "totalVideos": n,
        "analyzedVideos": len(stat),
        "window": {"since": args.since, "inWindow": len(inwin), "excluded": sorted(out_set)},
        "young": {"minAgeDays": args.min_age_days, "indexes": young, "fallbackAllYoung": young_fallback},
        "accountMedianViews": round(acc_median),
        "accountMedianSaveRate": round(median([rate(videos[i], "saves") for i in stat]), 2),
        "accountMedianShareRate": round(median([rate(videos[i], "shares") for i in stat]), 2),
        "accountMedianEngagement": round(median(acc_eng) * 100, 2) if acc_eng else None,
        "engagementFormula": ER_FORMULA if metric == "views" else None,
        "concentration": {
            "totalViews": total,
            "top1Share": round(100 * sum(val(i) for i in by_val[:1]) / total, 1) if total else 0,
            "top5Share": round(100 * sum(val(i) for i in by_val[:5]) / total, 1) if total else 0,
            "hitsShare": round(100 * sum(val(i) for i in hits) / total, 1) if total else 0,
            "hits": [{"index": i, "views": val(i), "young": i in young_set,
                      "multiplier": round(val(i) / acc_median, 1)} for i in hits],
        },
        "patterns": out_patterns,
        "unassigned": {
            "count": len(un_shown),
            "indexes": un_shown,
            "medianViews": round(median([val(i) for i in un_stat])) if un_stat else 0,
        },
        "splits": splits,
        "labelNames": names,
    }
    print(f"window: {len(inwin)}/{n} posts in window; {len(young)} young (<{args.min_age_days} d) left out "
          f"of medians {young}{' (all young: kept)' if young_fallback else ''}; metric {metric}; "
          f"account median {round(acc_median)}", file=sys.stderr)
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"report written to {args.out}", file=sys.stderr)
    print(text)

if __name__ == "__main__":
    main()
