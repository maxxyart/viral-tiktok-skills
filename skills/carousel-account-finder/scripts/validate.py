#!/usr/bin/env python3
"""Check the agents' output. Usage: python3 validate.py OUT_DIR [--stage ocr|decide]

  ocr     (after stage A, Haiku): every job carousel has ocr/<id>.json with slides, visual, hook, formula.
  decide  (default, after stage B or the single-agent prompt): also analysis/<h>.json with the needed keys,
          "fit" in every ocr file, and persona / angle ids that exist in taxonomy.json (when it exists).
Prints the accounts that need a rerun."""
import argparse
import json
import os

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--stage", choices=["ocr", "decide"], default="decide")
args = ap.parse_args()
OUT = args.out
need = {"handle", "hooks", "consistency_level", "niche_fit", "fit_reason", "persona", "angle", "product_yes",
        "product_name", "product", "topic", "repeats"}
ocr_need = {"slides", "visual", "hook", "hook_meaning", "formula"}
jobs = json.load(open(os.path.join(OUT, "candidates.json")))["jobs"]
_tx = os.path.join(OUT, "taxonomy.json")
ids = None
if os.path.exists(_tx):
    t = json.load(open(_tx))
    ids = {i["id"] for i in t.get("personas", []) + t.get("angles", [])} | {"none", ""}


def load(p):
    try:
        return json.load(open(p))
    except Exception:
        return None


bad = []
for h, j in jobs.items():
    probs = []
    for i in j["ids"]:
        o = load(os.path.join(OUT, "ocr", f"{i}.json"))
        if o is None:
            probs.append(f"ocr {i} missing/broken"); continue
        if ocr_need - set(o):
            probs.append(f"ocr {i} lacks {sorted(ocr_need - set(o))}")
        if args.stage == "decide":
            a_ = load(os.path.join(OUT, "analysis", f"{h}.json")) or {}
            o = {**o, **((a_.get("carousels") or {}).get(i) or {})}
            if "fit" not in o:
                probs.append(f"ocr {i} no fit")
            if ids is not None and (str(o.get("persona", "none")) not in ids or str(o.get("angle", "none")) not in ids):
                probs.append(f"ocr {i} unknown persona/angle {o.get('persona')}/{o.get('angle')}")
    if args.stage == "decide":
        a = load(os.path.join(OUT, "analysis", f"{h}.json"))
        if a is None:
            probs.append("analysis missing/broken")
        else:
            if need - set(a):
                probs.append(f"analysis lacks {sorted(need - set(a))}")
            if ids is not None and (str(a.get("persona")) not in ids or str(a.get("angle")) not in ids):
                probs.append(f"unknown persona/angle {a.get('persona')}/{a.get('angle')}")
            if "—" in json.dumps({k: v for k, v in a.items() if k != "hooks"}, ensure_ascii=False):  # hooks quote slides verbatim
                probs.append("em dash")
            print(f"{h:<26} {a.get('niche_fit', '?'):<13} {str(a.get('persona')):<6} {str(a.get('angle')):<7} "
                  f"repeats={len(a.get('repeats') or [])}")
    if probs:
        bad.append(h)
        print("  RERUN", h, "|", "; ".join(probs[:4]))
print(f"{len(jobs)} accounts, {len(bad)} need a rerun{': ' + ','.join(bad) if bad else ''}")
