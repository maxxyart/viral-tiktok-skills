#!/usr/bin/env python3
"""Compute per-pattern analytics from meta.json + Claude's clusters.json.

Usage:
  python3 pattern_stats.py META.json CLUSTERS.json [--out REPORT.json]

clusters.json format (produced by Claude after reading covers):
{
  "patterns": [
    {"patternName": "...", "formula": "...", "visualFormat": "...", "indexes": [0, 7, 12]}
  ],
  "unassigned": [3, 41]        # optional; explicit bucket, never silent
}

Validation is STRICT: every video index 0..N-1 must appear exactly once across
patterns + unassigned. Duplicates or missing indexes → exit 1 with the list,
so the caller must fix the assignment (no silent drops possible).

Output: report JSON with account median, per-pattern stats sorted by median views
(count, median/avg views, virality, median likes/saves, engagement, top-5 videos,
outlier & small-sample flags).
"""
import argparse, json, statistics, sys

def median(vals):
    return statistics.median(vals) if vals else 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("meta")
    ap.add_argument("clusters")
    ap.add_argument("--out")
    args = ap.parse_args()

    meta = json.load(open(args.meta, encoding="utf-8"))
    clusters = json.load(open(args.clusters, encoding="utf-8"))
    videos = meta["videos"]
    n = len(videos)

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

    acc_median = median([v["views"] for v in videos])

    def build(name, formula, visual, idxs):
        vids = sorted((videos[i] | {"index": i} for i in idxs), key=lambda v: -v["views"])
        views = [v["views"] for v in vids]
        med, av = median(views), (sum(views) / len(views) if views else 0)
        eng = [ (v["likes"] + v["comments"]) / v["views"] for v in vids if v["views"] ]
        return {
            "patternName": name,
            "formula": formula,
            "visualFormat": visual,
            "count": len(vids),
            "medianViews": round(med),
            "avgViews": round(av),
            "viralityRate": round(med / acc_median, 2) if acc_median else 0,
            "medianLikes": round(median([v["likes"] for v in vids])),
            "medianSaves": round(median([v["saves"] for v in vids])),
            "medianEngagement": round(median(eng) * 100, 2) if eng else 0,
            "outlierWarning": bool(views) and av > 3 * med and len(views) >= 2,
            "belowMinimum": len(vids) < 3,
            "topVideos": [{"index": v["index"], "id": v["id"], "views": v["views"],
                           "likes": v["likes"], "saves": v["saves"], "date": v["date"],
                           "link": v["link"]} for v in vids[:5]],
        }

    out_patterns = [build(p["patternName"], p.get("formula", ""), p.get("visualFormat", ""),
                          p["indexes"]) for p in clusters.get("patterns", [])]
    out_patterns.sort(key=lambda p: -p["medianViews"])

    unassigned = clusters.get("unassigned", [])
    report = {
        "platform": meta.get("platform"),
        "handle": meta.get("handle"),
        "totalVideos": n,
        "accountMedianViews": round(acc_median),
        "patterns": out_patterns,
        "unassigned": {
            "count": len(unassigned),
            "indexes": sorted(unassigned),
            "medianViews": round(median([videos[i]["views"] for i in unassigned])) if unassigned else 0,
        },
    }
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"report written to {args.out}", file=sys.stderr)
    print(text)

if __name__ == "__main__":
    main()
