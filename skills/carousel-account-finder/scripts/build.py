#!/usr/bin/env python3
"""Build the artifact page: one block per passing account + screening table.

Usage:
  python3 build.py OUT_DIR --topic "trauma bonding" [--title "Trauma Bonding Carousel Accounts"]
                   [--reference h1,h2] [--max-accounts 60]
                   [--pin h1,h2 --pin-label "red flags in communication"]   # these go first, with a 🚩 badge
                   [--fav h1]                                                # very first, ★ on by default

English page, one account per screen: summary tiles, badges, metrics, integration (product name +
verbatim quotes from analysis/<h>.integration.json), top-5 carousels. Filter: all / with / without integration.

Reads screening.json, screen_params.json, search_candidates.json, accounts/*.json, acc/<h>/{strips,thumbs},
analysis/<h>.json (written by the analysis agents), covers.json (covers.py, optional). Writes:
  OUT_DIR/carousel-accounts.html   the page to publish (title = --title)
  OUT_DIR/accounts.csv             every screened account with metrics, bio and reasons
  OUT_DIR/publish_batches.json     lists of relative file paths, each batch <= 240 files and <= 3 MB (bigger batches drop with 'socket hang up')
"""
import argparse
import csv
import html
import json
import os
import re
import statistics
from datetime import date

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--topic", required=True)
ap.add_argument("--title")
ap.add_argument("--reference", default="")
ap.add_argument("--max-accounts", type=int, default=20)
ap.add_argument("--pin", default="")
ap.add_argument("--pin-label", default="")
ap.add_argument("--fav", default="")
ap.add_argument("--mark", default="", help="comma-separated handles that get a --mark-label badge without moving (e.g. new in round 2)")
ap.add_argument("--mark-label", default="new")
ap.add_argument("--max-supers", type=int, default=0, help="cap block 2 (super carousels, applied after dedup); 0 = all")
ap.add_argument("--allow-dupes", action="store_true",
                help="show a carousel in several blocks; default: once, priority accounts > repeats > supers")
ap.add_argument("--max-repeats", type=int, default=0, help="cap block 3 (repeat groups); 0 = all")
ap.add_argument("--drop-off", action="store_true", help="leave off-niche carousels/groups out of blocks 2 and 3")
ap.add_argument("--strip-thumbs", action="store_true",
                help="use the strip as the thumbnail (cropped to slide 1 in CSS): half the files, for the 511-file limit")
ap.add_argument("--demote-tag", default="", help="accounts carrying this tag go after the rest inside their niche group")
ap.add_argument("--group-filter", default="",
                help='2026-11-03: account groups from the agent "group" key, as "A=Relationships,B=Intimacy": badge + filter row on all tabs')
ap.add_argument("--christian-rule", action="store_true",
                help="faith-app runs: keep Christian accounts in niche or adjacent, non-Christian only strictly in niche; "
                     "adds the Christian badge and filter (analysis 'christian' key, falls back to covers p_christian)")
args = ap.parse_args()
OUT = args.out
title = args.title or f"{args.topic.strip().title()} Carousel Accounts"
refs = {h.strip().lstrip("@") for h in args.reference.split(",") if h.strip()}

scr = json.load(open(os.path.join(OUT, "screening.json")))
params = json.load(open(os.path.join(OUT, "screen_params.json")))
meta = json.load(open(os.path.join(OUT, "search_candidates.json")))
analysis = {}
adir = os.path.join(OUT, "analysis")
for f in (os.listdir(adir) if os.path.isdir(adir) else []):
    if f.endswith(".integration.json"):
        continue
    if f.endswith(".json"):
        try:
            x = json.load(open(os.path.join(adir, f)))
            analysis[x["handle"]] = x
        except Exception as e:
            print(f"WARN bad analysis file {f}: {e}")
