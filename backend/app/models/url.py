"""Shortened URL model."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.click import Click
    from app.models.user import User


class URL(Base):
    __tablename__ = "urls"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_url: Mapped[str] = mapped_column(Text, nullable=False)

    # Always populated: the custom alias when the user supplied one, else a
    # generated code. Keeping a single lookup column makes redirects a single
    # indexed read and keeps uniqueness in one place.
    short_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    custom_alias: Mapped[str | None] = mapped_column(
        String(32), unique=True, index=True, nullable=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    owner: Mapped["User"] = relationship(back_populates="urls")
    clicks: Mapped[list["Click"]] = relationship(
        back_populates="url", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return expires_at <= datetime.now(UTC)

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<URL {self.short_code} -> {self.original_url[:40]}>"