"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Each enum is referenced by exactly one column below, so leaving the default
# create_type=True lets op.create_table create it exactly once, in place.
timeframe_enum = sa.Enum("DAY", "WEEK", "MONTH", "ALL", name="timeframe")
best_timeframe_enum = sa.Enum("DAY", "WEEK", "MONTH", "ALL", name="best_timeframe")
variant_enum = sa.Enum("combined", "day", "week", "month", "all_time", name="variant")
scan_status_enum = sa.Enum("running", "completed", "failed", name="scan_status")


def upgrade() -> None:
    op.create_table(
        "traders",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("wallet_address", sa.String(42), nullable=False),
        sa.Column("username", sa.String(255)),
        sa.Column("profile_image", sa.Text()),
        sa.Column("x_username", sa.String(255)),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("wallet_address", name="uq_traders_wallet_address"),
    )
    op.create_index("ix_traders_wallet_address", "traders", ["wallet_address"])

    op.create_table(
        "markets",
        sa.Column("condition_id", sa.String(66), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("slug", sa.String(255), nullable=False, server_default=""),
        sa.Column("event_slug", sa.String(255), nullable=False, server_default=""),
        sa.Column("category", sa.String(100)),
        sa.Column("image_url", sa.Text()),
        sa.Column("end_date", sa.DateTime(timezone=True)),
        sa.Column("metadata_updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "scans",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("status", scan_status_enum, nullable=False),
        sa.Column("traders_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("positions_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_value", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("error", sa.Text()),
    )
    op.create_index("ix_scans_status_completed_at", "scans", ["status", "completed_at"])

    op.create_table(
        "trader_leaderboard_ranks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("scan_id", sa.BigInteger(), sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trader_id", sa.BigInteger(), sa.ForeignKey("traders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("timeframe", timeframe_enum, nullable=False),
        sa.Column("rank", sa.SmallInteger(), nullable=False),
        sa.Column("pnl", sa.Numeric(18, 6), nullable=False),
        sa.Column("vol", sa.Numeric(18, 6), nullable=False),
        sa.UniqueConstraint("scan_id", "trader_id", "timeframe", name="uq_tlr_scan_trader_timeframe"),
    )
    op.create_index("ix_trader_leaderboard_ranks_scan_id", "trader_leaderboard_ranks", ["scan_id"])

    op.create_table(
        "consensus_positions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("scan_id", sa.BigInteger(), sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant", variant_enum, nullable=False),
        sa.Column("condition_id", sa.String(66), sa.ForeignKey("markets.condition_id"), nullable=False),
        sa.Column("outcome_index", sa.SmallInteger(), nullable=False),
        sa.Column("outcome_label", sa.String(100), nullable=False),
        sa.Column("current_price", sa.Numeric(9, 6), nullable=False),
        sa.Column("whale_count", sa.Integer(), nullable=False),
        sa.Column("combined_value", sa.Numeric(18, 6), nullable=False),
        sa.Column("consensus_score", sa.Numeric(18, 6), nullable=False),
        sa.UniqueConstraint(
            "scan_id", "variant", "condition_id", "outcome_index", name="uq_cp_scan_variant_condition_outcome"
        ),
    )
    op.create_index("ix_consensus_positions_scan_id", "consensus_positions", ["scan_id"])
    op.create_index("ix_consensus_positions_variant", "consensus_positions", ["variant"])

    op.create_table(
        "consensus_position_traders",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "consensus_position_id",
            sa.BigInteger(),
            sa.ForeignKey("consensus_positions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trader_id", sa.BigInteger(), sa.ForeignKey("traders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("best_timeframe", best_timeframe_enum, nullable=False),
        sa.Column("best_rank", sa.SmallInteger(), nullable=False),
        sa.Column("position_value", sa.Numeric(18, 6), nullable=False),
        sa.Column("size", sa.Numeric(18, 6), nullable=False),
        sa.Column("avg_entry_price", sa.Numeric(9, 6), nullable=False),
        sa.Column("current_price", sa.Numeric(9, 6), nullable=False),
        sa.Column("cash_pnl", sa.Numeric(18, 6), nullable=False),
        sa.Column("percent_pnl", sa.Numeric(14, 6), nullable=False),
        sa.UniqueConstraint("consensus_position_id", "trader_id", name="uq_cpt_position_trader"),
    )
    op.create_index("ix_consensus_position_traders_position_id", "consensus_position_traders", ["consensus_position_id"])


def downgrade() -> None:
    op.drop_table("consensus_position_traders")
    op.drop_table("consensus_positions")
    op.drop_table("trader_leaderboard_ranks")
    op.drop_table("scans")
    op.drop_table("markets")
    op.drop_table("traders")

    # Unlike CREATE TABLE, DROP TABLE does not auto-drop the Postgres ENUM
    # types used by its columns — drop them explicitly, checkfirst since a
    # type may already be gone if downgrade is re-run after a partial failure.
    bind = op.get_bind()
    scan_status_enum.drop(bind, checkfirst=True)
    variant_enum.drop(bind, checkfirst=True)
    best_timeframe_enum.drop(bind, checkfirst=True)
    timeframe_enum.drop(bind, checkfirst=True)
