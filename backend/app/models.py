from __future__ import annotations

from datetime import datetime
from enum import Enum

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship as sa_relationship

from .db import Base


def relationship(*args, **kwargs):
    """Wrap SQLAlchemy relationship to forbid lazy loading by default."""
    kwargs.setdefault("lazy", "raise")
    return sa_relationship(*args, **kwargs)


class SocialPlatform(str, Enum):
    youtube = "YouTube"
    tiktok = "TikTok"
    vk = "VK"
    instagram = "Instagram"


class SocialAccount(Base):
    __tablename__ = "social_accounts"
    __table_args__ = (sa.UniqueConstraint("platform", "login", name="uq_social_accounts_platform_login"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[SocialPlatform] = mapped_column(sa.String(32), nullable=False)
    label: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    handle: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    login: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    url: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    youtube_channel_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True, index=True)
    phone_id: Mapped[int | None] = mapped_column(sa.ForeignKey("phones.id", ondelete="SET NULL"), nullable=True)
    email_id: Mapped[int | None] = mapped_column(sa.ForeignKey("emails.id", ondelete="SET NULL"), nullable=True)
    account_password: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    purchase_price: Mapped[float | None] = mapped_column(sa.Numeric(12, 2), nullable=True)
    purchase_currency: Mapped[str | None] = mapped_column(sa.String(8), nullable=True, server_default="RUB")
    purchase_source_url: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    raw_import_blob: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    sync_status: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    sync_error: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    project_id: Mapped[int | None] = mapped_column(sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )

    onboarding: Mapped["AccountOnboarding"] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
        uselist=False,
    )
    metrics: Mapped[list["AccountMetricsDaily"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    phone: Mapped["Phone | None"] = relationship(back_populates="accounts")
    email: Mapped["Email | None"] = relationship(back_populates="accounts")
    youtube_channel: Mapped["YouTubeChannel | None"] = relationship(
        back_populates="account", cascade="all, delete-orphan", uselist=False
    )
    youtube_videos: Mapped[list["YouTubeVideo"]] = relationship(
        back_populates="account", cascade="all, delete-orphan", passive_deletes=True
    )
    vk_profile: Mapped["VKProfile | None"] = relationship(
        back_populates="account", cascade="all, delete-orphan", uselist=False
    )
    vk_posts: Mapped[list["VKPost"]] = relationship(
        back_populates="account", cascade="all, delete-orphan", passive_deletes=True
    )
    vk_videos: Mapped[list["VKVideo"]] = relationship(
        back_populates="account", cascade="all, delete-orphan", passive_deletes=True
    )
    vk_clips: Mapped[list["VKClip"]] = relationship(
        back_populates="account", cascade="all, delete-orphan", passive_deletes=True
    )
    tiktok_profile: Mapped["TikTokProfile | None"] = relationship(
        back_populates="account", cascade="all, delete-orphan", uselist=False
    )
    tiktok_videos: Mapped[list["TikTokVideo"]] = relationship(
        back_populates="account", cascade="all, delete-orphan", passive_deletes=True
    )
    instagram_profile: Mapped["InstagramProfile | None"] = relationship(
        back_populates="account", cascade="all, delete-orphan", uselist=False
    )
    instagram_posts: Mapped[list["InstagramPost"]] = relationship(
        back_populates="account", cascade="all, delete-orphan", passive_deletes=True
    )
    project: Mapped["Project | None"] = relationship(back_populates="accounts")
    project_sources: Mapped[list["ProjectSource"]] = relationship(
        back_populates="social_account", cascade="all, delete-orphan", passive_deletes=True
    )
    project_destinations: Mapped[list["ProjectDestination"]] = relationship(
        back_populates="social_account", cascade="all, delete-orphan", passive_deletes=True
    )
    publish_tasks_source: Mapped[list["PublishTask"]] = relationship(
        back_populates="source_account", foreign_keys="PublishTask.source_social_account_id", passive_deletes=True
    )
    publish_tasks_destination: Mapped[list["PublishTask"]] = relationship(
        back_populates="destination_account",
        foreign_keys="PublishTask.destination_social_account_id",
        passive_deletes=True,
    )


class AccountOnboarding(Base):
    __tablename__ = "account_onboarding"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(64), nullable=False, server_default="completed")
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )

    account: Mapped[SocialAccount] = relationship(back_populates="onboarding")


