"""add trader_weight to consensus_position_traders

Revision ID: 0005_trader_weight
Revises: 0004_trader_track_records
Create Date: 2026-07-29

Persists each holder's trader_weight at scan time so smaller top-N cuts can
be derived (re-scored) from the stored top_n=100 rows at read time, instead
of independently persisting all 5 top-N cuts per variant every scan — that
was multiplying write volume 5x for no benefit and blew past a gigabyte of
DB storage in under a day.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_trader_weight"
down_revision: Union[str, None] = "0004_trader_track_records"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "consensus_position_traders",
        sa.Column("trader_weight", sa.Numeric(18, 6), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("consensus_position_traders", "trader_weight")
