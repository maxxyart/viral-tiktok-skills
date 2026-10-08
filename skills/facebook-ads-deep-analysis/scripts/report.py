#!/usr/bin/env python3
"""Render the Facebook ads deep-analysis HTML report.

Numbers come from the data: the enriched CSV (analyze.py output), the
facebook-ads-short-analysis sidecars and the impression ranks. Words come from
insights.json written by the agent after reading the enriched rows. The
renderer never invents findings: every cluster, pain, format and adaptation is
tied to ad_archive_ids, and the script computes their reach shares itself.

Reach weight: Meta exposes only an impression rank, so each ranked ad weighs
1/sqrt(rank). Shares are a ranking proxy, not view counts.

Usage:
  python3 report.py --enriched-csv acme_top_enriched.csv --insights insights.json \
      [--out acme_report.html] [--media videos|posters|none] [--lang ru|en]
"""
import argparse, base64, collections, csv, html, json, math, os, re, sys, time
import urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, urlparse

E = lambda s: html.escape(str(s if s is not None else ""))

L = {
 "ru": dict(kpi_ads="объявлений в выборке", kpi_ok="разобрано моделью", kpi_cr="уникальных креативов",
   kpi_max="макс. объявлений на один креатив", kpi_inactive="остановлено", tldr="Коротко",
   angles="Энглы по весу показов", angle="Энгл", share="Доля веса", best="Лучший ранг", top10="Топ-10",
   top25="Топ-25", ads="Объявл.", creatives="Креативов", maxdays="Дней макс", formats="Форматы",
   fmt="Формат", clusters="Энглы", pmoment="Когда продукт на экране", length="Длина",
   angles_cards="Энглы с креативами", cta="Call to action", cta_video="В самих креативах",
   cta_type="Тип CTA", cta_ad="В объявлении: заголовок, текст, кнопка", title="Заголовок",
   body="Текст объявления", button="Кнопка", buttons="Кнопки", active="активные", inactive="остановленные",
   pains="Боли", pain="Боль", weight="Вес", testing="Как они тестируют", launches="Запуски активных объявлений по неделям",
   week="Неделя", adapt="Что взять себе", avoid="Что не брать", gallery="Все креативы по рангу",
   show="Показать галерею", rank="ранг", n_ads="объявл.", app="продукт на экране", voice="Сценарий",
   example="пример", unassigned="Не размечено", limits="Ограничения данных", more="Ещё креативы",
   hook="Хук", stale="ссылка устарела", lim_rank="Meta показывает только порядок по показам, без цифр. Вес объявления 1/√ранг, доли считаются от суммы весов всех ранжированных объявлений выборки.",
   lim_ok="Моделью разобрано {ok} из {n} объявлений; доли энглов считаются только по размеченным.",
   lim_dco="В DCO и каруселях разбирается первый креатив, а вес объявления целиком идёт ему.",
   lim_un="{un:.0f}% веса приходится на объявления без энгла (не разобраны или не размечены)."),
 "en": dict(kpi_ads="ads in the sample", kpi_ok="analyzed by the model", kpi_cr="unique creatives",
   kpi_max="max ads per creative", kpi_inactive="stopped", tldr="Summary",
   angles="Angles by reach weight", angle="Angle", share="Reach share", best="Best rank", top10="Top 10",
   top25="Top 25", ads="Ads", creatives="Creatives", maxdays="Max days", formats="Formats",
   fmt="Format", clusters="Angles", pmoment="Product on screen", length="Length",
   angles_cards="Angles with creatives", cta="Call to action", cta_video="Inside the creatives",
   cta_type="CTA type", cta_ad="In the ad: headline, text, button", title="Headline",
   body="Ad text", button="Button", buttons="Buttons", active="active", inactive="stopped",
   pains="Pains", pain="Pain", weight="Weight", testing="How they test", launches="Active ad launches by week",
   week="Week", adapt="What to borrow", avoid="What not to borrow", gallery="All creatives by rank",
   show="Show gallery", rank="rank", n_ads="ads", app="product on screen", voice="Script",
   example="example", unassigned="Unassigned", limits="Data limits", more="More creatives",
   hook="Hook", stale="link expired", lim_rank="Meta shows only an impression rank, no numbers. Each ad weighs 1/sqrt(rank); shares are relative to all ranked ads in the sample.",
   lim_ok="The model analyzed {ok} of {n} ads; angle shares use labelled ads only.",
   lim_dco="For DCO and carousels the first creative is analyzed and receives the whole ad weight.",
   lim_un="{un:.0f}% of the weight sits on ads without an angle (not analyzed or not labelled)."),
}


