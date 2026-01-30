from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import ToolRegistry
from app.schemas import ToolRead

router = APIRouter(prefix="/api", tags=["tools"])

SessionDep = Depends(get_session)


@router.get("/tools", response_model=list[ToolRead])
async def list_tools(session: AsyncSession = SessionDep):
    res = await session.execute(select(ToolRegistry).where(ToolRegistry.is_active.is_(True)))
    return res.scalars().all()
