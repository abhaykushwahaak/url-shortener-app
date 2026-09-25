"""Short-code generation and CRUD for shortened URLs."""

import secrets
import string
import uuid
from datetime import UTC, date, datetime, time, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.cache import cache_url, invalidate_url
from app.core.config import get_settings
from app.models.click import Click
from app.models.url import URL
from app.models.user import User
from app.schemas.url import URLCreate, URLRead, URLUpdate

settings = get_settings()

# Ambiguous characters (0/O, 1/l/I) are dropped so codes stay readable and easy
# to type from a screenshot.
ALPHABET = "".join(
    c for c in string.ascii_letters + string.digits if c not in "0O1lI"
)

MAX_CODE_ATTEMPTS = 8


def generate_short_code(length: int | None = None) -> str:
    """Cryptographically random code, base-59ish (secrets, not random)."""
    length = length or settings.SHORT_CODE_LENGTH
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def build_short_url(short_code: str) -> str:
    return f"{settings.BASE_URL.rstrip('/')}/{short_code}"


def _code_exists(db: Session, short_code: str) -> bool:
    return (
        db.scalar(select(URL.id).where(URL.short_code == short_code)) is not None
    )


def _alias_exists(db: Session, alias: str) -> bool:
    return db.scalar(select(URL.id).where(URL.custom_alias == alias)) is not None


def _unique_short_code(db: Session) -> str:
    """Draw codes until one is free.

    The existence check is only a fast path - two requests can still race, so the
    caller also catches IntegrityError on the unique constraint. With a 6-character
    code from a 59-symbol alphabet there are ~3.6e10 possibilities, so a single
    draw essentially always succeeds.
    """
    for _ in range(MAX_CODE_ATTEMPTS):
        code = generate_short_code()
        if not _code_exists(db, code):
            return code
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Could not allocate a unique short code, please retry",
    )


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #
def get_owned_url(db: Session, url_id: uuid.UUID, user: User) -> URL:
    """Fetch a URL that belongs to `user`, or raise 404.

    Returning 404 (rather than 403) for someone else's URL avoids leaking which
    ids exist.
    """
    url = db.scalar(select(URL).where(URL.id == url_id, URL.user_id == user.id))
    if url is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="URL not found")
    return url


def get_active_url_by_code(db: Session, short_code: str) -> URL | None:
    """Used by the redirect endpoint when Redis misses."""
    url = db.scalar(select(URL).where(URL.short_code == short_code))
    if url is None:
        return None
    if not url.is_active or url.is_expired:
        return None
    return url


def cache_payload(url: URL) -> dict:
    return {
        "url_id": str(url.id),
        "short_code": url.short_code,
        "original_url": url.original_url,
        "is_active": url.is_active,
        "expires_at": url.expires_at.isoformat() if url.expires_at else None,
    }


def _click_counts(
    db: Session, url_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, int, int]]:
    """One grouped query for every card on the URLs page.

    Returns {url_id: (total, today, this_week)}. Doing this in a single query
    instead of one query per URL is what keeps the list endpoint flat as the
    number of URLs grows (no N+1).
    """
    if not url_ids:
        return {}

    now = datetime.now(UTC)
    start_of_today = datetime.combine(now.date(), time.min, tzinfo=UTC)
    start_of_week = start_of_today - timedelta(days=now.weekday())

    rows = db.execute(
        select(
            Click.url_id,
            func.count(Click.id),
            func.count(Click.id).filter(Click.clicked_at >= start_of_today),
            func.count(Click.id).filter(Click.clicked_at >= start_of_week),
        )
        .where(Click.url_id.in_(url_ids))
        .group_by(Click.url_id)
    ).all()

    return {row[0]: (row[1], row[2], row[3]) for row in rows}


def serialize_url(url: URL, counts: tuple[int, int, int] | None = None) -> URLRead:
    total, today, week = counts or (0, 0, 0)
    return URLRead(
        id=url.id,
        original_url=url.original_url,
        short_code=url.short_code,
        custom_alias=url.custom_alias,
        short_url=build_short_url(url.short_code),
        is_active=url.is_active,
        is_expired=url.is_expired,
        expires_at=url.expires_at,
        created_at=url.created_at,
        updated_at=url.updated_at,
        total_clicks=total,
        clicks_today=today,
        clicks_this_week=week,
    )


def get_url_with_counts(db: Session, user: User, url_id: uuid.UUID) -> URLRead:
    """Single URL plus its click counters."""
    url = get_owned_url(db, url_id, user)
    return serialize_url(url, _click_counts(db, [url.id]).get(url.id))


