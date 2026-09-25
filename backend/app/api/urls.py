"""URL management routes. Handlers stay thin - the logic lives in app.services.url."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import Pagination, pagination_params
from app.core.database import get_db
from app.models.user import User
from app.schemas.analytics import TopURL
from app.schemas.url import PaginatedURLs, URLCreate, URLRead, URLStats, URLUpdate
from app.services import url as url_service
from app.services.auth import get_current_user

router = APIRouter(prefix="/urls", tags=["URLs"])


@router.post(
    "",
    response_model=URLRead,
    status_code=status.HTTP_201_CREATED,
    summary="Shorten a URL",
    description=(
        "Creates a short link. Supply `custom_alias` to choose your own code "
        "(3-32 chars: letters, numbers, hyphens, underscores), otherwise a random "
        "6-character code is generated. Returns **409** when the alias is taken."
    ),
)
def create_url(
    payload: URLCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> URLRead:
    return url_service.create_url(db, current_user, payload)


@router.get(
    "",
    response_model=PaginatedURLs,
    summary="List your URLs",
    description=(
        "Paginated list of the URLs you own, newest first. Supports filtering by "
        "`is_active` and a `search` term matched against the original URL and code."
    ),
)
def list_urls(
    pagination: Pagination = Depends(pagination_params),
    is_active: bool | None = Query(None, description="Filter by enabled/disabled state"),
    search: str | None = Query(None, max_length=200, description="Substring search"),
    sort: str = Query("-created_at", pattern="^-?created_at$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedURLs:
    items, total = url_service.list_urls(
        db,
        current_user,
        page=pagination.page,
        limit=pagination.limit,
        is_active=is_active,
        search=search,
        sort=sort,
    )
    return PaginatedURLs(
        items=items, page=pagination.page, limit=pagination.limit, total=total
    )


@router.get(
    "/stats",
    response_model=URLStats,
    summary="Dashboard totals",
    description="Total / active / expired URL counts and total clicks for the signed-in user.",
)
def url_stats(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> URLStats:
    return URLStats(**url_service.user_overview(db, current_user))


@router.get(
    "/top",
    response_model=list[TopURL],
    summary="Most-clicked URLs",
    description="Top N URLs by click count, used by the dashboard bar chart.",
)
def top_urls(
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TopURL]:
    return [TopURL(**row) for row in url_service.top_urls(db, current_user, limit)]


@router.get(
    "/{url_id}",
    response_model=URLRead,
    summary="Get one URL",
    description="Returns a single URL you own, including its click counters. **404** otherwise.",
)
def get_url(
    url_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> URLRead:
    return url_service.get_url_with_counts(db, current_user, url_id)


@router.patch(
    "/{url_id}",
    response_model=URLRead,
    summary="Update a URL",
    description=(
        "Partially updates a URL: destination, alias, expiration or enabled state. "
        "Only the fields you send are changed. Changing the alias changes the short "
        "code and invalidates the Redis cache entry for the old one."
    ),
)
def update_url(
    url_id: uuid.UUID,
    payload: URLUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> URLRead:
    return url_service.update_url(db, current_user, url_id, payload)


@router.delete(
    "/{url_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a URL",
    description="Deletes a URL and all of its click history. The cache entry is evicted.",
)
def delete_url(
    url_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    url_service.delete_url(db, current_user, url_id)