from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, HttpUrl, field_validator

from .models import SocialPlatform


class PhoneBase(BaseModel):
    phone_number: str
    label: str | None = None
    notes: str | None = None


class PhoneCreate(PhoneBase):
    pass


class PhoneRead(PhoneBase):
    id: int

    class Config:
        from_attributes = True


class EmailBase(BaseModel):
    email: str
    email_password: str | None = None
    notes: str | None = None


class EmailCreate(EmailBase):
    pass


class EmailRead(EmailBase):
    id: int

    class Config:
        from_attributes = True


class SocialAccountBase(BaseModel):
    platform: SocialPlatform
    label: str
    handle: str  # display, may contain @
    login: str  # normalized, without @
    url: HttpUrl

    @field_validator("handle")
    @classmethod
    def normalize_handle(cls, value: str) -> str:
        return value.strip()

    @field_validator("login")
    @classmethod
    def normalize_login(cls, value: str) -> str:
        return value.strip().replace(" ", "").removeprefix("@").lower()


class SocialAccountCreate(SocialAccountBase):
    handle: str | None = None
    login: str
    url: HttpUrl | None = None
    password: str | None = None
    purchase_price: float | None = None
    purchase_currency: str | None = "RUB"
    auto_sync: bool = True


class SocialAccountRead(SocialAccountBase):
    id: int
    project_id: int | None = None
    views_24h: int | None = None
    views_7d: int | None = None
    posts_total: int | None = None
    last_post_at: str | None = None
    phone: PhoneRead | None = None
    email: EmailRead | None = None
    youtube_channel_id: str | None = None
    subscribers: int | None = None
    views_total: int | None = None
    videos_total: int | None = None
    purchase_price: float | None = None
    purchase_currency: str | None = None
    sync_status: str | None = None
    sync_error: str | None = None
    last_synced_at: str | None = None
    avatar_url: str | None = None

    class Config:
        from_attributes = True


class SocialAccountUpdate(BaseModel):
    phone_id: int | None = None  # deprecated
    email_id: int | None = None
    account_password: str | None = None
    purchase_source_url: str | None = None  # deprecated
    raw_import_blob: str | None = None  # deprecated
    purchase_price: float | None = None
    purchase_currency: str | None = None
    label: str | None = None
    handle: str | None = None
    login: str | None = None
    url: str | None = None
    youtube_channel_id: str | None = None


# Export profiles
class ExportProfileRead(BaseModel):
    id: int
    name: str
    target_platform: str
    max_duration_sec: int
    recommended_duration_sec: int
    width: int
    height: int
    fps: int
    codec: str
    video_bitrate: str
    audio_bitrate: str
    audio_sample_rate: int
    safe_area: dict | None = None
    safe_area_mode: str = "platform_default"
    extra: dict | None = None
    is_builtin: bool

    class Config:
        from_attributes = True


# Projects / Publish tasks
class ProjectCreate(BaseModel):
    name: str
    theme_type: str | None = None
    status: str | None = None
    mode: str | None = None
    settings_json: dict | None = None
    policy: dict | None = None
    export_profile_id: int | None = None
    preset_id: int | None = None


class ProjectRead(BaseModel):
    id: int
    name: str
    theme_type: str | None = None
    status: str
    mode: str
    settings_json: dict | None = None
    policy: dict | None = None
    export_profile_id: int | None = None
    preset_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class ProjectUpdate(BaseModel):
    name: str | None = None
    theme_type: str | None = None
    status: str | None = None
    mode: str | None = None
    settings_json: dict | None = None
    policy: dict | None = None
    export_profile_id: int | None = None
    preset_id: int | None = None


class ProjectSourceCreate(BaseModel):
    platform: str
    social_account_id: int
    source_type: str | None = None


class ProjectSourceRead(BaseModel):
    id: int
    project_id: int
    platform: str
    social_account_id: int
    source_type: str
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class ProjectDestinationCreate(BaseModel):
    platform: str
    social_account_id: int
    priority: int | None = None


class ProjectDestinationRead(BaseModel):
    id: int
    project_id: int
    platform: str
    social_account_id: int
    priority: int
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class PublishTaskRead(BaseModel):
    id: int
    project_id: int
    platform: str
    destination_social_account_id: int
    source_social_account_id: int | None
    external_id: str
    permalink: str | None
    preview_url: str | None
    download_url: str | None
    caption_text: str | None
    instructions: str | None
    status: str
    error_text: str | None
    processing_started_at: datetime | None = None
    processing_finished_at: datetime | None = None
    error_message: str | None = None
    preset_id: int | None = None
    artifacts: dict | None = None
    dag_debug: dict | None = None
    # Publishing result
    published_url: str | None = None
    published_external_id: str | None = None
    published_at: datetime | None = None
    publish_error: str | None = None
    last_metrics_json: dict | None = None
    last_metrics_at: datetime | None = None
    # Moderation fields
    moderation_mode: str = "manual"
    require_final_approval: bool = True
    current_step_index: int = 0
    pipeline_status: str = "pending"
    total_steps: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class PublishTaskUpdate(BaseModel):
    status: str
    error_text: str | None = None


class RunNowRequest(BaseModel):
    limit_per_source: int | None = 5
    limit_total: int | None = 50


class RunNowResponse(BaseModel):
    created_tasks: int
    debug: dict | None = None


