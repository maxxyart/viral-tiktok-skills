/**
 * Quick stats for a TikTok account: fetches ALL videos, outputs JSON with
 * aggregate metrics and top videos. No Gemini / video analysis involved.
 *
 * Features:
 *   - Disk cache at ~/.cache/tiktok_quick_stats/<handle>.json (TTL 6h default).
 *     Fresh cache hit → instant return, no API calls.
 *   - Incremental fetch past TTL: paginates "latest" until it hits a known
 *     video ID, then merges with cached videos.
 *   - Per-stage timing telemetry to stderr.
 *
 * Usage:
 *   npx tsx src/scripts/quick-stats.ts <handle> [flags]
 *   Flags:
 *     --no-cache           Disable cache entirely (full fetch, no save)
 *     --force-refresh      Ignore cache, do full fetch, overwrite cache
 *     --cache-ttl=SECONDS  Override default 6h TTL (e.g. --cache-ttl=86400)
 */

import { config as dotenvConfig } from "dotenv";
dotenvConfig({ quiet: true });
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { ScrapeCreatorsClient } from "../clients/scrapecreators-client.js";
import { TikTokClient } from "../clients/tiktok-client.js";

type VideoMeta = {
  id: string;
  desc: string;
  views: number;
  likes: number;
  comments: number;
  shares: number;
  saves: number;
  date: string;
  duration: number;
};

type CacheFile = {
  ts: number;
  handle: string;
  videos: VideoMeta[];
};

const CACHE_DIR = path.join(os.homedir(), ".cache", "tiktok_quick_stats");
const DEFAULT_TTL_SEC = 6 * 3600;

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 !== 0
    ? sorted[mid]
    : (sorted[mid - 1] + sorted[mid]) / 2;
}

function cachePath(handle: string): string {
  return path.join(CACHE_DIR, `${handle}.json`);
}

function loadCache(
  handle: string,
  ttlSec: number,
): { cache: CacheFile; ageSec: number; fresh: boolean } | null {
  const p = cachePath(handle);
  if (!fs.existsSync(p)) return null;
  try {
    const raw = fs.readFileSync(p, "utf-8");
    const data = JSON.parse(raw) as CacheFile;
    const ageSec = Date.now() / 1000 - data.ts;
    return { cache: data, ageSec, fresh: ageSec <= ttlSec };
  } catch {
    return null;
  }
}

function saveCache(handle: string, videos: VideoMeta[]): void {
  fs.mkdirSync(CACHE_DIR, { recursive: true });
  const data: CacheFile = {
    ts: Date.now() / 1000,
    handle,
    videos,
  };
  fs.writeFileSync(cachePath(handle), JSON.stringify(data));
}

function parseItem(item: any): VideoMeta {
  return {
    id: item.aweme_id ?? item.id ?? item.id_str ?? "unknown",
    desc: item.desc ?? "",
    views: item.statistics?.play_count ?? 0,
    likes: item.statistics?.digg_count ?? 0,
    comments: item.statistics?.comment_count ?? 0,
    shares: item.statistics?.share_count ?? 0,
    saves: item.statistics?.collect_count ?? 0,
    date: item.create_time
      ? new Date(item.create_time * 1000).toISOString().slice(0, 10)
      : "unknown",
    duration: item.video?.duration ?? 0,
  };
}