for h, a in analysis.items():
    ip = os.path.join(adir, f"{h}.integration.json")
    if os.path.exists(ip):
        a["quotes"] = json.load(open(ip)).get("quotes", [])
# taxonomy.json (2026-10-28): personas and angles from the product context, by id. Agents write ids ("P1", "A3");
# the page shows "P1 · <name as in the source>" so nothing is renamed or invented.
_tx = os.path.join(OUT, "taxonomy.json")
TX = {}
if os.path.exists(_tx):
    for it in (lambda t: t.get("personas", []) + t.get("angles", []))(json.load(open(_tx))):
        TX[it["id"]] = f'{it["id"]} · {it.get("label_en") or it["name"]}'
tx = lambda v: TX.get(str(v).strip(), v) if v else v
for a in analysis.values():
    a["persona"], a["angle"] = tx(a.get("persona")), tx(a.get("angle"))
    # angle filter (2026-10-28): an account matches its own angle or any of its carousels' angles
    a["angles"] = list(dict.fromkeys(x for x in [a["angle"]] + [tx((c or {}).get("angle")) for c in (a.get("carousels") or {}).values()] if x))
# Short product name ("Notes app") comes from the agent's "product_name"; product_names.json overrides it.
_pn = os.path.join(OUT, "product_names.json")
for h, name in (json.load(open(_pn)) if os.path.exists(_pn) else {}).items():
    if h in analysis: analysis[h]["product_name"] = name
cpath = os.path.join(OUT, "covers.json")
covers = json.load(open(cpath)) if os.path.exists(cpath) else {}
# Topic tags shown as badges: the agent's "tags" list, "lust_focus" -> "lust addiction", plus tags.json {handle: [tags]}.
_tp = os.path.join(OUT, "tags.json")
extra_tags = json.load(open(_tp)) if os.path.exists(_tp) else {}


def tags_of(h):
    an = analysis.get(h, {})
    t = list(an.get("tags") or []) + (["lust addiction"] if an.get("lust_focus") else []) + list(extra_tags.get(h, []))
    return list(dict.fromkeys(t))

def cr_stats(posts):
    """Comment rate (comments / views, %) over the window's carousels: weighted by views and median per post."""
    car = [p for p in posts if p["type"] == "carousel" and p["n_slides"] >= 2 and p["views"]]
    tv = sum(p["views"] for p in car)
    return {"car_comment_rate": round(100 * sum(p["comments"] for p in car) / tv, 3) if tv else None,
            "car_median_comment_rate": round(statistics.median(100 * p["comments"] / p["views"] for p in car), 3)
            if car else None}


def cr_from_account(h):
    path = os.path.join(OUT, "accounts", f"{h}.json")
    return cr_stats(json.load(open(path))["posts"]) if os.path.exists(path) else {}


def christian_of(h):
    """Christian signals: the agent's verdict by slides/captions/bio, else the cover predicate (None = unknown)."""
    an, cv = analysis.get(h, {}), covers.get(h, {})
    if isinstance(an.get("christian"), bool):
        return an["christian"]
    return None if cv.get("p_christian") is None else cv["p_christian"] >= 0.5


def christian_keep(h):
    """Christian rule: Christian accounts in niche or adjacent, non-Christian ones only strictly in niche."""
    niche = analysis.get(h, {}).get("niche_fit") or covers.get(h, {}).get("label", "")
    chr_ = christian_of(h)
    return niche in ("в нише", "смежная ниша") if chr_ else niche == "в нише"