class AccountMetricsDaily(Base):
    __tablename__ = "account_metrics_daily"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[datetime] = mapped_column(sa.Date(), nullable=False, index=True)
    views: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    likes: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    subs: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    posts: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )

    account: Mapped[SocialAccount] = relationship(back_populates="metrics")


class Phone(Base):
    __tablename__ = "phones"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    phone_number: Mapped[str] = mapped_column(sa.String(64), unique=True, nullable=False)
    label: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )

    accounts: Mapped[list[SocialAccount]] = relationship(back_populates="phone")


class Email(Base):
    __tablename__ = "emails"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(sa.String(255), unique=True, nullable=False)
    email_password: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )

    accounts: Mapped[list[SocialAccount]] = relationship(back_populates="email")


class YouTubeChannel(Base):
    __tablename__ = "youtube_channels"

    account_id: Mapped[int] = mapped_column(sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), primary_key=True)
    channel_id: Mapped[str] = mapped_column(sa.String(255), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    description: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    banner_url: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    handle: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    subscribers: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    views_total: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    videos_total: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), index=True, nullable=True)
    raw_json: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)

    account: Mapped[SocialAccount] = relationship(back_populates="youtube_channel")


class YouTubeVideo(Base):
    __tablename__ = "youtube_videos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), index=True)
    video_id: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    title: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), index=True, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    views: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    likes: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    comments: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    privacy_status: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    content_type: Mapped[str] = mapped_column(sa.String(16), nullable=False, server_default="video")
    live_status: Mapped[str | None] = mapped_column(sa.String(16), nullable=True)
    scheduled_start_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    actual_start_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    actual_end_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    permalink: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    raw: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), index=True, nullable=True)
    virality_score: Mapped[float | None] = mapped_column(sa.Float(), nullable=True, index=True)
    used_in_task_id: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    account: Mapped[SocialAccount] = relationship(back_populates="youtube_videos")


class VKProfile(Base):
    __tablename__ = "vk_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), unique=True)
    vk_owner_id: Mapped[int] = mapped_column(sa.Integer(), nullable=False, index=True)
    screen_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    photo_200: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    is_group: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, server_default=sa.false())
    country: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    members_count: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    followers_count: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    account: Mapped[SocialAccount] = relationship(back_populates="vk_profile")


class VKPost(Base):
    __tablename__ = "vk_posts"
    __table_args__ = (sa.UniqueConstraint("account_id", "post_id", name="uq_vk_posts_account_post"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    vk_owner_id: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    post_id: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True, index=True)
    text: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    permalink: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    views: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    likes: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    reposts: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    comments: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    attachments_count: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    raw: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    account: Mapped[SocialAccount] = relationship(back_populates="vk_posts")


class VKVideo(Base):
    __tablename__ = "vk_videos"
    __table_args__ = (sa.UniqueConstraint("account_id", "vk_owner_id", "video_id", name="uq_vk_videos_account_owner_video"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    vk_owner_id: Mapped[int] = mapped_column(sa.Integer(), nullable=False, index=True)
    video_id: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    vk_full_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    description: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True, index=True)
    duration_seconds: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    views: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    likes: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    comments: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    reposts: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    permalink: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    raw: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    virality_score: Mapped[float | None] = mapped_column(sa.Float(), nullable=True, index=True)
    used_in_task_id: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )

    account: Mapped[SocialAccount] = relationship(back_populates="vk_videos")


class VKClip(Base):
    __tablename__ = "vk_clips"
    __table_args__ = (sa.UniqueConstraint("account_id", "vk_owner_id", "clip_id", name="uq_vk_clips_account_owner_clip"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    vk_owner_id: Mapped[int] = mapped_column(sa.Integer(), nullable=False, index=True)
    clip_id: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    vk_full_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    media_type: Mapped[str] = mapped_column(sa.String(32), nullable=False, server_default="clip")
    title: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    description: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True, index=True)
    duration_seconds: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    views: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    likes: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    comments: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    reposts: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    permalink: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    raw: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    virality_score: Mapped[float | None] = mapped_column(sa.Float(), nullable=True, index=True)
    used_in_task_id: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )

    account: Mapped[SocialAccount] = relationship(back_populates="vk_clips")


class TikTokProfile(Base):
    __tablename__ = "tiktok_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), unique=True)
    username: Mapped[str] = mapped_column(sa.String(255), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    followers: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    following: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    likes_total: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    posts_total: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    raw: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    account: Mapped[SocialAccount] = relationship(back_populates="tiktok_profile")


class TikTokVideo(Base):
    __tablename__ = "tiktok_videos"
    __table_args__ = (sa.UniqueConstraint("account_id", "video_id", name="uq_tiktok_videos_account_video"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), nullable=False)
    video_id: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True, index=True)
    duration_seconds: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    views: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    likes: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    comments: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    shares: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    video_url: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    permalink: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    raw: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    virality_score: Mapped[float | None] = mapped_column(sa.Float(), nullable=True, index=True)
    used_in_task_id: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )

    account: Mapped[SocialAccount] = relationship(back_populates="tiktok_videos")


