"""auth config and content moderation tables

Revision ID: 0002_auth_and_moderation
Revises: 0001_initial
Create Date: 2026-07-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_auth_and_moderation"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_config",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("access_code_hash", sa.Text(), nullable=False),
        sa.Column("admin_password_hash", sa.Text(), nullable=False),
        sa.Column("value_normalizer", sa.Numeric(6, 3), nullable=False, server_default="6.0"),
        sa.Column("max_value_boost", sa.Numeric(6, 3), nullable=False, server_default="1.0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_app_config_singleton"),
    )

    op.create_table(
        "excluded_markets",
        sa.Column("condition_id", sa.String(66), primary_key=True),
        sa.Column("reason", sa.Text()),
        sa.Column("excluded_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "excluded_traders",
        sa.Column("wallet_address", sa.String(42), primary_key=True),
        sa.Column("reason", sa.Text()),
        sa.Column("excluded_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("excluded_traders")
    op.drop_table("excluded_markets")
    op.drop_table("app_config")