accounts, files = [], []
dropped_by_rule = []
for h, s in scr.items():
    if not s.get("pass"):
        continue
    if args.christian_rule and not christian_keep(h):
        dropped_by_rule.append(h)
        continue
    acc = json.load(open(os.path.join(OUT, "accounts", f"{h}.json")))
    m = {**acc["metrics"], **s}
    an = analysis.get(h, {})
    cv = covers.get(h, {})
    if not an.get("niche_fit") and cv.get("label"):  # no agent analysis: fall back to the cover label
        an = {**an, "niche_fit": cv["label"], "niche_source": "обложки"}
    if args.christian_rule:
        an = {**an, "christian": christian_of(h)}
    an = {**an, "tags": tags_of(h)}
    if args.group_filter:
        an = {**an, "grp": an.get("group") or "-"}
    top5 = sorted([p for p in acc["posts"] if p["type"] == "carousel" and p["n_slides"] >= 2],
                  key=lambda p: -p["views"])[:5]
    cars = []
    for p in top5:
        strip, thumb = f"acc/{h}/strips/{p['id']}.jpg", f"acc/{h}/thumbs/{p['id']}.jpg"
        if args.strip_thumbs:
            thumb = strip
        if not (os.path.exists(os.path.join(OUT, strip)) and os.path.exists(os.path.join(OUT, thumb))):
            continue
        sw, sh = Image.open(os.path.join(OUT, strip)).size
        n = p["n_slides"]
        files += [strip, thumb]
        v = p["views"] or 1
        cars.append({
            "id": p["id"], "url": p["url"], "date": p["date"], "views": p["views"], "likes": p["likes"],
            "comments": p["comments"], "saves": p["saves"], "shares": p["shares"],
            "save_rate": round(100 * p["saves"] / v, 2), "comment_rate": round(100 * p["comments"] / v, 2), "n_slides": n, "strip": strip, "thumb": thumb,
            "ar": f"{round(sw / n)} / {sh}", "music": p["music"], "desc": p["desc"],
            "hook": (an.get("hooks") or {}).get(p["id"], ""),
            "breakdown": (an.get("breakdowns") or {}).get(p["id"]),
        })
    if not cars:
        continue
    keys = ("handle", "url", "nickname", "bio", "bio_link", "followers", "total_likes", "all_time_posts", "tier",
            "posts_win", "carousels_win", "single_photos_win", "videos_win", "carousel_share", "car_total_views",
            "car_median_views", "car_avg_views", "car_total_comments", "car_total_saves", "vid_total_views")
    cr = cr_stats(acc["posts"])
    accounts.append({**{k: m.get(k) for k in keys}, **cr, "carousels": cars, "analysis": an,
                     "note": "★ reference" if h in refs else ""})

NICHE = {"в нише": 0, "смежная ниша": 1, "вне ниши": 2}
CONS = {"высокая": 0, "средняя": 1, "низкая": 2}
MONO = {"подходит": 0, "частично": 1, "цветные": 2}  # optional key: only when the run asked for monochrome tattoos
accounts.sort(key=lambda a: (NICHE.get(a["analysis"].get("niche_fit"), 3), MONO.get(a["analysis"].get("mono_fit"), 1),
                             bool(args.demote_tag) and args.demote_tag in a["analysis"].get("tags", []),
                             not a["analysis"].get("christian") if args.christian_rule else 0,
                             CONS.get(a["analysis"].get("consistency_level"), 3), -a["car_median_views"]))
PIN = [h.strip().lstrip("@") for h in args.pin.split(",") if h.strip()]
accounts.sort(key=lambda a: PIN.index(a["handle"]) if a["handle"] in PIN else len(PIN))
FAV = [h.strip().lstrip("@") for h in args.fav.split(",") if h.strip()]
MARK = {h.strip().lstrip("@") for h in args.mark.split(",") if h.strip()}
for a in accounts:
    if a["handle"] in MARK and not a["note"]: a["note"] = args.mark_label
    if a["handle"] in PIN: a["note"] = "🚩 " + args.pin_label
    a["fav"] = a["handle"] in FAV
accounts.sort(key=lambda a: FAV.index(a["handle"]) if a["handle"] in FAV else len(FAV))
shown = accounts[:args.max_accounts]
keep_h = {a["handle"] for a in shown}
files = [f for f in files if f.split("/")[1] in keep_h]

