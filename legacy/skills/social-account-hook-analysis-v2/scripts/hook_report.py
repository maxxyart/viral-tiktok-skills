#!/usr/bin/env python3
"""Render portable HTML with metrics, cover evidence, and agent-authored insights."""
import argparse
import base64
import csv
import html
import math
from pathlib import Path
from urllib.parse import urlparse

from social import csv_cell, load


def esc(value):
    return html.escape(str(value), quote=True)


def fmt(value):
    if value is None:
        return "N/A"
    if isinstance(value, str):
        return esc(value)
    return f"{value:,.2f}".rstrip("0").rstrip(".") if not float(value).is_integer() else f"{int(value):,}"


def link(url, text):
    if not url or urlparse(url).scheme not in ("https", "http"):
        return esc(text)
    return f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(text)} ↗</a>'


def image(path, out, alt):
    if not path:
        return '<div class="missing">Cover unavailable</div>'
    p = (out / path).resolve()
    if not p.is_relative_to(out.resolve()) or not p.is_file() or p.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        return '<div class="missing">Cover unavailable</div>'
    mime = "jpeg" if p.suffix.lower() in {".jpg", ".jpeg"} else p.suffix[1:].lower()
    return f'<img loading="lazy" alt="{esc(alt)}" src="data:image/{mime};base64,{base64.b64encode(p.read_bytes()).decode()}">'


def table(headers, lines):
    return '<div class="scroll"><table><thead><tr>' + ''.join(f'<th>{esc(h)}</th>' for h in headers) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f'<td>{v}</td>' for v in row) + '</tr>' for row in lines) + '</tbody></table></div>'