def md(s):
    """Escape, then allow **bold** and [text](https://url)."""
    s = E(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    return re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
                  r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)


def to_int(v, default=None):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def asset_key(url):
    """Stable id of a media file: fbcdn efg.xpv_asset_id, else the file name."""
    if not url:
        return ""
    try:
        e = parse_qs(urlparse(url).query)["efg"][0]
        aid = json.loads(base64.urlsafe_b64decode(e + "=" * (-len(e) % 4))).get("xpv_asset_id")
        if aid:
            return str(aid)
    except Exception:
        pass
    return re.sub(r"[^A-Za-z0-9_-]", "", Path(urlparse(url).path).stem)[:60]


def find_sidecar(csv_path, suffix):
    d = Path(csv_path).resolve().parent
    stem = Path(csv_path).stem
    for cut in ("_top_enriched", "_enriched", "_by_impressions", "_ads"):
        if cut in stem:
            p = d / (stem.split(cut)[0] + suffix)
            if p.exists():
                return p
    hits = sorted(d.glob("*" + suffix))
    return hits[0] if len(hits) == 1 else None


def fetch(url, dest, retries=3):
    if dest.exists() and dest.stat().st_size > 0:
        return "ok"
    delay = 1.0
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            dest.write_bytes(data)
            return "ok"
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410):
                return "stale"
            if attempt == retries:
                return f"error:{e.code}"
        except Exception as e:
            if attempt == retries:
                return f"error:{type(e).__name__}"
        time.sleep(delay)
        delay *= 2