EN = {"в нише": "in niche", "смежная ниша": "adjacent niche", "вне ниши": "off niche", "высокая": "high", "средняя": "medium",
      "низкая": "low", "карусельный": "carousel-first", "пограничный": "borderline", "видео-аккаунт": "video account",
      "фото-аккаунт": "photo account", "эталон": "reference", "подписка": "follow", "сохранить/поделиться": "save/share",
      "комментарий": "comment", "ссылка в био": "link in bio", "покупка/магазин": "purchase/shop", "запись/услуга": "booking/service",
      "другое": "other", "нет": "none"}
def en_reason(r):
    r = re.sub(r"^карусели (\d+)/(\d+)", r"carousels \1/\2", r).replace(", одиночных фото", ", single photos")
    r = r.replace("медиана", "median").replace("всего", "only").replace(" карусел.", " carousels")
    return r
for a in accounts:
    a["tier"] = EN.get(a["tier"], a["tier"]); a["note"] = EN.get(a["note"], a["note"])
    an = a["analysis"] = dict(a["analysis"])
    for k in ("niche_fit", "consistency_level"):
        if an.get(k): an[k] = EN.get(an[k], an[k])
    an["breakdowns"] = {i: {**b, "cta_type": EN.get(b.get("cta_type"), b.get("cta_type"))} for i, b in (an.get("breakdowns") or {}).items()}
    for c in a["carousels"]:
        if c.get("breakdown") and c["breakdown"].get("cta_type"):
            c["breakdown"] = {**c["breakdown"], "cta_type": EN.get(c["breakdown"]["cta_type"], c["breakdown"]["cta_type"])}


# Super carousels and successful repeats (2026-10-27). Need candidates.json (candidates.py) + ocr/<id>.json and
# analysis/<h>.json from the OCR agents (references/ocr_decide_prompt.md).
cand = json.load(open(os.path.join(OUT, "candidates.json"))) if os.path.exists(os.path.join(OUT, "candidates.json")) else {}
MEDALL = cand.get("median_all", {})


def ocr_of(i):
    q = os.path.join(OUT, "ocr", f"{i}.json")
    return json.load(open(q)) if os.path.exists(q) else {}


def car_card(h, p):
    strip, thumb = f"acc/{h}/strips/{p['id']}.jpg", f"acc/{h}/thumbs/{p['id']}.jpg"
    if args.strip_thumbs:
        thumb = strip
    if not (os.path.exists(os.path.join(OUT, strip)) and os.path.exists(os.path.join(OUT, thumb))):
        return None
    o = {**ocr_of(p["id"]), **((analysis.get(h, {}).get("carousels") or {}).get(p["id"]) or {})}
    med = MEDALL.get(h) or 1
    return {"id": p["id"], "url": p["url"], "date": p["date"], "views": p["views"], "likes": p["likes"], "comments": p["comments"],
            "saves": p["saves"], "n_slides": p["n_slides"], "strip": strip, "thumb": thumb, "x": round(p["views"] / med, 1),
            "hook": o.get("hook") or "", "hook_meaning": o.get("hook_meaning") or "", "formula": o.get("formula") or "",
            "cta": o.get("cta") or "", "format": (o.get("visual") or {}).get("format", ""), "visual": o.get("visual") or {},
            "fit": EN.get(o.get("fit"), o.get("fit") or ""), "persona": tx(o.get("persona")) or "", "angle": tx(o.get("angle")) or "",
            "ocr_scope": o.get("ocr_scope") or ("full" if o else "")}