def transcript_csv(out, rows, transcripts):
    if not transcripts:
        return
    fields = ["recent_rank", "id", "published_at_utc", "url", "views", "likes", "comments", "shares", "saves",
              "duration_seconds", "virality_multiplier", "comment_rate_pct", "hook_text_exact", "hook_status",
              "text_formula", "visual_format", "character_role", "cover_status", "cover_file",
              "audio_status", "audio_language", "spoken_first_3s", "audio_transcript"]
    with (out / "videos_with_transcripts.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            t = transcripts.get(str(row["id"]), {})
            values = {key: row.get(key) for key in fields}
            values.update(audio_status=t.get("status"), audio_language=t.get("language"),
                          spoken_first_3s=t.get("opening_0_3s"), audio_transcript=t.get("transcript"))
            writer.writerow({key: csv_cell(value) for key, value in values.items()})


def scatter(rows):
    """A descriptive, linked view-multiple × comment-rate map."""
    valid = [r for r in rows if r.get("virality_multiplier") is not None and r.get("comment_rate_pct") is not None]
    if not valid:
        return '<p>Недостаточно данных для карты.</p>'
    xmax = max(1, max(r["virality_multiplier"] for r in valid))
    ymax = max(.01, max(r["comment_rate_pct"] for r in valid))
    parts = ['<svg class="plot" viewBox="0 0 920 430" role="img" aria-label="Просмотры к медиане и доля комментариев">']
    for tick in (0, .25, .5, .75, 1):
        y = 25 + 350 * (1 - tick)
        parts.append(f'<line x1="65" x2="880" y1="{y:.1f}" y2="{y:.1f}" class="gridline"/><text x="58" y="{y+4:.1f}" text-anchor="end">{fmt(ymax*tick)}%</text>')
    for tick in sorted({0, 1, 3, 10, round(xmax)}):
        if tick > xmax:
            continue
        x = 65 + 815 * math.log1p(tick) / math.log1p(xmax)
        parts.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="25" y2="375" class="gridline"/><text x="{x:.1f}" y="400" text-anchor="middle">{tick}×</text>')
    for r in valid:
        x = 65 + 815 * math.log1p(r["virality_multiplier"]) / math.log1p(xmax)
        y = 25 + 350 * (1 - r["comment_rate_pct"] / ymax)
        title = f'#{r["recent_rank"]} · {r.get("hook_text_exact") or r["id"]} · {fmt(r["views"])} просмотров · {fmt(r["comment_rate_pct"])}% CR'
        dot = f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" class="dot"><title>{esc(title)}</title></circle>'
        url = r.get("url")
        parts.append(f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{dot}</a>' if url and urlparse(url).scheme in ("http", "https") else dot)
    parts.append('</svg>')
    return ''.join(parts)


def render(out, insights=None, lang="ru"):
    stats, rows = load(out / "analysis.json"), load(out / "analyzed-videos.json")
    transcripts_path = out / "transcripts.json"
    transcript_rows = load(transcripts_path) if transcripts_path.exists() else []
    transcripts = {str(t["id"]): t for t in transcript_rows}
    selected_ids = {str(r["id"]) for r in rows}
    if len(transcripts) != len(transcript_rows) or not set(transcripts) <= selected_ids:
        raise ValueError("Audio transcripts must have unique IDs from the selected cohort")
    transcript_csv(out, rows, transcripts)
    snap, overall = stats["snapshot"], stats["overall"]
    labels = {
        "ru": {"title": "Хуки и визуальные приёмы", "summary": "Коротко", "map": "Карта роликов", "metrics": "Метрики", "months": "Месяцы публикации", "top": "Лидеры по просмотрам", "patterns": "Повторяющиеся приёмы", "insights": "Выводы и гипотезы", "sheets": "Обложки по 20", "catalog": "Все ролики", "methods": "Данные и ограничения", "draft": "Черновик данных: добавьте проверенные выводы в insights.json.", "text_formula": "Текстовые формулы", "visual_format": "Визуальные приёмы", "character_role": "Роли персонажей", "text_x_visual": "Текст × визуал"},
        "en": {"title": "Hooks and visual techniques", "summary": "In brief", "map": "Video map", "metrics": "Metrics", "months": "Publication months", "top": "Most viewed", "patterns": "Recurring techniques", "insights": "Findings and hypotheses", "sheets": "Cover sheets of 20", "catalog": "All videos", "methods": "Data and limitations", "draft": "Data draft: add verified findings in insights.json.", "text_formula": "Text formulas", "visual_format": "Visual techniques", "character_role": "Character roles", "text_x_visual": "Text × visual"},
    }
    if lang not in labels:
        raise ValueError("--lang must be ru or en")
    t = labels[lang]
    by_id = {r["id"]: r for r in rows}
    for item in (insights or {}).get("summary", []):
        if not set(item.get("reference_ids", [])) <= by_id.keys():
            raise ValueError("Summary cites a video outside the selected cohort")
    dates = [r["published_at_utc"][:10] for r in rows if r.get("published_at_utc")]
    span = f'{min(dates)} — {max(dates)}' if dates else "unknown"
    coverage = stats.get("annotation_coverage", {})
    nav = [("summary", "summary"), ("map", "map"), ("metrics", "metrics"), ("top", "top"), ("patterns", "patterns"), ("insights", "insights"), ("months", "months"), ("catalog", "catalog"), ("methods", "methods")]
    parts = []
    parts.append(f'<header class="hero"><small>VIRAL CAMP · {esc(snap["platform"].upper())} · {esc(snap["fetched_at_utc"][:10])}</small><h1>{esc(t["title"])}<br><em>@{esc(snap["handle"])}</em></h1><p>{snap["selected_count"]} videos · {esc(span)} · ScrapeCreators / {esc(snap["transport"])}</p><div class="kpis"><div><b>{snap["selected_count"]}</b><span>videos</span></div><div><b>{fmt(overall["views"]["median"])}</b><span>median views</span></div><div><b>{fmt(overall["comment_rate_pct"]["median"])}%</b><span>median comment rate</span></div><div><b>{coverage.get("legible", 0)}/{len(rows)}</b><span>legible cover hooks</span></div></div><nav class="toc" aria-label="Contents">' + ''.join(f'<a href="#{anchor}">{esc(t[key])}</a>' for anchor, key in nav) + '</nav></header>')
    limitations = snap.get("limitations", []) + ["Monthly figures are snapshot totals grouped by publication month, not views earned during that month.", "Views / cohort median is a virality multiplier, not a share rate or probability."]
    if not snap["scope_complete"]:
        parts.append(f'<aside>PARTIAL COLLECTION — {esc(snap["stop_reason"])}. Do not interpret this as the whole requested account.</aside>')
    if not snap.get("latest_order_verified"):
        parts.append('<aside>Publication ordering could not be fully verified. Missing dates remain unknown.</aside>')
    if insights is None:
        parts.append(f'<aside>{esc(t["draft"])}</aside>')
    parts.append(f'<section id="summary"><h2>{esc(t["summary"])}</h2>')
    if insights and insights.get("summary"):
        parts.append('<ol class="findings">')
        for item in insights["summary"]:
            refs = ' '.join(link(by_id[i].get("url"), f'#{by_id[i]["recent_rank"]}') for i in item.get("reference_ids", []))
            parts.append(f'<li><strong>{esc(item.get("title", ""))}</strong><p>{esc(item.get("text", ""))}</p><small>{refs}</small></li>')
        parts.append('</ol>')
    else:
        parts.append(f'<p>{esc(t["draft"])}</p>')
    parts.append('</section>')
    parts.append(f'<section id="map"><h2>{esc(t["map"])}</h2><p>Views / cohort median × comment rate. Each point links to its source; the horizontal axis uses log(1+x).</p>{scatter(rows)}</section>')
    parts.append(f'<section id="metrics"><h2>{esc(t["metrics"])}</h2>' + table(["Metric", "Sum", "Mean", "Median", "Known / missing"], [[esc(k), fmt(v.get("sum")) if "sum" in v else "Not additive", fmt(v["mean"]), fmt(v["median"]), f'{v["known_n"]} / {v["missing_n"]}'] for k, v in overall.items() if isinstance(v, dict) and "median" in v]) + f'<p>Weighted comment rate: {fmt(overall["weighted_comment_rate_pct"])}% · eligible videos {overall["weighted_comment_rate_n"]} · view coverage {fmt(None if overall["weighted_comment_rate_view_coverage"] is None else overall["weighted_comment_rate_view_coverage"] * 100)}%</p></section>')
    month_section = f'<section id="months"><h2>{esc(t["months"])}</h2><p>Cumulative counters grouped by publication month; these are not views earned during that month.</p>' + table(["Month", "N", "Views Σ", "Views mean", "Views median", "Comments Σ", "Comments mean", "Comments median", "CR mean %", "CR median %", "CR weighted %", "Viral median ×"], [[esc(m), str(v["n"]), fmt(v["views"]["sum"]), fmt(v["views"]["mean"]), fmt(v["views"]["median"]), fmt(v["comments"]["sum"]), fmt(v["comments"]["mean"]), fmt(v["comments"]["median"]), fmt(v["comment_rate_pct"]["mean"]), fmt(v["comment_rate_pct"]["median"]), fmt(v["weighted_comment_rate_pct"]), fmt(v["virality_multiplier"]["median"])] for m, v in stats["months"].items()]) + '</section>'
    parts.append(f'<section id="top"><h2>{esc(t["top"])}</h2><div class="top-grid">' + ''.join('<article>' + image(r.get("cover_file"), out, r["id"]) + f'<h3>#{r["recent_rank"]} · {link(r.get("url"), transcripts.get(str(r["id"]), {}).get("opening_0_3s") or r.get("hook_text_exact") or r["id"])}</h3><p>{fmt(r.get("views"))} views · {fmt(r.get("comments"))} comments · {fmt(r.get("comment_rate_pct"))}% CR</p></article>' for r in stats["top5"]) + '</div></section>')
    parts.append(f'<section id="patterns"><h2>{esc(t["patterns"])}</h2><p>1 video: hypothesis · 2: exploratory · 3+: repeated observation. The groups describe association in this sample, not cause.</p>')
    for axis, groups in stats.get("patterns", {}).items():
        max_median = max((g["views"]["median"] or 0 for g in groups), default=0) or 1
        lines = []
        for g in groups:
            median = g["views"]["median"]
            bar = f'<span class="bar" style="width:{100*(median or 0)/max_median:.1f}%"></span>'
            refs = ''.join('<div class="mini-ref">' + image(r.get("cover_file"), out, r["id"]) + link(r.get("url"), transcripts.get(str(r["id"]), {}).get("opening_0_3s") or r.get("hook_text_exact") or r["id"]) + '</div>' for r in g["references"])
            share = fmt(g["top1_view_share"] * 100) + '%' if g.get("top1_view_share") is not None else '—'
            lines.append([f'<strong>{esc(g["label"])}</strong><small>{esc(g["evidence"])}</small>', str(g["n"]), f'<div class="bar-track">{bar}</div>{fmt(median)}', fmt(g["views"]["mean"]), fmt(g["comment_rate_pct"]["median"]), fmt(g["virality_multiplier"]["median"]), share, refs])
        parts.append(f'<details class="axis" {"open" if axis == "text_formula" else ""}><summary>{esc(t.get(axis, axis))} · {len(groups)}</summary>' + table(["Pattern", "N", "Views median", "Views mean", "CR median %", "Virality ×", "Top-1 share", "Peak + typical examples"], lines) + '</details>')
    parts.append('</section>')
    if insights:
        allowed_ids = {r["id"] for r in rows}
        parts.append(f'<section id="insights"><h2>{esc(t["insights"])}</h2>')
        for section in insights.get("sections", []):
            parts.append(f'<h3>{esc(section["title"])}</h3><div class="insight-grid">')
            for item in section.get("items", []):
                ids = item.get("reference_ids", [])
                if not set(ids) <= allowed_ids:
                    raise ValueError("Insight cites a video outside the selected cohort")
                if item.get("formula") and not 1 <= len(ids) <= 2:
                    raise ValueError("Each formula needs 1–2 reference IDs")
                parts.append(f'<article><h3>{esc(item.get("title", ""))}</h3><p>{esc(item["text"])}</p>')
                if item.get("formula"):
                    parts.append(f'<blockquote>{esc(item["formula"])}</blockquote>')
                if item.get("adaptation"):
                    parts.append(f'<p>Proposed adaptation: {esc(item["adaptation"])}</p>')
                for ident in ids:
                    r = next(r for r in rows if r["id"] == ident)
                    parts.append('<div class="reference">' + image(r.get("cover_file"), out, ident) + '<div>' + link(r.get("url"), transcripts.get(str(ident), {}).get("opening_0_3s") or r.get("hook_text_exact") or ident) + f'<p>{fmt(r.get("views"))} views · {fmt(r.get("comment_rate_pct"))}% CR · {fmt(r.get("virality_multiplier"))}×</p></div></div>')
                parts.append('</article>')
            parts.append('</div>')
        parts.append('</section>')
    else:
        parts.append(f'<section id="insights"><h2>{esc(t["insights"])}</h2><p>{esc(t["draft"])}</p></section>')
    parts.append(month_section)
    sheets = sorted((out / "sheets").glob("covers-*.jpg"))
    if sheets:
        parts.append(f'<section><h2>{esc(t["sheets"])}</h2>' + ''.join('<details><summary>' + esc(p.stem) + '</summary>' + image(p.relative_to(out), out, p.stem) + '</details>' for p in sheets) + '</section>')
    formula_options = sorted({r.get("text_formula", "") for r in rows if r.get("text_formula")})
    visual_options = sorted({r.get("visual_format", "") for r in rows if r.get("visual_format")})
    parts.append(f'<section id="catalog"><h2>{esc(t["catalog"])} · {len(rows)}</h2><p>Click a column heading to sort. Search includes the complete audio transcript when available.</p><div class="filters"><input id="q" type="search" placeholder="Search hook, transcript, caption or ID"><select id="formula"><option value="">All formulas</option>' + ''.join(f'<option value="{esc(x)}">{esc(x)}</option>' for x in formula_options) + '</select><select id="visual"><option value="">All visuals</option>' + ''.join(f'<option value="{esc(x)}">{esc(x)}</option>' for x in visual_options) + '</select><output id="count"></output></div><div class="scroll catalog-scroll"><table id="catalog-table"><thead><tr><th data-sort="rank">#</th><th>Cover / opening</th><th data-sort="date">Published</th><th data-sort="views">Views</th><th data-sort="virality">Views / median</th><th data-sort="cr">CR %</th><th data-sort="comments">Comments</th><th data-sort="duration">Seconds</th><th>Cover hook</th><th>Spoken first 3 s</th><th>Audio transcript</th><th>Text formula / visual</th><th>Source</th></tr></thead><tbody id="catalog-grid">')
    for r in rows:
        tr = transcripts.get(str(r["id"]), {})
        transcript = tr.get("transcript") or ""
        spoken = tr.get("opening_0_3s") or ""
        search = ' '.join(str(r.get(k) or '') for k in ("id", "hook_text_exact", "caption", "text_formula", "visual_format")) + ' ' + transcript + ' ' + spoken
        cover_path = r.get("cover_file") or tr.get("opening_frame_file")
        cover_note = "frame 0.35 s" if r.get("cover_status") == "opening_frame_fallback" else "cover" if r.get("cover_file") else "frame 0.35 s" if cover_path else "unavailable"
        audio_cell = f'<details><summary>{esc(transcript[:95] or tr.get("status") or "not transcribed")}</summary><p>{esc(transcript)}</p><small>{esc(tr.get("language") or "")} · {esc(tr.get("status") or "not transcribed")}</small></details>' if transcript else esc(tr.get("status") or "not transcribed")
        parts.append(f'<tr data-rank="{r["recent_rank"]}" data-date="{esc(r.get("published_at_utc") or "")}" data-views="{r.get("views") if r.get("views") is not None else -1}" data-virality="{r.get("virality_multiplier") if r.get("virality_multiplier") is not None else -1}" data-cr="{r.get("comment_rate_pct") if r.get("comment_rate_pct") is not None else -1}" data-comments="{r.get("comments") if r.get("comments") is not None else -1}" data-duration="{r.get("duration_seconds") if r.get("duration_seconds") is not None else -1}" data-formula="{esc(r.get("text_formula", ""))}" data-visual="{esc(r.get("visual_format", ""))}" data-search="{esc(search.lower())}"><th scope="row">{r["recent_rank"]}</th><td class="catalog-cover">{image(cover_path, out, r["id"])}<small>{cover_note}</small></td><td>{esc((r.get("published_at_utc") or "unknown")[:10])}</td><td class="num">{fmt(r.get("views"))}</td><td class="num">{fmt(r.get("virality_multiplier"))}×</td><td class="num">{fmt(r.get("comment_rate_pct"))}</td><td class="num">{fmt(r.get("comments"))}</td><td class="num">{fmt(r.get("duration_seconds"))}</td><td class="catalog-hook">{esc(r.get("hook_text_exact") or "—")}<small>{esc(r.get("hook_status") or "not annotated")}</small></td><td class="catalog-hook">{esc(spoken or "—")}</td><td class="catalog-transcript">{audio_cell}</td><td>{esc(r.get("text_formula") or "unassigned")}<br><small>{esc(r.get("visual_format") or "unknown")}</small></td><td>{link(r.get("url"), "Watch")}</td></tr>')
    parts.append(f'</tbody></table></div></section><footer id="methods"><h2>{esc(t["methods"])}</h2><p>Comment rate = comments / views × 100; weighted CR = sum of comments / sum of views for complete positive-view pairs. Baseline = median known views of this exact selected cohort. Zero denominator → N/A. Missing counters are not zero. A cover is not necessarily the opening frame. Audio transcripts are machine-generated and may contain recognition errors; the first-three-second speech is transcribed from a separately clipped audio segment.</p><p>Captured {esc(snap["fetched_at_utc"])} · {esc(snap["stop_reason"])} · {esc(snap["transport"])} · {snap["selected_count"]}/{snap.get("requested_count") or snap["selected_count"]} selected</p>' + ''.join(f'<p>{esc(x)}</p>' for x in limitations) + '</footer>')
    css = '''*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f5f3ed;color:#14241d;font:16px/1.55 system-ui,-apple-system,sans-serif}main{max-width:1360px;margin:auto;padding:0 28px}a{color:#086646;text-decoration:none}a:hover{text-decoration:underline}h1,h2,h3{line-height:1.12;letter-spacing:-.035em}h2{font-size:clamp(28px,3vw,42px);margin:0 0 20px}p{max-width:85ch}small{display:block;color:#607369;font-size:12px}.hero{padding:70px 0 30px}.hero>small{text-transform:uppercase;letter-spacing:.15em;font-weight:700;color:#31795b}h1{font-size:clamp(46px,7vw,94px);margin:14px 0;overflow-wrap:anywhere}h1 em{color:#178656;font-style:normal}.hero>p{font-size:18px;color:#55665e}.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:40px 0}.kpis>div{min-height:140px;background:#102a20;color:white;border-radius:18px;padding:18px}.kpis b{font-size:clamp(28px,3vw,45px);display:block;line-height:1.2}.kpis span{font-size:13px;color:#b9d2c2;display:block;margin-top:12px}.toc{display:flex;flex-wrap:wrap;gap:9px;padding:20px 0}.toc a{border:1px solid #b6cabe;border-radius:20px;padding:6px 12px;font-size:13px}section,footer{border-top:1px solid #cbd8ce;padding:55px 0}aside{padding:16px 20px;background:#ffe9ba;border-radius:12px;margin:20px 0}.findings{counter-reset:item;list-style:none;padding:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px}.findings li{position:relative;background:white;border-radius:16px;padding:22px 22px 20px 58px;box-shadow:0 3px 18px #1434260a}.findings li:before{counter-increment:item;content:counter(item,decimal-leading-zero);position:absolute;left:18px;top:21px;color:#188559;font-size:13px;font-weight:700}.findings p{margin:7px 0}.plot{width:100%;max-width:1000px;background:#fff;border:1px solid #e1e8e0;border-radius:18px;padding:12px}.plot text{fill:#607369;font-size:13px}.gridline{stroke:#e4ebe5}.dot{fill:#1e9c68;fill-opacity:.67;stroke:#075e3e;stroke-width:1}.dot:hover{fill:#ff9c35;fill-opacity:1;r:9}.scroll{overflow:auto;background:white;border-radius:16px;border:1px solid #dce6dd}table{border-collapse:collapse;width:100%;font-size:13px}td,th{text-align:left;vertical-align:top;padding:13px;border-bottom:1px solid #e5ece6}th{background:#e8f0e9;white-space:nowrap}td small{margin-top:5px}.top-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px}.top-grid article,.insight-grid article{background:white;border-radius:16px;padding:16px}.top-grid img{width:100%;height:230px;object-fit:contain;background:#e8eee8}.top-grid h3{font-size:16px;overflow-wrap:anywhere}.top-grid p{font-size:13px}.axis{margin:12px 0;background:#e8f0e9;border-radius:14px}.axis>summary{cursor:pointer;padding:15px 20px;font-weight:700}.axis .scroll{max-height:640px}.axis td:first-child{min-width:180px}.axis td:last-child{min-width:230px}.bar-track{height:5px;border-radius:3px;background:#e5eee6;margin:4px 0 8px;width:110px}.bar{display:block;height:100%;background:#25a56e;border-radius:3px}.mini-ref{display:flex;align-items:center;gap:8px;margin:0 0 8px}.mini-ref img{width:40px;height:60px;object-fit:contain}.mini-ref a{font-size:12px;max-width:220px}.insight-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.insight-grid h3{font-size:20px}.insight-grid blockquote{border-left:4px solid #1e9c68;margin:20px 0;padding-left:14px;font-weight:700}.reference{display:flex;align-items:center;gap:12px;margin:13px 0}.reference img{width:66px;max-height:112px;object-fit:contain}.reference p{font-size:12px}.missing{display:flex;align-items:center;justify-content:center;background:#e8eee8;color:#68766d;font-size:11px;min-height:80px;text-align:center}.filters{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}.filters input,.filters select{border:1px solid #b6cabe;border-radius:9px;background:white;padding:10px;font:inherit}.filters input{min-width:280px;flex:1}.filters output{padding:10px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:15px}.grid article{background:white;padding:16px;border-radius:16px;margin:0}.grid img{height:320px;width:100%;object-fit:contain}.grid h3{font-size:14px;overflow-wrap:anywhere}.grid blockquote{margin:15px 0;font-weight:700;overflow-wrap:anywhere}.grid p{font-size:13px}.grid article[hidden]{display:none}footer p{color:#52645a}@media(max-width:1000px){.top-grid{grid-template-columns:repeat(3,1fr)}.grid{grid-template-columns:repeat(3,1fr)}}@media(max-width:700px){main{padding:0 16px}.hero{padding-top:36px}.kpis{grid-template-columns:repeat(2,1fr)}.findings,.insight-grid{grid-template-columns:1fr}.top-grid,.grid{grid-template-columns:repeat(2,1fr)}section,footer{padding:38px 0}}@media(max-width:480px){.grid{grid-template-columns:1fr}}'''
    css += '''.catalog-scroll{max-height:75vh}.catalog-scroll table{min-width:1700px}.catalog-scroll thead th{position:sticky;top:0;z-index:2;cursor:pointer}.catalog-scroll thead th:hover{background:#d4e8d7}.catalog-scroll td,.catalog-scroll th{padding:10px;line-height:1.35}.catalog-scroll tr[hidden]{display:none}.catalog-scroll tbody tr:nth-child(even){background:#f8faf7}.catalog-scroll tbody tr:hover{background:#ebf4ed}.catalog-cover{min-width:105px}.catalog-cover img{width:80px;height:125px;object-fit:contain}.catalog-hook{min-width:210px;max-width:310px;white-space:normal}.catalog-transcript{min-width:280px;max-width:420px}.catalog-transcript summary{cursor:pointer;max-width:400px;overflow-wrap:anywhere}.catalog-transcript details p{max-height:230px;overflow:auto;white-space:pre-wrap}.catalog-scroll .num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}'''
    js = '''const grid=document.querySelector('#catalog-grid'),cards=[...grid.children],q=document.querySelector('#q'),formula=document.querySelector('#formula'),visual=document.querySelector('#visual'),count=document.querySelector('#count');let sortKey='rank',sortDirection=1;function update(){const needle=q.value.trim().toLocaleLowerCase();let n=0;for(const card of cards){const show=(!needle||card.dataset.search.includes(needle))&&(!formula.value||card.dataset.formula===formula.value)&&(!visual.value||card.dataset.visual===visual.value);card.hidden=!show;if(show)n++}count.textContent=n+' / '+cards.length;cards.sort((a,b)=>sortDirection*(sortKey==='date'?a.dataset.date.localeCompare(b.dataset.date):Number(a.dataset[sortKey])-Number(b.dataset[sortKey])));grid.append(...cards)}for(const control of [q,formula,visual])control.addEventListener('input',update);for(const head of document.querySelectorAll('#catalog-table th[data-sort]'))head.addEventListener('click',()=>{const next=head.dataset.sort;sortDirection=sortKey===next?-sortDirection:(next==='rank'?1:-1);sortKey=next;update()});update();'''
    output = '<!doctype html><html lang="' + esc(lang) + '"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Viral Camp · ' + esc(snap["handle"]) + '</title><style>' + css + '</style></head><body><main>' + ''.join(parts) + '</main><script>' + js + '</script></body></html>'
    (out / "report.html").write_text(output, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--insights", type=Path)
    parser.add_argument("--lang", choices=("ru", "en"), default="ru")
    args = parser.parse_args()
    render(args.out, load(args.insights) if args.insights else None, args.lang)
