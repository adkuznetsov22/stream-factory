from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Preset, PresetAsset, PresetStep, ToolRegistry
from app.schemas import (
    PresetAssetCreate,
    PresetAssetRead,
    PresetCreate,
    PresetRead,
    PresetStepCreate,
    PresetStepRead,
    PresetStepUpdate,
    PresetUpdate,
)

router = APIRouter(prefix="/api", tags=["presets"])
SessionDep = Depends(get_session)


@router.get("/presets", response_model=list[PresetRead])
async def list_presets(session: AsyncSession = SessionDep):
    res = await session.execute(select(Preset))
    return res.scalars().all()


@router.post("/presets", response_model=PresetRead, status_code=status.HTTP_201_CREATED)
async def create_preset(data: PresetCreate, session: AsyncSession = SessionDep):
    preset = Preset(name=data.name, description=data.description, is_active=data.is_active if data.is_active is not None else True)
    session.add(preset)
    await session.commit()
    await session.refresh(preset)
    return preset


@router.get("/presets/{preset_id}", response_model=PresetRead)
async def get_preset(preset_id: int, session: AsyncSession = SessionDep):
    preset = await session.get(Preset, preset_id)
    if not preset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preset not found")
    return preset


@router.patch("/presets/{preset_id}", response_model=PresetRead)
async def update_preset(preset_id: int, data: PresetUpdate, session: AsyncSession = SessionDep):
    preset = await session.get(Preset, preset_id)
    if not preset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preset not found")
    for field in ["name", "description", "is_active"]:
        value = getattr(data, field)
        if value is not None:
            setattr(preset, field, value)
    session.add(preset)
    await session.commit()
    await session.refresh(preset)
    return preset


@router.get("/presets/{preset_id}/steps", response_model=list[PresetStepRead])
async def list_preset_steps(preset_id: int, session: AsyncSession = SessionDep):
    res = await session.execute(select(PresetStep).where(PresetStep.preset_id == preset_id).order_by(PresetStep.order_index))
    return res.scalars().all()


@router.post("/presets/{preset_id}/steps", response_model=PresetStepRead, status_code=status.HTTP_201_CREATED)
async def create_preset_step(preset_id: int, data: PresetStepCreate, session: AsyncSession = SessionDep):
    preset = await session.get(Preset, preset_id)
    if not preset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preset not found")
    tool_name = data.name
    if not tool_name:
        tool = await session.get(ToolRegistry, data.tool_id)
        tool_name = tool.name if tool else data.tool_id
    step = PresetStep(
        preset_id=preset_id,
        tool_id=data.tool_id,
        name=tool_name or data.tool_id,
        enabled=data.enabled,
        order_index=data.order_index,
        params=data.params or {},
    )
    session.add(step)
    await session.commit()
    await session.refresh(step)
    return step


@router.patch("/preset-steps/{step_id}", response_model=PresetStepRead)
async def update_preset_step(step_id: int, data: PresetStepUpdate, session: AsyncSession = SessionDep):
    step = await session.get(PresetStep, step_id)
    if not step:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preset step not found")
    if data.enabled is not None:
        step.enabled = data.enabled
    if data.order_index is not None:
        step.order_index = data.order_index
    if data.params is not None:
        step.params = data.params
    if data.name is not None:
        step.name = data.name
    session.add(step)
    await session.commit()
    await session.refresh(step)
    return step


@router.delete("/preset-steps/{step_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preset_step(step_id: int, session: AsyncSession = SessionDep):
    step = await session.get(PresetStep, step_id)
    if not step:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preset step not found")
    await session.delete(step)
    await session.commit()
    return {}


@router.get("/presets/{preset_id}/assets", response_model=list[PresetAssetRead])
async def list_preset_assets(preset_id: int, session: AsyncSession = SessionDep):
    res = await session.execute(select(PresetAsset).where(PresetAsset.preset_id == preset_id))
    return res.scalars().all()


@router.post("/presets/{preset_id}/assets", response_model=PresetAssetRead, status_code=status.HTTP_201_CREATED)
async def create_preset_asset(preset_id: int, data: PresetAssetCreate, session: AsyncSession = SessionDep):
    preset = await session.get(Preset, preset_id)
    if not preset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preset not found")
    asset = PresetAsset(
        preset_id=preset_id,
        asset_type=data.asset_type,
        asset_id=data.asset_id,
        params=data.params or {},
    )
    session.add(asset)
    await session.commit()
    await session.refresh(asset)
    return asset


@router.delete("/preset-assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preset_asset(asset_id: int, session: AsyncSession = SessionDep):
    asset = await session.get(PresetAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preset asset not found")
    await session.delete(asset)
    await session.commit()
    return {}
