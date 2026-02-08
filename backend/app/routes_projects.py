from __future__ import annotations

import asyncio
import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import (
    ExportProfile,
    Project,
    Preset,
    PresetStep,
    InstagramPost,
    ProjectDestination,
    ProjectSource,
    PublishTask,
    SocialAccount,
    TikTokVideo,
    VKClip,
    VKVideo,
    YouTubeVideo,
)
from app.schemas import (
    ExportProfileRead,
    ProjectCreate,
    ProjectDestinationCreate,
    ProjectDestinationRead,
    ProjectRead,
    ProjectSourceCreate,
    ProjectSourceRead,
    ProjectUpdate,
    PublishTaskRead,
    PublishTaskUpdate,
    RunNowRequest,
    RunNowResponse,
)

router = APIRouter(prefix="/api", tags=["projects"])

SessionDep = Depends(get_session)
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
TASKS_DIR = DATA_DIR / "tasks"
TASKS_DIR.mkdir(parents=True, exist_ok=True)
TASK_FILE_WHITELIST = {
    "raw.mp4",
    "ready.mp4",
    "final.mp4",
    "thumb.jpg",
    "preview.mp4",
    "probe.json",
    "process.log",
    "captions.srt",
}

TASK_STATUS_LABELS = {
    "queued": "В очереди",
    "processing": "В обработке",
    "ready_for_review": "На проверке",
    "done": "Готово",
    "completed": "Готово",
    "error": "Ошибка",
}

STEP_STATUS_LABELS = {
    "ok": "Выполнено",
    "error": "Ошибка",
    "skipped": "Пропущено",
    "processing": "В обработке",
}

TOOL_TITLES = {
    "T04_CROP_RESIZE": {"title": "Обрезка/Resize", "description": "Приведение видео к вертикальному формату 9:16 (1080×1920)."},
    "T14_BURN_CAPTIONS": {"title": "Вшивка субтитров", "description": "Добавление субтитров в видео."},
    "T02_PROBE_MEDIA": {"title": "Проверка медиа", "description": "Анализ файла (ffprobe)."},
    "T07_EXTRACT_AUDIO": {"title": "Извлечение аудио", "description": "Получение аудио-дорожки из видео."},
}

OUTPUT_LABELS = {
    "final_video_path": "Итоговое видео",
    "ready_video_path": "Готовое видео (до субтитров)",
    "raw_video_path": "Исходник",
    "preview_path": "Превью",
    "thumbnail_path": "Миниатюра",
    "captions_path": "Субтитры (SRT)",
    "probe_path": "Метаданные",
    "logs_path": "Лог обработки",
}


def _serialize_project(p: Project) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "theme_type": p.theme_type,
        "status": p.status,
        "mode": p.mode,
        "settings_json": p.settings_json,
        "preset_id": p.preset_id,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(data: ProjectCreate, session: AsyncSession = SessionDep):
    project = Project(
        name=data.name,
        theme_type=data.theme_type,
        status=data.status or "draft",
        mode=data.mode or "MANUAL",
        settings_json=data.settings_json,
        preset_id=data.preset_id,
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


@router.get("/projects", response_model=List[ProjectRead])
async def list_projects(session: AsyncSession = SessionDep):
    res = await session.execute(select(Project))
    return res.scalars().all()


@router.get("/projects/{project_id}", response_model=ProjectRead)
async def get_project(project_id: int, session: AsyncSession = SessionDep):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.patch("/projects/{project_id}", response_model=ProjectRead)
async def update_project(project_id: int, data: ProjectUpdate, session: AsyncSession = SessionDep):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    for field in ["name", "theme_type", "status", "mode", "settings_json", "preset_id"]:
        value = getattr(data, field)
        if value is not None:
            setattr(project, field, value)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


@router.post("/projects/{project_id}/pause", response_model=ProjectRead)
async def pause_project(project_id: int, session: AsyncSession = SessionDep):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    project.status = "paused"
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


@router.post("/projects/{project_id}/resume", response_model=ProjectRead)
async def resume_project(project_id: int, session: AsyncSession = SessionDep):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    project.status = "active"
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def _ensure_account_free_or_same(session: AsyncSession, account: SocialAccount, project_id: int):
    # Проверяем фактические привязки в таблицах источников/приёмников
    existing_link = (
        await session.execute(
            select(func.count(ProjectSource.id)).where(
                ProjectSource.social_account_id == account.id, ProjectSource.project_id != project_id
            )
        )
    ).scalar_one()
    existing_link += (
        await session.execute(
            select(func.count(ProjectDestination.id)).where(
                ProjectDestination.social_account_id == account.id, ProjectDestination.project_id != project_id
            )
        )
    ).scalar_one()

    if account.project_id and account.project_id != project_id:
        existing_link += 1

    if existing_link > 0:
        other = None
        if account.project_id and account.project_id != project_id:
            other = await session.get(Project, account.project_id)
        if not other:
            # пробуем взять любой проект из ссылок
            other = (
                await session.execute(
                    select(Project)
                    .join(ProjectSource, ProjectSource.project_id == Project.id)
                    .where(ProjectSource.social_account_id == account.id)
                    .limit(1)
                )
            ).scalar_one_or_none() or (
                await session.execute(
                    select(Project)
                    .join(ProjectDestination, ProjectDestination.project_id == Project.id)
                    .where(ProjectDestination.social_account_id == account.id)
                    .limit(1)
                )
            ).scalar_one_or_none()
        other_name = other.name if other else "другой проект"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Аккаунт уже привязан к проекту «{other_name}». Сначала отвяжите его.",
        )


