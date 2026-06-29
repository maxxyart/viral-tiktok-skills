/**
 * Analyze hook TEXT from TikTok video cover images.
 * Downloads cover images, uses Gemini vision to OCR hook text,
 * then discovers repeating hook PATTERNS via a second Gemini call.
 *
 * Much faster & cheaper than full video analysis — only processes static images.
 *
 * Usage: npx tsx src/scripts/analyze-cover-hooks.ts [handle] [--skip N] [--count N]
 */

import "dotenv/config";
import { writeFileSync } from "node:fs";
import axios from "axios";
import { GoogleGenerativeAI } from "@google/generative-ai";
import { ScrapeCreatorsClient } from "../clients/scrapecreators-client.js";
import { TikTokClient } from "../clients/tiktok-client.js";
import { assertGoogleApiKey } from "../config/env.js";

function parseArgs() {
  const args = process.argv.slice(2);
  let handle = "trackwithpaulina";
  let skip = 0;
  let count = 50;
  let concurrency = 10;
  let outJson: string | null = null;
  let outCsv: string | null = null;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--skip" && args[i + 1]) {
      skip = parseInt(args[++i], 10);
    } else if (args[i] === "--count" && args[i + 1]) {
      count = parseInt(args[++i], 10);
    } else if (args[i] === "--concurrency" && args[i + 1]) {
      concurrency = parseInt(args[++i], 10);
    } else if (args[i] === "--out" && args[i + 1]) {
      outJson = args[++i];
    } else if (args[i] === "--out-csv" && args[i + 1]) {
      outCsv = args[++i];
    } else if (!args[i].startsWith("--")) {
      handle = args[i];
    }
  }
  return { handle, skip, count, concurrency, outJson, outCsv };
}

const {
  handle: HANDLE,
  skip: SKIP,
  count: TARGET_COUNT,
  concurrency: CONCURRENCY,
  outJson: OUT_JSON,
  outCsv: OUT_CSV,
} = parseArgs();
const MODEL = "gemini-3.1-flash-lite-preview";

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
  coverUrl: string | null;
};

type CoverAnalysisResult = {
  hookText: string;
  hasText: boolean;
};

type AnalyzedVideo = VideoMeta & CoverAnalysisResult;

type PatternCluster = {
  patternName: string;
  formula: string;
  count: number;
  medianViews: number;
  avgViews: number;
  viralityRate: number;
  medianLikes: number;
  medianSaves: number;
  videos: AnalyzedVideo[];
};

// ── Step 1: Fetch videos ──

async function fetchLatestVideos(
  handle: string,
  count: number,
  skip: number,
): Promise<VideoMeta[]> {
  const scrapeClient = new ScrapeCreatorsClient();
  const tiktok = new TikTokClient(scrapeClient);

  const totalNeeded = skip + count;
  const allVideos: VideoMeta[] = [];
  let cursor: string | number | null = null;
  let page = 0;

  while (allVideos.length < totalNeeded) {
    page++;
    console.error(`  Fetching page ${page} (cursor=${cursor ?? "start"})...`);

    const resp: any = await tiktok.getProfileVideos({
      handle,
      maxCursor: cursor,
      sortBy: "latest",
      trim: false,
    });

    const items: any[] = resp.aweme_list ?? [];
    if (items.length === 0) break;

    for (const item of items) {
      if (allVideos.length >= totalNeeded) break;

      const coverUrl = extractCoverUrl(item);

      allVideos.push({
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
        coverUrl,
      });
    }

    const hasMore = Number(resp.has_more ?? 0) === 1;
    cursor = resp.max_cursor ?? null;
    if (!hasMore || cursor === null) break;
  }

  return allVideos.slice(skip, skip + count);
}

function extractCoverUrl(item: any): string | null {
  // Prefer origin_cover (full resolution) > cover_large > cover > dynamic_cover
  const paths = [
    item.video?.origin_cover?.url_list?.[0],
    item.video?.cover_large?.url_list?.[0],
    item.video?.cover?.url_list?.[0],
    item.video?.dynamic_cover?.url_list?.[0],
    item.video?.ai_dynamic_cover?.url_list?.[0],
  ];
  for (const url of paths) {
    if (typeof url === "string" && url.length > 0) return url;
  }
  return null;
}

