"""One row per redirect - the raw material for every analytics query."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.url import URL

# PostgreSQL gets BIGSERIAL (clicks is the table that grows without bound).
# SQLite only auto-increments a column declared exactly as INTEGER PRIMARY KEY,
# so it needs the plain Integer variant.
ClickIdType = BigInteger().with_variant(Integer, "sqlite")


class Click(Base):
    __tablename__ = "clicks"

    id: Mapped[int] = mapped_column(ClickIdType, primary_key=True, autoincrement=True)
    url_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("urls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    clicked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    device: Mapped[str | None] = mapped_column(String(32), nullable=True)
    browser: Mapped[str | None] = mapped_column(String(64), nullable=True)
    referrer: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)

    url: Mapped["URL"] = relationship(back_populates="clicks")

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Click url={self.url_id} at={self.clicked_at}>"