"""Celery application. The worker process imports this via `celery -A app.core.celery_app`."""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "urlshortener",
    broker=settings.broker_url,
    backend=settings.result_backend,
    include=["app.tasks.analytics"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    task_eager_propagates=True,
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)