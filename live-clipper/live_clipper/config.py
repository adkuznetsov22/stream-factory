from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LC_", env_file=".env", extra="ignore")

    data_dir: Path = Path("./data")

    # Admin panel
    admin_host: str = "0.0.0.0"
    admin_port: int = 8080
    admin_password: str | None = None

    # Discovery
    game_name: str = "Grand Theft Auto VI"
    language: str = "RU"
    whitelist: list[str] = ["buster", "evelone2004", "strogo", "recrent", "t2x2", "skywhywalker"]
    blacklist: list[str] = []
    whitelist_any_game: bool = False
    auto_discover: bool = True
    min_viewers: int = 5000
    max_streams: int = 8
    discovery_interval: int = 60
    drop_after_misses: int = 3

    # Ingest
    quality: str = "720p60,720p,best"
    buffer_seconds: int = 900
    segment_seconds: int = 2

    # Detection
    trigger_score: float = 4.0
    cooldown: float = 120.0
    baseline_seconds: int = 300
    warmup_seconds: int = 60
    reaction_delay: float = 3.0
    clip_before: float = 18.0
    clip_after: float = 12.0

    # Render
    layout: str = "blur"  # blur | facecam
    facecam: dict[str, list[float]] = {}  # login -> [x, y, w, h] as fractions of the source frame
    gameplay_height: int = 810
    video_encoder: str = "libx264"  # libx264 | h264_nvenc
    output_fps: int = 30
    render_concurrency: int = 2
    font_file: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    subtitles: bool = True
    mask_subtitles: bool = True
    source_padding: float = 15.0
    whisper_model: str = "small"
    whisper_device: str = "auto"
    whisper_compute_type: str = "int8"

    # Titles
    openrouter_api_key: str | None = None
    openrouter_model: str = "google/gemini-2.5-flash"
    hashtags: list[str] = ["#gta6", "#gta", "#shorts"]

    # Publishing; empty list = dry-run (files and meta.json only)
    publish_targets: list[str] = []
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    vk_access_token: str | None = None
    vk_group_id: int | None = None
    youtube_client_id: str | None = None
    youtube_client_secret: str | None = None
    youtube_refresh_token: str | None = None
    youtube_privacy: str = "public"
    publish_paused: bool = False
    max_publish_age_min: int = 30

    # Retention: rendered clips are deleted after N hours (published ones are kept longer)
    retention_hours: float = 12
    retention_published_hours: float = 72
    retention_source_hours: float = 6

    # Owner alerts via the Telegram bot of the first Telegram target
    alerts_chat_id: str | None = None
    timezone: str = "Europe/Moscow"
    dedup_window: float = 25.0
    feature_days: float = 14
    judge_model: str = "anthropic/claude-sonnet-4.6"
    openai_api_key: str = ""
    openai_judge_model: str = "gpt-4.1-mini"
    model_trigger: bool = True
    train_hours: float = 6

    @property
    def buffer_dir(self) -> Path:
        return self.data_dir / "buffer"

    @property
    def clips_dir(self) -> Path:
        return self.data_dir / "clips"


# Settings editable from the admin panel; stored in the DB and applied without restart.
EDITABLE = [
    "game_name", "language", "whitelist_any_game", "auto_discover", "min_viewers",
    "max_streams", "trigger_score", "cooldown", "warmup_seconds", "reaction_delay", "clip_before", "clip_after",
    "layout", "subtitles", "mask_subtitles", "hashtags", "openrouter_api_key", "openrouter_model", "judge_model", "openai_api_key", "openai_judge_model", "model_trigger", "train_hours", "publish_paused",
    "max_publish_age_min", "retention_hours", "retention_published_hours", "retention_source_hours", "alerts_chat_id",
    "dedup_window", "source_padding", "buffer_seconds",
]
SECRET_FIELDS = {"openai_api_key", "openrouter_api_key", "bot_token", "access_token", "client_secret", "refresh_token"}

settings = Settings()
