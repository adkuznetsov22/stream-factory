export type InstagramProfile = {
  username?: string | null;
  full_name?: string | null;
  avatar_url?: string | null;
  followers?: number | null;
  following?: number | null;
  posts_total?: number | null;
  last_synced_at?: string | null;
};

export type InstagramPost = {
  post_id: string;
  caption?: string | null;
  published_at?: string | null;
  media_type?: string | null;
  views?: number | null;
  likes?: number | null;
  comments?: number | null;
  thumbnail_url?: string | null;
  media_url?: string | null;
  permalink?: string | null;
};
