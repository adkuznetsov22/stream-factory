"""
Scheduler API Routes

Endpoints for managing the automatic task scheduler.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.services.scheduler import scheduler_service

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


class SchedulerStatus(BaseModel):
    running: bool
    jobs_count: int
    jobs: list[dict]


class ProjectScheduleRequest(BaseModel):
    interval_minutes: int = 60
    tasks_per_run: int = 5


@router.get("/status", response_model=SchedulerStatus)
async def get_scheduler_status():
    """Get scheduler status and list of jobs."""
    jobs = scheduler_service.get_jobs()
    return SchedulerStatus(
        running=scheduler_service.is_running(),
        jobs_count=len(jobs),
        jobs=jobs,
    )


@router.post("/start", response_model=dict)
async def start_scheduler():
    """Start the scheduler."""
    if scheduler_service.is_running():
        return {"status": "already_running"}
    
    scheduler_service.start()
    return {"status": "started", "jobs": scheduler_service.get_jobs()}


@router.post("/stop", response_model=dict)
async def stop_scheduler():
    """Stop the scheduler."""
    if not scheduler_service.is_running():
        return {"status": "already_stopped"}
    
    scheduler_service.stop()
    return {"status": "stopped"}


@router.post("/jobs/{job_id}/run", response_model=dict)
async def run_job_now(job_id: str):
    """Run a specific job immediately."""
    result = await scheduler_service.run_now(job_id)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@router.post("/projects/{project_id}/schedule", response_model=dict)
async def schedule_project(project_id: int, request: ProjectScheduleRequest):
    """
    Add custom schedule for a project.
    
    This creates a dedicated job that generates tasks at the specified interval.
    """
    scheduler_service.add_project_job(
        project_id,
        interval_minutes=request.interval_minutes,
        tasks_per_run=request.tasks_per_run,
    )
    return {
        "ok": True,
        "project_id": project_id,
        "interval_minutes": request.interval_minutes,
        "tasks_per_run": request.tasks_per_run,
    }


@router.delete("/projects/{project_id}/schedule", response_model=dict)
async def unschedule_project(project_id: int):
    """Remove custom schedule for a project."""
    scheduler_service.remove_project_job(project_id)
    return {"ok": True, "project_id": project_id}