posts_of = lambda h: {p["id"]: p for p in json.load(open(os.path.join(OUT, "accounts", f"{h}.json")))["posts"]}
card_fit = lambda h, i: EN.get(((analysis.get(h, {}).get("carousels") or {}).get(i) or {}).get("fit"), "")
supers = []
for r in cand.get("super", []):
    if args.drop_off and card_fit(r["handle"], r["id"]) == "off niche":
        continue
    c = car_card(r["handle"], posts_of(r["handle"])[r["id"]])
    if not c:
        continue
    s_ = scr.get(r["handle"], {})
    an = analysis.get(r["handle"], {})
    supers.append({**c, "grp": analysis.get(r["handle"], {}).get("group") or "-", "handle": r["handle"], "acc_url": f"https://www.tiktok.com/@{r['handle']}", "median_all": MEDALL.get(r["handle"]),
                   "followers": s_.get("followers"), "mono": bool(s_.get("pass")), "acc_topic": an.get("topic", "")})
FITORD = {"in niche": 0, "adjacent niche": 1, "off niche": 2}
supers.sort(key=lambda c: (FITORD.get(c["fit"], 3), -c["views"]))
rp = cand.get("params", {})
rep_views, rep_x = rp.get("rep_views", 10_000), rp.get("rep_x", 2)
repeats = []
for h in cand.get("repeat", {}):
    an = analysis.get(h, {})
    po = posts_of(h)
    med = MEDALL.get(h) or 1
    if args.drop_off and an.get("niche_fit") == "вне ниши":
        continue
    for g in an.get("repeats") or []:
        ps = [po[i] for i in g.get("ids", []) if i in po and po[i]["views"] >= rep_views]
        if len(ps) < 3:
            continue
        gmed = statistics.median([p["views"] for p in ps])
        if gmed < rep_x * med:
            continue
        cards = [c for c in (car_card(h, p) for p in sorted(ps, key=lambda p: -p["views"])) if c]
        if len(cards) < 3:
            continue
        repeats.append({"grp": analysis.get(h, {}).get("group") or "-", "handle": h, "acc_url": f"https://www.tiktok.com/@{h}", "hook_template": g.get("hook_template", ""),
                        "formula": g.get("formula", ""), "why": g.get("why", ""), "items": cards, "n": len(cards),
                        "group_median": int(gmed), "group_x": round(gmed / med, 1), "median_all": med,
                        "fit": EN.get(an.get("niche_fit"), an.get("niche_fit", "")), "persona": tx(an.get("persona")) or "",
                        "angle": tx(an.get("angle")) or "", "followers": scr.get(h, {}).get("followers"), "mono": bool(scr.get(h, {}).get("pass"))})
repeats.sort(key=lambda g: (FITORD.get(g["fit"], 3), -g["group_x"]))
if args.max_repeats:
    repeats = repeats[:args.max_repeats]
# Each carousel once (2026-10-28): accounts block > repeats > supers. A repeat member already in an account card
# becomes a compact reference ("ref"); supers drop what blocks 1 and 3 show and backfill from the remaining candidates.
if not args.allow_dupes:
    in_acc = {c["id"] for a in shown for c in a["carousels"]}
    for g in repeats:
        for c in g["items"]:
            if c["id"] in in_acc:
                c["ref"] = g["handle"]
    in_rep = {c["id"] for g in repeats for c in g["items"]}
    n0 = len(supers)
    supers = [c for c in supers if c["id"] not in in_acc and c["id"] not in in_rep]
    print(f"dedup: {n0 - len(supers)} super carousels already in blocks 1/3, "
          f"{sum(1 for g in repeats for c in g['items'] if c.get('ref'))} repeat members shown as references")
if args.max_supers:
    supers = supers[:args.max_supers]
for x in supers + repeats:
    x["note"] = args.mark_label if x["handle"] in MARK else ""
# files only for cards that made it onto the page
for c in supers + [c for g in repeats for c in g["items"] if not c.get("ref")]:
    files.extend([c["strip"], c["thumb"]])
files = list(dict.fromkeys(files))

screened = sorted(scr.values(), key=lambda s: (not s.get("pass"), -(s.get("car_total_views") or 0)))
screened = [{k: s.get(k) for k in ("handle", "url", "posts_win", "carousels_win", "carousel_share", "car_total_views",
                                    "car_median_views", "car_avg_views", "car_total_comments", "vid_total_views",
                                    "pass", "reasons", "error")} for s in screened]
