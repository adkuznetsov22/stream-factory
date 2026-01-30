"""
Moderation API routes for pipeline step results.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .db import get_session
from .models import StepResult, PublishTask, Project
from .schemas import (
    StepResultRead,
    StepApproveRequest,
    StepRejectRequest,
    StepRetryRequest,
    ModerationQueueItem,
    TaskModerationModeUpdate,
)

router = APIRouter(prefix="/api/moderation", tags=["moderation"])


@router.get("/queue")
async def get_moderation_queue(
    session: AsyncSession = Depends(get_session),
    status: Optional[str] = Query(None, description="Filter by moderation_status"),
    project_id: Optional[int] = Query(None, description="Filter by project"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Get queue of step results pending moderation."""
    query = (
        select(StepResult, PublishTask, Project)
        .join(PublishTask, StepResult.task_id == PublishTask.id)
        .join(Project, PublishTask.project_id == Project.id)
        .where(StepResult.moderation_status.in_(["pending", "needs_rework"]))
    )
    
    if status:
        query = query.where(StepResult.moderation_status == status)
    if project_id:
        query = query.where(PublishTask.project_id == project_id)
    
    query = query.order_by(StepResult.created_at.asc()).offset(offset).limit(limit)
    
    result = await session.execute(query)
    rows = result.all()
    
    items = []
    for step_result, task, project in rows:
        items.append({
            "task_id": task.id,
            "step_index": step_result.step_index,
            "step_result_id": step_result.id,
            "tool_id": step_result.tool_id,
            "step_name": step_result.step_name,
            "project_id": project.id,
            "project_name": project.name,
            "moderation_status": step_result.moderation_status,
            "status": step_result.status,
            "created_at": step_result.created_at.isoformat() if step_result.created_at else None,
        })
    
    # Get total count
    count_query = (
        select(func.count(StepResult.id))
        .join(PublishTask, StepResult.task_id == PublishTask.id)
        .where(StepResult.moderation_status.in_(["pending", "needs_rework"]))
    )
    if status:
        count_query = count_query.where(StepResult.moderation_status == status)
    if project_id:
        count_query = count_query.where(PublishTask.project_id == project_id)
    
    total = await session.scalar(count_query)
    
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/stats")
async def get_moderation_stats(
    session: AsyncSession = Depends(get_session),
    project_id: Optional[int] = Query(None),
):
    """Get moderation statistics."""
    base_query = select(StepResult.moderation_status, func.count(StepResult.id))
    
    if project_id:
        base_query = (
            base_query
            .join(PublishTask, StepResult.task_id == PublishTask.id)
            .where(PublishTask.project_id == project_id)
        )
    
    query = base_query.group_by(StepResult.moderation_status)
    result = await session.execute(query)
    
    stats = {row[0]: row[1] for row in result.all()}
    
    return {
        "pending": stats.get("pending", 0),
        "approved": stats.get("approved", 0),
        "rejected": stats.get("rejected", 0),
        "auto_approved": stats.get("auto_approved", 0),
        "needs_rework": stats.get("needs_rework", 0),
        "total": sum(stats.values()),
    }


# ============ Task-level endpoints ============

