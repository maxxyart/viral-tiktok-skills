#!/usr/bin/env python3
"""Collect/replay ScrapeCreators video feeds, then export auditable cohort metrics."""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from metrics import analyze

ENDPOINTS = {"instagram": "/v1/instagram/user/reels", "tiktok": "/v3/tiktok/profile/videos"}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def first(*values):
    return next((v for v in values if v is not None), None)


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(value)
        return int(n) if math.isfinite(n) and n >= 0 and n.is_integer() else None
    except (ValueError, TypeError):
        return None


def timestamp(value):
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            n = float(value)
            dt = datetime.fromtimestamp(n / 1000 if n > 1e12 else n, timezone.utc)
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError, OSError):
        return None


def parse_account(value, platform=None):
    if "://" in value:
        u = urlparse(value)
        host = (u.hostname or "").lower()
        inferred = "instagram" if host in {"instagram.com", "www.instagram.com"} else "tiktok" if host in {"tiktok.com", "www.tiktok.com", "m.tiktok.com"} else None
        if inferred is None or (platform and platform != inferred):
            raise ValueError("Use a full Instagram/TikTok profile URL matching --platform; resolve short links first")
        parts = u.path.strip("/").split("/")
        value, platform = parts[0].lstrip("@"), inferred
        if (platform == "instagram" and (value in {"p", "reel", "reels", "explore"} or parts[1:] not in ([], ["reels"]))) or (platform == "tiktok" and (not parts[0].startswith("@") or len(parts) > 1)):
            raise ValueError("Expected an account URL, not a post URL")
    if platform is None:
        raise ValueError("A bare handle needs --platform instagram|tiktok")
    handle = value.lstrip("@").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.]{1,32}", handle) or handle in {".", ".."}:
        raise ValueError("Invalid account handle")
    return handle, platform


def unwrap(body):
    if not isinstance(body, dict):
        raise ValueError("Expected JSON object")
    if body.get("success") is False or body.get("ok") is False or body.get("isError") is True:
        raise ValueError("ScrapeCreators returned an error payload")
    if "structuredContent" in body:
        return unwrap(body["structuredContent"])
    if "content" in body and isinstance(body["content"], list):
        texts = [x.get("text") for x in body["content"] if x.get("type") == "text"]
        if len(texts) == 1:
            return unwrap(json.loads(texts[0]))
    if isinstance(body.get("data"), dict) and not any(k in body for k in ("items", "aweme_list")):
        return unwrap(body["data"])
    return body


def page_data(body, platform):
    body = unwrap(body)
    key = "items" if platform == "instagram" else "aweme_list"
    if key not in body or not isinstance(body[key], list):
        raise ValueError(f"Response schema changed: missing list {key}")
    paging = body.get("paging_info") or {}
    cursor = first(paging.get("max_id"), body.get("max_id")) if platform == "instagram" else body.get("max_cursor")
    more = first(paging.get("more_available"), body.get("more_available")) if platform == "instagram" else body.get("has_more")
    if more in (True, 1, "1", "true"):
        more = True
    elif more in (False, 0, "0", "false"):
        more = False
    else:
        more = None
    return body[key], cursor, more


def normalize(item, platform, handle, fetched_at, page):
    m = item.get("media", item)
    if platform == "instagram":
        if m.get("media_type") in (1, 8) or m.get("product_type") == "carousel_container":
            return None
        code = m.get("code")
        # Shortcodes survive JSON transports that round Instagram's >53-bit numeric IDs.
        ident = first(code, m.get("pk"), m.get("id"))
        fields = ["play_count", "ig_play_count", "video_play_count", "video_view_count"]
        view_field = next((k for k in fields if m.get(k) is not None), None)
        metrics = {"views": m.get(view_field) if view_field else None, "likes": m.get("like_count"), "comments": m.get("comment_count"), "shares": m.get("reshare_count"), "saves": m.get("save_count")}
        published = timestamp(first(m.get("created_at"), m.get("taken_at")))
        caption = m.get("caption")
        caption = caption.get("text") if isinstance(caption, dict) else caption
        candidates = (m.get("image_versions2") or {}).get("candidates") or []
        cover = max(candidates, key=lambda c: (c.get("width") or 0) * (c.get("height") or 0)).get("url") if candidates else first(m.get("display_uri"), m.get("thumbnail_url"))
        url = f"https://www.instagram.com/reel/{code}/" if code else None
        duration = m.get("video_duration")
        pinned = bool(m.get("is_pinned") or m.get("is_pinned_to_main_grid"))
    else:
        if m.get("image_post_info") or m.get("aweme_type") in (68, 150):
            return None
        ident = first(m.get("aweme_id"), m.get("id"), m.get("id_str"))
        st, video = m.get("statistics") or {}, m.get("video") or {}
        view_field = "statistics.play_count" if st.get("play_count") is not None else None
        metrics = {"views": st.get("play_count"), "likes": st.get("digg_count"), "comments": st.get("comment_count"), "shares": st.get("share_count"), "saves": st.get("collect_count")}
        published, caption = timestamp(m.get("create_time")), m.get("desc")
        cover, heic_fallback = None, None
        for key in ("origin_cover", "cover_large", "cover", "dynamic_cover"):
            values = (video.get(key) or {}).get("url_list") or []
            if values:
                # TikTok often lists HEIC first; a later cover type may offer
                # JPEG even when the preferred origin cover does not.
                heic_fallback = heic_fallback or values[0]
                cover = next((value for value in values if urlparse(value).path.lower().endswith((".jpeg", ".jpg", ".png", ".webp"))), None)
                if cover:
                    break
        cover = cover or heic_fallback
        url = f"https://www.tiktok.com/@{handle}/video/{ident}" if ident else None
        duration = (video["duration"] / 1000) if isinstance(video.get("duration"), (int, float)) else None
        pinned = bool(m.get("is_top") or m.get("is_pinned"))
    if ident is None or str(ident) in {"", "unknown", "None"}:
        raise ValueError("Video has no stable ID; cannot silently discard it")
    return {"id": str(ident), "platform": platform, "handle": handle, "url": url,
            "published_at_utc": published, "fetched_at_utc": fetched_at,
            **{k: number(v) for k, v in metrics.items()}, "views_source_field": view_field,
            "caption": caption, "duration_seconds": duration, "is_pinned": pinned,
            "cover_url": cover, "cover_file": None, "cover_status": "not_requested", "source_page": page}


