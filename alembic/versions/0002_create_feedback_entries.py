"""Create REC-scoped ROI feedback entries.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feedback_entries",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("community_key", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("page_url", sa.Text(), nullable=False),
        sa.Column("page_title", sa.Text()),
        sa.Column("page_path", sa.Text()),
        sa.Column("locale", sa.String(length=32)),
        sa.Column("timezone", sa.String(length=64)),
        sa.Column("user_agent", sa.Text()),
        sa.Column("viewport_width", sa.Integer()),
        sa.Column("viewport_height", sa.Integer()),
        sa.Column("screen_width", sa.Integer()),
        sa.Column("screen_height", sa.Integer()),
        sa.Column("color_scheme", sa.String(length=16)),
        sa.Column("client_timestamp", sa.DateTime(timezone=True)),
        sa.Column("client_ip", sa.String(length=50)),
        sa.Column("extra_context", JSONB()),
        sa.Column("screenshot_mime_type", sa.String(length=64)),
        sa.Column("screenshot_bytes", sa.LargeBinary()),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="new",
            nullable=False,
        ),
        sa.Column("seen_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("status_updated_by", sa.String(length=255)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_roi_feedback_community_status",
        "feedback_entries",
        ["community_key", "status"],
    )
    op.create_index(
        "idx_roi_feedback_created_at",
        "feedback_entries",
        ["created_at"],
        postgresql_using="btree",
    )


def downgrade() -> None:
    op.drop_index("idx_roi_feedback_created_at", table_name="feedback_entries")
    op.drop_index("idx_roi_feedback_community_status", table_name="feedback_entries")
    op.drop_table("feedback_entries")
