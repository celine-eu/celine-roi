"""Record the caller's address on estimates.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("estimates", sa.Column("client_ip", sa.String(length=50)))


def downgrade() -> None:
    op.drop_column("estimates", "client_ip")
