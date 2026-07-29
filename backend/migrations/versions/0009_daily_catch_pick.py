"""lock whale-spotlight daily catch pick per calendar day

Revision ID: 0009_daily_catch_pick
Revises: 0008_access_codes_support
Create Date: 2026-07-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_daily_catch_pick"
down_revision: Union[str, None] = "0008_access_codes_support"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_catch_picks",
        sa.Column("pick_date", sa.Date(), primary_key=True),
        sa.Column("condition_id", sa.String(66), nullable=False),
        sa.Column("outcome_index", sa.SmallInteger(), nullable=False),
        sa.Column("picked_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("daily_catch_picks")
