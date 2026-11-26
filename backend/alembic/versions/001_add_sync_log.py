"""Add sync_log table for automated ingestion observability

Revision ID: 001_add_sync_log
Revises:
Create Date: 2026-11-26 21:26:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "001_add_sync_log"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("sync_log"):
        op.create_table(
            "sync_log",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("source", sa.String(length=50), nullable=False),
            sa.Column("job_type", sa.String(length=40), nullable=False, server_default="manual"),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("records_upserted", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("etag", sa.String(length=255), nullable=True),
        )
        op.create_index("ix_sync_log_started_at", "sync_log", ["started_at"])
        op.create_index("ix_sync_log_source", "sync_log", ["source"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("sync_log"):
        op.drop_index("ix_sync_log_source", table_name="sync_log")
        op.drop_index("ix_sync_log_started_at", table_name="sync_log")
        op.drop_table("sync_log")
