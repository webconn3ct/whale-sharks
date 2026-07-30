"""login-page signup box (email/IG handle log for admin)

Revision ID: 0011_signups
Revises: 0010_bot_pause_switch
Create Date: 2026-07-30

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_signups"
down_revision: Union[str, None] = "0010_bot_pause_switch"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "signups",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("contact", sa.String(255), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_signups_submitted_at", "signups", ["submitted_at"])


def downgrade() -> None:
    op.drop_index("ix_signups_submitted_at", table_name="signups")
    op.drop_table("signups")