def fetch_api(path, params, transport):
    if transport == "cli":
        platform = "instagram" if "/instagram/" in path else "tiktok"
        action = "profile" if path.endswith("/profile") else "user-reels" if platform == "instagram" else "profile-videos"
        cmd = ["scrapecreators", "--format", "json", platform, action]
        for k, v in params.items():
            if v is not None:
                cmd += ["--" + k.replace("_", "-"), str(v)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode:
            raise ValueError("ScrapeCreators CLI failed; check authentication/credits without exposing credentials")
        return json.loads(proc.stdout)
    key = os.environ.get("SCRAPE_CREATORS_API_KEY") or os.environ.get("SCRAPECREATORS_API_KEY")
    if not key:
        raise ValueError("Set SCRAPE_CREATORS_API_KEY in environment, use authenticated CLI, or import MCP pages")
    query = urlencode({k: v for k, v in params.items() if v is not None})
    req = Request("https://api.scrapecreators.com" + path + "?" + query, headers={"x-api-key": key})
    for attempt in range(3):
        try:
            with urlopen(req, timeout=45) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise ValueError(f"ScrapeCreators HTTP {error.code}; no automatic credit purchase") from None
        except (URLError, TimeoutError):
            if attempt == 2:
                raise ValueError("ScrapeCreators network timeout") from None
        time.sleep(2 ** attempt)


def collect(handle, platform, getter, out, count=60, all_videos=False, max_pages=100, transport="mcp-import", region=None, fetched_at=None):
    selected, seen_cursors, dates, errors = {}, set(), [], []
    cursor, duplicates, excluded, exhausted, order_issue = None, 0, 0, False, False
    extra_after_target, stop, pages = 0, "page_limit", 0
    stamp = fetched_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for page in range(1, max_pages + 1):
        params = {"handle": handle}
        params.update({"max_id": cursor} if platform == "instagram" else {"max_cursor": cursor, "sort_by": "latest", "region": region})
        try:
            body = getter(ENDPOINTS[platform], params)
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            stop = "fetch_error"
            errors.append(str(error))
            break
        if body is None:
            stop = "import_ended_without_exhaustion"
            break
        pages = page
        write_json(out / "raw" / f"page-{page:04d}.json", body)
        try:
            items, nxt, more = page_data(body, platform)
            new_rows = [normalize(it, platform, handle, stamp, page) for it in items]
        except (ValueError, TypeError, KeyError) as error:
            stop = "schema_error"
            errors.append(str(error))
            break
        new_count = 0
        for row in new_rows:
            if row is None:
                excluded += 1
                continue
            if row["id"] in selected:
                duplicates += 1
                continue
            if not row["published_at_utc"]:
                order_issue = True
            if not row["is_pinned"] and row["published_at_utc"]:
                if dates and row["published_at_utc"] > dates[-1]:
                    order_issue = True
                dates.append(row["published_at_utc"])
            selected[row["id"]] = row
            new_count += 1
        if more is False:
            exhausted, stop = True, "source_exhausted"
            break
        if not items:
            stop = "empty_page_with_more_or_unknown"
            break
        if nxt is None or str(nxt) in seen_cursors:
            stop = "missing_or_repeated_cursor"
            break
        if not new_count and any(row is not None for row in new_rows):
            stop = "no_new_ids"
            break
        # Read two additional pages beyond N. Unknown/reordered dates force exhaustion.
        if not all_videos and len(selected) >= count and not order_issue:
            extra_after_target += 1
            if extra_after_target >= 3:
                stop = "latest_boundary_checked"
                break
        cursor = nxt
        seen_cursors.add(str(cursor))
    ordered = sorted(selected.values(), key=lambda r: (r["published_at_utc"] or "", r["id"]), reverse=True)
    rows = ordered if all_videos else ordered[:count]
    dated = all(r["published_at_utc"] for r in ordered)
    scope_complete = exhausted or (stop == "latest_boundary_checked" and dated)
    snapshot = {"schema_version": 1, "platform": platform, "handle": handle, "provider": "ScrapeCreators",
                "transport": transport, "fetched_at_utc": stamp, "scope": "all_available_videos" if all_videos else "latest_videos",
                "requested_count": None if all_videos else count, "selected_count": len(rows), "fetched_unique_count": len(ordered),
                "pages": pages, "excluded_nonvideo_count": excluded, "duplicates_removed": duplicates,
                "source_exhausted": exhausted, "scope_complete": scope_complete, "latest_order_verified": dated and scope_complete,
                "observed_order_issue": order_issue, "stop_reason": stop, "errors": errors,
                "limitations": (["Instagram Reels endpoint may omit pinned reels; scope is available feed, not guaranteed full account.", "Views represent Instagram only, not combined Instagram + Facebook.", "Captions may require post-detail enrichment."] if platform == "instagram" else [])}
    rows = [{**r, "recent_rank": i + 1} for i, r in enumerate(rows)]
    write_json(out / "fetched-videos.json", ordered)
    write_json(out / "snapshot.json", snapshot)
    write_json(out / "videos.json", rows)
    export(out)
    return snapshot


def csv_cell(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    # Keep untrusted caption/hook text from becoming a spreadsheet formula.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export(out, cards_path=None):
    rows, stats = analyze(load(out / "videos.json"), load(out / "snapshot.json"), load(cards_path) if cards_path else None)
    write_json(out / "analysis.json", stats)
    write_json(out / "analyzed-videos.json", rows)
    fields = list(dict.fromkeys(k for r in rows for k in r)) or ["id", "views", "comments"]
    with (out / "videos.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: csv_cell(v) for k, v in r.items()} for r in rows)
    month_fields = ["month", "n", "views_sum", "views_mean", "views_median", "comments_sum", "comments_mean", "comments_median", "comment_rate_mean_pct", "comment_rate_median_pct", "weighted_comment_rate_pct", "virality_mean", "virality_median"]
    with (out / "months.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=month_fields)
        writer.writeheader()
        for month, m in stats["months"].items():
            writer.writerow({"month": month, "n": m["n"], **{f"{k}_{a}": m[k][a] for k in ("views", "comments") for a in ("sum", "mean", "median")},
                             "comment_rate_mean_pct": m["comment_rate_pct"]["mean"], "comment_rate_median_pct": m["comment_rate_pct"]["median"],
                             "weighted_comment_rate_pct": m["weighted_comment_rate_pct"], "virality_mean": m["virality_multiplier"]["mean"], "virality_median": m["virality_multiplier"]["median"]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("collect")
    fetch.add_argument("account")
    fetch.add_argument("--platform", choices=ENDPOINTS)
    scope = fetch.add_mutually_exclusive_group()
    scope.add_argument("--count", type=int, default=60)
    scope.add_argument("--all", action="store_true")
    fetch.add_argument("--transport", choices=("api", "cli"), default="api")
    fetch.add_argument("--pages-dir", type=Path, help="Replay page-*.json from MCP or a saved API run; no network")
    fetch.add_argument("--import-transport", choices=("mcp", "cli", "api"), default="mcp")
    fetch.add_argument("--fetched-at", help="Original UTC capture time, required when importing pages")
    fetch.add_argument("--region")
    fetch.add_argument("--max-pages", type=int, default=100)
    fetch.add_argument("--out", type=Path, required=True)
    summary = sub.add_parser("analyze")
    summary.add_argument("--out", type=Path, required=True)
    summary.add_argument("--cards", type=Path)
    args = parser.parse_args()
    if args.command == "analyze":
        export(args.out, args.cards)
        return
    if args.count <= 0 or args.max_pages <= 0:
        parser.error("count/max-pages must be positive")
    handle, platform = parse_account(args.account, args.platform)
    if args.out.exists() and any(args.out.iterdir()):
        parser.error("Use a new output directory to preserve prior snapshots")
    if args.pages_dir:
        paths = sorted(args.pages_dir.glob("page-*.json"))
        if not paths or not args.fetched_at or not timestamp(args.fetched_at):
            parser.error("Import needs page-*.json and a valid original --fetched-at UTC timestamp")
        pages = iter(paths)
        def getter(path, params):
            entry = next(pages, None)
            return load(entry) if entry else None
        transport = args.import_transport + "-import"
    else:
        getter = lambda path, params: fetch_api(path, params, args.transport)
        transport = args.transport
    args.out.mkdir(parents=True, exist_ok=True)
    if not args.pages_dir:
        try:
            write_json(args.out / "profile.json", fetch_api(f"/v1/{platform}/profile", {"handle": handle}, args.transport))
        except (ValueError, OSError, subprocess.SubprocessError):
            write_json(args.out / "profile-status.json", {"status": "unavailable"})
    status = collect(handle, platform, getter, args.out, args.count, args.all, args.max_pages, transport, args.region, timestamp(args.fetched_at) if args.fetched_at else None)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    if not status["scope_complete"]:
        sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        sys.exit(str(error))
