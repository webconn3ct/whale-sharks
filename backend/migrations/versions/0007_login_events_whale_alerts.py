"""admin: login events + whale (large-trade) alerts

Revision ID: 0007_login_events_whale_alerts
Revises: 0006_mini_whale_bot
Create Date: 2026-07-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_login_events_whale_alerts"
down_revision: Union[str, None] = "0006_mini_whale_bot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "login_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("visitor_hash", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_login_events_visitor_hash", "login_events", ["visitor_hash"])
    op.create_index("ix_login_events_occurred_at", "login_events", ["occurred_at"])

    op.create_table(
        "whale_alerts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("wallet_address", sa.String(42), nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("condition_id", sa.String(66), nullable=False),
        sa.Column("outcome_index", sa.SmallInteger(), nullable=False),
        sa.Column("outcome_label", sa.String(100), nullable=False),
        sa.Column("market_title", sa.Text(), nullable=False),
        sa.Column("position_value", sa.Numeric(18, 6), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("wallet_address", "condition_id", "outcome_index", name="uq_whale_alerts_wallet_market_outcome"),
    )
    op.create_index("ix_whale_alerts_detected_at", "whale_alerts", ["detected_at"])


def downgrade() -> None:
    op.drop_index("ix_whale_alerts_detected_at", table_name="whale_alerts")
    op.drop_table("whale_alerts")
    op.drop_index("ix_login_events_occurred_at", table_name="login_events")
    op.drop_index("ix_login_events_visitor_hash", table_name="login_events")
    op.drop_table("login_events")
