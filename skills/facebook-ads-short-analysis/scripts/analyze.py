#!/usr/bin/env python3
"""FB Ads short analysis — ScrapeCreators-only, no Gemini."""
import os, sys, json, csv, time, argparse, re, urllib.parse, asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import httpx

API_KEY = os.environ.get("SCRAPE_CREATORS_API_KEY") or os.environ.get("SCRAPECREATORS_API_KEY", "")


def load_env_file(path):
    """Read KEY=VALUE lines from an explicitly passed file. No automatic search."""
    global API_KEY
    for line in open(os.path.expanduser(path), encoding="utf-8", errors="ignore"):
        m = re.match(r'\s*(?:export\s+)?(SCRAPE_CREATORS_API_KEY|SCRAPECREATORS_API_KEY)=["\']?([^"\'\n ]+)', line)
        if m and not API_KEY:
            API_KEY = m.group(2)
ADS_URL = "https://api.scrapecreators.com/v1/facebook/adLibrary/company/ads"
CACHE_DIR = Path.home() / ".cache" / "fb_ads_short_analysis"
CACHE_TTL_SEC = 6 * 3600  # 6 hours default
MEDIA_SHARDS = ["ALL"]  # single shard — safer (media_type filters can miss ads)
RETRIABLE_STATUS = {429, 500, 502, 503, 504}

# When --countries ALL is used, also probe these specific geos to get a per-country
# breakdown (the ALL shard returns the union but ScrapeCreators leaves
# targeted_or_reached_countries empty, so we infer geo membership by re-querying).
DEFAULT_PROBE_GEOS = [
    "US","CA","GB","AU","NZ","IE","ZA",          # core English
    "DE","FR","ES","IT","NL","PL","SE","NO","DK","FI","PT","BE","AT","CH","CZ","RO","GR",  # Europe
    "MX","BR","AR","CL","CO","PE",               # LATAM
    "IN","PH","ID","TH","VN","MY","SG","HK","TW","JP","KR",  # APAC
    "AE","SA","IL","TR",                          # MENA
    "RU","UA","KZ",                               # CIS
]

STOPWORDS = set("""
a an the and or of to in for on at is are was were be been being this that these those with by from as it its
i my me you your he she they them we our us is am do does did done have has had not no so if but just
el la los las un una unos unas y o de del a en por para con sin es son ser estar está están está esto eso mi mis tu tus su sus lo ya que como qué cuál cual mas pero si sí no más muy también fue fueron todo toda todos todas este esta estos estas
я ты он она они мы вы это то не ни и или а но да нет как что чтобы для в на по из от с без к у о об про ли ж же уж уже ещё мне тебе ему ей нас вас меня тебя себя себе свой своя свои своих свою всё все всего всему всём был была были быть этот эта эти
""".split())

REQUESTS_MADE = 0  # every HTTP attempt (incl. retries); ScrapeCreators bills per request

# ---- HTTP with retry ----

async def api_get(client, url, params, retries=3):
    """GET with exponential backoff on 429/5xx/network errors.
    431 (cursor-size ceiling) and other 4xx raise immediately."""
    global REQUESTS_MADE
    delay = 1.0
    last = None
    for attempt in range(retries + 1):
        REQUESTS_MADE += 1
        try:
            r = await client.get(url, headers={"x-api-key": API_KEY}, params=params, timeout=60.0)
            r.raise_for_status()
            return r
        except httpx.HTTPStatusError as e:
            last = e
            if e.response.status_code not in RETRIABLE_STATUS or attempt == retries:
                raise
        except httpx.HTTPError as e:
            last = e
            if attempt == retries:
                raise
        await asyncio.sleep(delay)
        delay *= 2
    raise last

# ---- cache ----
# File format: {"ts": ..., "meta": {...}, "ads": [...]}. Older cache files have no
# "meta" key; catalog loads tolerate that, the impressions load treats them as
# not-exhausted (forces one refetch — old files may hold cap-truncated lists).

def cache_path(page_id, country, media_type, variant=""):
    return CACHE_DIR / f"{page_id}_{country}_{media_type}{variant}.json"

def load_cache(page_id, country, media_type, ttl, variant=""):
    p = cache_path(page_id, country, media_type, variant)
    if not p.exists(): return None
    age = time.time() - p.stat().st_mtime
    if age > ttl: return None
    try:
        d = json.loads(p.read_text())
        return d["ads"], d.get("meta", {}), age
    except Exception:
        return None

def save_cache(page_id, country, media_type, ads, meta=None, variant=""):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = cache_path(page_id, country, media_type, variant)
    p.write_text(json.dumps({"ts": time.time(), "meta": meta or {}, "ads": ads}))

# ---- fetch ----

