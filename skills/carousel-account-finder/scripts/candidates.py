#!/usr/bin/env python3
"""Pick what the OCR agents read, in three blocks (2026-10-27).

Usage: python3 candidates.py OUT_DIR [--super-views 100000] [--super-x 5] [--rep-views 10000] [--rep-x 2]
                                     [--rep-max 12]

Baseline for every multiplier: median views of ALL posts of the account in the window (videos, photos and
carousels), so a video account with one carousel still gets a fair x.

  mono     accounts that passed screen.py (carousel share >= 40% etc.): top-5 carousels.
  super    single super carousels on ANY screened account: views >= --super-views and >= --super-x × median.
  repeat   accounts with >= 3 carousels of >= --rep-views views, at least 2 of them >= --rep-x × median
           (a 3-carousel group can only reach a 2× median if two of its members do). Up to --rep-max carousels
           by views go to the agents, who group them by meaning-level hook and formula; build.py keeps groups
           of >= 3, each >= --rep-views, whose median is >= --rep-x × the account median (2026-10-28).

Writes OUT_DIR/candidates.json:
  {"params": {...}, "median_all": {h: n}, "mono": [h], "super": [{"handle", "id", "views", "x"}],
   "repeat": {h: [id]}, "jobs": {h: {"ids": [id], "roles": ["mono", "super", "repeat"]}}}
"""
import argparse
import json
import os
import statistics

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--super-views", type=int, default=100_000)
ap.add_argument("--super-x", type=float, default=5)
ap.add_argument("--rep-views", type=int, default=10_000)
ap.add_argument("--rep-x", type=float, default=2)
ap.add_argument("--rep-max", type=int, default=12)
args = ap.parse_args()
OUT = args.out

scr = json.load(open(os.path.join(OUT, "screening.json")))
median_all, mono, sup, rep, jobs = {}, [], [], {}, {}


def job(h, ids, role):
    j = jobs.setdefault(h, {"ids": [], "roles": []})
    for i in ids:
        if i not in j["ids"]:
            j["ids"].append(i)
    if role not in j["roles"]:
        j["roles"].append(role)


for h, s in scr.items():
    p = os.path.join(OUT, "accounts", f"{h}.json")
    if s.get("error") or not os.path.exists(p):
        continue
    posts = json.load(open(p))["posts"]
    allv = [x["views"] for x in posts if not x.get("pinned")] or [x["views"] for x in posts]
    if not allv:
        continue
    med = max(1, int(statistics.median(allv)))
    median_all[h] = med
    cars = sorted([x for x in posts if x["type"] == "carousel" and x["n_slides"] >= 2], key=lambda x: -x["views"])
    if s.get("pass"):
        mono.append(h)
        job(h, [x["id"] for x in cars[:5]], "mono")
    for x in cars:
        if x["views"] >= args.super_views and x["views"] >= args.super_x * med:
            sup.append({"handle": h, "id": x["id"], "views": x["views"], "x": round(x["views"] / med, 1)})
            job(h, [x["id"]], "super")
    big = [x for x in cars if x["views"] >= args.rep_views]
    if len(big) >= 3 and sum(1 for x in big if x["views"] >= args.rep_x * med) >= 2:
        rep[h] = [x["id"] for x in big[:args.rep_max]]
        job(h, rep[h], "repeat")

sup.sort(key=lambda r: -r["views"])
json.dump({"params": vars(args), "median_all": median_all, "mono": mono, "super": sup, "repeat": rep, "jobs": jobs},
          open(os.path.join(OUT, "candidates.json"), "w"), ensure_ascii=False, indent=1)
n_car = sum(len(j["ids"]) for j in jobs.values())
print(f"mono accounts: {len(mono)} | super carousels: {len(sup)} on {len({r['handle'] for r in sup})} accounts | "
      f"repeat candidates: {len(rep)} accounts | agent jobs: {len(jobs)} accounts, {n_car} carousels")
for r in sup[:15]:
    print(f"  super @{r['handle']:<24} {r['views']:>10,}  {r['x']}x")
