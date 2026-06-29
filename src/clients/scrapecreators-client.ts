import axios, { AxiosError, AxiosInstance } from "axios";
import PQueue from "p-queue";
import {
  RATE_LIMIT,
  REQUEST_TIMEOUT_MS,
  RETRIES,
  SCRAPE_CREATORS_BASE_URL,
} from "../config/constants.js";
import { assertScrapeCreatorsKey } from "../config/env.js";
import { logger } from "../utils/logger.js";
import { getRetryDecision, sleep } from "../utils/retries.js";

export class ScrapeCreatorsClient {
  private readonly http: AxiosInstance;
  private readonly queue: PQueue;
  private apiCalls = 0;

  constructor() {
    this.http = axios.create({
      baseURL: SCRAPE_CREATORS_BASE_URL,
      timeout: REQUEST_TIMEOUT_MS,
      headers: {
        "x-api-key": assertScrapeCreatorsKey(),
      },
    });

    this.queue = new PQueue({
      concurrency: RATE_LIMIT.concurrency,
      intervalCap: RATE_LIMIT.intervalCap,
      interval: RATE_LIMIT.interval,
      carryoverConcurrencyCount: true,
    });
  }

  getApiCallCount(): number {
    return this.apiCalls;
  }

  resetApiCallCount(): void {
    this.apiCalls = 0;
  }

  async get<T>(path: string, params?: Record<string, unknown>): Promise<T> {
    return this.queue.add(async () => this.requestWithRetry<T>(path, params));
  }

  private async requestWithRetry<T>(
    path: string,
    params?: Record<string, unknown>,
  ): Promise<T> {
    const maxAttempts = Math.max(RETRIES.tooManyRequests, RETRIES.serverErrors);

    for (let attempt = 0; attempt <= maxAttempts; attempt += 1) {
      try {
        this.apiCalls += 1;
        const response = await this.http.get<T>(path, {
          params,
        });
        return response.data;
      } catch (error) {
        const axiosError = error as AxiosError;
        const status = axiosError.response?.status;
        const { shouldRetry, waitMs } = getRetryDecision(
          status,
          attempt,
          RETRIES.tooManyRequests,
          RETRIES.serverErrors,
        );

        if (!shouldRetry) {
          throw error;
        }

        logger.warn(
          {
            path,
            attempt,
            status,
            waitMs,
          },
          "ScrapeCreators request failed, retrying",
        );
        await sleep(waitMs);
      }
    }

    throw new Error("Unexpected retry loop exit");
  }
}