async def fetch_shard(client, page_id, country, media_type, cache_ttl, status="ACTIVE"):
    """One paginated chain for a given country/media_type/status.
    Returns (country, media_type, ads, page_times, from_cache, ok, truncated).
    Partial results after a transient error are used for this run but NOT cached."""
    variant = "" if status == "ACTIVE" else f"_{status}"
    cached = load_cache(page_id, country, media_type, cache_ttl, variant) if cache_ttl > 0 else None
    if cached:
        ads, meta, age = cached
        print(f"  [{country}/{media_type:5}{variant}] CACHE HIT ({len(ads)} ads, age {age:.0f}s)")
        return (country, media_type, ads, [], True, True, meta.get("truncated", False))

    ads = []
    cursor = None
    page_times = []
    ok = True
    truncated = False
    while True:
        p = {"pageId": page_id, "country": country, "status": status,
             "media_type": media_type, "sort_by": "relevancy_monthly_grouped"}
        if cursor: p["cursor"] = cursor
        t0 = time.time()
        try:
            r = await api_get(client, ADS_URL, p)
        except Exception as e:
            code = e.response.status_code if isinstance(e, httpx.HTTPStatusError) else None
            if code == 431:
                # deterministic cursor-size ceiling (~1000 ads) — list is complete
                # as far as the API allows; safe to cache with a truncation mark
                truncated = True
            else:
                print(f"  [{country}/{media_type}{variant}] fetch error after retries: {str(e)[:120]}", file=sys.stderr)
                ok = False
            break
        page_times.append(time.time() - t0)
        d = r.json()
        res = d.get("results") or []
        ads.extend(res)
        cursor = d.get("cursor")
        if not cursor or not res: break
    if ok:
        save_cache(page_id, country, media_type, ads, {"complete": True, "truncated": truncated}, variant)
    tsum = sum(page_times)
    flag = " [TRUNCATED]" if truncated else ("" if ok else " [FAILED — not cached]")
    print(f"  [{country}/{media_type:5}{variant}] {len(ads):4d} ads | {len(page_times)} pages | {tsum:.2f}s{flag}")
    return (country, media_type, ads, page_times, False, ok, truncated)

async def fetch_all(page_id, countries, cache_ttl, status="ACTIVE"):
    """Run MEDIA_SHARDS × countries pagination chains in parallel."""
    sem = asyncio.Semaphore(10)
    async with httpx.AsyncClient(timeout=60.0,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=20)) as cl:
        async def bounded(country, mt):
            async with sem:
                return await fetch_shard(cl, page_id, country, mt, cache_ttl, status)
        tasks = [bounded(c, mt) for c in countries for mt in MEDIA_SHARDS]
        return await asyncio.gather(*tasks)

async def fetch_impressions(page_id, cache_ttl, cap, country="ALL"):
    """Single paginated chain sorted by total_impressions (high -> low).

    Meta exposes no numeric impression value in this view (impressions_with_index
    is null on collation representatives), so this yields a RANK only. The view
    returns collation representatives whose ad_archive_id can differ from the
    per-country catalog. Cache stores exhausted/truncated metadata so a capped
    pull can never masquerade as a full one on a later run."""
    cached = load_cache(page_id, country, "__IMP__", cache_ttl) if cache_ttl > 0 else None
    if cached:
        ads, meta, age = cached
        exhausted = meta.get("exhausted", False)  # old-format files: assume capped
        truncated = meta.get("truncated", False)
        if exhausted or (cap > 0 and len(ads) >= cap):
            print(f"  [impressions/{country}] CACHE HIT ({len(ads)} ads, age {age:.0f}s)")
            return (ads if cap <= 0 else ads[:cap]), truncated
        print(f"  [impressions/{country}] cache insufficient (cached pull shallower than requested) — refetching")

    ads = []
    cursor = None
    pages = 0
    truncated = False
    error = False
    t0 = time.time()
    async with httpx.AsyncClient(timeout=60.0) as cl:
        while True:
            p = {"pageId": page_id, "country": country, "status": "ACTIVE",
                 "media_type": "ALL", "sort_by": "total_impressions"}
            if cursor: p["cursor"] = cursor
            try:
                r = await api_get(cl, ADS_URL, p)
            except Exception as e:
                code = e.response.status_code if isinstance(e, httpx.HTTPStatusError) else None
                if code == 431:
                    truncated = True  # deterministic ceiling — cacheable
                else:
                    print(f"  [impressions/{country}] stopped early ({len(ads)} ads): {str(e)[:120]}", file=sys.stderr)
                    truncated = True
                    error = True  # transient — do not cache the partial list
                break
            d = r.json()
            res = d.get("results") or []
            ads.extend(res)
            pages += 1
            cursor = d.get("cursor")
            if cap > 0 and len(ads) >= cap: break
            if not cursor or not res: break
    print(f"  [impressions/{country}] {len(ads):4d} ads | {pages} pages | {time.time()-t0:.2f}s"
          + (" [TRUNCATED at API cursor limit]" if truncated else ""))
    if ads and not error:
        stopped_by_cap = cap > 0 and len(ads) >= cap and not truncated
        save_cache(page_id, country, "__IMP__", ads,
                   {"exhausted": not stopped_by_cap, "truncated": truncated})
    return (ads if cap <= 0 else ads[:cap]), truncated

# ---- classify / extract ----

def ts_iso(t):
    if not t: return ""
    try: return datetime.fromtimestamp(int(t), tz=timezone.utc).strftime("%Y-%m-%d")
    except: return ""

def days_running(a):
    s = a.get("start_date")
    if not s: return ""
    try:
        start = datetime.fromtimestamp(int(s), tz=timezone.utc)
    except Exception:
        return ""
    e = a.get("end_date")
    try:
        end = datetime.fromtimestamp(int(e), tz=timezone.utc) if e else datetime.now(timezone.utc)
    except Exception:
        end = datetime.now(timezone.utc)
    return max((end - start).days, 0)

