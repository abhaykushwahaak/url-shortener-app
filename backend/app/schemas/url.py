"""URL request/response models, including alias and expiration validation."""

import re
import uuid
from datetime import UTC, datetime
from typing import Annotated

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.core.config import get_settings

settings = get_settings()

# Aliases end up directly in a path segment, so allow only URL-safe characters.
ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

# Codes we must never hand out because they collide with real routes.
RESERVED_ALIASES = {
    "api",
    "docs",
    "redoc",
    "openapi.json",
    "health",
    "static",
    "favicon.ico",
    "auth",
    "urls",
    "analytics",
}


def _validate_alias(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not (settings.MIN_ALIAS_LENGTH <= len(value) <= settings.MAX_ALIAS_LENGTH):
        raise ValueError(
            f"alias must be between {settings.MIN_ALIAS_LENGTH} and "
            f"{settings.MAX_ALIAS_LENGTH} characters"
        )
    if not ALIAS_PATTERN.match(value):
        raise ValueError("alias may only contain letters, numbers, hyphens and underscores")
    if value.lower() in RESERVED_ALIASES:
        raise ValueError(f"'{value}' is a reserved word and cannot be used as an alias")
    return value


def _validate_expiry(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    if value <= datetime.now(UTC):
        raise ValueError("expires_at must be in the future")
    return value


class URLCreate(BaseModel):
    original_url: AnyHttpUrl = Field(..., examples=["https://example.com/very/long/url"])
    custom_alias: str | None = Field(
        None, min_length=3, max_length=32, examples=["github"]
    )
    expires_at: datetime | None = Field(None, examples=["2026-12-31T00:00:00Z"])

    @field_validator("custom_alias")
    @classmethod
    def check_alias(cls, v: str | None) -> str | None:
        return _validate_alias(v)

    @field_validator("expires_at")
    @classmethod
    def check_expiry(cls, v: datetime | None) -> datetime | None:
        return _validate_expiry(v)


class URLUpdate(BaseModel):
    """Every field is optional - only what is sent gets changed."""

    original_url: AnyHttpUrl | None = None
    custom_alias: str | None = None
    is_active: bool | None = None
    expires_at: datetime | None = None

    @field_validator("custom_alias")
    @classmethod
    def check_alias(cls, v: str | None) -> str | None:
        return _validate_alias(v)

    @field_validator("expires_at")
    @classmethod
    def check_expiry(cls, v: datetime | None) -> datetime | None:
        return _validate_expiry(v)


class URLRead(BaseModel):
    id: uuid.UUID
    original_url: str
    short_code: str
    custom_alias: str | None
    short_url: str
    is_active: bool
    is_expired: bool
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
    total_clicks: int = 0
    clicks_today: int = 0
    clicks_this_week: int = 0


class PaginatedURLs(BaseModel):
    items: list[URLRead]
    page: int
    limit: int
    total: int


class URLStats(BaseModel):
    """Lightweight per-URL numbers used on the dashboard cards."""

    total_urls: int
    active_urls: int
    expired_urls: int
    total_clicks: int