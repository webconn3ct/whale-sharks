"""admin kill switch: pause new bot entries

Revision ID: 0010_bot_pause_switch
Revises: 0009_daily_catch_pick
Create Date: 2026-07-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_bot_pause_switch"
down_revision: Union[str, None] = "0009_daily_catch_pick"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bot_state", sa.Column("entries_paused", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("bot_state", "entries_paused")