@router.post("/projects/{project_id}/sources", response_model=ProjectSourceRead, status_code=status.HTTP_201_CREATED)
async def add_source(project_id: int, data: ProjectSourceCreate, session: AsyncSession = SessionDep):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    account = await session.get(SocialAccount, data.social_account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Social account not found")
    await _ensure_account_free_or_same(session, account, project_id)
    source = ProjectSource(
        project_id=project_id,
        platform=data.platform,
        social_account_id=data.social_account_id,
        source_type=data.source_type or "manual",
    )
    account.project_id = project_id
    session.add(account)
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return source


@router.delete("/projects/{project_id}/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(project_id: int, source_id: int, session: AsyncSession = SessionDep):
    source = await session.get(ProjectSource, source_id)
    if not source or source.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    account = await session.get(SocialAccount, source.social_account_id)
    await session.delete(source)
    await session.flush()
    if account:
        remaining_source = (
            await session.execute(
                select(ProjectSource.project_id).where(ProjectSource.social_account_id == account.id).limit(1)
            )
        ).scalar_one_or_none()
        remaining_dest = (
            await session.execute(
                select(ProjectDestination.project_id).where(ProjectDestination.social_account_id == account.id).limit(1)
            )
        ).scalar_one_or_none()
        new_pid = remaining_source or remaining_dest
        account.project_id = new_pid
        session.add(account)
    await session.commit()
    return {}


@router.get("/projects/{project_id}/sources", response_model=List[ProjectSourceRead])
async def list_sources(project_id: int, session: AsyncSession = SessionDep):
    res = await session.execute(select(ProjectSource).where(ProjectSource.project_id == project_id))
    return res.scalars().all()


@router.post(
    "/projects/{project_id}/destinations",
    response_model=ProjectDestinationRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_destination(project_id: int, data: ProjectDestinationCreate, session: AsyncSession = SessionDep):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    account = await session.get(SocialAccount, data.social_account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Social account not found")
    await _ensure_account_free_or_same(session, account, project_id)
    destination = ProjectDestination(
        project_id=project_id,
        platform=data.platform,
        social_account_id=data.social_account_id,
        priority=data.priority or 0,
    )
    account.project_id = project_id
    session.add(account)
    session.add(destination)
    await session.commit()
    await session.refresh(destination)
    return destination


@router.delete("/projects/{project_id}/destinations/{dest_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_destination(project_id: int, dest_id: int, session: AsyncSession = SessionDep):
    dest = await session.get(ProjectDestination, dest_id)
    if not dest or dest.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Destination not found")
    account = await session.get(SocialAccount, dest.social_account_id)
    await session.delete(dest)
    await session.flush()
    if account:
        remaining_source = (
            await session.execute(
                select(ProjectSource.project_id).where(ProjectSource.social_account_id == account.id).limit(1)
            )
        ).scalar_one_or_none()
        remaining_dest = (
            await session.execute(
                select(ProjectDestination.project_id).where(ProjectDestination.social_account_id == account.id).limit(1)
            )
        ).scalar_one_or_none()
        new_pid = remaining_source or remaining_dest
        account.project_id = new_pid
        session.add(account)
    await session.commit()
    return {}


@router.get("/projects/{project_id}/destinations", response_model=List[ProjectDestinationRead])
async def list_destinations(project_id: int, session: AsyncSession = SessionDep):
    res = await session.execute(select(ProjectDestination).where(ProjectDestination.project_id == project_id))
    return res.scalars().all()


async def _fetch_tiktok_items(session: AsyncSession, account_id: int, limit: int) -> list[dict]:
    stmt = (
        select(TikTokVideo)
        .where(TikTokVideo.account_id == account_id)
        .order_by(TikTokVideo.published_at.desc().nullslast(), TikTokVideo.id.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    items = []
    for v in rows:
        items.append(
            {
                "external_id": v.video_id,
                "permalink": v.permalink,
                "preview_url": v.thumbnail_url,
                "download_url": v.video_url,
                "caption_text": v.title,
                "published_at": v.published_at or datetime.now(timezone.utc),
            }
        )
    return items


async def _fetch_instagram_items(session: AsyncSession, account_id: int, limit: int) -> list[dict]:
    stmt = (
        select(InstagramPost)
        .where(InstagramPost.account_id == account_id)
        .order_by(InstagramPost.published_at.desc().nullslast(), InstagramPost.id.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    now = datetime.now(timezone.utc)
    return [
        {
            "external_id": p.post_id,
            "permalink": p.permalink,
            "preview_url": p.thumbnail_url,
            "download_url": p.media_url,
            "caption_text": p.caption,
            "published_at": p.published_at or now,
        }
        for p in rows
    ]


async def _fetch_youtube_items(session: AsyncSession, account_id: int, limit: int) -> list[dict]:
    stmt = (
        select(YouTubeVideo)
        .where(YouTubeVideo.account_id == account_id)
        .order_by(YouTubeVideo.published_at.desc().nullslast(), YouTubeVideo.id.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    now = datetime.now(timezone.utc)
    return [
        {
            "external_id": v.video_id,
            "permalink": v.permalink,
            "preview_url": v.thumbnail_url,
            "download_url": None,
            "caption_text": v.title,
            "published_at": v.published_at or now,
        }
        for v in rows
    ]


async def _fetch_vk_items(session: AsyncSession, account_id: int, limit: int) -> list[dict]:
    stmt_videos = (
        select(VKVideo)
        .where(VKVideo.account_id == account_id)
        .order_by(VKVideo.published_at.desc().nullslast(), VKVideo.id.desc())
        .limit(limit)
    )
    stmt_clips = (
        select(VKClip)
        .where(VKClip.account_id == account_id)
        .order_by(VKClip.published_at.desc().nullslast(), VKClip.id.desc())
        .limit(limit)
    )
    videos = (await session.execute(stmt_videos)).scalars().all()
    clips = (await session.execute(stmt_clips)).scalars().all()
    now = datetime.now(timezone.utc)
    items = [
        {
            "external_id": v.video_id,
            "permalink": v.permalink,
            "preview_url": v.thumbnail_url,
            "download_url": None,
            "caption_text": v.title or v.description,
            "published_at": v.published_at or now,
        }
        for v in videos
    ] + [
        {
            "external_id": c.clip_id,
            "permalink": c.permalink,
            "preview_url": c.thumbnail_url,
            "download_url": None,
            "caption_text": c.title or c.description,
            "published_at": c.published_at or now,
        }
        for c in clips
    ]
    # сортируем по времени
    items.sort(key=lambda x: x["published_at"], reverse=True)
    return items[:limit]


async def _fetch_content_for_source(session: AsyncSession, platform: str, account_id: int, limit: int) -> list[dict]:
    platform_lower = platform.lower()
    if platform_lower == "tiktok":
        return await _fetch_tiktok_items(session, account_id, limit)
    if platform_lower == "instagram":
        return await _fetch_instagram_items(session, account_id, limit)
    if platform_lower == "youtube":
        return await _fetch_youtube_items(session, account_id, limit)
    if platform_lower == "vk":
        return await _fetch_vk_items(session, account_id, limit)
    return []


@router.post("/projects/{project_id}/run-now", response_model=RunNowResponse)
async def project_run_now(
    project_id: int,
    payload: RunNowRequest | None = None,
    session: AsyncSession = SessionDep,
):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    limit_per_source = payload.limit_per_source if payload and payload.limit_per_source else 5
    limit_total = payload.limit_total if payload and payload.limit_total else 50

    # sources/destinations
    sources = (
        await session.execute(
            select(ProjectSource).where(ProjectSource.project_id == project_id, ProjectSource.is_active.is_(True))
        )
    ).scalars().all()
    destinations = (
        await session.execute(
            select(ProjectDestination).where(
                ProjectDestination.project_id == project_id, ProjectDestination.is_active.is_(True)
            )
        )
    ).scalars().all()

    debug: dict = {
        "project_id": project_id,
        "sources_count": len(sources),
        "destinations_count": len(destinations),
        "per_platform": [],
        "limit_per_source": limit_per_source,
        "limit_total": limit_total,
    }

    if not sources or not destinations:
        debug["skip_reason"] = "no_sources_or_destinations"
        return RunNowResponse(created_tasks=0, debug=debug)

    # group destinations by platform sorted by priority desc
    dest_by_platform: dict[str, list[ProjectDestination]] = {}
    for d in destinations:
        dest_by_platform.setdefault(d.platform.lower(), []).append(d)
    for lst in dest_by_platform.values():
        lst.sort(key=lambda x: x.priority, reverse=True)

    created = 0
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)
    new_tasks: list[PublishTask] = []

    for source in sources:
        platform = source.platform.lower()
        entry = {
            "platform": platform,
            "source_account_id": source.social_account_id,
            "found_items_in_db": 0,
            "selected_items": 0,
            "created_tasks": 0,
            "skipped_duplicates": 0,
            "skip_reason": None,
        }
        debug["per_platform"].append(entry)
        if platform not in dest_by_platform:
            entry["skip_reason"] = "no_destinations"
            continue
        dests = dest_by_platform[platform]
        if not dests:
            entry["skip_reason"] = "no_destinations"
            continue
        content_items = await _fetch_content_for_source(session, platform, source.social_account_id, limit_per_source)
        entry["found_items_in_db"] = len(content_items)
        if not content_items:
            entry["skip_reason"] = "no_content_in_db"
            continue
        rr_index = 0
        for item in content_items:
            entry["selected_items"] += 1
            if created >= limit_total:
                break
            destination = dests[rr_index % len(dests)]
            rr_index += 1

            # check duplicates
            existing = await session.execute(
                select(func.count(PublishTask.id)).where(
                    PublishTask.project_id == project_id,
                    PublishTask.platform == platform,
                    PublishTask.destination_social_account_id == destination.social_account_id,
                    PublishTask.external_id == item["external_id"],
                    PublishTask.created_at > seven_days_ago,
                    PublishTask.status.in_(["queued", "in_progress", "done"]),
                )
            )
            if existing.scalar_one() > 0:
                entry["skipped_duplicates"] += 1
                continue

            task = PublishTask(
                project_id=project_id,
                platform=platform,
                destination_social_account_id=destination.social_account_id,
                source_social_account_id=source.social_account_id,
                external_id=item["external_id"],
                permalink=item.get("permalink"),
                preview_url=item.get("preview_url"),
                download_url=item.get("download_url"),
                caption_text=item.get("caption_text"),
                status="queued",
            )
            new_tasks.append(task)
            created += 1
            entry["created_tasks"] += 1
            if created >= limit_total:
                break

    if new_tasks:
        session.add_all(new_tasks)
    # decision log
    from app.models import DecisionLog  # local import to avoid circular

    decision = DecisionLog(
        project_id=project_id,
        payload_json={
            "created_tasks": created,
            "debug": debug,
        },
    )
    session.add(decision)
    await session.commit()
    return RunNowResponse(created_tasks=created, debug=debug)


@router.get("/publish-tasks", response_model=list[PublishTaskRead])
async def list_publish_tasks(
    status_filter: str | None = Query(default=None, alias="status"),
    project_id: int | None = None,
    platform: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = SessionDep,
):
    stmt = select(PublishTask).order_by(PublishTask.created_at.desc()).offset(offset).limit(limit)
    if status_filter:
        stmt = stmt.where(PublishTask.status == status_filter)
    if project_id:
        stmt = stmt.where(PublishTask.project_id == project_id)
    if platform:
        stmt = stmt.where(PublishTask.platform == platform.lower())
    tasks = (await session.execute(stmt)).scalars().all()
    return tasks


@router.get("/publish-tasks/{task_id}", response_model=PublishTaskRead)
async def get_publish_task(task_id: int, session: AsyncSession = SessionDep):
    task = await session.get(PublishTask, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.patch("/publish-tasks/{task_id}", response_model=PublishTaskRead)
async def update_publish_task(task_id: int, data: PublishTaskUpdate, session: AsyncSession = SessionDep):
    task = await session.get(PublishTask, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    task.status = data.status
    if data.error_text is not None:
        task.error_text = data.error_text
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


def _build_dag_debug(preset: Preset | None) -> dict:
    if not preset or not preset.steps:
        return {"steps": []}
    ordered = sorted(preset.steps, key=lambda s: s.order_index)
    return {
        "steps": [
            {"id": s.id, "tool_id": s.tool_id, "name": s.name, "order_index": s.order_index, "enabled": s.enabled}
            for s in ordered
        ]
    }


def _path_to_file_url(path: str | None, task_id: int | None) -> str | None:
    if not path:
        return None
    if path.startswith("/files/"):
        return path
    if path.startswith("/data/tasks/") and task_id:
        filename = path.split("/")[-1]
        return f"/files/tasks/{task_id}/{filename}"
    return path


def _status_label(value: str | None) -> str:
    if not value:
        return "Неизвестно"
    return TASK_STATUS_LABELS.get(value, "Неизвестно")


def _step_status_label(value: str | None) -> str:
    if not value:
        return STEP_STATUS_LABELS.get("skipped", "—")
    return STEP_STATUS_LABELS.get(value, "—")


def _tool_title(tool_id: str | None, fallback: str | None = None) -> dict:
    data = TOOL_TITLES.get(tool_id or "", None)
    if data:
        return data
    text = fallback or (tool_id or "Шаг")
    return {"title": text, "description": None}


async def _process_task(task: PublishTask, session: AsyncSession):
    now = datetime.now(timezone.utc)
    project = await session.scalar(
        select(Project)
        .where(Project.id == task.project_id)
        .options(selectinload(Project.preset).selectinload(Preset.steps))
    )
    preset = project.preset if project else None
    steps_debug = _init_steps_debug(preset)

    task.preset_id = project.preset_id if project else None
    task.status = "processing"
    task.processing_started_at = now
    task.error_message = None
    session.add(task)
    await session.commit()
    await session.refresh(task)

    task_dir = TASKS_DIR / str(task.id)
    task_dir.mkdir(parents=True, exist_ok=True)
    log_path = task_dir / "process.log"

    def _log(msg: str):
        timestamp = datetime.now(timezone.utc).isoformat()
        with log_path.open("a", encoding="utf-8") as lf:
            lf.write(f"[{timestamp}] {msg}\n")

    raw_path = task_dir / "raw.mp4"
    ready_path = task_dir / "ready.mp4"
    thumb_path = task_dir / "thumb.jpg"
    preview_path = task_dir / "preview.mp4"
    probe_path = task_dir / "probe.json"
    captions_path = task_dir / "captions.srt"
    final_path = task_dir / "final.mp4"

    try:
        if not task.download_url:
            raise RuntimeError("Нет download_url для скачивания")

        download_err: Exception | None = None
        try:
            await _download_file(task.download_url, raw_path, log_cb=_log)
        except Exception as exc:
            download_err = exc

        if download_err:
            fallback_url = await _find_fallback_download_url(task, session, log_cb=_log)
            if fallback_url:
                _log(f"fallback url found, retry download: {fallback_url}")
                await _download_file(fallback_url, raw_path, log_cb=_log)
                download_err = None

        if download_err and task.permalink:
            _log(f"download via url failed ({download_err}), trying yt-dlp with permalink")
            try:
                await _download_via_ytdlp(task.permalink, raw_path, log_cb=_log)
                download_err = None
            except Exception as exc:
                download_err = exc

        if download_err:
            raise download_err

        probe_data = await _run_ffprobe(raw_path, probe_path, log_cb=_log)
        # Решаем, применять ли T04_CROP_RESIZE
        crop_step = None
        if preset and preset.steps:
            for s in preset.steps:
                if s.tool_id == "T04_CROP_RESIZE" and s.enabled:
                    crop_step = s
                    break

        if crop_step:
            crop_debug = _find_step_debug(steps_debug, crop_step.id)
            if crop_debug:
                crop_debug["status"] = "processing"
                crop_debug["started_at"] = datetime.now(timezone.utc).isoformat()
            t_start = datetime.now(timezone.utc)
            try:
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(raw_path),
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a?:0",
                    "-vf",
                    "scale='if(gte(a,1080/1920),-2,1080)':'if(gte(a,1080/1920),1920,-2)',crop=1080:1920,setsar=1",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "20",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    str(ready_path),
                ]
                await _run_cmd(cmd, _log)
                duration_ms = int((datetime.now(timezone.utc) - t_start).total_seconds() * 1000)
                if crop_debug:
                    crop_debug["status"] = "ok"
                    crop_debug["finished_at"] = datetime.now(timezone.utc).isoformat()
                    crop_debug["duration_ms"] = duration_ms
                    crop_debug["outputs"] = {"ready_video_path": str(ready_path)}
            except Exception as step_exc:
                duration_ms = int((datetime.now(timezone.utc) - t_start).total_seconds() * 1000)
                if crop_debug:
                    crop_debug["status"] = "error"
                    crop_debug["finished_at"] = datetime.now(timezone.utc).isoformat()
                    crop_debug["duration_ms"] = duration_ms
                    crop_debug["error"] = str(step_exc)
                raise
        else:
            await _make_ready_copy(raw_path, ready_path, log_cb=_log)
        await _make_thumbnail(raw_path, thumb_path, log_cb=_log)
        await _make_preview(raw_path, preview_path, log_cb=_log)

        # T14_BURN_CAPTIONS
        burn_step = None
        if preset and preset.steps:
            for s in preset.steps:
                if s.tool_id == "T14_BURN_CAPTIONS" and s.enabled:
                    burn_step = s
                    break
        if burn_step:
            burn_debug = _find_step_debug(steps_debug, burn_step.id)
            if burn_debug:
                burn_debug["status"] = "processing"
                burn_debug["started_at"] = datetime.now(timezone.utc).isoformat()
            t_start = datetime.now(timezone.utc)
            try:
                caption_text = task.caption_text or task.instructions or "Подпишись ❤️"
                await _create_captions_srt(caption_text, captions_path, log_cb=_log)
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(ready_path),
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a?:0",
                    "-vf",
                    f"subtitles={captions_path}:force_style='FontSize=36,Outline=2'",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "20",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    str(final_path),
                ]
                await _run_cmd(cmd, _log)
                duration_ms = int((datetime.now(timezone.utc) - t_start).total_seconds() * 1000)
                if burn_debug:
                    burn_debug["status"] = "ok"
                    burn_debug["finished_at"] = datetime.now(timezone.utc).isoformat()
                    burn_debug["duration_ms"] = duration_ms
                    burn_debug["outputs"] = {"final_video_path": str(final_path), "captions_path": str(captions_path)}
            except Exception as step_exc:
                duration_ms = int((datetime.now(timezone.utc) - t_start).total_seconds() * 1000)
                if burn_debug:
                    burn_debug["status"] = "error"
                    burn_debug["finished_at"] = datetime.now(timezone.utc).isoformat()
                    burn_debug["duration_ms"] = duration_ms
                    burn_debug["error"] = str(step_exc)
                raise

        dag_debug = _build_dag_debug(preset)
        if steps_debug:
            dag_debug = {"steps": steps_debug}
        artifacts = {
            "raw_video_path": str(raw_path),
            "ready_video_path": str(ready_path),
            "thumbnail_path": str(thumb_path),
            "preview_path": str(preview_path),
            "logs_path": str(log_path),
            "probe_path": str(probe_path),
            "probe_meta": probe_data,
            "captions_path": str(captions_path) if captions_path.exists() else None,
            "final_video_path": str(final_path) if final_path.exists() else None,
        }
        task.dag_debug = dag_debug
        task.artifacts = artifacts
        task.status = "ready_for_review"
        task.processing_finished_at = datetime.now(timezone.utc)
    except Exception as exc:
        _log(f"error: {exc}")
        task.status = "error"
        task.error_message = str(exc)
        task.processing_finished_at = datetime.now(timezone.utc)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def _download_file(url: str, dest: Path, retries: int = 2, timeout: float = 30.0, log_cb=lambda msg: None):
    dest.parent.mkdir(parents=True, exist_ok=True)
    min_size = 200 * 1024  # 200KB
    last_exc: Exception | None = None
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.tiktok.com/",
        "Accept": "*/*",
    }
    for attempt in range(1, retries + 2):
        try:
            log_cb(f"download attempt {attempt}: {url}")
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
                async with client.stream("GET", url) as resp:
                    ctype = (resp.headers.get("Content-Type") or "").lower()
                    clen = resp.headers.get("Content-Length")
                    log_cb(
                        f"final_url={resp.url} status={resp.status_code} "
                        f"content-type={ctype or 'unknown'} content-length={clen or 'unknown'}"
                    )
                    if resp.status_code >= 400:
                        raise RuntimeError(f"Download failed with status {resp.status_code}")
                    if ctype and not (ctype.startswith("video/") or ctype.startswith("application/octet-stream")):
                        raise RuntimeError(f"Скачивание не вернуло видео (Content-Type={ctype}, size={clen or 'unknown'})")
                    with dest.open("wb") as f:
                        async for chunk in resp.aiter_bytes():
                            f.write(chunk)
            size = dest.stat().st_size
            log_cb(f"downloaded to {dest} size={size} bytes")
            if size < min_size:
                raise RuntimeError(f"Скачивание не вернуло видео (Content-Type={ctype or 'unknown'}, size={size} bytes)")
            with dest.open("rb") as f:
                head = f.read(2048)
                head_lower = head.lower()
                if b"<html" in head_lower or b"<!doctype" in head_lower:
                    raise RuntimeError(
                        f"Скачивание не вернуло видео (Content-Type={ctype or 'unknown'}, size={size} bytes, html detected)"
                    )
                if b"webvtt" in head_lower[:2048]:
                    raise RuntimeError(
                        "Скачалось не видео, а субтитры (WEBVTT). Нужен другой video_url/download_url."
                    )
                if b"ftyp" not in head:
                    raise RuntimeError(
                        f"Скачивание не вернуло mp4 (нет ftyp, Content-Type={ctype or 'unknown'}, size={size} bytes)"
                    )
                # если Content-Type octet-stream, полагаемся на magic ftyp
                if ctype and ctype.startswith("application/octet-stream"):
                    log_cb("octet-stream accepted due to ftyp marker in file")
            return
        except Exception as exc:
            last_exc = exc
            if dest.exists():
                try:
                    dest.unlink()
                except Exception:
                    pass
            log_cb(f"download failed: {exc}")
            if attempt > retries:
                break
            await asyncio.sleep(1.5 * attempt)
    raise RuntimeError(f"Не удалось скачать файл: {last_exc}")


async def _run_cmd(cmd: list[str], log_cb=lambda msg: None):
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await proc.communicate()
    stdout_dec = stdout.decode(errors="ignore") if stdout else ""
    stderr_dec = stderr.decode(errors="ignore") if stderr else ""
    if stdout_dec:
        log_cb(stdout_dec)
    if stderr_dec:
        log_cb(stderr_dec)
    if proc.returncode != 0:
        raise RuntimeError(f"Команда завершилась с кодом {proc.returncode}: {' '.join(cmd)}; stderr: {stderr_dec[-400:]}")
    return stdout_dec, stderr_dec


async def _run_ffprobe(src: Path, probe_path: Path, log_cb=lambda msg: None) -> dict:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        str(src),
    ]
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await proc.communicate()
    if stderr:
        log_cb(stderr.decode(errors="ignore"))
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe вернул код {proc.returncode}")
    data = json.loads(stdout.decode())
    probe_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log_cb(f"ffprobe saved to {probe_path}")

    duration = None
    width = None
    height = None
    fps = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            width = stream.get("width")
            height = stream.get("height")
            fr = stream.get("avg_frame_rate") or stream.get("r_frame_rate")
            if fr and fr != "0/0":
                try:
                    num, den = fr.split("/")
                    fps = round(float(num) / float(den), 3) if float(den) else None
                except Exception:
                    fps = None
            break
    fmt = data.get("format") or {}
    if fmt.get("duration"):
        try:
            duration = float(fmt["duration"])
        except Exception:
            duration = None
    return {"duration": duration, "width": width, "height": height, "fps": fps}


async def _make_ready_copy(raw_path: Path, ready_path: Path, log_cb=lambda msg: None):
    # Простая копия/нормализация
    cmd = ["ffmpeg", "-y", "-i", str(raw_path), "-c", "copy", str(ready_path)]
    await _run_cmd(cmd, log_cb)
    log_cb(f"ready video saved to {ready_path}")


async def _make_thumbnail(raw_path: Path, thumb_path: Path, log_cb=lambda msg: None):
    cmd = ["ffmpeg", "-y", "-ss", "1", "-i", str(raw_path), "-frames:v", "1", "-q:v", "2", str(thumb_path)]
    await _run_cmd(cmd, log_cb)
    log_cb(f"thumbnail saved to {thumb_path}")


async def _make_preview(raw_path: Path, preview_path: Path, log_cb=lambda msg: None):
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(raw_path),
        "-t",
        "5",
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(preview_path),
    ]
    await _run_cmd(cmd, log_cb)
    log_cb(f"preview saved to {preview_path}")


async def _download_via_ytdlp(permalink: str, dest: Path, log_cb=lambda msg: None):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    cmd = [
        "yt-dlp",
        "-f",
        "mp4",
        "--merge-output-format",
        "mp4",
        "--no-part",
        "-o",
        str(dest),
        permalink,
    ]
    log_cb(f"yt-dlp start: {permalink}")
    await _run_cmd(cmd, log_cb)
    if not dest.exists():
        raise RuntimeError("yt-dlp не создал файл")
    size = dest.stat().st_size
    log_cb(f"yt-dlp saved {dest} size={size} bytes")
    if size < 200 * 1024:
        raise RuntimeError("yt-dlp вернул слишком маленький файл")
    with dest.open("rb") as f:
        head = f.read(2048)
        if b"webvtt" in head.lower():
            raise RuntimeError("yt-dlp вернул субтитры (WEBVTT)")
        if b"ftyp" not in head:
            raise RuntimeError("yt-dlp вернул не mp4 (нет ftyp)")


async def _find_fallback_download_url(task: PublishTask, session: AsyncSession, log_cb=lambda msg: None) -> str | None:
    # Пока только для TikTok: пытаемся вытащить альтернативный mp4 url из raw поля видео
    if task.platform.lower() != "tiktok" or not task.external_id:
        return None
    candidate_urls: list[str] = []
    video = await session.scalar(select(TikTokVideo).where(TikTokVideo.video_id == task.external_id))
    if not video or not video.raw:
        log_cb("fallback: нет raw для TikTok видео")
        return None

    def _add_if_url(val):
        if isinstance(val, str) and val.startswith("http"):
            candidate_urls.append(val)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str) and item.startswith("http"):
                    candidate_urls.append(item)

    raw = video.raw
    if isinstance(raw, dict):
        keys = [
            "downloadAddr",
            "download_addr",
            "video_url",
            "videoUrl",
            "playAddr",
            "play_addr",
            "playUrl",
            "play_url",
            "download_url",
            "url",
            "urls",
            "url_list",
            "urlList",
        ]
        for k in keys:
            if k in raw:
                _add_if_url(raw.get(k))
        # битрейты
        if "bit_rate" in raw and isinstance(raw["bit_rate"], list):
            for entry in raw["bit_rate"]:
                if isinstance(entry, dict):
                    _add_if_url(entry.get("play_addr"))
                    _add_if_url(entry.get("playAddr"))
                    _add_if_url(entry.get("download_addr"))
                    _add_if_url(entry.get("downloadAddr"))
        if "video" in raw and isinstance(raw["video"], dict):
            for k in keys:
                if k in raw["video"]:
                    _add_if_url(raw["video"].get(k))
            if "bitrate_info" in raw["video"] and isinstance(raw["video"]["bitrate_info"], list):
                for entry in raw["video"]["bitrate_info"]:
                    if isinstance(entry, dict):
                        _add_if_url(entry.get("play_addr"))
                        _add_if_url(entry.get("playAddr"))
                        _add_if_url(entry.get("download_addr"))
                        _add_if_url(entry.get("downloadAddr"))

    # Фильтруем явные mp4
    candidate_urls = [u for u in candidate_urls if ".mp4" in u or "video_mp4" in u]
    seen = set()
    unique_candidates = []
    for u in candidate_urls:
        if u not in seen:
            seen.add(u)
            unique_candidates.append(u)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.tiktok.com/",
        "Accept": "*/*",
    }

    for cand in unique_candidates:
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers) as client:
                resp = await client.head(cand)
                ctype = (resp.headers.get("Content-Type") or "").lower()
                log_cb(f"fallback HEAD {cand} status={resp.status_code} ctype={ctype or 'unknown'}")
                if resp.status_code < 400 and (ctype.startswith("video/") or "mp4" in ctype):
                    return str(resp.url)
        except Exception as exc:
            log_cb(f"fallback HEAD failed for {cand}: {exc}")
            continue
    log_cb("fallback: подходящий mp4 url не найден")
    return None


def _init_steps_debug(preset: Preset | None) -> list[dict]:
    if not preset or not preset.steps:
        return []
    ordered = sorted(preset.steps, key=lambda s: s.order_index)
    steps_debug = []
    for s in ordered:
        steps_debug.append(
            {
                "id": s.id,
                "tool_id": s.tool_id,
                "name": s.name,
                "order_index": s.order_index,
                "enabled": s.enabled,
                "status": "skipped",
                "started_at": None,
                "finished_at": None,
                "duration_ms": None,
                "error": None,
                "outputs": None,
            }
        )
    return steps_debug


def _find_step_debug(steps_debug: list[dict], step_id: int | None) -> dict | None:
    if step_id is None:
        return None
    for entry in steps_debug:
        if entry.get("id") == step_id:
            return entry
    return None


async def _create_captions_srt(text: str, dest: Path, log_cb=lambda msg: None):
    dest.parent.mkdir(parents=True, exist_ok=True)
    base_text = text.strip() or "Подпишись ❤️"
    words = base_text.split()
    chunks: list[str] = []
    current: list[str] = []
    max_len = 8
    for w in words:
        current.append(w)
        if len(current) >= max_len:
            chunks.append(" ".join(current))
            current = []
    if current:
        chunks.append(" ".join(current))
    if not chunks:
        chunks = [base_text]
    while len(chunks) < 2:
        chunks.append(base_text)
    if len(chunks) > 3:
        chunks = chunks[:3]

    timings = [
        ("00:00:00,000", "00:00:02,500"),
        ("00:00:02,500", "00:00:05,000"),
        ("00:00:05,000", "00:00:07,000"),
    ]
    with dest.open("w", encoding="utf-8") as f:
        for idx, chunk in enumerate(chunks, start=1):
            start, end = timings[idx - 1] if idx - 1 < len(timings) else timings[-1]
            f.write(f"{idx}\n{start} --> {end}\n{chunk}\n\n")
    log_cb(f"captions written to {dest}")


@router.post("/publish-tasks/{task_id}/process", response_model=PublishTaskRead)
async def process_publish_task(task_id: int, session: AsyncSession = SessionDep):
    task = await session.get(PublishTask, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.status not in {"queued", "error"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Task is not in queued/error state")
    return await _process_task(task, session)


@router.get("/publish-tasks/{task_id}/ui", response_model=dict)
async def get_publish_task_ui(task_id: int, session: AsyncSession = SessionDep):
    task = await session.get(PublishTask, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    project = await session.scalar(
        select(Project)
        .where(Project.id == task.project_id)
        .options(selectinload(Project.preset).selectinload(Preset.steps))
    )
    preset = project.preset if project else None
    preset_steps = sorted(preset.steps, key=lambda s: s.order_index) if preset and preset.steps else []

    dag_steps = []
    if task.dag_debug and isinstance(task.dag_debug, dict):
        dag_steps = task.dag_debug.get("steps") or []

    # result section
    artifacts = task.artifacts or {}
    task_id_str = str(task.id)
    result = {
        "preview": {
          "title": "Превью",
          "url": _path_to_file_url(str(artifacts.get("preview_path") or ""), task.id),
          "available": bool(artifacts.get("preview_path")),
        },
        "final": {
          "title": "Итоговое видео",
          "url": _path_to_file_url(str(artifacts.get("final_video_path") or ""), task.id),
          "available": bool(artifacts.get("final_video_path")),
        },
        "ready": {
          "title": "Готовое видео",
          "url": _path_to_file_url(str(artifacts.get("ready_video_path") or ""), task.id),
          "available": bool(artifacts.get("ready_video_path")),
        },
        "raw": {
          "title": "Исходное видео",
          "url": _path_to_file_url(str(artifacts.get("raw_video_path") or ""), task.id),
          "available": bool(artifacts.get("raw_video_path")),
        },
        "thumb": {
          "title": "Миниатюра",
          "url": _path_to_file_url(str(artifacts.get("thumbnail_path") or ""), task.id),
          "available": bool(artifacts.get("thumbnail_path")),
        },
    }

    # pipeline build
    steps_ui = []
    total_duration_ms = 0.0
    if preset_steps:
        for idx, pstep in enumerate(preset_steps, start=1):
            dag_match = None
            for d in dag_steps:
                if d.get("id") == pstep.id or d.get("tool_id") == pstep.tool_id:
                    dag_match = d
                    break
            status = (dag_match.get("status") if dag_match else None) or ("skipped" if not pstep.enabled else "skipped")
            status_label = _step_status_label(status)
            dur_ms = dag_match.get("duration_ms") if dag_match else None
            if isinstance(dur_ms, (int, float)):
                total_duration_ms += dur_ms
            outputs_list = []
            outputs_raw = dag_match.get("outputs") if dag_match else None
            if outputs_raw and isinstance(outputs_raw, dict):
                for key, val in outputs_raw.items():
                    title = OUTPUT_LABELS.get(key, key)
                    url = None
                    if isinstance(val, str):
                        url = _path_to_file_url(val, task.id)
                    outputs_list.append({"title": title, "url": url, "kind": "file"})
            # если шаг выключен
            if status == "skipped" and not pstep.enabled:
                error_message = "Шаг выключен в пресете"
            else:
                error_message = dag_match.get("error") if dag_match else None

            tool = _tool_title(pstep.tool_id, pstep.name)
            steps_ui.append(
                {
                    "index": idx,
                    "id": pstep.tool_id.lower(),
                    "title": tool["title"],
                    "description": tool["description"],
                    "status": status,
                    "status_label": status_label,
                    "duration_sec": round(dur_ms / 1000, 3) if isinstance(dur_ms, (int, float)) else None,
                    "error_message": error_message,
                    "outputs": outputs_list,
                }
            )
    elif dag_steps:
        for idx, d in enumerate(dag_steps, start=1):
            status = d.get("status") or "skipped"
            dur_ms = d.get("duration_ms")
            if isinstance(dur_ms, (int, float)):
                total_duration_ms += dur_ms
            outputs_list = []
            outputs_raw = d.get("outputs")
            if outputs_raw and isinstance(outputs_raw, dict):
                for key, val in outputs_raw.items():
                    title = OUTPUT_LABELS.get(key, key)
                    url = _path_to_file_url(val, task.id) if isinstance(val, str) else None
                    outputs_list.append({"title": title, "url": url, "kind": "file"})
            tool = _tool_title(d.get("tool_id"), d.get("name"))
            steps_ui.append(
                {
                    "index": idx,
                    "id": (d.get("tool_id") or f"step_{idx}").lower(),
                    "title": tool["title"],
                    "description": tool["description"],
                    "status": status,
                    "status_label": _step_status_label(status),
                    "duration_sec": round(dur_ms / 1000, 3) if isinstance(dur_ms, (int, float)) else None,
                    "error_message": d.get("error"),
                    "outputs": outputs_list,
                }
            )

    summary = {
        "total": len(steps_ui),
        "done": sum(1 for s in steps_ui if s["status"] == "ok"),
        "skipped": sum(1 for s in steps_ui if s["status"] == "skipped"),
        "error": sum(1 for s in steps_ui if s["status"] == "error"),
        "duration_sec": round(total_duration_ms / 1000, 3) if total_duration_ms else None,
    }

    def _artifact_item(name: str, key: str):
        path = artifacts.get(key)
        return {
            "title": OUTPUT_LABELS.get(key, name),
            "url": _path_to_file_url(path, task.id),
            "available": bool(path),
            "kind": "file",
            "file": name,
        }

    files = {
        "video": [
            _artifact_item("final.mp4", "final_video_path"),
            _artifact_item("ready.mp4", "ready_video_path"),
            _artifact_item("raw.mp4", "raw_video_path"),
        ],
        "preview": [
            _artifact_item("preview.mp4", "preview_path"),
            _artifact_item("thumb.jpg", "thumbnail_path"),
        ],
        "subtitles": [
            _artifact_item("captions.srt", "captions_path"),
        ],
        "technical": [
            _artifact_item("probe.json", "probe_path"),
            {"title": "Лог обработки", "url": f"/api/publish-tasks/{task.id}/log?tail=500", "available": True, "kind": "log", "file": "process.log"},
        ],
    }

    actions = {
        "can_process": task.status in {"queued", "error"},
        "can_mark_done": task.status not in {"done", "completed"},
        "can_mark_error": task.status != "error",
    }

    response = {
        "task": {
            "id": task.id,
            "status": task.status,
            "status_label": _status_label(task.status),
            "project_id": task.project_id,
            "project_name": project.name if project else None,
            "platform": task.platform,
            "platform_label": task.platform.capitalize(),
            "preset_id": project.preset_id if project else None,
            "preset_name": preset.name if preset else None,
            "external_id": task.external_id,
            "permalink": task.permalink,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        },
        "result": result,
        "pipeline": {"summary": summary, "steps": steps_ui},
        "files": files,
        "actions": actions,
    }
    return response

@router.get("/publish-tasks/{task_id}/log", response_model=dict)
async def get_publish_task_log(task_id: int, tail: int = Query(default=200, ge=1, le=5000), session: AsyncSession = SessionDep):
    task = await session.get(PublishTask, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    log_path_str = None
    if task.artifacts and isinstance(task.artifacts, dict):
        log_path_str = task.artifacts.get("logs_path")
    content = ""
    if log_path_str:
        path = Path(log_path_str)
        if path.exists() and path.is_file():
            content = path.read_text(encoding="utf-8", errors="ignore")
            if tail and len(content.splitlines()) > tail:
                content = "\n".join(content.splitlines()[-tail:])
    return {"task_id": task_id, "tail": content}


@router.post("/projects/{project_id}/process-queue", response_model=dict)
async def process_project_queue(project_id: int, limit: int = 10, session: AsyncSession = SessionDep):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    tasks_stmt = (
        select(PublishTask)
        .where(PublishTask.project_id == project_id, PublishTask.status == "queued")
        .order_by(PublishTask.created_at.asc())
        .limit(limit)
    )
    tasks = (await session.execute(tasks_stmt)).scalars().all()
    processed = []
    for t in tasks:
        processed.append(await _process_task(t, session))
    return {"processed": len(processed), "task_ids": [t.id for t in processed]}


@router.post("/projects/{project_id}/generate-tasks", response_model=dict)
async def generate_project_tasks(
    project_id: int,
    count: int = Query(default=5, ge=1, le=50),
    platform: str | None = Query(default=None),
    min_score: float | None = Query(default=None),
    new_ratio: float = Query(default=0.6, ge=0, le=1),
    session: AsyncSession = SessionDep,
):
    """
    Generate publish tasks from video pool.
    
    Automatically selects top viral videos from project sources
    and creates tasks for destination accounts.
    """
    from app.services.task_generator import TaskGeneratorService
    
    generator = TaskGeneratorService(session)
    result = await generator.generate_tasks(
        project_id,
        count=count,
        platform=platform,
        min_score=min_score,
        new_ratio=new_ratio,
    )
    return result


@router.get("/projects/{project_id}/video-pool", response_model=dict)
async def get_project_video_pool(
    project_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    platform: str | None = Query(default=None),
    min_score: float | None = Query(default=None),
    include_used: bool = Query(default=False),
    session: AsyncSession = SessionDep,
):
    """
    Get available videos from project sources sorted by virality score.
    """
    from app.services.video_pool import VideoPoolService
    
    pool = VideoPoolService(session)
    videos = await pool.get_available_videos(
        project_id,
        platform=platform,
        limit=limit,
        min_score=min_score,
        include_used=include_used,
    )
    return {"items": videos, "total": len(videos)}


@router.get("/projects/{project_id}/video-pool/mixed", response_model=dict)
async def get_project_mixed_pool(
    project_id: int,
    limit: int = Query(default=10, ge=1, le=50),
    new_ratio: float = Query(default=0.6, ge=0, le=1),
    new_days: int = Query(default=7, ge=1, le=30),
    min_score: float | None = Query(default=None),
    platform: str | None = Query(default=None),
    session: AsyncSession = SessionDep,
):
    """
    Get mixed pool of new and top historical videos.
    
    - new_ratio=0.6 means 60% recent videos, 40% all-time top
    """
    from app.services.video_pool import VideoPoolService
    
    pool = VideoPoolService(session)
    result = await pool.get_mixed_pool(
        project_id,
        total_limit=limit,
        new_ratio=new_ratio,
        new_days=new_days,
        min_score=min_score,
        platform=platform,
    )
    return result


@router.post("/publish-tasks/{task_id}/process-v2", response_model=dict)
async def process_task_v2(task_id: int, session: AsyncSession = SessionDep):
    """
    Process a task using the new PipelineExecutor.
    
    This endpoint uses the modular pipeline system that dynamically
    executes preset steps.
    """
    from app.services.task_processor import TaskProcessor
    
    processor = TaskProcessor(session)
    result = await processor.process_task(task_id)
    return result


@router.post("/projects/{project_id}/process-batch", response_model=dict)
async def process_project_batch(
    project_id: int,
    limit: int = Query(default=5, ge=1, le=20),
    session: AsyncSession = SessionDep,
):
    """
    Process multiple queued tasks for a project.
    """
    from app.services.task_processor import TaskProcessor
    
    processor = TaskProcessor(session)
    result = await processor.process_batch(project_id=project_id, limit=limit)
    return result


@router.get("/pipeline/handlers", response_model=dict)
async def list_pipeline_handlers():
    """List all registered pipeline step handlers."""
    from app.services.pipeline_executor import PipelineExecutor
    
    handlers = PipelineExecutor.list_handlers()
    return {
        "handlers": handlers,
        "count": len(handlers),
    }


@router.post("/publish-tasks/{task_id}/publish", response_model=dict)
async def publish_task(task_id: int, session: AsyncSession = SessionDep):
    """
    Publish a completed task to its destination platform.
    Task must have status 'done' to be published.
    """
    from app.services.auto_publisher import auto_publisher
    
    result = await auto_publisher.publish_task(session, task_id)
    return result


@router.get("/publish-tasks/{task_id}/metrics", response_model=list[dict])
async def get_task_metrics(task_id: int, session: AsyncSession = SessionDep):
    """Get metric snapshots for a published task."""
    from app.models import PublishedVideoMetrics
    result = await session.execute(
        select(PublishedVideoMetrics)
        .where(PublishedVideoMetrics.task_id == task_id)
        .order_by(PublishedVideoMetrics.snapshot_at)
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "task_id": r.task_id,
            "candidate_id": r.candidate_id,
            "platform": r.platform,
            "views": r.views,
            "likes": r.likes,
            "comments": r.comments,
            "shares": r.shares,
            "snapshot_at": r.snapshot_at.isoformat() if r.snapshot_at else None,
            "hours_since_publish": r.hours_since_publish,
        }
        for r in rows
    ]


@router.get("/projects/{project_id}/analytics/score-vs-performance", response_model=list[dict])
async def score_vs_performance(
    project_id: int,
    platform: str | None = None,
    age_bucket: str | None = None,
    session: AsyncSession = SessionDep,
):
    """Candidate virality_score → actual published video performance.

    Includes age_bucket, performance_rate, and platform for proper
    comparison across different video ages and platforms.

    Query params:
      - platform: filter by platform (youtube, tiktok, instagram, vk)
      - age_bucket: filter by age bucket (0-6h, 6-24h, 1-3d, 3-7d, 7d+)
    """
    from app.models import Candidate, PublishedVideoMetrics, PublishTask
    from sqlalchemy import func, and_

    # Subquery: latest snapshot per task_id
    latest_snap = (
        select(
            PublishedVideoMetrics.task_id,
            func.max(PublishedVideoMetrics.snapshot_at).label("max_snap"),
        )
        .group_by(PublishedVideoMetrics.task_id)
        .subquery()
    )

    query = (
        select(
            Candidate.id.label("candidate_id"),
            Candidate.virality_score,
            Candidate.virality_factors,
            Candidate.title,
            Candidate.platform,
            PublishedVideoMetrics.views,
            PublishedVideoMetrics.likes,
            PublishedVideoMetrics.comments,
            PublishedVideoMetrics.shares,
            PublishedVideoMetrics.hours_since_publish,
            PublishedVideoMetrics.snapshot_at,
            PublishTask.published_url,
            PublishTask.published_at,
        )
        .join(PublishTask, Candidate.linked_publish_task_id == PublishTask.id)
        .join(PublishedVideoMetrics, PublishedVideoMetrics.task_id == PublishTask.id)
        .join(
            latest_snap,
            and_(
                PublishedVideoMetrics.task_id == latest_snap.c.task_id,
                PublishedVideoMetrics.snapshot_at == latest_snap.c.max_snap,
            ),
        )
        .where(
            Candidate.project_id == project_id,
            Candidate.virality_score.isnot(None),
            PublishTask.status == "published",
        )
        .order_by(Candidate.virality_score.desc())
    )

    if platform:
        query = query.where(Candidate.platform == platform.lower())

    result = await session.execute(query)
    rows = result.all()

    items = []
    for row in rows:
        h = row.hours_since_publish or 0
        bucket = _age_bucket(h)

        # Skip if age_bucket filter is set and doesn't match
        if age_bucket and bucket != age_bucket:
            continue

        views = row.views or 0
        likes = row.likes or 0
        comments = row.comments or 0

        views_per_hour = round(views / max(h, 1), 1)
        like_rate = round(likes / max(views, 1), 4)
        comment_rate = round(comments / max(views, 1), 4)

        items.append({
            "candidate_id": row.candidate_id,
            "virality_score": row.virality_score,
            "virality_factors": row.virality_factors,
            "title": row.title,
            "platform": row.platform,
            "views": views,
            "likes": likes,
            "comments": comments,
            "shares": row.shares,
            "hours_since_publish": h,
            "age_bucket": bucket,
            "performance_rate": {
                "views_per_hour": views_per_hour,
                "like_rate": like_rate,
                "comment_rate": comment_rate,
            },
            "snapshot_at": row.snapshot_at.isoformat() if row.snapshot_at else None,
            "published_url": row.published_url,
        })

    return items


def _age_bucket(hours: int) -> str:
    """Classify hours_since_publish into comparable age buckets."""
    if hours <= 6:
        return "0-6h"
    if hours <= 24:
        return "6-24h"
    if hours <= 72:
        return "1-3d"
    if hours <= 168:
        return "3-7d"
    return "7d+"


@router.get("/projects/{project_id}/analytics/calibration", response_model=dict)
async def get_scoring_calibration(project_id: int, session: AsyncSession = SessionDep):
    """Get cached scoring calibration for a project.

    Returns the latest calibration result from project.meta,
    or runs a fresh calibration if none exists.
    """
    from app.models import Project
    project = await session.get(Project, project_id)
    if not project:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Project not found")

    meta = project.meta or {}
    cached = meta.get("scoring_calibration")
    if cached:
        return cached

    # No cached result — run fresh
    from app.services.calibrate_scoring import calibrate_project_scoring
    return await calibrate_project_scoring(session, project_id)


@router.post("/projects/{project_id}/analytics/calibrate", response_model=dict)
async def run_scoring_calibration(project_id: int, session: AsyncSession = SessionDep):
    """Force a fresh scoring calibration for a project.

    Computes correlation virality_score vs views_per_hour,
    determines auto_approve_threshold, and identifies which
    virality_factors actually correlate with real performance.
    """
    from app.services.calibrate_scoring import calibrate_project_scoring
    return await calibrate_project_scoring(session, project_id)


@router.get("/export-profiles", response_model=list[ExportProfileRead])
async def list_export_profiles(session: AsyncSession = SessionDep):
    """Список всех доступных export-профилей."""
    res = await session.execute(select(ExportProfile).order_by(ExportProfile.id))
    return res.scalars().all()
