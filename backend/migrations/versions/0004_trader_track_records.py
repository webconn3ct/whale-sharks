"""trader track records (historical hit rate on resolved markets)

Revision ID: 0004_trader_track_records
Revises: 0003_top_n_and_market_status
Create Date: 2026-07-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_trader_track_records"
down_revision: Union[str, None] = "0003_top_n_and_market_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trader_track_records",
        sa.Column("trader_id", sa.BigInteger(), sa.ForeignKey("traders.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("win_rate", sa.Numeric(5, 4), nullable=False),
        sa.Column("recent_form", sa.Numeric(5, 4), nullable=False),
        sa.Column("sample_size", sa.SmallInteger(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("trader_track_records")
