from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from .routes_accounts import emails_router, phones_router, router as accounts_router
from .routes_youtube import router as youtube_router
from .routes_vk import router as vk_router
from .routes_tiktok import router as tiktok_router
from .routes_instagram import router as instagram_router
from .routes_projects import router as projects_router
from .routes_presets import router as presets_router
from .routes_tools import router as tools_router
from .routes_moderation import router as moderation_router
from .routes_files import router as files_router
from .routes_virality import router as virality_router
from .routes_scheduler import router as scheduler_router
from .routes_dashboard import router as dashboard_router
from .routes_auth import router as auth_router
from .routes_feed import router as feed_router
from .settings import get_settings

logger = logging.getLogger("app")

app = FastAPI()
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url)
    return PlainTextResponse("Internal Server Error", status_code=500)


@app.get("/ping")
async def ping():
    return {"status": "ok"}


app.include_router(accounts_router)
app.include_router(phones_router)
app.include_router(emails_router)
app.include_router(youtube_router)
app.include_router(vk_router)
app.include_router(tiktok_router)
app.include_router(instagram_router)
app.include_router(projects_router)
app.include_router(presets_router)
app.include_router(tools_router)
app.include_router(moderation_router)
app.include_router(files_router)
app.include_router(virality_router)
app.include_router(scheduler_router)
app.include_router(dashboard_router)
app.include_router(auth_router)
app.include_router(feed_router)


@app.on_event("startup")
async def startup_event():
    """Start scheduler on app startup."""
    from app.services.scheduler import scheduler_service
    scheduler_service.configure(settings.database_url)
    scheduler_service.start()
    logger.info("Scheduler started on app startup")


@app.on_event("shutdown")
async def shutdown_event():
    """Stop scheduler on app shutdown."""
    from app.services.scheduler import scheduler_service
    scheduler_service.stop()
    logger.info("Scheduler stopped on app shutdown")
