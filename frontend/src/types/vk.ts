export type VKProfile = {
  account_id?: number;
  vk_owner_id?: number;
  screen_name?: string | null;
  name?: string | null;
  photo_200?: string | null;
  is_group?: boolean;
  country?: string | null;
  description?: string | null;
  members_count?: number | null;
  followers_count?: number | null;
  last_synced_at?: string | null;
};

export type VKPost = {
  post_id: number;
  vk_owner_id: number;
  published_at?: string | null;
  text?: string | null;
  permalink?: string | null;
  views?: number | null;
  likes?: number | null;
  reposts?: number | null;
  comments?: number | null;
  attachments_count?: number | null;
};

export type VKVideo = {
  video_id: number;
  vk_owner_id: number;
  title?: string | null;
  description?: string | null;
  published_at?: string | null;
  duration_seconds?: number | null;
  views?: number | null;
  likes?: number | null;
  comments?: number | null;
  reposts?: number | null;
  thumbnail_url?: string | null;
  permalink?: string | null;
};

export type VKClip = {
  clip_id: number;
  vk_owner_id: number;
  title?: string | null;
  description?: string | null;
  published_at?: string | null;
  duration_seconds?: number | null;
  views?: number | null;
  likes?: number | null;
  comments?: number | null;
  reposts?: number | null;
  thumbnail_url?: string | null;
  permalink?: string | null;
};

export type VKContentItem = {
  content_type: "post" | "video" | "clip" | "short_video";
  id: number;
  owner_id: number;
  title?: string | null;
  text?: string | null;
  published_at?: string | null;
  views?: number | null;
  likes?: number | null;
  comments?: number | null;
  reposts?: number | null;
  thumbnail_url?: string | null;
  permalink?: string | null;
};