@router.get("/tasks/{task_id}/steps")
async def get_task_steps(
    task_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get all step results for a task."""
    query = (
        select(StepResult)
        .where(StepResult.task_id == task_id)
        .order_by(StepResult.step_index, StepResult.version.desc())
    )
    result = await session.execute(query)
    steps = result.scalars().all()
    
    # Group by step_index, take latest version
    step_map = {}
    for step in steps:
        if step.step_index not in step_map:
            step_map[step.step_index] = step
    
    return [StepResultRead.model_validate(s) for s in step_map.values()]


@router.get("/tasks/{task_id}/steps/{step_index}")
async def get_step_result(
    task_id: int,
    step_index: int,
    version: Optional[int] = Query(None, description="Specific version, or latest"),
    session: AsyncSession = Depends(get_session),
):
    """Get specific step result."""
    query = select(StepResult).where(
        and_(StepResult.task_id == task_id, StepResult.step_index == step_index)
    )
    
    if version:
        query = query.where(StepResult.version == version)
    else:
        query = query.order_by(StepResult.version.desc())
    
    result = await session.execute(query)
    step = result.scalars().first()
    
    if not step:
        raise HTTPException(status_code=404, detail="Step result not found")
    
    return StepResultRead.model_validate(step)


@router.post("/tasks/{task_id}/steps/{step_index}/approve")
async def approve_step(
    task_id: int,
    step_index: int,
    request: StepApproveRequest,
    session: AsyncSession = Depends(get_session),
):
    """Approve a step result."""
    query = (
        select(StepResult)
        .where(and_(StepResult.task_id == task_id, StepResult.step_index == step_index))
        .order_by(StepResult.version.desc())
    )
    result = await session.execute(query)
    step = result.scalars().first()
    
    if not step:
        raise HTTPException(status_code=404, detail="Step result not found")
    
    step.moderation_status = "approved"
    step.moderation_comment = request.comment
    step.moderated_at = datetime.utcnow()
    step.moderated_by = "user"  # TODO: get from auth
    
    await session.commit()
    
    # Check if we should continue pipeline
    await _maybe_continue_pipeline(session, task_id)
    
    return {"status": "approved", "step_index": step_index}


@router.post("/tasks/{task_id}/steps/{step_index}/reject")
async def reject_step(
    task_id: int,
    step_index: int,
    request: StepRejectRequest,
    session: AsyncSession = Depends(get_session),
):
    """Reject a step result."""
    query = (
        select(StepResult)
        .where(and_(StepResult.task_id == task_id, StepResult.step_index == step_index))
        .order_by(StepResult.version.desc())
    )
    result = await session.execute(query)
    step = result.scalars().first()
    
    if not step:
        raise HTTPException(status_code=404, detail="Step result not found")
    
    step.moderation_status = "rejected"
    step.moderation_comment = request.comment
    step.moderated_at = datetime.utcnow()
    step.moderated_by = "user"
    
    # Update task status
    task_query = select(PublishTask).where(PublishTask.id == task_id)
    task_result = await session.execute(task_query)
    task = task_result.scalars().first()
    if task:
        task.pipeline_status = "rejected"
    
    await session.commit()
    
    return {"status": "rejected", "step_index": step_index}


@router.post("/tasks/{task_id}/steps/{step_index}/retry")
async def retry_step(
    task_id: int,
    step_index: int,
    request: StepRetryRequest,
    session: AsyncSession = Depends(get_session),
):
    """Retry a step with optionally modified parameters."""
    query = (
        select(StepResult)
        .where(and_(StepResult.task_id == task_id, StepResult.step_index == step_index))
        .order_by(StepResult.version.desc())
    )
    result = await session.execute(query)
    old_step = result.scalars().first()
    
    if not old_step:
        raise HTTPException(status_code=404, detail="Step result not found")
    
    if not old_step.can_retry:
        raise HTTPException(status_code=400, detail="This step cannot be retried")
    
    # Create new version
    new_step = StepResult(
        task_id=task_id,
        step_index=step_index,
        tool_id=old_step.tool_id,
        step_name=old_step.step_name,
        status="pending",
        input_params=request.new_params if request.new_params else old_step.input_params,
        moderation_status="pending",
        can_retry=old_step.can_retry,
        retry_count=old_step.retry_count + 1,
        version=old_step.version + 1,
        previous_version_id=old_step.id,
    )
    session.add(new_step)
    
    # Update task to re-run from this step
    task_query = select(PublishTask).where(PublishTask.id == task_id)
    task_result = await session.execute(task_query)
    task = task_result.scalars().first()
    if task:
        task.current_step_index = step_index
        task.pipeline_status = "pending_retry"
    
    await session.commit()
    
    return {
        "status": "retry_scheduled",
        "step_index": step_index,
        "new_version": new_step.version,
    }


@router.patch("/tasks/{task_id}/steps/{step_index}/params")
async def update_step_params(
    task_id: int,
    step_index: int,
    params: dict,
    session: AsyncSession = Depends(get_session),
):
    """Update parameters for a step (creates new pending version)."""
    query = (
        select(StepResult)
        .where(and_(StepResult.task_id == task_id, StepResult.step_index == step_index))
        .order_by(StepResult.version.desc())
    )
    result = await session.execute(query)
    old_step = result.scalars().first()
    
    if not old_step:
        raise HTTPException(status_code=404, detail="Step result not found")
    
    # Merge params
    merged_params = {**(old_step.input_params or {}), **params}
    
    new_step = StepResult(
        task_id=task_id,
        step_index=step_index,
        tool_id=old_step.tool_id,
        step_name=old_step.step_name,
        status="pending",
        input_params=merged_params,
        moderation_status="pending",
        can_retry=old_step.can_retry,
        retry_count=old_step.retry_count,
        version=old_step.version + 1,
        previous_version_id=old_step.id,
    )
    session.add(new_step)
    await session.commit()
    
    return {"status": "params_updated", "new_version": new_step.version}


@router.patch("/tasks/{task_id}/steps/{step_index}/edit")
async def edit_step_output(
    task_id: int,
    step_index: int,
    output_data: dict,
    session: AsyncSession = Depends(get_session),
):
    """
    Edit text outputs of a step (e.g., transcript_text, caption_text, description).
    This modifies the output_data of the step without creating a new version.
    """
    query = (
        select(StepResult)
        .where(and_(StepResult.task_id == task_id, StepResult.step_index == step_index))
        .order_by(StepResult.version.desc())
    )
    result = await session.execute(query)
    step = result.scalars().first()
    
    if not step:
        raise HTTPException(status_code=404, detail="Step result not found")
    
    # Merge with existing output_data
    current_output = step.output_data or {}
    updated_output = {**current_output, **output_data}
    step.output_data = updated_output
    step.updated_at = datetime.utcnow()
    
    await session.commit()
    
    return {
        "status": "updated",
        "step_index": step_index,
        "output_data": updated_output,
    }


@router.patch("/tasks/{task_id}/moderation-mode")
async def update_task_moderation_mode(
    task_id: int,
    request: TaskModerationModeUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update moderation mode for a task."""
    if request.moderation_mode not in ("auto", "manual", "step_by_step"):
        raise HTTPException(status_code=400, detail="Invalid moderation mode")
    
    query = select(PublishTask).where(PublishTask.id == task_id)
    result = await session.execute(query)
    task = result.scalars().first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task.moderation_mode = request.moderation_mode
    await session.commit()
    
    return {"task_id": task_id, "moderation_mode": request.moderation_mode}


@router.post("/tasks/{task_id}/resume")
async def resume_task_pipeline(
    task_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Resume a paused pipeline."""
    query = select(PublishTask).where(PublishTask.id == task_id)
    result = await session.execute(query)
    task = result.scalars().first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.pipeline_status not in ("paused_for_review", "pending_retry"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resume task with status: {task.pipeline_status}"
        )
    
    task.pipeline_status = "running"
    await session.commit()
    
    # TODO: Trigger actual pipeline execution
    
    return {"task_id": task_id, "pipeline_status": "running"}


# ============ Helper functions ============

async def _maybe_continue_pipeline(session: AsyncSession, task_id: int):
    """Check if pipeline should continue after step approval."""
    task_query = select(PublishTask).where(PublishTask.id == task_id)
    task_result = await session.execute(task_query)
    task = task_result.scalars().first()
    
    if not task or task.moderation_mode != "step_by_step":
        return
    
    # Check if current step is approved
    step_query = (
        select(StepResult)
        .where(and_(
            StepResult.task_id == task_id,
            StepResult.step_index == task.current_step_index
        ))
        .order_by(StepResult.version.desc())
    )
    step_result = await session.execute(step_query)
    current_step = step_result.scalars().first()
    
    if current_step and current_step.moderation_status == "approved":
        # Move to next step
        if task.current_step_index < task.total_steps - 1:
            task.current_step_index += 1
            task.pipeline_status = "running"
        else:
            task.pipeline_status = "completed"
        await session.commit()
