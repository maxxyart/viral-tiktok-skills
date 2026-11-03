#!/usr/bin/env python3
"""Collect carousel authors from TikTok Top search (the only search route that returns photo carousels).

Usage:
  python3 search.py OUT_DIR --since YYYY-MM-DD [--pages 5] [--include h1,h2] "query 1" "query 2" ...

- Paginates /v1/tiktok/search/top per query until results run out (usually ~6 pages).
- Records every multi_photo post with its author; `fresh` = posted on/after --since.
- Merges into OUT_DIR/search_candidates.json if it exists (rerun with extra queries to widen the pool).
- Writes OUT_DIR/pool.txt: --include handles first, then authors whose newest found carousel is >= --since.
"""
import argparse
import json
import os
import sys

from common import api, credits_remaining

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("queries", nargs="+")
ap.add_argument("--since", required=True)
ap.add_argument("--pages", type=int, default=5)
ap.add_argument("--include", default="", help="comma-separated handles to always screen (reference accounts)")
args = ap.parse_args()
os.makedirs(args.out, exist_ok=True)
path = os.path.join(args.out, "search_candidates.json")
state = json.load(open(path)) if os.path.exists(path) else {"queries": [], "pages": [], "handles": {}}
found = state["handles"]

for q in args.queries:
    if q in state["queries"]:
        print(f"skip (already searched): {q}", file=sys.stderr)
        continue
    cursor, seen = 0, set()
    for page in range(1, args.pages + 1):
        try:
            d = api("/v1/tiktok/search/top", {"query": q, "cursor": cursor})
        except Exception as e:
            print(f"  {q} p{page} failed: {e}", file=sys.stderr)
            break
        items = d.get("items") or []
        new = [i for i in items if i.get("id") not in seen]
        seen.update(i.get("id") for i in items)
        car = [i for i in new if i.get("content_type") == "multi_photo"]
        for i in car:
            h = (i.get("author") or {}).get("unique_id")
            if not h:
                continue
            st = i.get("statistics") or {}
            date = (i.get("create_time") or "")[:10]
            found.setdefault(h, []).append({
                "id": i["id"], "date": date, "views": st.get("play_count", 0) or 0,
                "slides": len(i.get("images") or []), "desc": (i.get("desc") or "")[:120],
                "via": f"{q} p{page}", "fresh": date >= args.since,
            })
        line = f"{q} p{page}: {len(items)} items, {len(car)} carousels"
        state["pages"].append(line)
        print(line, file=sys.stderr)
        if not items or not d.get("cursor"):
            break
        cursor = d["cursor"]
    state["queries"].append(q)

for h in found:
    found[h] = sorted({x["id"]: x for x in found[h]}.values(), key=lambda x: -x["views"])
state["since"] = args.since
json.dump(state, open(path, "w"), ensure_ascii=False, indent=1)

include = [h.strip().lstrip("@") for h in args.include.split(",") if h.strip()]
pool = include + [h for h, xs in found.items() if h not in include and max(x["date"] for x in xs) >= args.since]
open(os.path.join(args.out, "pool.txt"), "w").write("\n".join(pool))
print(f"{len(found)} carousel authors found, {len(pool)} in pool (carousel since {args.since} + includes). "
      f"credits left: {credits_remaining()}")
