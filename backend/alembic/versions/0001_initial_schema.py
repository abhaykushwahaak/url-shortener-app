"""Initial schema: users, urls, clicks.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Matches the model definition: BIGSERIAL on PostgreSQL, plain INTEGER on SQLite
# (SQLite only auto-increments a column declared exactly INTEGER PRIMARY KEY).
CLICK_ID = sa.BigInteger().with_variant(sa.Integer, "sqlite")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "urls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("original_url", sa.Text(), nullable=False),
        sa.Column("short_code", sa.String(length=32), nullable=False),
        sa.Column("custom_alias", sa.String(length=32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_urls_user_id", "urls", ["user_id"])
    op.create_index("ix_urls_short_code", "urls", ["short_code"], unique=True)
    op.create_index("ix_urls_custom_alias", "urls", ["custom_alias"], unique=True)

    op.create_table(
        "clicks",
        sa.Column("id", CLICK_ID, autoincrement=True, nullable=False),
        sa.Column("url_id", sa.Uuid(), nullable=False),
        sa.Column(
            "clicked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("device", sa.String(length=32), nullable=True),
        sa.Column("browser", sa.String(length=64), nullable=True),
        sa.Column("referrer", sa.Text(), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.ForeignKeyConstraint(["url_id"], ["urls.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_clicks_url_id", "clicks", ["url_id"])
    op.create_index("ix_clicks_clicked_at", "clicks", ["clicked_at"])


def downgrade() -> None:
    op.drop_index("ix_clicks_clicked_at", table_name="clicks")
    op.drop_index("ix_clicks_url_id", table_name="clicks")
    op.drop_table("clicks")

    op.drop_index("ix_urls_custom_alias", table_name="urls")
    op.drop_index("ix_urls_short_code", table_name="urls")
    op.drop_index("ix_urls_user_id", table_name="urls")
    op.drop_table("urls")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")