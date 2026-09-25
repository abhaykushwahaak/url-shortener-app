"""Redis caching for short-code lookups + the Celery application instance.

Redis holds one key per short code:

    short:{code}  ->  JSON {"url_id": ..., "original_url": ..., "is_active": ..., "expires_at": ...}

The redirect endpoint can then answer without touching PostgreSQL. Cache entries are
invalidated whenever a URL is edited, disabled or deleted.
"""

import json
import logging
from typing import Any

import redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_pool: redis.ConnectionPool | None = None


def _build_pool() -> redis.ConnectionPool:
    return redis.ConnectionPool.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )


def get_redis() -> redis.Redis:
    """Return a Redis client. Connections are pooled and created lazily."""
    global _pool
    if _pool is None:
        _pool = _build_pool()
    return redis.Redis(connection_pool=_pool)


def _key(short_code: str) -> str:
    return f"short:{short_code}"


def get_cached_url(short_code: str) -> dict[str, Any] | None:
    """Return the cached URL payload, or None on a miss.

    Redis is an optimization, never a source of truth: if it is unavailable the
    function degrades to a miss so redirects keep working.
    """
    try:
        raw = get_redis().get(_key(short_code))
    except redis.RedisError as exc:
        logger.warning("Redis GET failed for %s: %s", short_code, exc)
        return None

    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def cache_url(
    short_code: str, payload: dict[str, Any], ttl: int | None = None
) -> None:
    """Store a URL payload, skipping inactive/expired rows (they must 404/410)."""
    if not payload.get("is_active") or payload.get("expires_at"):
        return
    try:
        get_redis().set(
            _key(short_code),
            json.dumps(payload),
            ex=ttl or settings.CACHE_TTL_SECONDS,
        )
    except redis.RedisError as exc:
        logger.warning("Redis SET failed for %s: %s", short_code, exc)


def invalidate_url(short_code: str) -> None:
    """Drop a cached entry. Called on edit, disable and delete."""
    try:
        get_redis().delete(_key(short_code))
    except redis.RedisError as exc:
        logger.warning("Redis DEL failed for %s: %s", short_code, exc)