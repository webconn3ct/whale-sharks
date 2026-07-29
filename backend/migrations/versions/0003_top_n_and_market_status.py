"""top-n leaderboard filter dimension and market active/closed status

Revision ID: 0003_top_n_and_market_status
Revises: 0002_auth_and_moderation
Create Date: 2026-07-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_top_n_and_market_status"
down_revision: Union[str, None] = "0002_auth_and_moderation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("markets", sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))

    op.drop_constraint("uq_cp_scan_variant_condition_outcome", "consensus_positions", type_="unique")
    op.add_column("consensus_positions", sa.Column("top_n", sa.SmallInteger(), nullable=False, server_default="25"))
    op.create_index("ix_consensus_positions_top_n", "consensus_positions", ["top_n"])
    op.create_unique_constraint(
        "uq_cp_scan_variant_topn_condition_outcome",
        "consensus_positions",
        ["scan_id", "variant", "top_n", "condition_id", "outcome_index"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_cp_scan_variant_topn_condition_outcome", "consensus_positions", type_="unique")
    op.drop_index("ix_consensus_positions_top_n", table_name="consensus_positions")
    op.drop_column("consensus_positions", "top_n")
    op.create_unique_constraint(
        "uq_cp_scan_variant_condition_outcome",
        "consensus_positions",
        ["scan_id", "variant", "condition_id", "outcome_index"],
    )

    op.drop_column("markets", "active")
