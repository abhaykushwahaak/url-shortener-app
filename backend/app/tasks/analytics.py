"""Background click recording.

The redirect handler must stay fast, so it only enqueues this task and returns.
The worker owns the database session and does the insert.
"""

import logging
import uuid

from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.services.analytics import record_click

logger = logging.getLogger(__name__)


@celery_app.task(
    name="analytics.record_click",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def record_click_task(
    self,
    url_id: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
    referrer: str | None = None,
    country: str | None = None,
) -> int | None:
    """Persist one click. Returns the new click id."""
    db = SessionLocal()
    try:
        click = record_click(
            db,
            url_id=uuid.UUID(url_id),
            ip_address=ip_address,
            user_agent=user_agent,
            referrer=referrer,
            country=country,
        )
        logger.info("Recorded click %s for url %s", click.id, url_id)
        return click.id
    except Exception as exc:  # noqa: BLE001 - report and let Celery retry
        logger.exception("Failed to record click for url %s", url_id)
        db.rollback()
        raise self.retry(exc=exc)
    finally:
        db.close()


def enqueue_click(
    url_id: str,
    ip_address: str | None,
    user_agent: str | None,
    referrer: str | None,
    country: str | None = None,
) -> None:
    """Fire-and-forget wrapper.

    If the broker is unreachable the redirect still succeeds - analytics is
    best-effort and must never break the user-facing redirect.
    """
    try:
        record_click_task.delay(
            url_id=url_id,
            ip_address=ip_address,
            user_agent=user_agent,
            referrer=referrer,
            country=country,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Could not enqueue click task for url %s", url_id)