class InstagramProfile(Base):
    __tablename__ = "instagram_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), unique=True)
    username: Mapped[str] = mapped_column(sa.String(255), nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    followers: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    following: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    posts_total: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    raw: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    account: Mapped[SocialAccount] = relationship(back_populates="instagram_profile")


class InstagramPost(Base):
    __tablename__ = "instagram_posts"
    __table_args__ = (sa.UniqueConstraint("account_id", "post_id", name="uq_instagram_posts_account_post"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), nullable=False)
    post_id: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    caption: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True, index=True)
    media_type: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    views: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    likes: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    comments: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    media_url: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    permalink: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    raw: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    virality_score: Mapped[float | None] = mapped_column(sa.Float(), nullable=True, index=True)
    used_in_task_id: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )

    account: Mapped[SocialAccount] = relationship(back_populates="instagram_posts")


class ExportProfile(Base):
    """Platform-specific export parameters for final video packaging."""
    __tablename__ = "export_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    target_platform: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    max_duration_sec: Mapped[int] = mapped_column(sa.Integer(), nullable=False, server_default="180")
    recommended_duration_sec: Mapped[int] = mapped_column(sa.Integer(), nullable=False, server_default="60")
    width: Mapped[int] = mapped_column(sa.Integer(), nullable=False, server_default="1080")
    height: Mapped[int] = mapped_column(sa.Integer(), nullable=False, server_default="1920")
    fps: Mapped[int] = mapped_column(sa.Integer(), nullable=False, server_default="30")
    codec: Mapped[str] = mapped_column(sa.String(16), nullable=False, server_default="h264")
    video_bitrate: Mapped[str] = mapped_column(sa.String(16), nullable=False, server_default="8M")
    audio_bitrate: Mapped[str] = mapped_column(sa.String(16), nullable=False, server_default="192k")
    audio_sample_rate: Mapped[int] = mapped_column(sa.Integer(), nullable=False, server_default="44100")
    safe_area: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    safe_area_mode: Mapped[str] = mapped_column(sa.String(32), nullable=False, server_default="platform_default")
    extra: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    is_builtin: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, server_default=sa.false())
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    theme_type: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    status: Mapped[str] = mapped_column(sa.Text(), nullable=False, server_default="draft")
    mode: Mapped[str] = mapped_column(sa.Text(), nullable=False, server_default="MANUAL")
    settings_json: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    policy: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    meta: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    feed_settings: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    export_profile_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("export_profiles.id", ondelete="SET NULL"), nullable=True
    )
    preset_id: Mapped[int | None] = mapped_column(sa.ForeignKey("presets.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )

    sources: Mapped[list["ProjectSource"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    destinations: Mapped[list["ProjectDestination"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    publish_tasks: Mapped[list["PublishTask"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    decision_logs: Mapped[list["DecisionLog"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    accounts: Mapped[list["SocialAccount"]] = relationship(
        back_populates="project", cascade="save-update", passive_deletes=True
    )
    preset: Mapped["Preset | None"] = relationship(back_populates="projects")
    export_profile: Mapped["ExportProfile | None"] = relationship()
    candidates: Mapped[list["Candidate"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    briefs: Mapped[list["Brief"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )


class ProjectSource(Base):
    __tablename__ = "project_sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    social_account_id: Mapped[int] = mapped_column(sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), nullable=False)
    source_type: Mapped[str] = mapped_column(sa.Text(), nullable=False, server_default="manual")
    is_active: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, server_default=sa.true())
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="sources")
    social_account: Mapped[SocialAccount] = relationship(back_populates="project_sources")


class ProjectDestination(Base):
    __tablename__ = "project_destinations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    social_account_id: Mapped[int] = mapped_column(sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), nullable=False)
    priority: Mapped[int] = mapped_column(sa.Integer(), nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, server_default=sa.true())
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="destinations")
    social_account: Mapped[SocialAccount] = relationship(back_populates="project_destinations")


class PublishTask(Base):
    __tablename__ = "publish_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    destination_social_account_id: Mapped[int] = mapped_column(
        sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), nullable=False
    )
    source_social_account_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("social_accounts.id", ondelete="SET NULL"), nullable=True
    )
    external_id: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    permalink: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    preview_url: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    download_url: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    caption_text: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    instructions: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    status: Mapped[str] = mapped_column(sa.Text(), nullable=False, server_default="queued")
    error_text: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    processing_finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    preset_id: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    artifacts: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    dag_debug: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    # Publishing result
    published_url: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    published_external_id: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    publish_error: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    last_metrics_json: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    last_metrics_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    # Moderation fields
    moderation_mode: Mapped[str] = mapped_column(sa.String(32), nullable=False, server_default="manual")
    require_final_approval: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, server_default=sa.true())
    current_step_index: Mapped[int] = mapped_column(sa.Integer(), nullable=False, server_default="0")
    pipeline_status: Mapped[str] = mapped_column(sa.String(32), nullable=False, server_default="pending")
    total_steps: Mapped[int] = mapped_column(sa.Integer(), nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="publish_tasks")
    destination_account: Mapped[SocialAccount] = relationship(
        foreign_keys=[destination_social_account_id], back_populates="publish_tasks_destination"
    )
    source_account: Mapped[SocialAccount | None] = relationship(
        foreign_keys=[source_social_account_id], back_populates="publish_tasks_source"
    )
    step_results: Mapped[list["StepResult"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", passive_deletes=True
    )
    candidate: Mapped["Candidate | None"] = relationship(
        back_populates="publish_task", uselist=False
    )


class DecisionLog(Base):
    __tablename__ = "decision_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    payload_json: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)

    project: Mapped[Project] = relationship(back_populates="decision_logs")


class ToolRegistry(Base):
    __tablename__ = "tool_registry"

    tool_id: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    inputs: Mapped[list | None] = mapped_column(sa.JSON(), nullable=True)
    outputs: Mapped[list | None] = mapped_column(sa.JSON(), nullable=True)
    default_params: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    is_active: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, server_default=sa.true())
    # New fields for enhanced UI
    description: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    icon: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    param_schema: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    ui_component: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    supports_preview: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, server_default=sa.false())
    supports_retry: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, server_default=sa.true())
    supports_manual_edit: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, server_default=sa.false())
    order_index: Mapped[int] = mapped_column(sa.Integer(), nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )


class Preset(Base):
    __tablename__ = "presets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    is_active: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, server_default=sa.true())
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )

    steps: Mapped[list["PresetStep"]] = relationship(
        back_populates="preset", cascade="all, delete-orphan", passive_deletes=True
    )
    assets: Mapped[list["PresetAsset"]] = relationship(
        back_populates="preset", cascade="all, delete-orphan", passive_deletes=True
    )
    projects: Mapped[list[Project]] = relationship(back_populates="preset")


class PresetStep(Base):
    __tablename__ = "preset_steps"
    __table_args__ = (sa.UniqueConstraint("preset_id", "order_index", name="uq_preset_steps_order"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    preset_id: Mapped[int] = mapped_column(sa.ForeignKey("presets.id", ondelete="CASCADE"), nullable=False)
    tool_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, server_default=sa.true())
    order_index: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    params: Mapped[dict] = mapped_column(sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb"))
    requires_moderation: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, server_default=sa.false())
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )

    preset: Mapped[Preset] = relationship(back_populates="steps")


class PresetAsset(Base):
    __tablename__ = "preset_assets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    preset_id: Mapped[int] = mapped_column(sa.ForeignKey("presets.id", ondelete="CASCADE"), nullable=False)
    asset_type: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    asset_id: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    params: Mapped[dict] = mapped_column(sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )

    preset: Mapped[Preset] = relationship(back_populates="assets")


class StepResult(Base):
    """Result of a single pipeline step execution with moderation support."""
    __tablename__ = "step_results"
    __table_args__ = (
        sa.UniqueConstraint("task_id", "step_index", "version", name="uq_step_results_task_step_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(sa.ForeignKey("publish_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    step_index: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    tool_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    step_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)

    # Execution status
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False, server_default="pending")
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)

    # Input/Output
    input_params: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    output_data: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    output_files: Mapped[list | None] = mapped_column(sa.JSON(), nullable=True)
    error_message: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    logs: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)

    # Moderation
    moderation_status: Mapped[str] = mapped_column(sa.String(32), nullable=False, server_default="pending")
    moderation_comment: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    moderated_by: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    moderated_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    # Capabilities & versioning
    can_retry: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, server_default=sa.true())
    retry_count: Mapped[int] = mapped_column(sa.Integer(), nullable=False, server_default="0")
    version: Mapped[int] = mapped_column(sa.Integer(), nullable=False, server_default="1")
    previous_version_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("step_results.id", ondelete="SET NULL"), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )

    # Relationships
    task: Mapped["PublishTask"] = relationship(back_populates="step_results")
    previous_version: Mapped["StepResult | None"] = relationship(
        remote_side=[id], foreign_keys=[previous_version_id]
    )