def classify_media(ad):
    snap = ad.get("snapshot") or {}
    df = (snap.get("display_format") or "").upper()
    if df == "VIDEO" or (snap.get("videos") or []):
        return "video"
    if df == "CAROUSEL" or (snap.get("cards") or []):
        return "carousel"
    if df in ("IMAGE","DCO") or (snap.get("images") or []):
        return "image"
    if df:
        return df.lower()
    return "unknown"

def classify_landing(url: str):
    if not url: return ("none","")
    u = url.lower()
    if "apps.apple.com" in u or "itunes.apple.com" in u: return ("ios_app_store", url)
    if "play.google.com" in u: return ("google_play", url)
    if re.match(r"^https?://(www\.)?(fb\.me|l\.facebook\.com|m\.me)", u): return ("fb_redirect", url)
    if "onelink.me" in u or "appsflyer" in u or "branch.io" in u or "go.onelink" in u:
        return ("attribution_link", url)
    return ("web_funnel", url)

def funnel_key(url: str):
    """Normalize web funnel URL → domain+path (strip query/hash)."""
    try:
        p = urllib.parse.urlparse(url)
        return f"{p.netloc}{p.path}".rstrip("/")
    except: return url

# Carousels keep their creative in snapshot.cards, not snapshot.body/images/videos —
# every extractor below falls back to the first card so carousel rows aren't empty.

def first_card(snap):
    cards = snap.get("cards") or []
    return cards[0] if cards and isinstance(cards[0], dict) else {}

def first_video_urls(snap):
    v = (snap.get("videos") or [])
    if v:
        x = v[0]
        return (x.get("video_sd_url") or "", x.get("video_hd_url") or "", x.get("video_preview_image_url") or "")
    c = first_card(snap)
    if c.get("video_hd_url") or c.get("video_sd_url"):
        return (c.get("video_sd_url") or "", c.get("video_hd_url") or "", c.get("video_preview_image_url") or "")
    return ("","","")

def first_image_url(snap):
    imgs = snap.get("images") or []
    if imgs:
        x = imgs[0]
        return x.get("original_image_url") or x.get("resized_image_url") or x.get("watermarked_resized_image_url") or ""
    c = first_card(snap)
    return c.get("original_image_url") or c.get("resized_image_url") or ""

def _card_text(v):
    if isinstance(v, str): return v
    if isinstance(v, dict): return v.get("text") or ""
    return ""

def snap_body_text(snap):
    body = (snap.get("body") or {}).get("text") or ""
    if body: return body
    for c in snap.get("cards") or []:
        t = _card_text(c.get("body"))
        if t: return t
    return ""

def snap_title(snap):
    if snap.get("title"): return snap["title"]
    for c in snap.get("cards") or []:
        if c.get("title"): return c["title"]
    return ""

def snap_link_url(snap):
    if snap.get("link_url"): return snap["link_url"]
    for c in snap.get("cards") or []:
        if c.get("link_url"): return c["link_url"]
    return ""

def snap_cta(snap):
    c = first_card(snap)
    return (snap.get("cta_type") or c.get("cta_type") or "",
            snap.get("cta_text") or c.get("cta_text") or "")

def media_stem(snap):
    """Asset-filename key for matching a creative across two API sort modes when
    ad_archive_id differs (collation). Uses the fbcdn filename (stable photo fbid),
    not the signed query string. Empty when no media. Exact-match only -> no false
    positives, just incomplete coverage if Meta re-renders the asset."""
    v = snap.get("videos") or []
    if v:
        u = v[0].get("video_preview_image_url") or ""
    else:
        imgs = snap.get("images") or []
        u = (imgs[0].get("original_image_url") or imgs[0].get("resized_image_url") or "") if imgs else ""
    if not u:
        c = first_card(snap)
        u = c.get("video_preview_image_url") or c.get("original_image_url") or c.get("resized_image_url") or ""
    if not u: return ""
    try:
        base = urllib.parse.urlparse(u).path.rsplit("/", 1)[-1]
    except Exception:
        return ""
    return base or ""

def impressions_text_of(a):
    return (a.get("impressions_with_index") or {}).get("impressions_text") or ""

# ---- text patterns ----

EMOJI_RE = re.compile("[\U00010000-\U0010ffff☀-➿⌀-⏿⬀-⯿]", re.UNICODE)
PUNCT_RE = re.compile(r"[^\w\sА-Яа-яÁÉÍÓÚÑáéíóúñÜü]", re.UNICODE)
WS = re.compile(r"\s+")

def norm(s: str) -> str:
    if not s: return ""
    s = s.lower()
    s = EMOJI_RE.sub(" ", s)
    s = PUNCT_RE.sub(" ", s)
    return WS.sub(" ", s).strip()

def body_key(text):
    """Join key for rank matching by body copy. Long-enough prefix only —
    short/empty bodies would collide."""
    n = norm(text)[:120]
    return n if len(n) >= 20 else ""

def ngrams(tokens, n):
    return [" ".join(tokens[i:i+n]) for i in range(len(tokens)-n+1)]

def tokens_of(text):
    return [t for t in norm(text).split() if len(t) > 2 and t not in STOPWORDS]

