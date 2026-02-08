"""
Celery tasks for pipeline processing.

Main task: pipeline.process_task — runs TaskProcessor in a synchronous
Celery worker context using asyncio.run().
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_sync_db_url() -> str:
    """Get synchronous database URL for Celery worker."""
    from app.settings import get_settings
    settings = get_settings()
    url = settings.database_url
    # Convert async URL to sync for worker
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "")
    return url


def _get_async_db_url() -> str:
    """Get async database URL."""
    from app.settings import get_settings
    return get_settings().async_database_url


async def _process_task_async(task_id: int) -> dict:
    """Run TaskProcessor.process_task in an async context with a fresh session."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.services.task_processor import TaskProcessor
    from app.models import PublishTask, StepResult

    engine = create_async_engine(_get_async_db_url(), echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            # Verify task exists and mark as processing
            task = await session.get(PublishTask, task_id)
            if not task:
                return {"error": f"Task {task_id} not found"}

            if task.status not in ("queued", "processing"):
                return {"error": f"Task {task_id} has status '{task.status}', expected queued/processing"}

            task.status = "processing"
            task.updated_at = datetime.now(timezone.utc)
            session.add(task)
            await session.commit()

            # Run the actual processing
            processor = TaskProcessor(session)
            result = await processor.process_task(task_id)

            logger.info(f"[worker] Task {task_id} finished: {result.get('status', result.get('error', '?'))}")
            return result

    except Exception as e:
        logger.error(f"[worker] Task {task_id} failed: {e}")
        # Try to mark task as error
        try:
            async with session_factory() as session:
                task = await session.get(PublishTask, task_id)
                if task:
                    task.status = "error"
                    task.publish_error = f"worker error: {str(e)[:500]}"
                    session.add(task)

                    session.add(StepResult(
                        task_id=task_id,
                        step_index=9997,
                        tool_id="WORKER",
                        step_name="Celery worker error",
                        status="error",
                        error_message=str(e)[:1000],
                        started_at=datetime.now(timezone.utc),
                        completed_at=datetime.now(timezone.utc),
                    ))
                    await session.commit()
        except Exception as e2:
            logger.error(f"[worker] Failed to mark task {task_id} as error: {e2}")
        raise
    finally:
        await engine.dispose()


@celery_app.task(
    bind=True,
    name="pipeline.process_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
    queue="pipeline",
)
def process_task(self, task_id: int) -> dict:
    """Celery task: process a PublishTask through the pipeline.

    Runs the async TaskProcessor in a new event loop.
    """
    logger.info(f"[worker] Starting task {task_id} (celery_id={self.request.id}, attempt={self.request.retries + 1})")
    try:
        result = asyncio.run(_process_task_async(task_id))
        return result
    except Exception as e:
        logger.error(f"[worker] Task {task_id} error (attempt {self.request.retries + 1}): {e}")
        raise
