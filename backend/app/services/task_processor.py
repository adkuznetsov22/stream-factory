"""
Task Processor Service

Processes PublishTasks using PipelineExecutor:
- Downloads source video
- Executes preset steps
- Creates thumbnails and previews
- Updates task status and artifacts
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import ExportProfile, Project, Preset, PublishTask
from app.services.pipeline_executor import PipelineExecutor, StepContext


TASKS_DIR = Path(os.getenv("DATA_DIR", "/data")) / "tasks"


class TaskProcessor:
    """Processes publish tasks through the pipeline."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def process_task(self, task_id: int) -> dict:
        """
        Process a single task.
        
        Args:
            task_id: ID of the task to process
        
        Returns:
            Dict with processing results
        """
        task = await self.session.get(PublishTask, task_id)
        if not task:
            return {"error": "Task not found", "task_id": task_id}
        
        if task.status not in {"queued", "error"}:
            return {"error": f"Task status is {task.status}, cannot process", "task_id": task_id}
        
        # Get project and preset
        project = await self.session.scalar(
            select(Project)
            .where(Project.id == task.project_id)
            .options(selectinload(Project.preset).selectinload(Preset.steps))
        )
        preset = project.preset if project else None
        
        # Setup task directory
        task_dir = TASKS_DIR / str(task.id)
        task_dir.mkdir(parents=True, exist_ok=True)
        log_path = task_dir / "process.log"
        
        def log_cb(msg: str):
            timestamp = datetime.now(timezone.utc).isoformat()
            with log_path.open("a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {msg}\n")
        
        # Update task status
        now = datetime.now(timezone.utc)
        task.preset_id = project.preset_id if project else None
        task.status = "processing"
        task.processing_started_at = now
        task.error_message = None
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        
        log_cb(f"Starting task processing (preset: {preset.name if preset else 'none'})")
        
        # Create context
        ctx = StepContext(
            task_id=task.id,
            task_dir=task_dir,
            log_cb=log_cb,
        )
        ctx.download_url = task.download_url
        ctx.permalink = task.permalink
        ctx.caption_text = task.caption_text or task.instructions
        
        # Populate GENERATE context from task artifacts
        if task.artifacts and isinstance(task.artifacts, dict) and task.artifacts.get("origin") == "GENERATE":
            ctx.candidate_meta = task.artifacts.get("candidate_meta", {})
            ctx.brief_data = task.artifacts.get("brief", {})
        
        # Populate project policy for QC enforcement
        if project and project.policy and isinstance(project.policy, dict):
            ctx.policy = project.policy
        
        # Populate publishing context for P01_PUBLISH
        ctx.session = self.session
        ctx.publish_task = task
        ctx.platform = task.platform
        ctx.destination_account_id = task.destination_social_account_id
        
        # Populate export profile for encoding steps
        if project and project.export_profile_id:
            ep = await self.session.get(ExportProfile, project.export_profile_id)
            if ep:
                ctx.export_profile = {
                    "name": ep.name,
                    "target_platform": ep.target_platform,
                    "max_duration_sec": ep.max_duration_sec,
                    "recommended_duration_sec": ep.recommended_duration_sec,
                    "width": ep.width,
                    "height": ep.height,
                    "fps": ep.fps,
                    "codec": ep.codec,
                    "video_bitrate": ep.video_bitrate,
                    "audio_bitrate": ep.audio_bitrate,
                    "audio_sample_rate": ep.audio_sample_rate,
                    "safe_area": ep.safe_area or {},
                    "safe_area_mode": ep.safe_area_mode,
                    "extra": ep.extra or {},
                }
                log_cb(f"Export profile: {ep.name} ({ep.target_platform})")
        
        # Build step list
        steps = self._build_steps(preset, task)
        
        # Execute pipeline
        executor = PipelineExecutor(ctx)
        
        try:
            result = await executor.execute_steps(steps)
            
            # Ensure final.mp4 exists after successful pipeline
            if result["success"] and not ctx.final_path.exists():
                # Copy from current_video or ready.mp4
                src = ctx.current_video
                if not src or not src.exists():
                    src = ctx.ready_path if ctx.ready_path.exists() else None
                if not src or not src.exists():
                    src = ctx.raw_path if ctx.raw_path.exists() else None
                if src and src.exists():
                    import shutil
                    shutil.copy2(src, ctx.final_path)
                    log_cb(f"[ensure_final] Copied {src.name} → final.mp4")
            
            # Build artifacts
            artifacts = {
                "raw_video_path": str(ctx.raw_path) if ctx.raw_path.exists() else None,
                "ready_video_path": str(ctx.ready_path) if ctx.ready_path.exists() else None,
                "final_video_path": str(ctx.final_path) if ctx.final_path.exists() else None,
                "thumbnail_path": str(ctx.thumb_path) if ctx.thumb_path.exists() else None,
                "preview_path": str(ctx.preview_path) if ctx.preview_path.exists() else None,
                "probe_path": str(ctx.probe_path) if ctx.probe_path.exists() else None,
                "captions_path": str(ctx.captions_path) if ctx.captions_path.exists() else None,
                "logs_path": str(log_path),
                "probe_meta": ctx.probe_data,
            }
            
            if result["success"]:
                task.status = "ready_for_review"
                log_cb(f"Task completed successfully ({result['steps_executed']} steps)")
            else:
                task.status = "error"
                task.error_message = result.get("error", "Unknown error")
                log_cb(f"Task failed: {task.error_message}")
            
            task.dag_debug = executor.get_debug_info()
            task.artifacts = artifacts
            task.processing_finished_at = datetime.now(timezone.utc)
            
        except Exception as e:
            log_cb(f"Fatal error: {e}")
            task.status = "error"
            task.error_message = str(e)
            task.processing_finished_at = datetime.now(timezone.utc)
            task.dag_debug = executor.get_debug_info()
            result = {"success": False, "error": str(e)}
        
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        
        return {
            "task_id": task.id,
            "status": task.status,
            "success": result.get("success", False),
            "steps_executed": result.get("steps_executed", 0),
            "error": result.get("error"),
        }
    
    def _build_steps(self, preset: Preset | None, task: PublishTask) -> list[dict]:
        """Build step list from preset or use defaults."""
        steps = []
        
        # Always start with download and probe
        steps.append({
            "id": "auto_download",
            "tool_id": "T01_DOWNLOAD",
            "name": "Download video",
            "enabled": True,
            "params": {},
        })
        steps.append({
            "id": "auto_probe",
            "tool_id": "T02_PROBE",
            "name": "Probe metadata",
            "enabled": True,
            "params": {},
        })
        
        # Add preset steps
        if preset and preset.steps:
            sorted_steps = sorted(preset.steps, key=lambda s: s.order_index)
            for step in sorted_steps:
                steps.append({
                    "id": step.id,
                    "tool_id": step.tool_id,
                    "name": step.name,
                    "enabled": step.enabled,
                    "params": step.params or {},
                })
        else:
            # Default steps if no preset
            steps.append({
                "id": "default_crop",
                "tool_id": "T04_CROP_RESIZE",
                "name": "Crop to 9:16",
                "enabled": True,
                "params": {"width": 1080, "height": 1920},
            })
        
        # Always add thumbnail at the end
        steps.append({
            "id": "auto_thumb",
            "tool_id": "T05_THUMBNAIL",
            "name": "Create thumbnail",
            "enabled": True,
            "params": {"timestamp": "00:00:01"},
        })
        
        return steps
    
    async def process_batch(
        self,
        task_ids: list[int] | None = None,
        project_id: int | None = None,
        limit: int = 10,
    ) -> dict:
        """
        Process multiple tasks.
        
        Args:
            task_ids: Specific task IDs to process
            project_id: Process queued tasks for this project
            limit: Maximum tasks to process
        
        Returns:
            Dict with batch processing results
        """
        if task_ids:
            tasks = []
            for tid in task_ids[:limit]:
                task = await self.session.get(PublishTask, tid)
                if task and task.status in {"queued", "error"}:
                    tasks.append(task)
        else:
            query = select(PublishTask).where(
                PublishTask.status.in_(["queued", "error"])
            ).order_by(PublishTask.created_at.asc()).limit(limit)
            
            if project_id:
                query = query.where(PublishTask.project_id == project_id)
            
            result = await self.session.execute(query)
            tasks = result.scalars().all()
        
        results = []
        for task in tasks:
            result = await self.process_task(task.id)
            results.append(result)
        
        successful = sum(1 for r in results if r.get("success"))
        failed = len(results) - successful
        
        return {
            "processed": len(results),
            "successful": successful,
            "failed": failed,
            "results": results,
        }
