export type TikTokProfileResponse = {
  user?: {
    id?: string;
    uniqueId?: string;
    nickname?: string;
    avatarLarger?: string;
    signature?: string;
    verified?: boolean;
    privateAccount?: boolean;
    secUid?: string;
    [key: string]: unknown;
  };
  stats?: {
    followerCount?: number;
    followingCount?: number;
    heartCount?: number;
    videoCount?: number;
    diggCount?: number;
    friendCount?: number;
    [key: string]: unknown;
  };
  [key: string]: unknown;
};

export type TikTokVideoItem = {
  id?: string;
  id_str?: string;
  aweme_id?: string;
  group_id?: string;
  item_id?: string;
  create_time?: number;
  create_time_utc?: string;
  desc?: string;
  url?: string;
  is_ad?: boolean;
  is_paid_partnership?: boolean;
  video?: {
    duration?: number;
    has_audio?: boolean;
    cover?: {
      url_list?: string[];
      [key: string]: unknown;
    };
    origin_cover?: {
      url_list?: string[];
      [key: string]: unknown;
    };
    dynamic_cover?: {
      url_list?: string[];
      [key: string]: unknown;
    };
    [key: string]: unknown;
  };
  statistics?: {
    play_count?: number;
    digg_count?: number;
    comment_count?: number;
    share_count?: number;
    collect_count?: number;
    download_count?: number;
    repost_count?: number;
    [key: string]: unknown;
  };
  [key: string]: unknown;
};

export type TikTokProfileVideosResponse = {
  aweme_list?: TikTokVideoItem[];
  has_more?: number;
  max_cursor?: string | number;
  min_cursor?: string | number;
  status_code?: number;
  status_msg?: string;
  [key: string]: unknown;
};

export type InstagramProfileResponse = {
  success?: boolean;
  status?: string;
  data?: {
    user?: {
      id?: string;
      username?: string;
      full_name?: string;
      biography?: string;
      profile_pic_url?: string;
      is_verified?: boolean;
      is_private?: boolean;
      edge_followed_by?: { count?: number };
      edge_follow?: { count?: number };
      edge_owner_to_timeline_media?: {
        count?: number;
        edges?: Array<{
          node?: {
            id?: string;
            shortcode?: string;
            is_video?: boolean;
            video_view_count?: number;
            edge_liked_by?: { count?: number };
            edge_media_to_comment?: { count?: number };
            edge_media_to_caption?: {
              edges?: Array<{
                node?: { text?: string };
              }>;
            };
            display_url?: string;
            thumbnail_src?: string;
            has_audio?: boolean;
            taken_at_timestamp?: number;
            product_type?: string;
            [key: string]: unknown;
          };
        }>;
      };
      [key: string]: unknown;
    };
  };
  [key: string]: unknown;
};

export type InstagramReelItem = {
  id?: string;
  pk?: string;
  code?: string;
  url?: string;
  caption?:
    | {
        text?: string;
      }
    | string
    | null;
  play_count?: number;
  ig_play_count?: number;
  like_count?: number;
  comment_count?: number;
  taken_at?: number;
  is_paid_partnership?: boolean;
  has_audio?: boolean;
  video_duration?: number;
  display_uri?: string;
  media?: {
    pk?: string;
    id?: string;
    code?: string;
    url?: string;
    caption?: {
      text?: string;
    } | string | null;
    play_count?: number;
    ig_play_count?: number;
    like_count?: number;
    comment_count?: number;
    taken_at?: number;
    is_paid_partnership?: boolean;
    has_audio?: boolean;
    video_duration?: number;
    display_uri?: string;
    [key: string]: unknown;
  };
};

export type InstagramPostResponse = {
  data?: {
    xdt_shortcode_media?: {
      id?: string;
      shortcode?: string;
      thumbnail_src?: string;
      video_url?: string;
      video_view_count?: number;
      video_play_count?: number;
      video_duration?: number;
      has_audio?: boolean;
      is_video?: boolean;
      is_published?: boolean;
      is_paid_partnership?: boolean;
      is_ad?: boolean;
      taken_at_timestamp?: number;
      comments_disabled?: boolean;
      product_type?: string;
      title?: string;
      clips_music_attribution_info?: {
        artist_name?: string;
        song_name?: string;
        uses_original_audio?: boolean;
        audio_id?: string;
      };
      owner?: {
        id?: string;
        username?: string;
        full_name?: string;
        is_verified?: boolean;
        profile_pic_url?: string;
        edge_followed_by?: { count?: number };
        edge_owner_to_timeline_media?: { count?: number };
      };
      edge_media_to_caption?: {
        edges?: Array<{
          node?: { text?: string; created_at?: string };
        }>;
      };
      edge_media_preview_like?: { count?: number };
      edge_media_to_parent_comment?: { count?: number };
      [key: string]: unknown;
    };
  };
  status?: string;
  [key: string]: unknown;
};

export type InstagramUserReelsResponse = {
  items?: InstagramReelItem[];
  max_id?: string;
  paging_info?: {
    max_id?: string;
    more_available?: boolean;
  };
  status?: string;
  [key: string]: unknown;
};

export type FacebookReelItem = {
  id?: string;
  post_id?: string;
  creation_time?: string;
  url?: string;
  view_count?: number;
  description?: string;
  video_id?: string;
  thumbnail?: string;
  play_time_in_ms?: number;
  video_url?: string;
  music?: {
    id?: string;
    track_title?: string;
  };
  author?: {
    id?: string;
    name?: string;
    is_verified?: boolean;
    url?: string;
    image?: string;
  };
  [key: string]: unknown;
};

export type FacebookProfileReelsResponse = {
  success?: boolean;
  credits_remaining?: number;
  reels?: FacebookReelItem[];
  cursor?: string;
  next_page_id?: string;
  [key: string]: unknown;
};