# Tools / Presets
class ToolRead(BaseModel):
    tool_id: str
    name: str
    category: str | None = None
    inputs: list[str] | None = None
    outputs: list[str] | None = None
    default_params: dict | None = None
    is_active: bool
    # Enhanced fields
    description: str | None = None
    icon: str | None = None
    param_schema: dict | None = None
    ui_component: str | None = None
    supports_preview: bool = False
    supports_retry: bool = True
    supports_manual_edit: bool = False
    order_index: int = 0

    class Config:
        from_attributes = True


class PresetCreate(BaseModel):
    name: str
    description: str | None = None
    is_active: bool | None = True


class PresetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class PresetRead(BaseModel):
    id: int
    name: str
    description: str | None = None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class PresetStepCreate(BaseModel):
    tool_id: str
    enabled: bool = True
    order_index: int
    params: dict | None = None
    name: str | None = None
    requires_moderation: bool = False


class PresetStepUpdate(BaseModel):
    enabled: bool | None = None
    order_index: int | None = None
    params: dict | None = None
    name: str | None = None
    requires_moderation: bool | None = None


class PresetStepMove(BaseModel):
    direction: str  # "up" or "down"


class PresetStepRead(BaseModel):
    id: int
    preset_id: int
    tool_id: str
    name: str
    enabled: bool
    order_index: int
    params: dict | None = None
    requires_moderation: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class PresetAssetCreate(BaseModel):
    asset_type: str
    asset_id: str
    params: dict | None = None


class PresetAssetRead(BaseModel):
    id: int
    preset_id: int
    asset_type: str
    asset_id: str
    params: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


# Step Results / Moderation
class StepResultRead(BaseModel):
    id: int
    task_id: int
    step_index: int
    tool_id: str
    step_name: str | None = None
    
    # Execution
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    
    # Input/Output
    input_params: dict | None = None
    output_data: dict | None = None
    output_files: list[str] | None = None
    error_message: str | None = None
    logs: str | None = None
    
    # Moderation
    moderation_status: str
    moderation_comment: str | None = None
    moderated_by: str | None = None
    moderated_at: datetime | None = None
    
    # Capabilities
    can_retry: bool = True
    retry_count: int = 0
    version: int = 1
    previous_version_id: int | None = None
    
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class StepResultCreate(BaseModel):
    task_id: int
    step_index: int
    tool_id: str
    step_name: str | None = None
    input_params: dict | None = None


class StepApproveRequest(BaseModel):
    comment: str | None = None


class StepRejectRequest(BaseModel):
    comment: str


class StepRetryRequest(BaseModel):
    new_params: dict | None = None


class StepManualUploadRequest(BaseModel):
    file_path: str
    comment: str | None = None


class ModerationQueueItem(BaseModel):
    task_id: int
    step_index: int
    step_result_id: int
    tool_id: str
    step_name: str | None = None
    project_id: int
    project_name: str | None = None
    moderation_status: str
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class TaskModerationModeUpdate(BaseModel):
    moderation_mode: str  # auto, manual, step_by_step


# ── Candidates / Feed ──────────────────────────────────────────

class CandidateRead(BaseModel):
    id: int
    project_id: int
    platform: str
    platform_video_id: str
    url: str | None = None
    author: str | None = None
    title: str | None = None
    caption: str | None = None
    thumbnail_url: str | None = None
    published_at: datetime | None = None
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    subscribers: int | None = None
    virality_score: float | None = None
    virality_factors: dict | None = None
    origin: str = "REPURPOSE"
    brief_id: int | None = None
    meta: dict | None = None
    status: str
    manual_rating: int | None = None
    notes: str | None = None
    reviewed_at: datetime | None = None
    linked_publish_task_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class CandidateCreate(BaseModel):
    platform: str
    platform_video_id: str
    url: str | None = None
    author: str | None = None
    title: str | None = None
    caption: str | None = None
    thumbnail_url: str | None = None
    published_at: datetime | None = None
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    subscribers: int | None = None
    virality_score: float | None = None
    virality_factors: dict | None = None
    origin: str = "REPURPOSE"
    brief_id: int | None = None
    meta: dict | None = None


class CandidateRateRequest(BaseModel):
    manual_rating: int
    notes: str | None = None


class CandidateApproveRequest(BaseModel):
    destination_id: int | None = None


class CandidateApproveResponse(BaseModel):
    candidate_id: int
    task_id: int
    status: str
    destination_platform: str | None = None
    destination_account_id: int | None = None


# ── Briefs ─────────────────────────────────────────────────────

class BriefRead(BaseModel):
    id: int
    project_id: int
    title: str
    topic: str | None = None
    description: str | None = None
    target_platform: str | None = None
    style: str | None = None
    tone: str | None = None
    language: str = "ru"
    target_duration_sec: int | None = None
    reference_urls: list | dict | None = None
    llm_prompt_template: str | None = None
    prompts: dict | None = None
    assets: dict | None = None
    settings: dict | None = None
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class BriefCreate(BaseModel):
    title: str
    topic: str | None = None
    description: str | None = None
    target_platform: str | None = None
    style: str | None = None
    tone: str | None = None
    language: str = "ru"
    target_duration_sec: int | None = None
    reference_urls: list | dict | None = None
    llm_prompt_template: str | None = None
    prompts: dict | None = None
    assets: dict | None = None
    settings: dict | None = None


class BriefUpdate(BaseModel):
    title: str | None = None
    topic: str | None = None
    description: str | None = None
    target_platform: str | None = None
    style: str | None = None
    tone: str | None = None
    language: str | None = None
    target_duration_sec: int | None = None
    reference_urls: list | dict | None = None
    llm_prompt_template: str | None = None
    prompts: dict | None = None
    assets: dict | None = None
    settings: dict | None = None
    status: str | None = None