class CandidateOrigin(str, Enum):
    repurpose = "REPURPOSE"
    generate = "GENERATE"


class CandidateStatus(str, Enum):
    new = "NEW"
    approved = "APPROVED"
    rejected = "REJECTED"
    used = "USED"


class Brief(Base):
    """Content generation brief for GENERATE mode."""
    __tablename__ = "briefs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    topic: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    description: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    target_platform: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    style: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    tone: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    language: Mapped[str] = mapped_column(sa.String(8), nullable=False, server_default="ru")
    target_duration_sec: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    reference_urls: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    llm_prompt_template: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    prompts: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    assets: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    settings: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False, server_default="draft")
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="briefs")
    candidates: Mapped[list["Candidate"]] = relationship(back_populates="brief")


class Candidate(Base):
    """Video candidate from competitor feed or generation."""
    __tablename__ = "candidates"
    __table_args__ = (
        sa.UniqueConstraint("project_id", "platform", "platform_video_id", name="uq_candidate_video"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    # Source identification
    platform: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    platform_video_id: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    url: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    author: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    caption: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    # Metrics
    views: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    likes: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    comments: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    shares: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    subscribers: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)

    # Scoring
    virality_score: Mapped[float | None] = mapped_column(sa.Float(), nullable=True, index=True)
    virality_factors: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)

    # Origin: REPURPOSE (from competitor feed) or GENERATE (from brief/LLM)
    origin: Mapped[str] = mapped_column(sa.String(16), nullable=False, server_default="REPURPOSE", index=True)
    brief_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("briefs.id", ondelete="SET NULL"), nullable=True
    )
    meta: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)

    # Status & review
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False, server_default="NEW", index=True)
    manual_rating: Mapped[int | None] = mapped_column(sa.SmallInteger(), nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    # Link to publish task
    linked_publish_task_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("publish_tasks.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )

    # Relationships
    project: Mapped[Project] = relationship(back_populates="candidates")
    publish_task: Mapped["PublishTask | None"] = relationship(
        back_populates="candidate", foreign_keys=[linked_publish_task_id]
    )
    brief: Mapped["Brief | None"] = relationship(back_populates="candidates")


class PublishedVideoMetrics(Base):
    """Periodic snapshots of metrics for published videos.

    Each row is a point-in-time snapshot (views, likes, comments, shares)
    for a published task. Collected by sync_published_metrics scheduler job.
    Enables analytics: candidate_score → actual performance.
    """
    __tablename__ = "published_video_metrics"
    __table_args__ = (
        sa.UniqueConstraint("platform", "external_id", "snapshot_at", name="uq_pvm_platform_extid_snap"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        sa.ForeignKey("publish_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True, index=True
    )
    platform: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    external_id: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)

    views: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    likes: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    comments: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    shares: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)

    snapshot_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True
    )
    hours_since_publish: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
