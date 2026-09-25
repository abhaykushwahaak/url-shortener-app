"""Analytics routes - summary, timeline and the raw click log."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import Pagination, pagination_params
from app.core.database import get_db
from app.models.user import User
from app.schemas.analytics import AnalyticsSummary, TimelineResponse
from app.services import analytics as analytics_service
from app.services.auth import get_current_user

router = APIRouter(prefix="/urls", tags=["Analytics"])
# Account-wide analytics live under /api/analytics/* so they cannot collide with
# the /api/urls/{url_id}/... path space.
account_router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get(
    "/{url_id}/analytics",
    response_model=AnalyticsSummary,
    summary="Analytics summary for a URL",
    description=(
        "Totals (all-time, today, this week), unique visitors and breakdowns by "
        "device, browser, referrer and country. Every count is computed in a "
        "single grouped query against the `clicks` table."
    ),
)
def analytics_summary(
    url_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnalyticsSummary:
    return analytics_service.get_summary(db, current_user, url_id)


@router.get(
    "/{url_id}/analytics/timeline",
    response_model=TimelineResponse,
    summary="Clicks per day for a URL",
    description=(
        "Returns one point per day for the requested window, including days with "
        "zero clicks so charts render a continuous axis. All buckets are UTC."
    ),
)
def analytics_timeline(
    url_id: uuid.UUID,
    days: int = Query(30, ge=1, le=365, description="Size of the window in days"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TimelineResponse:
    return analytics_service.get_timeline(db, current_user, url_id, days)


@router.get(
    "/{url_id}/analytics/clicks",
    summary="Raw click log for a URL",
    description="Newest-first click rows with device, browser, referrer and IP.",
)
def analytics_clicks(
    url_id: uuid.UUID,
    pagination: Pagination = Depends(pagination_params),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    clicks, total = analytics_service.get_click_history(
        db, current_user, url_id, page=pagination.page, limit=pagination.limit
    )
    return {
        "items": [
            {
                "id": click.id,
                "clicked_at": click.clicked_at.isoformat() if click.clicked_at else None,
                "device": click.device,
                "browser": click.browser,
                "referrer": click.referrer,
                "ip_address": click.ip_address,
                "country": click.country,
            }
            for click in clicks
        ],
        "page": pagination.page,
        "limit": pagination.limit,
        "total": total,
    }


# --------------------------------------------------------------------------- #
# Account-wide analytics (no url_id) - used by the dashboard
# --------------------------------------------------------------------------- #
@account_router.get(
    "/overview",
    response_model=TimelineResponse,
    summary="Account-wide clicks per day",
    description="Clicks per day across every URL the user owns.",
)
def account_timeline(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TimelineResponse:
    return analytics_service.user_timeline(db, current_user, days)