def load_insights(path):
    ins = json.load(open(path, encoding="utf-8"))
    for k in ("title", "clusters"):
        if k not in ins:
            sys.exit(f"ERROR: insights.json needs '{k}'")
    return ins


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--enriched-csv", required=True)
    ap.add_argument("--insights", required=True, help="agent-written insights.json")
    ap.add_argument("--out", default="")
    ap.add_argument("--full-json", default="", help="<prefix>_ads_full.json (auto-detected)")
    ap.add_argument("--inactive-csv", default="", help="<prefix>_inactive.csv (auto-detected)")
    ap.add_argument("--media", choices=["videos", "posters", "none"], default="videos",
                    help="download creatives next to the report (fbcdn links expire in ~1 day)")
    ap.add_argument("--media-dir", default="media")
    ap.add_argument("--cards-per-angle", type=int, default=6)
    ap.add_argument("--lang", choices=["ru", "en"], default="ru")
    args = ap.parse_args()
    T = L[args.lang]

    rows = list(csv.DictReader(open(args.enriched_csv, encoding="utf-8")))
    if not rows:
        sys.exit("ERROR: empty enriched CSV")
    ins = load_insights(args.insights)
    out = Path(args.out or Path(args.enriched_csv).with_name(Path(args.enriched_csv).stem.replace("_enriched", "") + "_report.html"))
    full_json = Path(args.full_json) if args.full_json else find_sidecar(args.enriched_csv, "_ads_full.json")
    inactive_csv = Path(args.inactive_csv) if args.inactive_csv else find_sidecar(args.enriched_csv, "_inactive.csv")
    pages = {}
    if full_json and full_json.exists():
        for a in json.load(open(full_json, encoding="utf-8")):
            pages[str(a.get("ad_archive_id"))] = (a.get("snapshot") or {}).get("page_name") or a.get("page_name")
    inactive = list(csv.DictReader(open(inactive_csv, encoding="utf-8"))) if inactive_csv and inactive_csv.exists() else []

    by_id = {r["ad_archive_id"]: r for r in rows}
    for r in rows:
        r["_rank"] = to_int(r.get("impression_rank"))
        r["_w"] = 1 / math.sqrt(r["_rank"]) if r["_rank"] else 0.0
        r["_ok"] = str(r.get("analysis_status", "")).startswith("ok")
        r["_days"] = to_int(r.get("days_running"), 0)
        vurl = r.get("video_hd_url") or r.get("video_sd_url") or ""
        iurl = r.get("image_url") or r.get("video_preview_image_url") or ""
        r["_video"], r["_poster"] = vurl, iurl
        r["_key"] = asset_key(vurl or iurl) or r["ad_archive_id"]
    total_w = sum(r["_w"] for r in rows) or 1.0

    # ---- clusters from insights, validated against the data ----
    assign, problems = {}, []
    for c in ins["clusters"]:
        for aid in c.get("ad_ids", []):
            aid = str(aid)
            if aid not in by_id:
                problems.append(f"cluster {c.get('id')}: unknown ad_archive_id {aid}")
            elif aid in assign:
                problems.append(f"ad {aid} is in clusters {assign[aid]} and {c.get('id')}")
            else:
                assign[aid] = c.get("id")
    if problems:
        sys.exit("ERROR in insights.json:\n  " + "\n  ".join(problems[:20]))

    creatives = collections.OrderedDict()
    for r in sorted(rows, key=lambda r: (r["_rank"] or 10**6, not r["_ok"])):
        c = creatives.setdefault(r["_key"], {"key": r["_key"], "rows": [], "rep": None})
        c["rows"].append(r)
        if c["rep"] is None and r["_ok"]:
            c["rep"] = r
    for c in creatives.values():
        c["rep"] = c["rep"] or c["rows"][0]
        ranks = [r["_rank"] for r in c["rows"] if r["_rank"]]
        c["best"] = min(ranks) if ranks else None
        c["n_ads"] = len(c["rows"])
        c["cluster"] = next((assign[r["ad_archive_id"]] for r in c["rows"] if r["ad_archive_id"] in assign), None)

    stats = {}
    for c in ins["clusters"]:
        ids = [str(a) for a in c.get("ad_ids", [])]
        rs = [by_id[a] for a in ids]
        ranks = [r["_rank"] for r in rs if r["_rank"]]
        stats[c["id"]] = dict(
            share=sum(r["_w"] for r in rs) / total_w, best=min(ranks) if ranks else None,
            top10=sum(1 for x in ranks if x <= 10), top25=sum(1 for x in ranks if x <= 25),
            ads=len(rs), creatives=len({r["_key"] for r in rs}), maxdays=max([r["_days"] for r in rs] or [0]))
    unassigned = sum(r["_w"] for r in rows if r["ad_archive_id"] not in assign) / total_w
    share_of = lambda ids: sum(stats[i]["share"] for i in ids if i in stats)

    # ---- media ----
    media_dir = out.parent / args.media_dir
    media_state = {}
    if args.media != "none":
        media_dir.mkdir(parents=True, exist_ok=True)
        jobs = []
        for c in creatives.values():
            rep = c["rep"]
            if rep["_poster"]:
                jobs.append((c["key"], "jpg", rep["_poster"]))
            if args.media == "videos" and rep["_video"]:
                jobs.append((c["key"], "mp4", rep["_video"]))
        with ThreadPoolExecutor(8) as pool:
            res = list(pool.map(lambda j: (j, fetch(j[2], media_dir / f"{j[0]}.{j[1]}")), jobs))
        for (key, ext, _), st in res:
            media_state[(key, ext)] = st
        bad = collections.Counter(st for st in media_state.values() if st != "ok")
        if bad:
            print(f"[WARN] media not downloaded: {dict(bad)} – stale links mean the short-analysis CSV is older than ~1 day", file=sys.stderr)

    def media_src(c, ext, remote):
        if media_state.get((c["key"], ext)) == "ok":
            return f"{args.media_dir}/{c['key']}.{ext}"
        return remote

    def card(c):
        r = c["rep"]
        poster = media_src(c, "jpg", r["_poster"])
        if r["_video"]:
            vid = media_src(c, "mp4", r["_video"])
            media = f'<video controls preload="none" playsinline poster="{E(poster)}" src="{E(vid)}"></video>'
        elif poster:
            media = f'<img loading="lazy" src="{E(poster)}" alt="">'
        else:
            media = '<div class="nomedia"></div>'
        page = pages.get(r["ad_archive_id"]) or ""
        chips = [f'<span class="chip rank">{T["rank"]} {E(c["best"] or "—")}</span>',
                 f'<span class="chip">{c["n_ads"]} {T["n_ads"]}</span>',
                 f'<span class="chip">{E(r.get("media_type") or r.get("display_format"))}</span>',
                 f'<span class="chip">{r["_days"]} d</span>']
        hook = r.get("hook_text_overlay") or r.get("visual_hook", "")[:120] or "—"
        lines = [f'<p class="hook">«{E(hook)}»</p>']
        if r.get("script"):
            lines.append(f'<p class="meta"><b>{T["voice"]}:</b> {E(r["script"][:220])}</p>')
        if r.get("product_moment"):
            lines.append(f'<p class="meta"><b>{T["app"]}:</b> {E(r["product_moment"][:120])}</p>')
        if r.get("cta"):
            lines.append(f'<p class="meta"><b>CTA:</b> {E(r["cta"][:140])}</p>')
        if page:
            lines.append(f'<p class="meta">{E(page)}</p>')
        return (f'<figure class="vcard">{media}<figcaption><div class="chips">{"".join(chips)}</div>'
                f'{"".join(lines)}<a href="{E(r.get("ad_library_url") or "https://www.facebook.com/ads/library/?id=" + r["ad_archive_id"])}" '
                f'target="_blank" rel="noopener">Ad Library ↗</a></figcaption></figure>')

    def ref_links(ids):
        out_ = []
        for aid in ids:
            r = by_id.get(str(aid))
            label = f'{T["rank"]} {r["_rank"]}' if r and r["_rank"] else str(aid)
            out_.append(f'<a href="https://www.facebook.com/ads/library/?id={E(aid)}" target="_blank" rel="noopener">{E(label)} ↗</a>')
        return " · ".join(out_)

    # ---- sections ----
    n_ok = sum(r["_ok"] for r in rows)
    mix = collections.Counter((r.get("media_type") or "?") for r in rows)
    kpis = [(len(rows), T["kpi_ads"] + "<br>" + ", ".join(f"{v} {k}" for k, v in mix.most_common())),
            (n_ok, T["kpi_ok"]), (len(creatives), T["kpi_cr"]),
            (max(c["n_ads"] for c in creatives.values()), T["kpi_max"])]
    if inactive:
        kpis.append((len(inactive), T["kpi_inactive"]))
    kpis += [(k.get("value"), E(k.get("label"))) for k in ins.get("kpis", [])]
    kpi_html = "".join(f'<div class="kpi"><b>{E(v)}</b><span>{lab}</span></div>' for v, lab in kpis)

    tldr = "".join(f"<li>{md(x)}</li>" for x in ins.get("tldr", []))
    cl_sorted = sorted(ins["clusters"], key=lambda c: -stats[c["id"]]["share"])
    maxshare = max([stats[c["id"]]["share"] for c in cl_sorted] + [1e-9])
    angle_rows = []
    for c in cl_sorted:
        s = stats[c["id"]]
        angle_rows.append(
            f'<tr><td><a href="#cl-{E(c["id"])}">{E(c["id"])}. {E(c["name"])}</a></td>'
            f'<td><div class="bar"><span style="width:{100*s["share"]/maxshare:.0f}%"></span></div>{100*s["share"]:.1f}%</td>'
            f'<td class="num">{E(s["best"] or "—")}</td><td class="num">{s["top10"]}</td><td class="num">{s["top25"]}</td>'
            f'<td class="num">{s["ads"]}</td><td class="num">{s["creatives"]}</td><td class="num">{s["maxdays"]}</td></tr>')
    if unassigned > 0.0005:
        angle_rows.append(f'<tr class="muted"><td>{T["unassigned"]}</td><td>{100*unassigned:.1f}%</td><td colspan="6"></td></tr>')

    fmt_rows = "".join(
        f'<tr><td>{md(f.get("name"))}</td><td>{E(", ".join(f.get("clusters", [])))}</td>'
        f'<td class="num">{100*share_of(f.get("clusters", [])):.0f}%</td><td>{md(f.get("product_moment", ""))}</td>'
        f'<td>{md(f.get("length", ""))}</td></tr>' for f in ins.get("formats", []))
    fmt_notes = "".join(f"<li>{md(x)}</li>" for x in ins.get("format_notes", []))

    blocks = []
    for c in cl_sorted:
        s = stats[c["id"]]
        crs = [x for x in creatives.values() if x["cluster"] == c["id"]]
        shown, rest = crs[:args.cards_per_angle], crs[args.cards_per_angle:]
        more = (f'<details><summary>{T["more"]}: {len(rest)}</summary><div class="grid">{"".join(card(x) for x in rest)}</div></details>'
                if rest else "")
        blocks.append(
            f'<section class="angle" id="cl-{E(c["id"])}"><h3>{E(c["id"])}. {E(c["name"])}</h3>'
            f'<div class="stats"><span><b>{100*s["share"]:.1f}%</b> {T["share"].lower()}</span>'
            f'<span>{T["best"].lower()} <b>{E(s["best"] or "—")}</b></span><span><b>{s["top25"]}</b> {T["top25"].lower()}</span>'
            f'<span><b>{s["ads"]}</b> {T["ads"].lower()}</span><span><b>{s["creatives"]}</b> {T["creatives"].lower()}</span></div>'
            + (f'<p><b>{T["fmt"]}:</b> {md(c["format"])}</p>' if c.get("format") else "")
            + (f'<p>{md(c["description"])}</p>' if c.get("description") else "")
            + (f'<p class="verdict">{md(c["verdict"])}</p>' if c.get("verdict") else "")
            + f'<div class="grid">{"".join(card(x) for x in shown)}</div>{more}</section>')

    cta_rows = []
    for g in ins.get("cta_groups", []):
        ids = [str(a) for a in g.get("ad_ids", []) if str(a) in by_id]
        ranks = [by_id[a]["_rank"] for a in ids if by_id[a]["_rank"]]
        ex = min(ids, key=lambda a: by_id[a]["_rank"] or 10**6) if ids else None
        cta_rows.append(f'<tr><td>{md(g.get("name"))}</td><td class="num">{len(ids)}</td>'
                        f'<td class="num">{100*sum(by_id[a]["_w"] for a in ids)/total_w:.0f}%</td>'
                        f'<td class="num">{E(min(ranks) if ranks else "—")}</td><td>{ref_links([ex]) if ex else ""}</td></tr>')
    cta_notes = "".join(f"<li>{md(x)}</li>" for x in ins.get("cta_notes", []))

    copy = collections.defaultdict(lambda: {"n": 0, "t10": 0, "t25": 0, "best": 10**6, "ids": []})
    for r in rows:
        key = (r.get("display_format") or r.get("media_type") or "", (r.get("title") or "—").strip(),
               re.sub(r"\s+", " ", (r.get("body_text") or "").strip())[:400], r.get("cta_text") or "")
        d = copy[key]; rk = r["_rank"] or 10**6
        d["n"] += 1; d["t10"] += rk <= 10; d["t25"] += rk <= 25; d["best"] = min(d["best"], rk); d["ids"].append(r["ad_archive_id"])
    copy_rows = "".join(
        f'<tr><td>{E(k[0])}</td><td>{E(k[1])}</td><td class="body">{E(k[2])}</td><td>{E(k[3])}</td>'
        f'<td class="num">{d["n"]}</td><td class="num">{d["t10"]}</td><td class="num">{d["t25"]}</td>'
        f'<td class="num">{d["best"] if d["best"] < 10**6 else "—"}</td><td>{ref_links([min(d["ids"], key=lambda a: by_id[a]["_rank"] or 10**6)])}</td></tr>'
        for k, d in sorted(copy.items(), key=lambda kv: kv[1]["best"])[:20])
    btn_a = collections.Counter(r.get("cta_text") or "—" for r in rows)
    btn_i = collections.Counter(r.get("cta_text") or "—" for r in inactive)
    btn_rows = "".join(f'<tr><td>{E(b)}</td><td class="num">{btn_a.get(b, 0)}</td>' + (f'<td class="num">{btn_i.get(b, 0)}</td>' if inactive else "") + "</tr>"
                       for b in sorted(set(btn_a) | set(btn_i), key=lambda b: -(btn_a.get(b, 0) + btn_i.get(b, 0))))
    copy_notes = "".join(f"<li>{md(x)}</li>" for x in ins.get("copy_notes", []))

    pain_rows = "".join(
        f'<tr><td>{md(p.get("pain"))}</td><td>{E(", ".join(p.get("clusters", [])))}</td>'
        f'<td class="num">{100*share_of(p.get("clusters", [])):.0f}%</td></tr>' for p in ins.get("pains", []))
    pain_gap = f'<p>{md(ins["pain_gap"])}</p>' if ins.get("pain_gap") else ""

    weeks = collections.Counter()
    for r in rows:
        st = to_int(r.get("start_date"))
        if st:
            weeks[time.strftime("%Y-%m-%d", time.gmtime(st - (time.gmtime(st).tm_wday * 86400)))] += 1
    week_rows = "".join(f'<tr><td>{w}</td><td class="num">{n}</td></tr>' for w, n in sorted(weeks.items())[-12:])
    testing = "".join(f"<li>{md(x)}</li>" for x in ins.get("testing_notes", []))

    adapt = "".join(
        f'<li><b>{md(a.get("title", ""))}</b> {md(a.get("text", ""))}'
        + (f'<br><span class="refs">{ref_links(a.get("refs", []))}</span>' if a.get("refs") else "") + "</li>"
        for a in ins.get("adaptations", []))
    avoid = "".join(f"<li>{md(x)}</li>" for x in ins.get("avoid", []))
    limits = [T["lim_rank"], T["lim_ok"].format(ok=n_ok, n=len(rows)), T["lim_dco"]]
    if unassigned > 0.0005:
        limits.append(T["lim_un"].format(un=100 * unassigned))
    limits += ins.get("limits", [])
    gallery = "".join(card(c) for c in creatives.values() if c["rep"]["_ok"])

    def section(title, body, cond=True):
        return f"<h2>{title}</h2>{body}" if cond else ""

    sub = md(ins.get("subtitle", ""))
    page_html = f'''<!doctype html><html lang="{args.lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(ins["title"])}</title>
<style>
:root{{--bg:#f7f6f3;--card:#fff;--ink:#1d1d1f;--mute:#6b6b70;--line:#e4e2dc;--acc:#3a5bd9;--acc2:#e8edff}}
@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{--bg:#141416;--card:#1d1d21;--ink:#ececf0;--mute:#9a9aa3;--line:#2e2e34;--acc:#8aa2ff;--acc2:#252b45}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif}}
main{{max-width:1240px;margin:0 auto;padding:32px 16px 80px}}
h1{{font-size:30px;margin:0 0 4px}}h2{{font-size:22px;margin:48px 0 12px;padding-top:12px;border-top:1px solid var(--line)}}h3{{font-size:18px;margin:0 0 8px}}
a{{color:var(--acc)}}.sub{{color:var(--mute);margin:0 0 20px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:16px 0}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px}}.kpi b{{font-size:24px;display:block}}.kpi span{{color:var(--mute);font-size:13px}}
.tldr{{background:var(--acc2);border-radius:14px;padding:16px 20px}}.tldr li{{margin:6px 0}}
.tw{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;background:var(--card);border-radius:12px;overflow:hidden;font-size:14px}}
th,td{{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}th{{color:var(--mute);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.03em}}
td.num{{text-align:right;font-variant-numeric:tabular-nums}}td.body{{max-width:380px;color:var(--mute)}}tr.muted td{{color:var(--mute)}}
.bar{{display:inline-block;width:90px;height:8px;background:var(--line);border-radius:4px;margin-right:8px;vertical-align:middle}}.bar span{{display:block;height:100%;background:var(--acc);border-radius:4px}}
.angle{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px;margin:18px 0}}
.stats{{display:flex;flex-wrap:wrap;gap:6px 16px;color:var(--mute);font-size:13px;margin-bottom:8px}}.stats b{{color:var(--ink)}}
.verdict{{font-weight:600}}.refs{{font-size:13px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:14px;margin-top:12px}}
.vcard{{margin:0;background:var(--bg);border:1px solid var(--line);border-radius:12px;overflow:hidden;display:flex;flex-direction:column}}
.vcard video,.vcard img,.nomedia{{width:100%;aspect-ratio:9/16;object-fit:cover;background:#000;display:block}}
.vcard img{{object-fit:contain}}.vcard figcaption{{padding:10px 12px;font-size:13px}}.vcard p{{margin:4px 0}}.hook{{font-weight:600;font-size:14px}}.meta{{color:var(--mute)}}
.chips{{display:flex;flex-wrap:wrap;gap:4px}}.chip{{font-size:11px;padding:2px 7px;border-radius:999px;background:var(--line);color:var(--ink)}}.chip.rank{{background:var(--acc);color:#fff}}
details summary{{cursor:pointer;font-weight:600;margin:12px 0}}.note{{color:var(--mute);font-size:13px}}
@media (max-width:600px){{.grid{{grid-template-columns:repeat(2,1fr);gap:8px}}h1{{font-size:24px}}}}
</style></head><body><main>
<h1>{E(ins["title"])}</h1><p class="sub">{sub}</p>
<div class="kpis">{kpi_html}</div>
{f'<div class="tldr"><b>{T["tldr"]}</b><ul>{tldr}</ul></div>' if tldr else ""}
<h2>1. {T["angles"]}</h2><p class="note">{T["lim_rank"]}</p>
<div class="tw"><table><tr><th>{T["angle"]}</th><th>{T["share"]}</th><th>{T["best"]}</th><th>{T["top10"]}</th><th>{T["top25"]}</th><th>{T["ads"]}</th><th>{T["creatives"]}</th><th>{T["maxdays"]}</th></tr>{"".join(angle_rows)}</table></div>
{section("2. " + T["formats"], f'<div class="tw"><table><tr><th>{T["fmt"]}</th><th>{T["clusters"]}</th><th>{T["share"]}</th><th>{T["pmoment"]}</th><th>{T["length"]}</th></tr>{fmt_rows}</table></div><ul>{fmt_notes}</ul>', bool(fmt_rows or fmt_notes))}
<h2>3. {T["angles_cards"]}</h2>{"".join(blocks)}
<h2>4. {T["cta"]}</h2>
{f'<h3>{T["cta_video"]}</h3><div class="tw"><table><tr><th>{T["cta_type"]}</th><th>{T["creatives"]}</th><th>{T["share"]}</th><th>{T["best"]}</th><th></th></tr>{"".join(cta_rows)}</table></div>' if cta_rows else ""}
<ul>{cta_notes}</ul>
<h3>{T["cta_ad"]}</h3>
<div class="tw"><table><tr><th>{T["fmt"]}</th><th>{T["title"]}</th><th>{T["body"]}</th><th>{T["button"]}</th><th>{T["ads"]}</th><th>{T["top10"]}</th><th>{T["top25"]}</th><th>{T["best"]}</th><th></th></tr>{copy_rows}</table></div>
<h3>{T["buttons"]}</h3><div class="tw"><table><tr><th>{T["button"]}</th><th>{T["active"]}</th>{f'<th>{T["inactive"]}</th>' if inactive else ""}</tr>{btn_rows}</table></div>
<ul>{copy_notes}</ul>
{section("5. " + T["pains"], f'<div class="tw"><table><tr><th>{T["pain"]}</th><th>{T["clusters"]}</th><th>{T["weight"]}</th></tr>{pain_rows}</table></div>{pain_gap}', bool(pain_rows))}
<h2>6. {T["testing"]}</h2><ul>{testing}</ul>
<h3>{T["launches"]}</h3><div class="tw"><table><tr><th>{T["week"]}</th><th>{T["ads"]}</th></tr>{week_rows}</table></div>
{section("7. " + T["adapt"], f"<ul>{adapt}</ul>", bool(adapt))}
{section(T["avoid"], f"<ul>{avoid}</ul>", bool(avoid))}
<h2>{T["gallery"]}</h2><details><summary>{T["show"]} ({sum(1 for c in creatives.values() if c["rep"]["_ok"])})</summary><div class="grid">{gallery}</div></details>
<h2>{T["limits"]}</h2><ul class="note">{"".join(f"<li>{md(x)}</li>" for x in limits)}</ul>
</main>
<script>document.addEventListener('play',e=>{{document.querySelectorAll('video').forEach(v=>{{if(v!==e.target)v.pause()}})}},true);</script>
</body></html>'''
    out.write_text(page_html, encoding="utf-8")
    ok_media = sum(1 for v in media_state.values() if v == "ok")
    print(f"Report: {out}")
    print(f"Angles: {len(ins['clusters'])} | labelled ads: {len(assign)}/{len(rows)} | unassigned weight: {100*unassigned:.1f}%")
    if args.media != "none":
        print(f"Media: {ok_media}/{len(media_state)} files in {media_dir} (keep the folder next to the HTML)")


if __name__ == "__main__":
    main()
