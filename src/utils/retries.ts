export type RetryDecision = {
  shouldRetry: boolean;
  waitMs: number;
};

export function getRetryDecision(
  status: number | undefined,
  attempt: number,
  retry429: number,
  retry5xx: number,
): RetryDecision {
  if (status === 429) {
    const shouldRetry = attempt < retry429;
    return { shouldRetry, waitMs: [5000, 10000, 20000][attempt] ?? 20000 };
  }

  if (status && status >= 500 && status < 600) {
    const shouldRetry = attempt < retry5xx;
    return { shouldRetry, waitMs: [3000, 3000, 3000][attempt] ?? 3000 };
  }

  return { shouldRetry: false, waitMs: 0 };
}

export async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}