for s in screened:
    s.update(cr_from_account(s["handle"]))
    s["url"] = s["url"] or f"https://www.tiktok.com/@{s['handle']}"
    s["reasons"] = [en_reason(r) for r in (s["reasons"] or [])]


since = params["since"]
fmt_d = lambda d: ".".join(reversed(d.split("-")))
num = lambda n: f"{n:,}".replace(",", " ")
qs = meta["queries"]
data = {
    "intro": (f"TikTok accounts where carousels are the main format and keep pulling views. Candidates are carousel authors "
              f"from TikTok Top search across {len(qs)} queries. Every account was screened on its feed since {fmt_d(since)}. "
              f"Each block shows the account's top 5 carousels on the left, a slide viewer in the middle, account metrics and the breakdown on the right. "
              f"Order: in-niche accounts first, then adjacent and off-niche; within each group by consistency, then median views."),
    "facts": [f"accounts screened: {len(scr)}", f"passed filters: {len(accounts)}",
              f"window {fmt_d(since)} – {fmt_d(date.today().isoformat())}",
              f"carousels ≥ {int(params['min_share'] * 100)}% of posts", f"median ≥ {num(params['min_median'])}",
              f"total ≥ {num(params['min_total'])}", f"carousels ≥ {params['min_carousels']}"],
    "screen_text": (f"Filters count carousels only (photo posts with 2+ slides) inside the window. Carousel-first account: "
                    f"over 50% of posts are carousels; borderline: {int(params['min_share'] * 100)}–50%. Cut: share under "
                    f"{int(params['min_share'] * 100)}%, median under {num(params['min_median'])}, total under "
                    f"{num(params['min_total'])} or fewer than {params['min_carousels']} carousels. Green bar = passed."),
    "footer": [
        "Source: ScrapeCreators. Search <code>/v1/tiktok/search/top</code> for queries: "
        + html.escape(", ".join(qs)) + ". Feed <code>/v3/tiktok/profile/videos</code>, profile <code>/v1/tiktok/profile</code>.",
        "The ScrapeCreators feed can skip individual posts, so counts are a lower bound. Followers as of collection date.",
        "Save rate = saves / views. Comment rate (CR) = comments / views × 100: per account, both the total across the window's carousels and the median per post. Single-photo posts (1 slide) are not counted as carousels.",
    ] + ([f"Showing the first {len(shown)} of {len(accounts)} passing accounts; the rest are in the table."] if len(accounts) > len(shown) else []),
    "summary": {"accounts": len(accounts), "carousels": sum(a["carousels_win"] or 0 for a in accounts),
                "views": sum(a["car_total_views"] or 0 for a in accounts),
                "in_niche": sum(1 for a in accounts if a["analysis"].get("niche_fit") == "in niche"),
                "christian": sum(1 for a in accounts if a["analysis"].get("christian")) if args.christian_rule else None},
    "christian_filter": args.christian_rule,
    "group_filter": [kv.split("=", 1) for kv in args.group_filter.split(",") if "=" in kv],
    "angle_order": list(TX.values()),
    "accounts": shown, "screened": screened, "supers": supers, "repeats": repeats,
    "block_rules": {"super": f"single carousels with ≥ {num(rp.get('super_views', 100_000))} views and ≥ {rp.get('super_x', 5):g}× the account median (all posts in the window)",
                    "repeat": f"3+ carousels of one account with the same meaning-level hook and formula, each ≥ {num(rep_views)} views, group median ≥ {rep_x:g}× the account median"},
}
if args.christian_rule:
    data["facts"][1] = f"passed filters: {len(accounts) + len(dropped_by_rule)}"
    data["facts"].append(f"kept {len(accounts)}: Christian in niche or adjacent, non-Christian only strictly on topic")
