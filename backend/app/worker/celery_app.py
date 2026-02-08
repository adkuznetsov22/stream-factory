"""
Celery application for pipeline task processing.

Broker/backend: Redis (REDIS_URL env).
Default queue: pipeline.
"""
from celery import Celery

from app.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "stream_factory",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=6 * 3600,       # 6 hours hard limit
    task_soft_time_limit=5 * 3600,   # 5 hours soft limit
    task_default_queue="pipeline",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # visibility_timeout MUST be > task_time_limit to prevent redelivery
    # of long-running tasks. 7h = 25200s > 6h = 21600s.
    broker_transport_options={"visibility_timeout": 7 * 3600},  # 25200s
)

# Auto-discover tasks in app.worker.tasks
celery_app.autodiscover_tasks(["app.worker"])