async function fetchVideos(
  handle: string,
  knownIds: Set<string>,
  sinceUnixSec: number | null,
): Promise<{
  videos: VideoMeta[];
  pages: number;
  pageTimes: number[];
  stoppedAtKnown: boolean;
  stoppedAtCutoff: boolean;
}> {
  const scrapeClient = new ScrapeCreatorsClient();
  const tiktok = new TikTokClient(scrapeClient);

  const videos: VideoMeta[] = [];
  const pageTimes: number[] = [];
  let cursor: string | number | null = null;
  let page = 0;
  let stoppedAtKnown = false;
  let stoppedAtCutoff = false;

  while (true) {
    page++;
    const t0 = Date.now();
    console.error(`  Fetching page ${page} (cursor=${cursor ?? "start"})...`);

    const resp: any = await tiktok.getProfileVideos({
      handle,
      maxCursor: cursor,
      sortBy: "latest",
      trim: true,
    });
    pageTimes.push((Date.now() - t0) / 1000);

    const items: any[] = resp.aweme_list ?? [];
    if (items.length === 0) break;

    let sawKnownInPage = false;
    let sawOldInPage = false;
    for (const item of items) {
      const createTime: number = item.create_time ?? 0;
      if (sinceUnixSec !== null && createTime > 0 && createTime < sinceUnixSec) {
        sawOldInPage = true;
        continue;
      }
      const meta = parseItem(item);
      if (knownIds.has(meta.id)) {
        sawKnownInPage = true;
        continue;
      }
      videos.push(meta);
    }

    if (sawOldInPage) {
      stoppedAtCutoff = true;
      break;
    }
    if (sawKnownInPage) {
      stoppedAtKnown = true;
      break;
    }
    const hasMore = Number(resp.has_more ?? 0) === 1;
    cursor = resp.max_cursor ?? null;
    if (!hasMore || cursor === null) break;
  }

  return { videos, pages: page, pageTimes, stoppedAtKnown, stoppedAtCutoff };
}

function parseArgs(argv: string[]): {
  handle: string;
  noCache: boolean;
  forceRefresh: boolean;
  cacheTtl: number;
  sinceUnixSec: number | null;
  sinceDisplay: string | null;
} {
  let handle = "trackwithpaulina";
  let noCache = false;
  let forceRefresh = false;
  let cacheTtl = DEFAULT_TTL_SEC;
  let sinceUnixSec: number | null = null;
  let sinceDisplay: string | null = null;

  for (const a of argv) {
    if (a === "--no-cache") noCache = true;
    else if (a === "--force-refresh") forceRefresh = true;
    else if (a.startsWith("--cache-ttl=")) {
      const n = parseInt(a.slice("--cache-ttl=".length), 10);
      if (Number.isFinite(n) && n >= 0) cacheTtl = n;
    } else if (a.startsWith("--since=")) {
      const raw = a.slice("--since=".length);
      const ms = Date.parse(raw);
      if (Number.isFinite(ms)) {
        sinceUnixSec = Math.floor(ms / 1000);
        sinceDisplay = raw;
      } else {
        console.error(`  WARN: --since=${raw} not parseable, ignoring`);
      }
    } else if (!a.startsWith("--")) {
      handle = a.replace(/^@/, "").replace(/^https?:\/\/(www\.)?tiktok\.com\/@?/, "").replace(/\/.*$/, "");
    }
  }
  return { handle, noCache, forceRefresh, cacheTtl, sinceUnixSec, sinceDisplay };
}

