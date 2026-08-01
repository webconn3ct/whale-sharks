"""add hedge_opposing_value to consensus_position_traders

Revision ID: 0012_hedge_opposing_value
Revises: 0011_signups
Create Date: 2026-08-01

Persists each holder's dollar value on OTHER outcomes of the same market
at scan time (NULL when they hold only this side) — lets leans and
KrillBot's own reasoning surface when a whale is hedged (e.g. betting
both the over and the under with different amounts) instead of treating
every position as full-conviction. trader_weight itself is already
hedge-discounted at scan time; this column is for display only.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_hedge_opposing_value"
down_revision: Union[str, None] = "0011_signups"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "consensus_position_traders",
        sa.Column("hedge_opposing_value", sa.Numeric(18, 6), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("consensus_position_traders", "hedge_opposing_value")