def analyze_text(bodies):
    tok_lists = [tokens_of(b) for b in bodies if b]
    uni = Counter(t for ts in tok_lists for t in ts)
    bi  = Counter(g for ts in tok_lists for g in ngrams(ts, 2))
    tri = Counter(g for ts in tok_lists for g in ngrams(ts, 3))
    # opening phrases: first 4 words of normalized body
    openings = Counter()
    for b in bodies:
        n = norm(b).split()[:4]
        if len(n) >= 3: openings[" ".join(n)] += 1
    # near-dup clusters: first 80 chars of normalized
    dup = Counter(norm(b)[:80] for b in bodies if b)
    return uni, bi, tri, openings, dup

# ---- rows ----

def base_fields(a):
    snap = a.get("snapshot") or {}
    v_sd, v_hd, v_prev = first_video_urls(snap)
    landing_type, landing_url = classify_landing(snap_link_url(snap))
    cta_type, cta_text = snap_cta(snap)
    return {
        "ad_archive_id": a.get("ad_archive_id") or "",
        "media_type": classify_media(a),
        "display_format": snap.get("display_format"),
        "start_date": ts_iso(a.get("start_date")),
        "end_date": ts_iso(a.get("end_date")),
        "days_running": days_running(a),
        "total_active_time": a.get("total_active_time") or "",
        "impressions_text": impressions_text_of(a),
        "collation_count": a.get("collation_count"),
        "cta_type": cta_type,
        "cta_text": cta_text,
        "landing_type": landing_type,
        "landing_url": landing_url,
        "caption": snap.get("caption"),
        "title": snap_title(snap),
        "body_text": snap_body_text(snap).replace("\n"," ").strip()[:2000],
        "video_sd_url": v_sd,
        "video_hd_url": v_hd,
        "video_preview_image_url": v_prev,
        "image_url": first_image_url(snap),
    }

