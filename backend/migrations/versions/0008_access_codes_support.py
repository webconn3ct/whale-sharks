"""multi-code visitor access + chat support-request notifications

Revision ID: 0008_access_codes_support
Revises: 0007_login_events_whale_alerts
Create Date: 2026-07-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_access_codes_support"
down_revision: Union[str, None] = "0007_login_events_whale_alerts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "access_codes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "support_requests",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("contact", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_support_requests_created_at", "support_requests", ["created_at"])

    # Carry the existing single access code forward as a named row so nothing
    # currently using it gets locked out.
    conn = op.get_bind()
    existing = conn.execute(sa.text("SELECT access_code_hash FROM app_config WHERE id = 1")).fetchone()
    if existing and existing[0]:
        conn.execute(
            sa.text(
                "INSERT INTO access_codes (name, code_hash, created_at, active) "
                "VALUES ('original', :code_hash, now(), true)"
            ),
            {"code_hash": existing[0]},
        )

    op.drop_column("app_config", "access_code_hash")


def downgrade() -> None:
    op.add_column("app_config", sa.Column("access_code_hash", sa.Text(), nullable=True))

    conn = op.get_bind()
    original = conn.execute(
        sa.text("SELECT code_hash FROM access_codes WHERE name = 'original' ORDER BY id LIMIT 1")
    ).fetchone()
    if original and original[0]:
        conn.execute(sa.text("UPDATE app_config SET access_code_hash = :code_hash WHERE id = 1"), {"code_hash": original[0]})

    op.drop_index("ix_support_requests_created_at", table_name="support_requests")
    op.drop_table("support_requests")
    op.drop_table("access_codes")
