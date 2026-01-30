"""
Dashboard API routes for analytics and statistics.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_session
from .models import PublishTask, Project, SocialAccount, StepResult

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_dashboard_stats(
    session: AsyncSession = Depends(get_session),
    days: int = Query(7, ge=1, le=90),
):
    """Get general dashboard statistics."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    # Task counts by status
    task_status_query = (
        select(PublishTask.status, func.count(PublishTask.id))
        .where(PublishTask.created_at >= cutoff)
        .group_by(PublishTask.status)
    )
    result = await session.execute(task_status_query)
    task_by_status = dict(result.all())
    
    # Total tasks
    total_tasks = sum(task_by_status.values())
    
    # Project counts
    project_count_query = select(func.count(Project.id))
    total_projects = await session.scalar(project_count_query)
    
    active_projects_query = select(func.count(Project.id)).where(Project.status == "active")
    active_projects = await session.scalar(active_projects_query)
    
    # Account counts
    account_count_query = select(func.count(SocialAccount.id))
    total_accounts = await session.scalar(account_count_query)
    
    # Tasks per day
    tasks_per_day_query = (
        select(
            func.date_trunc('day', PublishTask.created_at).label('day'),
            func.count(PublishTask.id).label('count')
        )
        .where(PublishTask.created_at >= cutoff)
        .group_by(func.date_trunc('day', PublishTask.created_at))
        .order_by(func.date_trunc('day', PublishTask.created_at))
    )
    result = await session.execute(tasks_per_day_query)
    tasks_per_day = [{"date": row.day.isoformat() if row.day else None, "count": row.count} for row in result.all()]
    
    # Completion rate
    completed = task_by_status.get("done", 0) + task_by_status.get("published", 0)
    completion_rate = (completed / total_tasks * 100) if total_tasks > 0 else 0
    
    return {
        "period_days": days,
        "tasks": {
            "total": total_tasks,
            "by_status": task_by_status,
            "completion_rate": round(completion_rate, 1),
            "per_day": tasks_per_day,
        },
        "projects": {
            "total": total_projects,
            "active": active_projects,
        },
        "accounts": {
            "total": total_accounts,
        },
    }


@router.get("/projects")
async def get_projects_stats(
    session: AsyncSession = Depends(get_session),
    days: int = Query(7, ge=1, le=90),
):
    """Get per-project statistics."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    # Tasks per project
    query = (
        select(
            Project.id,
            Project.name,
            Project.status,
            func.count(PublishTask.id).label('task_count'),
            func.sum(case((PublishTask.status == 'done', 1), else_=0)).label('done_count'),
            func.sum(case((PublishTask.status == 'error', 1), else_=0)).label('error_count'),
        )
        .outerjoin(PublishTask, and_(
            PublishTask.project_id == Project.id,
            PublishTask.created_at >= cutoff
        ))
        .group_by(Project.id, Project.name, Project.status)
        .order_by(func.count(PublishTask.id).desc())
    )
    
    result = await session.execute(query)
    
    return [
        {
            "id": row.id,
            "name": row.name,
            "status": row.status,
            "task_count": row.task_count or 0,
            "done_count": row.done_count or 0,
            "error_count": row.error_count or 0,
            "success_rate": round((row.done_count or 0) / row.task_count * 100, 1) if row.task_count else 0,
        }
        for row in result.all()
    ]


@router.get("/recent-tasks")
async def get_recent_tasks(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(10, ge=1, le=50),
):
    """Get recent tasks with basic info."""
    query = (
        select(PublishTask, Project.name.label('project_name'))
        .join(Project, PublishTask.project_id == Project.id)
        .order_by(PublishTask.created_at.desc())
        .limit(limit)
    )
    
    result = await session.execute(query)
    
    return [
        {
            "id": row.PublishTask.id,
            "project_id": row.PublishTask.project_id,
            "project_name": row.project_name,
            "platform": row.PublishTask.platform,
            "status": row.PublishTask.status,
            "pipeline_status": row.PublishTask.pipeline_status,
            "created_at": row.PublishTask.created_at.isoformat() if row.PublishTask.created_at else None,
        }
        for row in result.all()
    ]


@router.get("/activity")
async def get_activity_feed(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(20, ge=1, le=100),
):
    """Get recent activity (task state changes, completions, errors)."""
    # Get recently updated tasks
    query = (
        select(PublishTask, Project.name.label('project_name'))
        .join(Project, PublishTask.project_id == Project.id)
        .order_by(PublishTask.updated_at.desc())
        .limit(limit)
    )
    
    result = await session.execute(query)
    
    activities = []
    for row in result.all():
        task = row.PublishTask
        activity_type = "update"
        if task.status == "done":
            activity_type = "completed"
        elif task.status == "error":
            activity_type = "error"
        elif task.pipeline_status == "running":
            activity_type = "processing"
        
        activities.append({
            "type": activity_type,
            "task_id": task.id,
            "project_name": row.project_name,
            "platform": task.platform,
            "status": task.status,
            "message": task.error_message if task.status == "error" else None,
            "timestamp": task.updated_at.isoformat() if task.updated_at else None,
        })
    
    return activities


@router.get("/pipeline-performance")
async def get_pipeline_performance(
    session: AsyncSession = Depends(get_session),
    days: int = Query(7, ge=1, le=30),
):
    """Get pipeline step performance statistics."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    query = (
        select(
            StepResult.tool_id,
            func.count(StepResult.id).label('total'),
            func.sum(case((StepResult.status == 'completed', 1), else_=0)).label('success'),
            func.sum(case((StepResult.status == 'failed', 1), else_=0)).label('failed'),
            func.avg(StepResult.duration_ms).label('avg_duration_ms'),
        )
        .where(StepResult.created_at >= cutoff)
        .group_by(StepResult.tool_id)
        .order_by(func.count(StepResult.id).desc())
    )
    
    result = await session.execute(query)
    
    return [
        {
            "tool_id": row.tool_id,
            "total": row.total,
            "success": row.success or 0,
            "failed": row.failed or 0,
            "success_rate": round((row.success or 0) / row.total * 100, 1) if row.total else 0,
            "avg_duration_ms": round(row.avg_duration_ms) if row.avg_duration_ms else None,
        }
        for row in result.all()
    ]