// ── Step 2: Analyze cover images with Gemini Vision ──

const COVER_ANALYSIS_PROMPT = `You analyze TikTok video cover/thumbnail images for marketing research.

Look at this TikTok video cover image and extract ALL text visible on it.

Return strictly one JSON object:
{
  "hookText": "<ALL text visible on the cover image, preserving line breaks as ' | '. If no text, return empty string>",
  "hasText": <true if there is any readable text on the image, false otherwise>
}

Rules:
- Extract EVERY piece of text you can see, including small text, watermarks, captions
- Focus on the main hook text (usually large, centered text that grabs attention)
- Preserve the original language of the text (do NOT translate)
- If text spans multiple lines, join with " | "
- Return ONLY the JSON object, no markdown, no explanation`;

async function downloadImageAsBase64(url: string): Promise<{ base64: string; mimeType: string } | null> {
  try {
    const response = await axios.get(url, {
      responseType: "arraybuffer",
      timeout: 15_000,
      validateStatus: (status) => status >= 200 && status < 300,
    });

    const contentType = response.headers["content-type"];
    let mimeType = "image/jpeg";
    if (typeof contentType === "string") {
      const parsed = contentType.split(";")[0]?.trim();
      if (parsed && parsed.startsWith("image/")) {
        mimeType = parsed;
      }
      // TikTok sometimes returns HEIC — Gemini accepts it as image/heic
      if (parsed === "application/octet-stream" || parsed?.includes("heic")) {
        mimeType = "image/jpeg"; // fallback, usually works
      }
    }

    const base64 = Buffer.from(response.data).toString("base64");
    return { base64, mimeType };
  } catch (err: any) {
    console.error(`    Failed to download image: ${err.message?.slice(0, 100)}`);
    return null;
  }
}

async function analyzeCoverImage(
  model: any,
  video: VideoMeta,
): Promise<CoverAnalysisResult | null> {
  if (!video.coverUrl) {
    console.error(`    No cover URL for ${video.id}, skipping`);
    return null;
  }

  try {
    const imageData = await downloadImageAsBase64(video.coverUrl);
    if (!imageData) return null;

    const response = await model.generateContent({
      contents: [
        {
          role: "user",
          parts: [
            { text: COVER_ANALYSIS_PROMPT },
            {
              inlineData: {
                mimeType: imageData.mimeType,
                data: imageData.base64,
              },
            },
          ],
        },
      ],
    });

    const text = response.response.text().trim();
    const parsed = JSON.parse(text);
    return {
      hookText: parsed.hookText ?? "",
      hasText: parsed.hasText ?? false,
    };
  } catch (err: any) {
    console.error(`    Failed to analyze cover ${video.id}: ${err.message?.slice(0, 120)}`);
    return null;
  }
}

// ── Step 3: Discover hook patterns via text-only Gemini call ──

async function discoverPatterns(
  analyzed: AnalyzedVideo[],
): Promise<{ patternName: string; formula: string; videoIds: string[] }[]> {
  const apiKey = assertGoogleApiKey();
  const genAI = new GoogleGenerativeAI(apiKey);
  const model = genAI.getGenerativeModel({
    model: MODEL,
    generationConfig: { responseMimeType: "application/json" },
  });

  // Only include videos that have text on covers
  const withText = analyzed.filter((v) => v.hasText && v.hookText.length > 0);
  const withoutText = analyzed.filter((v) => !v.hasText || v.hookText.length === 0);

  if (withText.length === 0) {
    console.error("  No videos with hook text found. Cannot discover patterns.");
    return [];
  }

  const videoLines = withText
    .map((v) => `${v.id} | ${v.views} views | ${v.hookText}`)
    .join("\n");

  const prompt = `Below are hook texts extracted from TikTok video cover images (thumbnails).
Each line: VIDEO_ID | VIEWS | HOOK_TEXT_ON_COVER

${videoLines}

TASK: Identify ALL recurring hook text PATTERNS across these cover images.
A pattern is a repeating formula/template that multiple covers follow.
Strip specific details (names, numbers, destinations, products) to find the underlying template.

Rules:
- Every video with text must be assigned to exactly one pattern
- Name each pattern with a short label (3-7 words)
- Include the abstract formula with [PLACEHOLDERS] for variable parts
- Aim for 3-10 patterns (don't over-split similar hooks)
- Focus on the HOOK STRUCTURE, not the topic

Return JSON:
{
  "patterns": [
    {
      "patternName": "short descriptive name",
      "formula": "abstract hook formula with [PLACEHOLDERS]",
      "videoIds": ["id1", "id2", ...]
    }
  ]
}`;

  console.error("  Sending pattern discovery prompt to Gemini...");
  const response = await model.generateContent(prompt);
  const text = response.response.text().trim();
  const parsed = JSON.parse(text);

  // Add "No text on cover" pattern for videos without text
  const patterns = parsed.patterns ?? [];
  if (withoutText.length > 0) {
    patterns.push({
      patternName: "No text on cover",
      formula: "[Visual-only cover with no hook text]",
      videoIds: withoutText.map((v: AnalyzedVideo) => v.id),
    });
  }

  return patterns;
}