def list_urls(
    db: Session,
    user: User,
    page: int = 1,
    limit: int = 10,
    is_active: bool | None = None,
    search: str | None = None,
    sort: str = "-created_at",
) -> tuple[list[URLRead], int]:
    """Paginated list, newest first by default."""
    filters = [URL.user_id == user.id]
    if is_active is not None:
        filters.append(URL.is_active.is_(is_active))
    if search:
        pattern = f"%{search}%"
        filters.append(
            URL.original_url.ilike(pattern) | URL.short_code.ilike(pattern)
        )

    total = db.scalar(select(func.count(URL.id)).where(*filters)) or 0

    order_column = {
        "created_at": URL.created_at.asc(),
        "-created_at": URL.created_at.desc(),
    }.get(sort, URL.created_at.desc())

    offset = (page - 1) * limit
    urls = list(
        db.scalars(select(URL).where(*filters).order_by(order_column).offset(offset).limit(limit))
    )

    counts = _click_counts(db, [u.id for u in urls])
    return [serialize_url(u, counts.get(u.id)) for u in urls], total


def user_overview(db: Session, user: User) -> dict:
    """Numbers for the dashboard cards."""
    now = datetime.now(UTC)
    total_urls = db.scalar(select(func.count(URL.id)).where(URL.user_id == user.id)) or 0
    expired_urls = (
        db.scalar(
            select(func.count(URL.id)).where(
                URL.user_id == user.id,
                URL.expires_at.is_not(None),
                URL.expires_at <= now,
            )
        )
        or 0
    )
    active_urls = (
        db.scalar(
            select(func.count(URL.id)).where(
                URL.user_id == user.id,
                URL.is_active.is_(True),
                (URL.expires_at.is_(None)) | (URL.expires_at > now),
            )
        )
        or 0
    )
    total_clicks = (
        db.scalar(
            select(func.count(Click.id))
            .join(URL, Click.url_id == URL.id)
            .where(URL.user_id == user.id)
        )
        or 0
    )

    return {
        "total_urls": total_urls,
        "active_urls": active_urls,
        "expired_urls": expired_urls,
        "total_clicks": total_clicks,
    }


# --------------------------------------------------------------------------- #
# Writes
# --------------------------------------------------------------------------- #
def create_url(db: Session, user: User, payload: URLCreate) -> URLRead:
    original_url = str(payload.original_url)
    custom_alias = payload.custom_alias

    if custom_alias:
        if _alias_exists(db, custom_alias):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Alias '{custom_alias}' is already taken",
            )
        short_code = custom_alias
    else:
        short_code = _unique_short_code(db)

    url = URL(
        user_id=user.id,
        original_url=original_url,
        short_code=short_code,
        custom_alias=custom_alias,
        expires_at=payload.expires_at,
        is_active=True,
    )

    db.add(url)
    try:
        db.commit()
    except IntegrityError as exc:
        # Two requests raced for the same alias/code between the check and the insert.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That short code or alias is already taken",
        ) from exc

    db.refresh(url)
    cache_url(short_code, cache_payload(url))
    return serialize_url(url)


def update_url(db: Session, user: User, url_id: uuid.UUID, payload: URLUpdate) -> URLRead:
    url = get_owned_url(db, url_id, user)
    old_code = url.short_code
    data = payload.model_dump(exclude_unset=True)

    if "custom_alias" in data:
        new_alias = data.pop("custom_alias")
        # An alias we already own is a no-op; someone else's is a conflict.
        if new_alias == url.custom_alias:
            pass
        elif new_alias is not None and _alias_exists(db, new_alias):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Alias '{new_alias}' is already taken",
            )
        else:
            url.custom_alias = new_alias
            # The alias is what users see, so it becomes the public code. The
            # previous code is released for reuse.
            url.short_code = new_alias or generate_short_code()

    if "original_url" in data:
        url.original_url = str(data.pop("original_url"))
    if "expires_at" in data:
        url.expires_at = data.pop("expires_at")
    if "is_active" in data:
        url.is_active = data.pop("is_active")

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That short code or alias is already taken",
        ) from exc

    db.refresh(url)
    invalidate_url(old_code)
    if url.short_code != old_code:
        invalidate_url(url.short_code)
    else:
        cache_url(old_code, cache_payload(url))
    return serialize_url(url)


def delete_url(db: Session, user: User, url_id: uuid.UUID) -> None:
    url = get_owned_url(db, url_id, user)
    short_code = url.short_code
    db.delete(url)  # clicks fall away via ON DELETE CASCADE
    db.commit()
    invalidate_url(short_code)


def toggle_url(db: Session, user: User, url_id: uuid.UUID, is_active: bool) -> URLRead:
    return update_url(db, user, url_id, URLUpdate(is_active=is_active))


def top_urls(db: Session, user: User, limit: int = 5) -> list[dict]:
    """Most-clicked URLs for the dashboard chart."""
    rows = db.execute(
        select(URL.id, URL.short_code, URL.original_url, func.count(Click.id).label("clicks"))
        .join(Click, Click.url_id == URL.id)
        .where(URL.user_id == user.id)
        .group_by(URL.id, URL.short_code, URL.original_url)
        .order_by(func.count(Click.id).desc())
        .limit(limit)
    ).all()

    return [
        {
            "url_id": str(r[0]),
            "short_code": r[1],
            "original_url": r[2],
            "clicks": r[3],
        }
        for r in rows
    ]


def start_of_day(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)