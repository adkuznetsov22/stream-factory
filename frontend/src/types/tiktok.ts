export type TikTokProfile = {
  username?: string | null;
  display_name?: string | null;
  avatar_url?: string | null;
  followers?: number | null;
  following?: number | null;
  likes_total?: number | null;
  posts_total?: number | null;
  last_synced_at?: string | null;
};

export type TikTokVideo = {
  video_id: string;
  title?: string | null;
  published_at?: string | null;
  duration_seconds?: number | null;
  views?: number | null;
  likes?: number | null;
  comments?: number | null;
  shares?: number | null;
  thumbnail_url?: string | null;
  video_url?: string | null;
  permalink?: string | null;
};
