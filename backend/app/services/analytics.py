"""Click recording and the aggregation queries behind the dashboard."""

import uuid
from datetime import UTC, datetime, time, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.useragent import parse_all
from app.models.click import Click
from app.models.url import URL
from app.models.user import User
from app.schemas.analytics import (
    AnalyticsSummary,
    CountByKey,
    TimelinePoint,
    TimelineResponse,
)
from app.services.url import get_owned_url

MAX_COUNTRY_LENGTH = 2
MAX_IP_LENGTH = 45  # long enough for IPv6


def start_of_utc_day(day_offset: int = 0) -> datetime:
    """Midnight UTC, `day_offset` days ago. All analytics buckets are UTC."""
    today = datetime.now(UTC).date() - timedelta(days=day_offset)
    return datetime.combine(today, time.min, tzinfo=UTC)


def record_click(
    db: Session,
    url_id: uuid.UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
    referrer: str | None = None,
    country: str | None = None,
) -> Click:
    """Insert one click row. Runs inside the Celery worker, never on the request path."""
    device, browser = parse_all(user_agent)
    click = Click(
        url_id=url_id,
        ip_address=(ip_address or None) and ip_address[:MAX_IP_LENGTH],
        user_agent=user_agent,
        device=device,
        browser=browser,
        referrer=referrer,
        country=(country or None) and country[:MAX_COUNTRY_LENGTH],
    )
    db.add(click)
    db.commit()
    db.refresh(click)
    return click


def _grouped_counts(
    db: Session, url_id: uuid.UUID, column, limit: int = 10
) -> list[CountByKey]:
    """Top-N value counts for one column (device, browser, referrer, country)."""
    rows = db.execute(
        select(column, func.count(Click.id).label("count"))
        .where(Click.url_id == url_id, column.is_not(None))
        .group_by(column)
        .order_by(func.count(Click.id).desc())
        .limit(limit)
    ).all()
    return [CountByKey(key=str(row[0]), count=row[1]) for row in rows]


def get_summary(db: Session, user: User, url_id: uuid.UUID) -> AnalyticsSummary:
    url = get_owned_url(db, url_id, user)

    start_today = start_of_utc_day()
    start_week = start_today - timedelta(days=datetime.now(UTC).weekday())

    totals = db.execute(
        select(
            func.count(Click.id),
            func.count(Click.id).filter(Click.clicked_at >= start_today),
            func.count(Click.id).filter(Click.clicked_at >= start_week),
            func.count(func.distinct(Click.ip_address)),
            func.min(Click.clicked_at),
            func.max(Click.clicked_at),
        ).where(Click.url_id == url.id)
    ).one()

    total_clicks, today, week, unique_visitors = totals[0], totals[1], totals[2], totals[3]

    return AnalyticsSummary(
        url_id=str(url.id),
        short_code=url.short_code,
        original_url=url.original_url,
        total_clicks=total_clicks,
        clicks_today=today,
        clicks_this_week=week,
        unique_visitors=unique_visitors,
        first_click_at=totals[4].isoformat() if totals[4] else None,
        last_click_at=totals[5].isoformat() if totals[5] else None,
        devices=_grouped_counts(db, url.id, Click.device),
        browsers=_grouped_counts(db, url.id, Click.browser),
        referrers=_grouped_counts(db, url.id, Click.referrer),
        countries=_grouped_counts(db, url.id, Click.country),
    )


def get_timeline(
    db: Session, user: User, url_id: uuid.UUID, days: int = 30
) -> TimelineResponse:
    """Clicks per day for the last `days` days, including zero-click days.

    Only the `clicked_at` column is selected for the window and then bucketed in
    Python. That keeps the query portable between PostgreSQL and SQLite - a
    `date_trunc('day', ...)` version would be PostgreSQL-only - and the row count
    per URL is small enough that the trade-off does not matter. For a
    high-traffic service the bucketing would move into SQL.
    """
    url = get_owned_url(db, url_id, user)

    start = start_of_utc_day(days - 1)
    rows = db.scalars(
        select(Click.clicked_at).where(
            Click.url_id == url.id, Click.clicked_at >= start
        )
    ).all()

    buckets: dict[str, int] = {
        (start + timedelta(days=offset)).date().isoformat(): 0 for offset in range(days)
    }
    for clicked_at in rows:
        if clicked_at.tzinfo is None:
            clicked_at = clicked_at.replace(tzinfo=UTC)
        key = clicked_at.astimezone(UTC).date().isoformat()
        if key in buckets:
            buckets[key] += 1

    points = [
        TimelinePoint(date=datetime.fromisoformat(day).date(), clicks=count)
        for day, count in sorted(buckets.items())
    ]
    return TimelineResponse(url_id=str(url.id), days=days, points=points)


def user_timeline(db: Session, user: User, days: int = 30) -> TimelineResponse:
    """Same shape as get_timeline but aggregated across every URL the user owns."""
    start = start_of_utc_day(days - 1)
    rows = db.scalars(
        select(Click.clicked_at)
        .join(URL, Click.url_id == URL.id)
        .where(URL.user_id == user.id, Click.clicked_at >= start)
    ).all()

    buckets: dict[str, int] = {
        (start + timedelta(days=offset)).date().isoformat(): 0 for offset in range(days)
    }
    for clicked_at in rows:
        if clicked_at.tzinfo is None:
            clicked_at = clicked_at.replace(tzinfo=UTC)
        key = clicked_at.astimezone(UTC).date().isoformat()
        if key in buckets:
            buckets[key] += 1

    points = [
        TimelinePoint(date=datetime.fromisoformat(day).date(), clicks=count)
        for day, count in sorted(buckets.items())
    ]
    return TimelineResponse(url_id="all", days=days, points=points)


def get_click_history(
    db: Session, user: User, url_id: uuid.UUID, page: int = 1, limit: int = 20
) -> tuple[list[Click], int]:
    """Raw click log for a URL, newest first - powers the analytics table."""
    url = get_owned_url(db, url_id, user)
    total = db.scalar(select(func.count(Click.id)).where(Click.url_id == url.id)) or 0
    clicks = list(
        db.scalars(
            select(Click)
            .where(Click.url_id == url.id)
            .order_by(Click.clicked_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
    )
    return clicks, total


def daily_links_created(db: Session, user: User, days: int = 30) -> list[TimelinePoint]:
    """Secondary dashboard chart: how many links the user created per day."""
    start = start_of_utc_day(days - 1)
    rows = db.scalars(
        select(URL.created_at).where(URL.user_id == user.id, URL.created_at >= start)
    ).all()

    buckets: dict[str, int] = {
        (start + timedelta(days=offset)).date().isoformat(): 0 for offset in range(days)
    }
    for created_at in rows:
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        key = created_at.astimezone(UTC).date().isoformat()
        if key in buckets:
            buckets[key] += 1

    return [
        TimelinePoint(date=datetime.fromisoformat(day).date(), clicks=count)
        for day, count in sorted(buckets.items())
    ]