# ---- main ----

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page-id", required=True)
    ap.add_argument("--env-file", default="", help="explicit .env file with SCRAPE_CREATORS_API_KEY")
    ap.add_argument("--countries", required=True, help="comma-separated 2-letter codes, or ALL")
    ap.add_argument("--out-prefix", default="fb_ads")
    ap.add_argument("--cache-ttl", type=int, default=CACHE_TTL_SEC, help="cache TTL in seconds (0 = disable)")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--offline", action="store_true",
                    help="Serve everything possible from cache regardless of age (shards without "
                         "cache still hit the API). For re-running analytics without fresh credits.")
    ap.add_argument("--geo-breakdown", action="store_true",
                    help="When passing ALL, also probe DEFAULT_PROBE_GEOS to attribute each ad to specific countries. "
                         "Auto-enabled when --countries=ALL.")
    ap.add_argument("--no-geo-breakdown", action="store_true",
                    help="Disable the automatic geo breakdown probes when --countries=ALL.")
    ap.add_argument("--probe-geos", default="",
                    help="Comma-separated geos to probe instead of DEFAULT_PROBE_GEOS (only used when geo breakdown is on).")
    ap.add_argument("--no-impressions-rank", action="store_true",
                    help="Skip the second pass that ranks creatives by total_impressions.")
    ap.add_argument("--impressions-cap", type=int, default=0,
                    help="Max creatives to pull in the impressions pass (0 = ALL creatives). Default 0.")
    ap.add_argument("--include-inactive", action="store_true",
                    help="Also pull status=INACTIVE ads (what they recently stopped running) into "
                         "<prefix>_inactive.csv + a report section. No probes/rank for these.")
    args = ap.parse_args()

    if args.env_file:
        load_env_file(args.env_file)
    if not API_KEY:
        sys.exit("ERROR: set SCRAPE_CREATORS_API_KEY (or SCRAPECREATORS_API_KEY), or pass --env-file")

    cache_ttl = 0 if args.no_cache else (10**10 if args.offline else args.cache_ttl)
    if args.offline:
        print("[offline] serving from cache regardless of age; missing shards will still hit the API")

    countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()]

    # Decide whether to run geo probes.
    do_geo_probe = (args.geo_breakdown or "ALL" in countries) and not args.no_geo_breakdown
    probe_geos = []
    if do_geo_probe:
        if args.probe_geos:
            probe_geos = [c.strip().upper() for c in args.probe_geos.split(",") if c.strip()]
        else:
            probe_geos = list(DEFAULT_PROBE_GEOS)
        # avoid re-probing countries the user already passed
        probe_geos = [c for c in probe_geos if c not in countries]

    fetch_countries = countries + probe_geos
    print(f"page_id={args.page_id} countries={countries}"
          + (f" + probe={probe_geos}" if probe_geos else ""))

    t_fetch_start = time.time()
    results = asyncio.run(fetch_all(args.page_id, fetch_countries, cache_ttl))
    t_fetch = time.time() - t_fetch_start
    print(f"\n[TIMING] fetch total: {t_fetch:.2f}s ({len(fetch_countries)} shards)")

    # dedupe by ad_archive_id, track per-country membership (union across shards)
    # "ALL" is treated as a meta-shard — it contributes ads to the inventory but
    # is NOT added to seen_in / per_country (otherwise every ad would show "ALL").
    t0 = time.time()
    by_id = {}
    seen_in = defaultdict(set)
    per_country = defaultdict(int)
    per_country_unique = defaultdict(set)
    all_page_times = []
    cache_hits = 0
    failed_shards = []
    truncated_shards = []
    for c, mt, ads, pts, from_cache, ok, trunc in results:
        all_page_times.extend(pts)
        if from_cache: cache_hits += 1
        if not ok: failed_shards.append(c)
        if trunc: truncated_shards.append(c)
        for a in ads:
            aid = a.get("ad_archive_id")
            if not aid: continue
            if aid not in by_id or (not by_id[aid].get("snapshot") and a.get("snapshot")):
                by_id[aid] = a
            if c != "ALL":
                seen_in[aid].add(c)
                per_country_unique[c].add(aid)
    for c, s in per_country_unique.items():
        per_country[c] = len(s)
    t_dedupe = time.time() - t0
    avg_page = sum(all_page_times)/len(all_page_times) if all_page_times else 0
    print(f"[TIMING] dedupe: {t_dedupe:.3f}s | API pages: {len(all_page_times)} | avg page: {avg_page:.2f}s | cache hits: {cache_hits}/{len(results)} shards")
    if failed_shards:
        print(f"[WARN] shards failed after retries (not cached, geo counts undercounted): {', '.join(failed_shards)}", file=sys.stderr)

    all_ads = list(by_id.values())
    print(f"Total unique ads: {len(all_ads)}")

    if not all_ads:
        print("No ads returned — aborting. Check network access, API key, and page_id "
              "(this script makes direct HTTPS calls to api.scrapecreators.com).", file=sys.stderr)
        sys.exit(1)

    # -------- impressions pass: rank creatives by total_impressions --------
    # Separate chain sorted high->low. Meta gives no numbers in this view, so it
    # is a RANK. When the user asked for exactly one real country, rank within it
    # (otherwise the rank is global while the catalog is local). The impression
    # view collates creatives, so its ad_archive_id can differ from the catalog ->
    # join by id, then media asset filename, then unique body copy.
    imp_country = countries[0] if (len(countries) == 1 and countries[0] != "ALL") else "ALL"
    imp_ads = []
    imp_truncated = False
    imp_rank_by_id = {}
    imp_rank_by_stem = {}
    imp_rank_by_body = {}
    if not args.no_impressions_rank:
        t0 = time.time()
        imp_ads, imp_truncated = asyncio.run(
            fetch_impressions(args.page_id, cache_ttl, args.impressions_cap, imp_country))
        body_counts = Counter()
        for a in imp_ads:
            bk = body_key(snap_body_text(a.get("snapshot") or {}))
            if bk: body_counts[bk] += 1
        for i, a in enumerate(imp_ads, 1):
            aid = a.get("ad_archive_id")
            if aid and aid not in imp_rank_by_id:
                imp_rank_by_id[aid] = i
            snap = a.get("snapshot") or {}
            st = media_stem(snap)
            if st and st not in imp_rank_by_stem:
                imp_rank_by_stem[st] = i
            bk = body_key(snap_body_text(snap))
            if bk and body_counts[bk] == 1:
                imp_rank_by_body[bk] = i
        print(f"[TIMING] impressions pass: {time.time()-t0:.2f}s ({len(imp_ads)} ranked)")

    def impression_rank_for(a):
        aid = a.get("ad_archive_id")
        if aid in imp_rank_by_id:
            return imp_rank_by_id[aid], "id"
        snap = a.get("snapshot") or {}
        st = media_stem(snap)
        if st and st in imp_rank_by_stem:
            return imp_rank_by_stem[st], "media"
        bk = body_key(snap_body_text(snap))
        if bk and bk in imp_rank_by_body:
            return imp_rank_by_body[bk], "body"
        return "", ""

    # -------- full catalog CSV --------
    t0 = time.time()
    rows = []
    for a in all_ads:
        b = base_fields(a)
        irank, imatch = impression_rank_for(a)
        aid = b["ad_archive_id"]
        rows.append({
            "ad_archive_id": aid,
            "impression_rank": irank,
            "impression_rank_match": imatch,
            "is_active": a.get("is_active"),
            "media_type": b["media_type"],
            "display_format": b["display_format"],
            "start_date": b["start_date"],
            "end_date": b["end_date"],
            "days_running": b["days_running"],
            "total_active_time": b["total_active_time"],
            "impressions_text": b["impressions_text"],
            "countries_seen": ",".join(sorted(seen_in[aid])),
            "country_count": len(seen_in[aid]),
            "publisher_platform": ",".join(a.get("publisher_platform") or []),
            "page_id": a.get("page_id"),
            "page_name": a.get("page_name"),
            "collation_count": b["collation_count"],
            "cta_type": b["cta_type"],
            "cta_text": b["cta_text"],
            "landing_type": b["landing_type"],
            "landing_url": b["landing_url"],
            "caption": b["caption"],
            "title": b["title"],
            "body_text": b["body_text"],
            "video_sd_url": b["video_sd_url"],
            "video_hd_url": b["video_hd_url"],
            "video_preview_image_url": b["video_preview_image_url"],
            "image_url": b["image_url"],
        })
    t_rows = time.time() - t0
    print(f"[TIMING] build rows (classify+extract): {t_rows:.3f}s")

    t0 = time.time()
    csv_path = f"{args.out_prefix}_ads.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    t_csv = time.time() - t0
    print(f"[TIMING] write CSV: {t_csv:.3f}s")

    t0 = time.time()
    with open(f"{args.out_prefix}_ads_full.json","w") as f:
        json.dump(all_ads, f, ensure_ascii=False, separators=(",", ":"))
    t_json = time.time() - t0
    print(f"[TIMING] write full JSON: {t_json:.3f}s ({os.path.getsize(f'{args.out_prefix}_ads_full.json')/1024:.0f} KB)")

    # -------- by-impressions CSV: every ranked creative high->low --------
    imp_csv_path = None
    imp_rows = []
    if imp_ads:
        t0 = time.time()
        for i, a in enumerate(imp_ads, 1):
            b = base_fields(a)
            aid = b["ad_archive_id"]
            imp_rows.append({
                "impression_rank": i,
                "ad_archive_id": aid,
                "ad_library_url": f"https://www.facebook.com/ads/library/?id={aid}",
                "in_catalog": "yes" if aid in by_id else "no",
                "collation_count": b["collation_count"],
                "media_type": b["media_type"],
                "display_format": b["display_format"],
                "start_date": b["start_date"],
                "end_date": b["end_date"],
                "days_running": b["days_running"],
                "cta_type": b["cta_type"],
                "cta_text": b["cta_text"],
                "landing_type": b["landing_type"],
                "landing_url": b["landing_url"],
                "title": b["title"],
                "body_text": b["body_text"],
                "video_hd_url": b["video_hd_url"],
                "video_preview_image_url": b["video_preview_image_url"],
                "image_url": b["image_url"],
            })
        imp_csv_path = f"{args.out_prefix}_by_impressions.csv"
        with open(imp_csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(imp_rows[0].keys()))
            w.writeheader(); w.writerows(imp_rows)
        print(f"[TIMING] write impressions CSV: {time.time()-t0:.3f}s ({len(imp_rows)} rows)")

    # -------- inactive pass (optional) --------
    inactive_rows = []
    inactive_csv_path = None
    if args.include_inactive:
        t0 = time.time()
        in_results = asyncio.run(fetch_all(args.page_id, countries, cache_ttl, status="INACTIVE"))
        in_by_id = {}
        for c, mt, ads, pts, from_cache, ok, trunc in in_results:
            for a in ads:
                aid = a.get("ad_archive_id")
                if aid and aid not in in_by_id:
                    in_by_id[aid] = a
        for a in in_by_id.values():
            b = base_fields(a)
            b.pop("caption", None)
            b.pop("video_sd_url", None)
            b["publisher_platform"] = ",".join(a.get("publisher_platform") or [])
            inactive_rows.append(b)
        inactive_rows.sort(key=lambda r: r["end_date"], reverse=True)
        if inactive_rows:
            inactive_csv_path = f"{args.out_prefix}_inactive.csv"
            with open(inactive_csv_path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(inactive_rows[0].keys()))
                w.writeheader(); w.writerows(inactive_rows)
        print(f"[TIMING] inactive pass: {time.time()-t0:.2f}s ({len(inactive_rows)} ads)")

    # -------- analytics --------
    t0 = time.time()
    media_counts = Counter(r["media_type"] for r in rows)
    landing_counts = Counter(r["landing_type"] for r in rows)
    cta_counts = Counter((r["cta_type"] or "NONE") for r in rows)

    web_funnels = Counter()
    app_urls = Counter()
    for r in rows:
        lt, lu = r["landing_type"], r["landing_url"]
        if lt == "web_funnel":
            web_funnels[funnel_key(lu)] += 1
        elif lt in ("ios_app_store","google_play"):
            app_urls[(lt, lu)] += 1

    # text patterns on body_text
    bodies = [r["body_text"] for r in rows]
    uni, bi, tri, openings, dup = analyze_text(bodies)

    # write markdown report
    md = []
    md.append(f"# FB Ads Short Analysis — page_id {args.page_id}\n")
    md.append(f"**Countries scanned:** {', '.join(countries)}"
              + (f" + probe geos ({len(probe_geos)})" if probe_geos else "") + "\n")
    md.append(f"**Total unique active creatives:** {len(rows)}\n")
    if failed_shards:
        md.append(f"> ⚠️ Shards failed after retries: **{', '.join(failed_shards)}** — their geo "
                  "counts are undercounted this run (failed shards are never cached; re-run to retry).\n")
    if truncated_shards:
        md.append(f"> ⚠️ Catalog shards cut at the API's ~1000-ad cursor ceiling: {', '.join(truncated_shards)}.\n")
    if do_geo_probe and "ALL" in countries:
        unattr = sum(1 for r in rows if not r["countries_seen"])
        if unattr:
            md.append(f"> ℹ️ **{unattr}** ads appear in the ALL feed but in none of the probed geos — "
                      "they run in markets outside the probe list (filter empty `countries_seen` in the CSV).\n")
    # ---- impressions ranking section ----
    if imp_ads:
        n_id = sum(1 for r in rows if r["impression_rank_match"] == "id")
        n_media = sum(1 for r in rows if r["impression_rank_match"] == "media")
        n_body = sum(1 for r in rows if r["impression_rank_match"] == "body")
        n_ranked = n_id + n_media + n_body
        cat = max(len(rows), 1)
        imp_n = max(len(imp_ads), 1)
        mapped = len({r["impression_rank"] for r in rows if r["impression_rank"] != ""})
        md.append("\n## Creatives ranked by impressions\n")
        md.append(f"Pulled **{len(imp_ads)}** creatives via `sort_by=total_impressions` "
                  f"(country={imp_country}, high → low). "
                  "Meta exposes no impression numbers in this view, so this is a **rank, not absolute views**. "
                  f"Authoritative ranked list: `{os.path.basename(imp_csv_path)}`.\n")
        if imp_truncated:
            md.append("> ⚠️ The impressions pull stopped at the API's cursor-size limit (~1000 ads), so the lowest-reach "
                      "long tail is not ranked. The top ranks — the ones that matter — are complete.\n")
        md.append(f"**Impression-ranked → catalog match:** {mapped}/{len(imp_ads)} ({mapped*100//imp_n}%) of the "
                  "ranked creatives tie back to at least one catalog row. "
                  "The rest are collation representatives whose id/asset isn't in the catalog (the two sort modes "
                  "group creatives differently), so match by creative, not id.\n")
        md.append(f"**Catalog rows carrying a rank:** {n_ranked}/{len(rows)} ({n_ranked*100//cat}%) — "
                  f"{n_id} by ad id, {n_media} by media asset, {n_body} by unique body copy; the rest sit "
                  "below the pulled impression depth or didn't map. Treat `*_by_impressions.csv` as the source of truth.\n")

        def tier_stats(subset):
            mt = Counter(x["media_type"] for x in subset)
            ld = Counter(x["landing_type"] for x in subset)
            colls = [x["collation_count"] for x in subset if isinstance(x["collation_count"], int)]
            avg_coll = (sum(colls) / len(colls)) if colls else 0
            days = [x["days_running"] for x in subset if isinstance(x["days_running"], int)]
            avg_days = (sum(days) / len(days)) if days else 0
            hook = Counter(norm(x["body_text"])[:60] for x in subset if x["body_text"]).most_common(1)
            return mt, ld, avg_coll, avg_days, hook

        tiers = [t for t in (10, 25, 50, 100) if t <= len(imp_rows)]
        if len(imp_rows) not in tiers:
            tiers.append(len(imp_rows))
        md.append("Breakdown of the top creatives by reach (each tier is cumulative from rank 1):\n")
        md.append("| Tier | Media mix | Top landing | Avg collation | Avg days live | Dominant hook |")
        md.append("|---|---|---|---:|---:|---|")
        for t in tiers:
            sub = imp_rows[:t]
            mt, ld, avg_coll, avg_days, hook = tier_stats(sub)
            mt_s = ", ".join(f"{m} {n*100//len(sub)}%" for m, n in mt.most_common(3))
            ld_s = ", ".join(f"{l} {n*100//len(sub)}%" for l, n in ld.most_common(2))
            hk = (hook[0][0][:40] + f" (×{hook[0][1]})") if hook else "—"
            label = f"top {t}" if t != len(imp_rows) else f"all {t}"
            md.append(f"| {label} | {mt_s} | {ld_s} | {avg_coll:.1f} | {avg_days:.0f} | {hk} |")

        md.append("\n### Top 15 creatives by impressions\n")
        for x in imp_rows[:15]:
            tt = (x["title"] or x["body_text"] or "").strip()[:70]
            bits = [f"[{x['media_type']}]"]
            if isinstance(x["days_running"], int): bits.append(f"{x['days_running']}d live")
            md.append(f"{x['impression_rank']}. {' '.join(bits)} {tt} — {x['ad_library_url']}")

    # Per-country breakdown (excludes the "ALL" meta-shard).
    real_country_counts = [(c, per_country[c]) for c in per_country if c != "ALL" and per_country[c] > 0]
    real_country_counts.sort(key=lambda x: -x[1])
    if real_country_counts:
        md.append("\n## Per-country active ad counts\n")
        md.append("Each ad can appear in multiple countries, so the sum may exceed total unique creatives. Geos with 0 hits are omitted.\n")
        md.append("| Country | Active ads | % of total |")
        md.append("|---|---:|---:|")
        for c, n in real_country_counts:
            pct = n * 100 // max(len(rows), 1)
            md.append(f"| {c} | {n} | {pct}% |")
        # Solo-geo ads (only one country in seen_in)
        solo = Counter()
        for aid, s in seen_in.items():
            if len(s) == 1:
                solo[next(iter(s))] += 1
        if solo:
            md.append("\n### Solo-geo ads (ads appearing in exactly one probed country)\n")
            for c, n in solo.most_common(20):
                md.append(f"- {c}: {n}")

    md.append("\n## Media type breakdown\n")
    for m, n in media_counts.most_common():
        md.append(f"- {m}: **{n}** ({n*100//len(rows)}%)")

    plat = Counter()
    for r in rows:
        for pf in (r["publisher_platform"] or "").split(","):
            if pf: plat[pf] += 1
    if plat:
        md.append("\n## Publisher platforms (an ad counts once per platform)\n")
        for p, n in plat.most_common():
            md.append(f"- {p}: **{n}** ({n*100//len(rows)}%)")

    md.append("\n## Landing destinations\n")
    for lt, n in landing_counts.most_common():
        md.append(f"- {lt}: **{n}**")
    if app_urls:
        md.append("\n### App store links\n")
        for (lt, lu), n in app_urls.most_common():
            md.append(f"- `{lt}` × {n} → {lu}")
    if web_funnels:
        md.append("\n### Web funnel URLs (normalized domain+path, top 20)\n")
        for k, n in web_funnels.most_common(20):
            md.append(f"- **×{n}** — {k}")

    md.append("\n## CTA button types\n")
    for c, n in cta_counts.most_common():
        md.append(f"- {c}: {n}")

    # Impression buckets: Meta sometimes exposes coarse ranges (<100, 100-1K, ...)
    # in the per-country catalog view — free numbers when present.
    buckets = Counter(r["impressions_text"] for r in rows if r["impressions_text"])
    if buckets:
        md.append("\n## Impression buckets (where Meta exposes them)\n")
        md.append(f"{sum(buckets.values())}/{len(rows)} catalog rows carry a coarse `impressions_text` range:\n")
        for b_, n in buckets.most_common():
            md.append(f"- {b_}: {n}")

    # Launch velocity: how many still-active creatives were launched each month.
    months = Counter(r["start_date"][:7] for r in rows if r["start_date"])
    if months:
        md.append("\n## Creative launch velocity (still-active creatives by launch month, last 12)\n")
        last = sorted(months)[-12:]
        peak = max(months[m] for m in last)
        for m in last:
            bar = "█" * max(1, months[m] * 24 // max(peak, 1))
            md.append(f"- {m}: {months[m]:4d} {bar}")

    md.append("\n## Text patterns (body_text)\n")
    md.append("### Top opening phrases (first 3-4 words)\n")
    for p, n in openings.most_common(20):
        if n >= 2: md.append(f"- ×{n}: {p}")
    md.append("\n### Top bigrams\n")
    for g, n in bi.most_common(25): md.append(f"- ×{n}: {g}")
    md.append("\n### Top trigrams\n")
    for g, n in tri.most_common(25): md.append(f"- ×{n}: {g}")
    md.append("\n### Near-duplicate body_text clusters (first 80 chars, ≥2 ads)\n")
    for t, n in dup.most_common(25):
        if n >= 2 and t: md.append(f"- ×{n}: {t}")
    md.append("\n### Top unigrams\n")
    for g, n in uni.most_common(30): md.append(f"- ×{n}: {g}")

    if args.include_inactive:
        md.append(f"\n## Recently stopped ads (status=INACTIVE): {len(inactive_rows)}\n")
        if inactive_rows:
            imt = Counter(r["media_type"] for r in inactive_rows)
            md.append("Media mix: " + ", ".join(f"{m} {n}" for m, n in imt.most_common()) + "\n")
            md.append("Last 10 by end date:\n")
            for r in inactive_rows[:10]:
                tt = (r["title"] or r["body_text"] or "").strip()[:70]
                md.append(f"- {r['end_date']} [{r['media_type']}] ({r['days_running']}d live) {tt}")
            md.append(f"\nFull list: `{os.path.basename(inactive_csv_path)}`")

    t_analytics = time.time() - t0
    print(f"[TIMING] analytics (counters + ngrams): {t_analytics:.3f}s")

    t0 = time.time()
    md_path = f"{args.out_prefix}_analytics.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    t_md = time.time() - t0
    print(f"[TIMING] write markdown report: {t_md:.3f}s")

    # run metadata (for later runs / comparisons)
    meta_out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "page_id": args.page_id,
        "page_name": rows[0]["page_name"] if rows else "",
        "countries": countries,
        "probe_geos": probe_geos,
        "total_unique_ads": len(rows),
        "impressions": {"pulled": len(imp_ads), "country": imp_country,
                        "truncated": imp_truncated, "cap": args.impressions_cap},
        "inactive_ads": len(inactive_rows) if args.include_inactive else None,
        "failed_shards": failed_shards,
        "truncated_shards": truncated_shards,
        "api_requests": REQUESTS_MADE,
    }
    with open(f"{args.out_prefix}_meta.json", "w") as f:
        json.dump(meta_out, f, indent=2, ensure_ascii=False)

    total = t_fetch + t_dedupe + t_rows + t_csv + t_json + t_analytics + t_md
    print(f"\n[TIMING BREAKDOWN]")
    print(f"  fetch (API):  {t_fetch:6.2f}s  ({t_fetch*100/total:.0f}%)")
    print(f"  dedupe:       {t_dedupe:6.3f}s  ({t_dedupe*100/total:.0f}%)")
    print(f"  build rows:   {t_rows:6.3f}s  ({t_rows*100/total:.0f}%)")
    print(f"  write CSV:    {t_csv:6.3f}s  ({t_csv*100/total:.0f}%)")
    print(f"  write JSON:   {t_json:6.3f}s  ({t_json*100/total:.0f}%)")
    print(f"  analytics:    {t_analytics:6.3f}s  ({t_analytics*100/total:.0f}%)")
    print(f"  write MD:     {t_md:6.3f}s  ({t_md*100/total:.0f}%)")
    print(f"  TOTAL:        {total:6.2f}s")
    print(f"\n[COST] API requests this run (≈ credits): {REQUESTS_MADE}")

    print(f"\nCSV:      {csv_path}")
    if imp_csv_path:
        print(f"Impr CSV: {imp_csv_path}")
    if inactive_csv_path:
        print(f"Inactive: {inactive_csv_path}")
    print(f"Full JSON:{args.out_prefix}_ads_full.json")
    print(f"Meta:     {args.out_prefix}_meta.json")
    print(f"Report:   {md_path}")

if __name__ == "__main__":
    main()
