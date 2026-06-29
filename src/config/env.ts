import { config as dotenvConfig } from "dotenv";
import { z } from "zod";

process.env.DOTENV_CONFIG_QUIET = "true";
dotenvConfig();

const envSchema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  TZ: z.string().default("UTC"),
  SERVICE_ROLE: z.enum(["api", "worker"]).default("api"),
  API_PORT: z.coerce.number().int().positive().default(3000),
  DATABASE_URL: z.string().optional(),
  SCRAPE_CREATORS_API_KEY: z.string().optional(),
  GOOGLE_API_KEY: z.string().optional(),
  SCRAPER_CONCURRENCY: z.coerce.number().int().positive().default(1),
  SCRAPER_INTERVAL_CAP: z.coerce.number().int().positive().default(2),
  SCRAPER_INTERVAL_MS: z.coerce.number().int().positive().default(1000),
  SCRAPER_REQUEST_TIMEOUT_MS: z.coerce.number().int().positive().default(30000),
  RETRY_429_ATTEMPTS: z.coerce.number().int().positive().default(3),
  RETRY_5XX_ATTEMPTS: z.coerce.number().int().positive().default(3),
  ENABLE_SCHEDULER: z
    .enum(["true", "false"])
    .default("false")
    .transform((value) => value === "true"),
  SCHEDULER_ADVISORY_LOCK_KEY: z.coerce.number().int().default(424242),
  API_TOKENS: z.string().optional(),
  TEST_INSTAGRAM_HANDLE: z.string().default("tina_herbalist"),
  TEST_TIKTOK_HANDLE: z.string().default("secretherbsnana"),
});

const parsed = envSchema.parse(process.env);

export const env = {
  ...parsed,
  API_TOKENS: parsed.API_TOKENS
    ? parsed.API_TOKENS.split(",")
        .map((token) => token.trim())
        .filter((token) => token.length > 0)
    : [],
} as const;

export function assertScrapeCreatorsKey(): string {
  if (!env.SCRAPE_CREATORS_API_KEY) {
    throw new Error("SCRAPE_CREATORS_API_KEY is required");
  }
  return env.SCRAPE_CREATORS_API_KEY;
}

export function assertDatabaseUrl(): string {
  if (!env.DATABASE_URL) {
    throw new Error("DATABASE_URL is required");
  }
  return env.DATABASE_URL;
}

export function assertGoogleApiKey(): string {
  if (!env.GOOGLE_API_KEY) {
    throw new Error("GOOGLE_API_KEY is required");
  }
  return env.GOOGLE_API_KEY;
}
