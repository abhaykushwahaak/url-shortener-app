"""The redirect endpoint - the hot path of the whole service.

Order of operations, deliberately chosen so user-visible latency stays low:

  1. Look the code up in Redis (one GET, no database round-trip).
  2. On a miss, read PostgreSQL once and populate the cache.
  3. Enqueue the click-recording Celery task (a few milliseconds).
  4. Return the redirect.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip
from app.core.cache import cache_url, get_cached_url
from app.core.database import get_db
from app.models.url import URL
from app.services.url import cache_payload, get_active_url_by_code
from app.tasks.analytics import enqueue_click

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Redirect"])

REDIRECT_STATUS = status.HTTP_307_TEMPORARY_REDIRECT


@router.get(
    "/{short_code}",
    status_code=REDIRECT_STATUS,
    summary="Follow a short link",
    description=(
        "Resolves a short code and redirects to the destination. Served from Redis "
        "when possible. Returns **404** for an unknown code and **410** when the "
        "link has been disabled or has expired. Click metadata is recorded "
        "asynchronously, so this endpoint never waits on the database write."
    ),
    responses={
        307: {"description": "Redirect to the destination URL"},
        404: {"description": "Unknown short code"},
        410: {"description": "Link is disabled or expired"},
    },
)
def redirect_to_original(
    short_code: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    payload = get_cached_url(short_code)

    if payload is None:
        url = get_active_url_by_code(db, short_code)
        if url is None:
            _raise_unavailable(db, short_code)
        payload = cache_payload(url)
        cache_url(short_code, payload)

    enqueue_click(
        url_id=payload["url_id"],
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        referrer=request.headers.get("referer"),
    )

    # 307 preserves the HTTP method, which matters if a short link is used in a
    # non-GET context; browsers treat it exactly like a 302 for normal navigation.
    return RedirectResponse(url=payload["original_url"], status_code=REDIRECT_STATUS)


def _raise_unavailable(db: Session, short_code: str) -> None:
    """Distinguish 'never existed' from 'exists but is switched off'.

    Expired and disabled links are 410 Gone rather than 404: the code exists, it
    is just no longer servable. Note that the disabled/expired case is *not*
    cached - caching it would keep a re-enabled link failing until the TTL ran out.
    """
    exists = db.scalar(select(URL.id).where(URL.short_code == short_code)) is not None
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Short link not found"
        )

    url = db.scalar(select(URL).where(URL.short_code == short_code))
    detail = "This link has expired" if url.is_expired else "This link has been disabled"
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=detail)