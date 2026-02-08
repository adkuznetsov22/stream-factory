"""
Operations endpoints — watchdog, health, system status.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter(prefix="/api/ops", tags=["ops"])

SessionDep = Depends(get_session)


@router.post("/watchdog")
async def run_watchdog_endpoint(
    dry_run: bool = Query(default=True),
    session: AsyncSession = SessionDep,
):
    """Run watchdog to find and mark stuck tasks."""
    from app.services.watchdog_service import run_watchdog
    return await run_watchdog(session, dry_run=dry_run)


@router.get("/health")
async def health_endpoint(
    session: AsyncSession = SessionDep,
):
    """System health overview: task counts, stuck tasks, scheduler status."""
    from app.services.watchdog_service import get_health
    return await get_health(session)