// ── Step 4: Calculate analytics ──

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 !== 0
    ? sorted[mid]
    : (sorted[mid - 1] + sorted[mid]) / 2;
}

function avg(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((s, v) => s + v, 0) / values.length;
}

function formatNum(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(Math.round(n));
}

function buildPatternClusters(
  patterns: { patternName: string; formula: string; videoIds: string[] }[],
  analyzed: AnalyzedVideo[],
  accountMedianViews: number,
): PatternCluster[] {
  const videoMap = new Map(analyzed.map((v) => [v.id, v]));

  const clusters: PatternCluster[] = [];
  for (const p of patterns) {
    const vids = p.videoIds
      .map((id) => videoMap.get(id))
      .filter((v): v is AnalyzedVideo => v !== undefined);

    if (vids.length === 0) continue;

    const views = vids.map((v) => v.views);
    const likes = vids.map((v) => v.likes);
    const saves = vids.map((v) => v.saves);
    const med = median(views);

    clusters.push({
      patternName: p.patternName,
      formula: p.formula,
      count: vids.length,
      medianViews: med,
      avgViews: avg(views),
      viralityRate: accountMedianViews > 0 ? med / accountMedianViews : 0,
      medianLikes: median(likes),
      medianSaves: median(saves),
      videos: vids.sort((a, b) => b.views - a.views),
    });
  }

  return clusters.sort((a, b) => b.medianViews - a.medianViews);
}

// ── Output ──