async function main() {
  const { handle, noCache, forceRefresh, cacheTtl, sinceUnixSec, sinceDisplay } =
    parseArgs(process.argv.slice(2));
  console.error(
    `\nFetching stats for @${handle}${sinceDisplay ? ` (since ${sinceDisplay})` : ""}...\n`,
  );

  const tTotal0 = Date.now();

  const tCache0 = Date.now();
  const cached = noCache ? null : loadCache(handle, cacheTtl);
  const tCacheLoad = (Date.now() - tCache0) / 1000;

  let videos: VideoMeta[];
  let fromCache = false;
  let pages = 0;
  let pageTimes: number[] = [];
  let tFetch = 0;
  let tSave = 0;
  let newCount = 0;
  let stoppedAtKnown = false;
  let stoppedAtCutoff = false;

  if (cached && cached.fresh && !forceRefresh) {
    console.error(
      `  CACHE HIT (${cached.cache.videos.length} videos, age ${cached.ageSec.toFixed(0)}s, TTL ${cacheTtl}s)`,
    );
    videos = cached.cache.videos;
    fromCache = true;
  } else {
    const knownIds =
      cached && !forceRefresh && !noCache
        ? new Set(cached.cache.videos.map((v) => v.id))
        : new Set<string>();

    if (cached && !forceRefresh && !noCache) {
      console.error(
        `  CACHE STALE (age ${cached.ageSec.toFixed(0)}s > TTL ${cacheTtl}s) — incremental fetch (${knownIds.size} known IDs)`,
      );
    } else if (noCache) {
      console.error(`  --no-cache — full fetch, no cache write`);
    } else if (forceRefresh) {
      console.error(`  --force-refresh — full fetch, cache will be overwritten`);
    } else {
      console.error(`  NO CACHE — full fetch`);
    }

    const tFetch0 = Date.now();
    const r = await fetchVideos(handle, knownIds, sinceUnixSec);
    tFetch = (Date.now() - tFetch0) / 1000;
    pages = r.pages;
    pageTimes = r.pageTimes;
    newCount = r.videos.length;
    stoppedAtKnown = r.stoppedAtKnown;
    stoppedAtCutoff = r.stoppedAtCutoff;

    const existing =
      cached && !forceRefresh && !noCache ? cached.cache.videos : [];
    const merged = [...r.videos, ...existing];
    const seen = new Set<string>();
    videos = merged.filter((v) =>
      seen.has(v.id) ? false : (seen.add(v.id), true),
    );

    if (sinceUnixSec !== null) {
      videos = videos.filter((v) => {
        const t = v.date ? Date.parse(v.date) / 1000 : 0;
        return t >= sinceUnixSec;
      });
    }

    console.error(
      `  Fetched ${r.videos.length} new + ${existing.length} cached = ${videos.length} total${sinceDisplay ? ` (after since=${sinceDisplay} filter)` : ""}`,
    );
    if (r.stoppedAtCutoff) {
      console.error(`  Stopped at --since cutoff (${sinceDisplay})`);
    }
    if (r.stoppedAtKnown) {
      console.error(`  Stopped at known ID (incremental boundary reached)`);
    }

    if (!noCache) {
      const tSave0 = Date.now();
      saveCache(handle, videos);
      tSave = (Date.now() - tSave0) / 1000;
    }
  }

  if (videos.length === 0) {
    console.log(JSON.stringify({ error: "No videos found", handle }, null, 2));
    process.exit(1);
  }

  const tAgg0 = Date.now();
  const views = videos.map((v) => v.views);
  const totalViews = views.reduce((s, v) => s + v, 0);
  const avgViews = Math.round(totalViews / views.length);
  const medianViews = median(views);

  const top5 = [...videos]
    .sort((a, b) => b.views - a.views)
    .slice(0, 5)
    .map((v) => ({
      id: v.id,
      desc: v.desc.slice(0, 120),
      date: v.date,
      views: v.views,
      likes: v.likes,
      comments: v.comments,
      shares: v.shares,
      saves: v.saves,
      engagementRate:
        v.views > 0
          ? +(
              ((v.likes + v.comments + v.shares + v.saves) / v.views) *
              100
            ).toFixed(2)
          : 0,
      viralityRate:
        medianViews > 0 ? +(v.views / medianViews).toFixed(2) : 0,
      link: `https://www.tiktok.com/@${handle}/video/${v.id}`,
    }));

  const descriptions = videos.map((v) => v.desc).filter((d) => d.length > 0);

  const result = {
    handle,
    videoCount: videos.length,
    totalViews,
    avgViews,
    medianViews,
    top5,
    descriptions,
    _meta: {
      fromCache,
      cacheAgeSec: cached ? +cached.ageSec.toFixed(0) : null,
      newlyFetched: fromCache ? 0 : newCount,
      stoppedAtKnown,
      stoppedAtCutoff,
      sinceFilter: sinceDisplay,
      pagesFetched: pages,
    },
  };
  const tAgg = (Date.now() - tAgg0) / 1000;

  const tTotal = (Date.now() - tTotal0) / 1000;
  const avgPage =
    pageTimes.length > 0
      ? pageTimes.reduce((a, b) => a + b, 0) / pageTimes.length
      : 0;

  console.error(`\n[TIMING]`);
  console.error(`  cache load:  ${tCacheLoad.toFixed(3)}s`);
  console.error(
    `  fetch:       ${tFetch.toFixed(2)}s  (${pages} pages${pages > 0 ? `, avg ${avgPage.toFixed(2)}s/page` : ""})`,
  );
  console.error(`  cache save:  ${tSave.toFixed(3)}s`);
  console.error(`  aggregate:   ${tAgg.toFixed(3)}s`);
  const mode = fromCache
    ? "cache hit"
    : stoppedAtCutoff
      ? "cutoff fetch"
      : stoppedAtKnown
        ? "incremental"
        : "full fetch";
  console.error(`  TOTAL:       ${tTotal.toFixed(2)}s  (${mode})`);

  console.log(JSON.stringify(result, null, 2));
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
