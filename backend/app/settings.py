from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )

    app_name: str = "stream-factory"
    environment: str = Field(default="local", validation_alias=AliasChoices("ENVIRONMENT", "STREAM_FACTORY_ENVIRONMENT"))
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@db:5432/stream_factory",
        validation_alias=AliasChoices("DATABASE_URL", "STREAM_FACTORY_DATABASE_URL"),
    )
    youtube_api_key: str | None = Field(default=None, validation_alias=AliasChoices("YOUTUBE_API_KEY", "STREAM_FACTORY_YOUTUBE_API_KEY"))
    vk_access_token: str | None = Field(default=None, validation_alias=AliasChoices("VK_ACCESS_TOKEN", "STREAM_FACTORY_VK_ACCESS_TOKEN"))
    vk_api_version: str = Field(default="5.131", validation_alias=AliasChoices("VK_API_VERSION", "STREAM_FACTORY_VK_API_VERSION"))
    vk_default_posts_limit: int = Field(default=200, validation_alias=AliasChoices("VK_DEFAULT_POSTS_LIMIT", "STREAM_FACTORY_VK_DEFAULT_POSTS_LIMIT"))
    vk_default_videos_limit: int = Field(default=200, validation_alias=AliasChoices("VK_DEFAULT_VIDEOS_LIMIT", "STREAM_FACTORY_VK_DEFAULT_VIDEOS_LIMIT"))
    vk_default_clips_limit: int = Field(default=200, validation_alias=AliasChoices("VK_DEFAULT_CLIPS_LIMIT", "STREAM_FACTORY_VK_DEFAULT_CLIPS_LIMIT"))
    apify_token: str | None = Field(default=None, validation_alias=AliasChoices("APIFY_TOKEN", "STREAM_FACTORY_APIFY_TOKEN"))
    telegram_bot_token: str | None = Field(default=None, validation_alias=AliasChoices("TELEGRAM_BOT_TOKEN", "STREAM_FACTORY_TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str | None = Field(default=None, validation_alias=AliasChoices("TELEGRAM_CHAT_ID", "STREAM_FACTORY_TELEGRAM_CHAT_ID"))
    admin_password: str | None = Field(default=None, validation_alias=AliasChoices("ADMIN_PASSWORD", "STREAM_FACTORY_ADMIN_PASSWORD"))
    scheduler_enabled: bool = Field(default=True, validation_alias=AliasChoices("SCHEDULER_ENABLED", "STREAM_FACTORY_SCHEDULER_ENABLED"))
    auto_process_enabled: bool = Field(default=True, validation_alias=AliasChoices("AUTO_PROCESS_ENABLED", "STREAM_FACTORY_AUTO_PROCESS_ENABLED"))
    auto_process_interval_minutes: int = Field(default=5, validation_alias=AliasChoices("AUTO_PROCESS_INTERVAL_MINUTES", "STREAM_FACTORY_AUTO_PROCESS_INTERVAL_MINUTES"))
    auto_process_max_parallel: int = Field(default=2, validation_alias=AliasChoices("AUTO_PROCESS_MAX_PARALLEL", "STREAM_FACTORY_AUTO_PROCESS_MAX_PARALLEL"))
    auto_process_max_parallel_per_destination: int = Field(default=1, validation_alias=AliasChoices("AUTO_PROCESS_MAX_PARALLEL_PER_DESTINATION", "STREAM_FACTORY_AUTO_PROCESS_MAX_PARALLEL_PER_DESTINATION"))
    redis_url: str = Field(default="redis://redis:6379/0", validation_alias=AliasChoices("REDIS_URL", "STREAM_FACTORY_REDIS_URL"))
    celery_enabled: bool = Field(default=True, validation_alias=AliasChoices("CELERY_ENABLED", "STREAM_FACTORY_CELERY_ENABLED"))
    pipeline_default_step_timeout_sec: int = Field(default=600, validation_alias=AliasChoices("PIPELINE_DEFAULT_STEP_TIMEOUT_SEC", "STREAM_FACTORY_PIPELINE_DEFAULT_STEP_TIMEOUT_SEC"))
    pipeline_ffmpeg_timeout_sec: int = Field(default=1800, validation_alias=AliasChoices("PIPELINE_FFMPEG_TIMEOUT_SEC", "STREAM_FACTORY_PIPELINE_FFMPEG_TIMEOUT_SEC"))
    pipeline_whisper_timeout_sec: int = Field(default=3600, validation_alias=AliasChoices("PIPELINE_WHISPER_TIMEOUT_SEC", "STREAM_FACTORY_PIPELINE_WHISPER_TIMEOUT_SEC"))
    redis_semaphore_ttl_sec: int = Field(default=7200, validation_alias=AliasChoices("REDIS_SEMAPHORE_TTL_SEC", "STREAM_FACTORY_REDIS_SEMAPHORE_TTL_SEC"))
    max_ffmpeg_concurrency: int = Field(default=2, validation_alias=AliasChoices("MAX_FFMPEG_CONCURRENCY", "STREAM_FACTORY_MAX_FFMPEG_CONCURRENCY"))
    max_whisper_concurrency: int = Field(default=1, validation_alias=AliasChoices("MAX_WHISPER_CONCURRENCY", "STREAM_FACTORY_MAX_WHISPER_CONCURRENCY"))
    semaphore_wait_timeout_sec: int = Field(default=1200, validation_alias=AliasChoices("SEMAPHORE_WAIT_TIMEOUT_SEC", "STREAM_FACTORY_SEMAPHORE_WAIT_TIMEOUT_SEC"))
    watchdog_enabled: bool = Field(default=True, validation_alias=AliasChoices("WATCHDOG_ENABLED", "STREAM_FACTORY_WATCHDOG_ENABLED"))
    watchdog_interval_minutes: int = Field(default=5, validation_alias=AliasChoices("WATCHDOG_INTERVAL_MINUTES", "STREAM_FACTORY_WATCHDOG_INTERVAL_MINUTES"))
    stuck_processing_minutes: int = Field(default=90, validation_alias=AliasChoices("STUCK_PROCESSING_MINUTES", "STREAM_FACTORY_STUCK_PROCESSING_MINUTES"))
    stuck_publishing_minutes: int = Field(default=30, validation_alias=AliasChoices("STUCK_PUBLISHING_MINUTES", "STREAM_FACTORY_STUCK_PUBLISHING_MINUTES"))
    watchdog_auto_requeue: bool = Field(default=False, validation_alias=AliasChoices("WATCHDOG_AUTO_REQUEUE", "STREAM_FACTORY_WATCHDOG_AUTO_REQUEUE"))

    @property
    def async_database_url(self) -> str:
        if self.database_url.startswith("postgresql+"):
            return self.database_url
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self.database_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
