import { ScrapeCreatorsClient } from "./scrapecreators-client.js";
import {
  TikTokProfileResponse,
  TikTokProfileVideosResponse,
} from "./types.js";

export class TikTokClient {
  constructor(private readonly client: ScrapeCreatorsClient) {}

  async getProfile(handle: string): Promise<TikTokProfileResponse> {
    return this.client.get<TikTokProfileResponse>("/v1/tiktok/profile", {
      handle,
    });
  }

  async getProfileVideos(input: {
    handle: string;
    userId?: string | null;
    maxCursor?: string | number | null;
    sortBy?: "latest" | "popular";
    trim?: boolean;
  }): Promise<TikTokProfileVideosResponse> {
    return this.client.get<TikTokProfileVideosResponse>("/v3/tiktok/profile/videos", {
      handle: input.handle,
      user_id: input.userId ?? undefined,
      max_cursor: input.maxCursor ?? undefined,
      sort_by: input.sortBy ?? "latest",
      trim: input.trim ?? true,
    });
  }
}