function csvEscape(value: unknown): string {
  const s = value === null || value === undefined ? "" : String(value);
  if (s.includes(",") || s.includes("\"") || s.includes("\n") || s.includes("\r")) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

function buildCsv(
  handle: string,
  clusters: PatternCluster[],
  accountMedianViews: number,
): string {
  const header = [
    "video_id",
    "date",
    "views",
    "likes",
    "saves",
    "comments",
    "shares",
    "hook_text",
    "pattern_name",
    "pattern_formula",
    "pattern_virality_rate",
    "account_median_views",
    "link",
  ];

  const rows: string[][] = [header];
  for (const c of clusters) {
    for (const v of c.videos) {
      rows.push([
        v.id,
        v.date,
        String(v.views),
        String(v.likes),
        String(v.saves),
        String(v.comments),
        String(v.shares),
        v.hookText,
        c.patternName,
        c.formula,
        c.viralityRate.toFixed(3),
        String(accountMedianViews),
        `https://www.tiktok.com/@${handle}/video/${v.id}`,
      ]);
    }
  }

  return rows.map((r) => r.map(csvEscape).join(",")).join("\n") + "\n";
}

function buildJsonOutput(
  handle: string,
  analyzed: AnalyzedVideo[],
  clusters: PatternCluster[],
  accountMedianViews: number,
) {
  const withText = analyzed.filter((v) => v.hasText);
  const withoutText = analyzed.filter((v) => !v.hasText);

  return {
    handle,
    totalVideos: analyzed.length,
    videosWithHookText: withText.length,
    videosWithoutText: withoutText.length,
    accountMedianViews,
    patterns: clusters.map((c) => ({
      patternName: c.patternName,
      formula: c.formula,
      count: c.count,
      medianViews: c.medianViews,
      avgViews: Math.round(c.avgViews),
      viralityRate: +c.viralityRate.toFixed(2),
      medianLikes: c.medianLikes,
      medianSaves: c.medianSaves,
      topVideos: c.videos.slice(0, 5).map((v) => ({
        id: v.id,
        hookText: v.hookText,
        views: v.views,
        likes: v.likes,
        saves: v.saves,
        date: v.date,
        link: `https://www.tiktok.com/@${handle}/video/${v.id}`,
      })),
    })),
  };
}

// ── Main ──

async function main() {
  console.error(
    `\nAnalyzing cover hooks for ${TARGET_COUNT} videos from @${HANDLE} (skip=${SKIP})\n`,
  );

  // 1. Fetch videos
  console.error("Step 1: Fetching videos...");
  const videos = await fetchLatestVideos(HANDLE, TARGET_COUNT, SKIP);
  console.error(`  Fetched ${videos.length} videos (skipped first ${SKIP})\n`);

  if (videos.length === 0) {
    console.log(JSON.stringify({ error: "No videos found", handle: HANDLE }));
    process.exit(1);
  }

  // 2. Analyze each cover image with Gemini Vision (parallel with semaphore)
  console.error(
    `Step 2: Analyzing cover images with Gemini Vision (${MODEL}, concurrency=${CONCURRENCY})...`,
  );
  const apiKey = assertGoogleApiKey();
  const genAI = new GoogleGenerativeAI(apiKey);
  const model = genAI.getGenerativeModel({
    model: MODEL,
    generationConfig: { responseMimeType: "application/json" },
  });

  const ocrStart = Date.now();
  const analyzed: AnalyzedVideo[] = new Array(videos.length);
  let done = 0;

  async function worker(i: number) {
    const v = videos[i];
    const result = await analyzeCoverImage(model, v);
    done++;
    const tag = `[${done}/${videos.length}]`;
    if (result) {
      analyzed[i] = { ...v, ...result };
      const hookPreview = result.hasText
        ? `Hook: ${result.hookText.slice(0, 60)}`
        : "(no text)";
      console.error(`  ${tag} ${formatNum(v.views)} views | ${hookPreview}`);
    } else {
      analyzed[i] = { ...v, hookText: "", hasText: false };
      console.error(`  ${tag} ${formatNum(v.views)} views | (download/OCR failed)`);
    }
  }

  // Mini semaphore: keep at most CONCURRENCY workers in flight.
  let next = 0;
  const runners: Promise<void>[] = [];
  const slotCount = Math.min(CONCURRENCY, videos.length);
  for (let s = 0; s < slotCount; s++) {
    runners.push(
      (async () => {
        while (true) {
          const i = next++;
          if (i >= videos.length) return;
          await worker(i);
        }
      })(),
    );
  }
  await Promise.all(runners);

  const ocrSec = (Date.now() - ocrStart) / 1000;
  const withText = analyzed.filter((v) => v.hasText);
  console.error(
    `\n  ${withText.length}/${analyzed.length} covers have hook text`,
  );
  console.error(
    `  OCR phase: ${ocrSec.toFixed(1)}s total, ${(ocrSec / videos.length).toFixed(2)}s/cover avg\n`,
  );

  // 3. Discover patterns across all hooks
  console.error("Step 3: Discovering hook text patterns...");
  const rawPatterns = await discoverPatterns(analyzed);
  console.error(`  Found ${rawPatterns.length} patterns\n`);

  // 4. Calculate analytics & output JSON
  const accountMedianViews = median(analyzed.map((v) => v.views));
  console.error(`Account median views: ${formatNum(accountMedianViews)}\n`);

  const clusters = buildPatternClusters(rawPatterns, analyzed, accountMedianViews);
  const output = buildJsonOutput(HANDLE, analyzed, clusters, accountMedianViews);
  const jsonStr = JSON.stringify(output, null, 2);

  if (OUT_JSON) {
    writeFileSync(OUT_JSON, jsonStr);
    console.error(`JSON written to ${OUT_JSON}`);
  }
  if (OUT_CSV) {
    const csv = buildCsv(HANDLE, clusters, accountMedianViews);
    writeFileSync(OUT_CSV, csv);
    console.error(`CSV written to ${OUT_CSV}`);
  }
  if (!OUT_JSON && !OUT_CSV) {
    console.log(jsonStr);
  }
  console.error("\nDone.");
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
