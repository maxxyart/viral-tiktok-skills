#!/usr/bin/env python3
"""Render portable HTML with metrics, cover evidence, and agent-authored insights."""
import argparse
import base64
import html
from pathlib import Path
from urllib.parse import urlparse

from social import load


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


def render(out, insights=None, lang="en"):
    stats, rows = load(out / "analysis.json"), load(out / "analyzed-videos.json")
    snap, overall = stats["snapshot"], stats["overall"]
    parts = []
    parts.append(f'<header><small>VIRAL CAMP · {esc(snap["platform"].upper())}</small><h1>@{esc(snap["handle"])}</h1><p>Social account {"hook" if "patterns" in stats else "short"} analysis</p><p>{snap["selected_count"]} videos · {esc(snap["scope"])} · Captured {esc(snap["fetched_at_utc"])} · ScrapeCreators / {esc(snap["transport"])}</p></header>')
    limitations = snap.get("limitations", []) + ["Monthly figures are snapshot totals grouped by publication month, not views earned during that month.", "Views / cohort median is a virality multiplier, not a share rate or probability."]
    if not snap["scope_complete"]:
        parts.append(f'<aside>PARTIAL COLLECTION — {esc(snap["stop_reason"])}. Do not interpret this as the whole requested account.</aside>')
    if not snap.get("latest_order_verified"):
        parts.append('<aside>Publication ordering could not be fully verified. Missing dates remain unknown.</aside>')
    if insights is None:
        parts.append('<aside>DATA DRAFT — Add insights.json and visually inspect the report before delivery.</aside>')
    parts.append('<section><h2>Metrics</h2>' + table(["Metric", "Sum", "Mean", "Median", "Known / missing"], [[esc(k), fmt(v.get("sum")) if "sum" in v else "Not additive", fmt(v["mean"]), fmt(v["median"]), f'{v["known_n"]} / {v["missing_n"]}'] for k, v in overall.items() if isinstance(v, dict) and "median" in v]) + f'<p>Weighted comment rate: {fmt(overall["weighted_comment_rate_pct"])}% · eligible videos {overall["weighted_comment_rate_n"]} · view coverage {fmt(None if overall["weighted_comment_rate_view_coverage"] is None else overall["weighted_comment_rate_view_coverage"] * 100)}%</p></section>')
    parts.append('<section><h2>Publication-month cohorts</h2>' + table(["Month", "N", "Views Σ", "Views mean", "Views median", "Comments Σ", "Comments mean", "Comments median", "CR mean %", "CR median %", "CR weighted %", "Viral median ×"], [[esc(m), str(v["n"]), fmt(v["views"]["sum"]), fmt(v["views"]["mean"]), fmt(v["views"]["median"]), fmt(v["comments"]["sum"]), fmt(v["comments"]["mean"]), fmt(v["comments"]["median"]), fmt(v["comment_rate_pct"]["mean"]), fmt(v["comment_rate_pct"]["median"]), fmt(v["weighted_comment_rate_pct"]), fmt(v["virality_multiplier"]["median"])] for m, v in stats["months"].items()]) + '</section>')
    parts.append('<section><h2>Top 5 by views</h2>' + table(["Reference", "Views", "Comments", "CR %", "Virality ×"], [[link(r.get("url"), r["id"]), fmt(r.get("views")), fmt(r.get("comments")), fmt(r.get("comment_rate_pct")), fmt(r.get("virality_multiplier"))] for r in stats["top5"]]) + '</section>')
    for axis, groups in stats.get("patterns", {}).items():
        parts.append(f'<section><h2>{esc(axis)}</h2>' + table(["Pattern", "N / evidence", "Views median", "Views mean", "CR median %", "Virality ×", "References: peak + typical"], [[esc(g["label"]), f'{g["n"]} · {esc(g["evidence"])}', fmt(g["views"]["median"]), fmt(g["views"]["mean"]), fmt(g["comment_rate_pct"]["median"]), fmt(g["virality_multiplier"]["median"]), '<br>'.join(link(r.get("url"), r.get("hook_text_exact") or r["id"]) for r in g["references"])] for g in groups]) + '</section>')
    if insights:
        allowed_ids = {r["id"] for r in rows}
        for section in insights.get("sections", []):
            parts.append(f'<section><h2>{esc(section["title"])}</h2>')
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
                    parts.append('<div class="reference">' + image(r.get("cover_file"), out, ident) + '<div>' + link(r.get("url"), r.get("hook_text_exact") or ident) + f'<p>{fmt(r.get("views"))} views · {fmt(r.get("comment_rate_pct"))}% CR · {fmt(r.get("virality_multiplier"))}×</p></div></div>')
                parts.append('</article>')
            parts.append('</section>')
    sheets = sorted((out / "sheets").glob("covers-*.jpg"))
    if sheets:
        parts.append('<section><h2>Contact sheets · 20 covers each</h2>' + ''.join('<details><summary>' + esc(p.stem) + '</summary>' + image(p.relative_to(out), out, p.stem) + '</details>' for p in sheets) + '</section>')
    parts.append('<section><h2>Complete evidence catalog</h2><div class="grid">')
    for r in rows:
        parts.append('<article>' + image(r.get("cover_file"), out, r["id"]) + f'<h3>#{r["recent_rank"]} · {link(r.get("url"), r["id"])}</h3><blockquote>{esc(r.get("hook_text_exact") or "No verified transcription")}</blockquote><p>{fmt(r.get("views"))} views · {fmt(r.get("comments"))} comments · {fmt(r.get("comment_rate_pct"))}% CR · {fmt(r.get("virality_multiplier"))}×</p><p>{esc(r.get("text_formula", ""))}<br>{esc(r.get("visual_format", ""))}</p><small>{esc(r.get("hook_status", "not annotated"))} · {esc(r.get("evidence_scope", "metadata only"))}</small></article>')
    parts.append('</div></section><footer><h2>Methods and limitations</h2><p>Comment rate = comments / views × 100; weighted CR = sum of comments / sum of views for complete positive-view pairs. Baseline = median known views of this exact selected cohort. Zero denominator → N/A. Missing counters are not zero.</p>' + ''.join(f'<p>{esc(x)}</p>' for x in limitations) + '</footer>')
    css = '''*{box-sizing:border-box}body{margin:0;background:#f4f2e9;color:#142720;font:16px/1.55 system-ui,sans-serif}main{max-width:1220px;margin:auto;padding:30px}header{padding:50px 0}h1{font-size:clamp(38px,7vw,76px);margin:8px 0;overflow-wrap:anywhere}h2{font-size:28px}small{color:#53665e}section,footer{padding:28px 0;border-top:1px solid #c6d4ca}aside{background:#f9dfac;padding:18px;margin:15px 0;border-radius:12px}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}td,th{text-align:left;padding:12px;border-bottom:1px solid #c6d4ca;vertical-align:top}th{background:#dde8de}a{color:#126143;overflow-wrap:anywhere}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:15px}article{background:white;padding:16px;border-radius:16px;margin:12px 0}img{max-width:100%;object-fit:contain}.grid img{height:320px;width:100%}blockquote{margin:15px 0;font-weight:700;overflow-wrap:anywhere}.reference{display:flex;gap:20px;align-items:center;margin:16px 0}.reference img{width:120px;max-height:214px}.missing{background:#e3e9e4;padding:22px;color:#5d6961}summary{cursor:pointer;padding:16px;background:#e3e9e4}@media(max-width:850px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:480px){main{padding:16px}.grid{grid-template-columns:1fr}}'''
    output = '<!doctype html><html lang="' + esc(lang) + '"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Viral Camp · ' + esc(snap["handle"]) + '</title><style>' + css + '</style></head><body><main>' + ''.join(parts) + '</main></body></html>'
    (out / "report.html").write_text(output, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--insights", type=Path)
    parser.add_argument("--lang", default="en")
    args = parser.parse_args()
    render(args.out, load(args.insights) if args.insights else None, args.lang)
