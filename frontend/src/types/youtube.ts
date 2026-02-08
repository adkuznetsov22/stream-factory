export type YouTubeProfile = {
  channel_id?: string | null;
  title?: string | null;
  handle?: string | null;
  url?: string | null;
  thumbnail_url?: string | null;
  description?: string | null;
  published_at?: string | null;
  last_synced_at?: string | null;
  subscribers?: number | null;
  views_total?: number | null;
  videos_total?: number | null;
};

export type YouTubeVideo = {
  video_id: string;
  title?: string | null;
  published_at?: string | null;
  thumbnail_url?: string | null;
  views?: number | null;
  likes?: number | null;
  duration_seconds?: number | null;
  comments?: number | null;
  privacy_status?: string | null;
  content_type: "video" | "short" | "live";
  live_status?: string | null;
  scheduled_start_at?: string | null;
  actual_start_at?: string | null;
  actual_end_at?: string | null;
  permalink?: string | null;
};
