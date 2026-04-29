"""create estimates table

Revision ID: 0001
Revises:
Create Date: 2026-04-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "estimates",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("endpoint", sa.String(20), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("request", JSONB, nullable=False),
        sa.Column("response", JSONB),
        sa.Column("error_message", sa.Text),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_estimates_created_at", "estimates", ["created_at"], postgresql_using="btree")
    op.create_index("idx_estimates_endpoint", "estimates", ["endpoint"], postgresql_using="btree")


def downgrade() -> None:
    op.drop_index("idx_estimates_endpoint", table_name="estimates")
    op.drop_index("idx_estimates_created_at", table_name="estimates")
    op.drop_table("estimates")
