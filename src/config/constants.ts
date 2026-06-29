import { env } from "./env.js";

export const SCRAPE_CREATORS_BASE_URL = "https://api.scrapecreators.com";

export const RATE_LIMIT = {
  concurrency: env.SCRAPER_CONCURRENCY,
  intervalCap: env.SCRAPER_INTERVAL_CAP,
  interval: env.SCRAPER_INTERVAL_MS,
} as const;

export const RETRIES = {
  tooManyRequests: env.RETRY_429_ATTEMPTS,
  serverErrors: env.RETRY_5XX_ATTEMPTS,
  backoffMs429: [5000, 10000, 20000],
  backoffMs5xx: [3000, 3000, 3000],
} as const;

export const REQUEST_TIMEOUT_MS = env.SCRAPER_REQUEST_TIMEOUT_MS;

export const SCHEDULER_CRON = "0 * * * *";
