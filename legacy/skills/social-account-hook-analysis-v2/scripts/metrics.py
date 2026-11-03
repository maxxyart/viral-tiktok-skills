"""Deterministic, null-aware cohort analytics. Python 3.10+, stdlib only."""
from collections import defaultdict
from statistics import mean, median


def distribution(values):
    known = [v for v in values if v is not None]
    return {"known_n": len(known), "missing_n": len(values) - len(known),
            "sum": sum(known) if known else None,
            "mean": mean(known) if known else None,
            "median": median(known) if known else None}


def ratio(numerator, denominator, scale=1):
    return numerator / denominator * scale if numerator is not None and denominator is not None and denominator > 0 else None


def enrich(rows, baseline=None):
    if baseline is None:
        baseline = distribution([r.get("views") for r in rows])["median"]
    return [{**r, "comment_rate_pct": ratio(r.get("comments"), r.get("views"), 100),
             "virality_multiplier": ratio(r.get("views"), baseline)} for r in rows]


def summarize(rows, baseline):
    pairs = [r for r in rows if r.get("views") is not None and r.get("comments") is not None and r["views"] > 0]
    stats = {key: distribution([r.get(key) for r in rows]) for key in ("views", "comments", "likes", "shares", "saves", "comment_rate_pct", "virality_multiplier")}
    # Percentages and median multiples are not additive quantities.
    for key in ("comment_rate_pct", "virality_multiplier"):
        stats[key].pop("sum")
    known_views = [r["views"] for r in rows if r.get("views") is not None]
    positive = [r for r in rows if r.get("views") is not None and r["views"] > 0]
    stats.update(n=len(rows), baseline_views=baseline,
                 weighted_comment_rate_pct=ratio(sum(r["comments"] for r in pairs), sum(r["views"] for r in pairs), 100),
                 weighted_comment_rate_n=len(pairs),
                 weighted_comment_rate_view_coverage=ratio(sum(r["views"] for r in pairs), sum(r["views"] for r in positive)),
                 top1_view_share=ratio(max(known_views, default=0), sum(known_views)),
                 above_3x_n=sum(r.get("virality_multiplier") is not None and r["virality_multiplier"] >= 3 for r in rows),
                 evidence="single example" if len(rows) == 1 else "exploratory pair" if len(rows) == 2 else "repeated observation")
    return stats


def analyze(rows, snapshot, cards=None):
    ids = [r["id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate stable video IDs in cohort")
    baseline = distribution([r.get("views") for r in rows])["median"]
    rows = enrich(rows, baseline)
    months = defaultdict(list)
    for row in rows:
        months[(row.get("published_at_utc") or "unknown")[:7]].append(row)
    result = {"snapshot": snapshot, "overall": summarize(rows, baseline),
              "months": {k: summarize(v, baseline) for k, v in sorted(months.items())},
              "top5": sorted([r for r in rows if r.get("views") is not None], key=lambda r: (-r["views"], r["id"]))[:5]}
    if cards is None:
        return rows, result
    card_ids = [c["id"] for c in cards]
    if len(set(card_ids)) != len(card_ids) or set(card_ids) != set(ids):
        raise ValueError("Cards must cover every selected stable ID exactly once; missing/extra/duplicate IDs found")
    by_id = {c["id"]: c for c in cards}
    required = {"hook_text_exact", "hook_status", "text_formula", "visual_format", "character_role", "evidence_scope"}
    for card in cards:
        if not required <= card.keys():
            raise ValueError(f"Card {card['id']} missing {sorted(required - card.keys())}")
        if card["hook_status"] not in {"legible", "partial", "no_text", "unreadable", "missing_cover"}:
            raise ValueError("Invalid hook_status")
        if card["evidence_scope"] not in {"cover_only", "opening_frames", "full_video"}:
            raise ValueError("Invalid evidence_scope")
        if not all(isinstance(card[k], str) and card[k].strip() for k in ("text_formula", "visual_format", "character_role")):
            raise ValueError("Use explicit unassigned/unknown labels instead of empty groups")
        if card["hook_status"] == "legible" and not card["hook_text_exact"]:
            raise ValueError("Legible hook requires exact text")
    rows = [{**r, **{k: v for k, v in by_id[r["id"]].items() if k not in r}} for r in rows]
    result["patterns"] = {}
    for axis in ("text_formula", "visual_format", "character_role", "text_x_visual"):
        buckets = defaultdict(list)
        for row in rows:
            key = row["text_formula"] + " × " + row["visual_format"] if axis == "text_x_visual" else row[axis]
            buckets[key].append(row)
        groups = []
        for label, group in buckets.items():
            group_stats = summarize(group, baseline)
            group_stats.update(label=label, ids=[r["id"] for r in group],
                               view_share=ratio(sum(r["views"] for r in group if r.get("views") is not None), result["overall"]["views"]["sum"]))
            valid = [r for r in group if r.get("views") is not None]
            med = group_stats["views"]["median"]
            refs = sorted(valid, key=lambda r: (-r["views"], r["id"]))[:1]
            rest = [r for r in valid if r not in refs]
            if rest:
                refs += [min(rest, key=lambda r: abs(r["views"] - med))]
            group_stats["references"] = [{k: r.get(k) for k in ("id", "url", "cover_file", "views", "comments", "comment_rate_pct", "virality_multiplier", "hook_text_exact")} for r in refs]
            group_stats["by_month"] = {month: summarize([r for r in group if (r.get("published_at_utc") or "unknown")[:7] == month], baseline)
                                       for month in sorted({(r.get("published_at_utc") or "unknown")[:7] for r in group})}
            groups.append(group_stats)
        result["patterns"][axis] = sorted(groups, key=lambda g: (g["views"]["median"] is None, -(g["views"]["median"] or 0), g["label"]))
    result["annotation_coverage"] = {status: sum(c["hook_status"] == status for c in cards) for status in ("legible", "partial", "no_text", "unreadable", "missing_cover")}
    result["top5"] = [next(r for r in rows if r["id"] == t["id"]) for t in result["top5"]]
    return rows, result
