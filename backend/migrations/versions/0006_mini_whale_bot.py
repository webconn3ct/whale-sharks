"""mini whale bot: state, positions, recalibration log

Revision ID: 0006_mini_whale_bot
Revises: 0005_trader_weight
Create Date: 2026-07-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_mini_whale_bot"
down_revision: Union[str, None] = "0005_trader_weight"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bot_position_status = sa.Enum("open", "closed", name="bot_position_status")
    bot_exit_reason = sa.Enum(
        "take_profit", "stop_loss", "signal_lost", "market_resolved", name="bot_exit_reason"
    )

    op.create_table(
        "bot_state",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("cash_balance", sa.Numeric(12, 2), nullable=False, server_default="500"),
        sa.Column("starting_balance", sa.Numeric(12, 2), nullable=False, server_default="500"),
        sa.Column("entry_min_whales", sa.SmallInteger(), nullable=False, server_default="3"),
        sa.Column("entry_score_threshold", sa.Numeric(10, 2), nullable=False, server_default="250.0"),
        sa.Column("medium_bet_score", sa.Numeric(10, 2), nullable=False, server_default="450.0"),
        sa.Column("large_bet_score", sa.Numeric(10, 2), nullable=False, server_default="800.0"),
        sa.Column("take_profit_pct", sa.Numeric(5, 2), nullable=False, server_default="0.40"),
        sa.Column("stop_loss_pct", sa.Numeric(5, 2), nullable=False, server_default="0.35"),
        sa.Column("signal_decay_fraction", sa.Numeric(4, 3), nullable=False, server_default="0.5"),
        sa.Column("trades_since_recalibration", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_recalibrated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "bot_positions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("condition_id", sa.String(66), nullable=False),
        sa.Column("outcome_index", sa.SmallInteger(), nullable=False),
        sa.Column("outcome_label", sa.String(100), nullable=False),
        sa.Column("market_title", sa.Text(), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("status", bot_position_status, nullable=False),
        sa.Column("stake", sa.Numeric(6, 2), nullable=False),
        sa.Column("shares", sa.Numeric(18, 6), nullable=False),
        sa.Column("entry_price", sa.Numeric(9, 6), nullable=False),
        sa.Column("entry_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_consensus_score", sa.Numeric(18, 6), nullable=False),
        sa.Column("entry_whale_count", sa.Integer(), nullable=False),
        sa.Column("entry_reasoning", sa.Text(), nullable=True),
        sa.Column("exit_price", sa.Numeric(9, 6), nullable=True),
        sa.Column("exit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_reason", bot_exit_reason, nullable=True),
        sa.Column("realized_pnl", sa.Numeric(10, 2), nullable=True),
    )
    op.create_index("ix_bot_positions_condition_id", "bot_positions", ["condition_id"])
    op.create_index("ix_bot_positions_status", "bot_positions", ["status"])

    op.create_table(
        "bot_recalibrations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("old_thresholds", sa.JSON(), nullable=False),
        sa.Column("new_thresholds", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("bot_recalibrations")
    op.drop_index("ix_bot_positions_status", table_name="bot_positions")
    op.drop_index("ix_bot_positions_condition_id", table_name="bot_positions")
    op.drop_table("bot_positions")
    op.drop_table("bot_state")
    sa.Enum(name="bot_exit_reason").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="bot_position_status").drop(op.get_bind(), checkfirst=True)