tpl = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
page = (tpl.replace("__TITLE__", html.escape(title)).replace("__TOPIC__", html.escape(args.topic))
        .replace("/*DATA*/", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")))
dst = os.path.join(OUT, "carousel-accounts.html")
open(dst, "w", encoding="utf-8").write(page)

cols = ["handle", "url", "pass", "tier", "reasons", "followers", "posts_win", "carousels_win", "single_photos_win",
        "videos_win", "carousel_share", "car_total_views", "car_median_views", "car_avg_views", "car_total_comments",
        "car_total_saves", "car_max_views", "car_comment_rate", "car_median_comment_rate", "vid_total_views", "niche_final", "mono_fit", "cover_mono_label", "cover_p_mono", "cover_p_colour", "niche_source", "cover_label",
        "cover_p_in", "cover_p_adj", "cover_p_out", "cover_p_en", "covers_checked", "christian", "christian_signals",
        "cover_p_christian", "christian_rule", "tags", "found_via", "bio", "bio_link", "capped", "error"]
via = {h: "; ".join(sorted({x["via"].rsplit(" p", 1)[0] for x in xs})) for h, xs in meta.get("handles", {}).items()}
with open(os.path.join(OUT, "accounts.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for s in sorted(scr.values(), key=lambda s: (not s.get("pass"), -(s.get("car_total_views") or 0))):
        row = dict(s)
        row["reasons"] = "; ".join(row.get("reasons") or [])
        row.update(cr_from_account(s["handle"]))
        cv, an = covers.get(s["handle"], {}), analysis.get(s["handle"], {})
        row.update(cover_label=cv.get("label", ""), cover_p_in=cv.get("p_in"), cover_p_adj=cv.get("p_adj"),
                   cover_p_out=cv.get("p_out"), cover_p_en=cv.get("p_en"), covers_checked=cv.get("n_images"))
        row["niche_final"] = an.get("niche_fit") or cv.get("label", "")
        row["mono_fit"] = an.get("mono_fit", "")
        row.update(cover_mono_label=cv.get("mono_label", ""), cover_p_mono=cv.get("p_mono"), cover_p_colour=cv.get("p_colour"))
        row["niche_source"] = "агент по слайдам" if an.get("niche_fit") else ("обложки" if cv.get("label") else "")
        chr_ = christian_of(s["handle"])
        row.update(christian="" if chr_ is None else ("yes" if chr_ else "no"), christian_signals=an.get("christian_signals", ""),
                   cover_p_christian=cv.get("p_christian"), found_via=via.get(s["handle"], ""),
                   tags="; ".join(tags_of(s["handle"])))
        if args.christian_rule and s.get("pass"):
            row["christian_rule"] = "keep" if christian_keep(s["handle"]) else "drop"
        w.writerow(row)

batches, cur, size = [], [], 0
for f in files:
    fs = os.path.getsize(os.path.join(OUT, f))
    if cur and (len(cur) >= 240 or size + fs > 3e6):
        batches.append(cur)
        cur, size = [], 0
    cur.append(f)
    size += fs
if cur:
    batches.append(cur)
json.dump(batches, open(os.path.join(OUT, "publish_batches.json"), "w"), indent=0)
total_mb = sum(os.path.getsize(os.path.join(OUT, f)) for f in files) / 1e6
print(f"built {dst} ({os.path.getsize(dst) // 1024} KB): {len(shown)} accounts shown of {len(accounts)} passing, "
      f"{len(files)} files {total_mb:.1f} MB in {len(batches)} publish batch(es)")
if args.christian_rule:
    print(f"christian rule: kept {len(accounts)}, dropped {len(dropped_by_rule)}: {', '.join(dropped_by_rule) or '-'}")
missing = [a["handle"] for a in shown if not a["analysis"]]
if missing:
    print("WARN no analysis for:", ", ".join(missing))
