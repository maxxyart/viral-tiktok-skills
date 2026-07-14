#!/usr/bin/env python3
"""
Aggregate per-pattern stats after Claude assigns a pattern label to each carousel.

Usage:
  python3 aggregate.py <carousels_ocr.json> <mapping.json>

mapping.json: {"<carousel id>": "P1 short pattern name", ...}
Unmapped carousels are grouped under "P? unclassified".
Prints a table ranked by peak views: n, peak, avg, total, save%.
"""
import sys, json
from collections import defaultdict

cs = json.load(open(sys.argv[1]))
mapping = json.load(open(sys.argv[2]))

agg = defaultdict(lambda: {"n": 0, "views": 0, "saves": 0, "peak": 0, "ref": ""})
for c in cs:
    g = mapping.get(str(c["id"]), "P? unclassified")
    a = agg[g]
    a["n"] += 1
    a["views"] += c["views"]
    a["saves"] += c["saves"]
    if c["views"] >= a["peak"]:          # remember the peak-views carousel as the pattern's reference
        a["peak"] = c["views"]
        a["ref"] = c.get("url", "")

rows = sorted(agg.items(), key=lambda kv: kv[1]["peak"], reverse=True)
print(f"{'pattern':52} | {'n':>2} | {'peak':>10} | {'avg':>9} | {'total':>11} | {'save%':>5}")
print("-" * 102)
for g, a in rows:
    savep = 100 * a["saves"] / a["views"] if a["views"] else 0
    print(f"{g:52} | {a['n']:>2} | {a['peak']:>10,} | {a['views'] // a['n']:>9,} | "
          f"{a['views']:>11,} | {savep:>4.1f}%")
print(f"\ntotal: {len(cs)} carousels, {sum(a['n'] for _, a in rows)} classified into {len(rows)} patterns")

print("\ntop reference per pattern (peak-views carousel — link it in the report):")
for g, a in rows:
    if a["ref"]:
        print(f"  {g:52} {a['peak']:>11,}v  {a['ref']}")
