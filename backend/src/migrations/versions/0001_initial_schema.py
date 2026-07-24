"""initial schema: users, ingestion_sources, dataset_records, log_assignments, roi_cache

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-25

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "ingestion_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("records_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("records_valid", sa.Integer(), server_default="0", nullable=False),
        sa.Column("records_rejected", sa.Integer(), server_default="0", nullable=False),
        sa.Column("normalization_report", postgresql.JSONB(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="ingesting",
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "dataset_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("gold_category", sa.String(length=64), nullable=True),
        sa.Column("style", sa.String(length=64), nullable=True),
        sa.Column("tokens", sa.Integer(), nullable=True),
        sa.Column("manual_time_minutes", sa.Float(), nullable=True),
        sa.Column("tools_used", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_id"], ["ingestion_sources.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_dataset_records_source_request",
        "dataset_records",
        ["source_id", "request_id"],
        unique=True,
    )

    op.create_table(
        "log_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=True),
        sa.Column("classification_confidence", sa.Float(), nullable=True),
        sa.Column("scenario_id", sa.String(length=128), nullable=True),
        sa.Column("scenario_name", sa.String(length=255), nullable=True),
        sa.Column("is_outlier", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "has_failure_signals",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["ingestion_sources.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_log_assignments_source_request",
        "log_assignments",
        ["source_id", "request_id"],
        unique=True,
    )

    op.create_table(
        "roi_cache",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=512), nullable=False),
        sa.Column("summary", postgresql.JSONB(), nullable=True),
        sa.Column("by_category", postgresql.JSONB(), nullable=True),
        sa.Column("by_scenario", postgresql.JSONB(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("roi_cache")
    op.drop_index("ix_log_assignments_source_request", table_name="log_assignments")
    op.drop_table("log_assignments")
    op.drop_index("ix_dataset_records_source_request", table_name="dataset_records")
    op.drop_table("dataset_records")
    op.drop_table("ingestion_sources")
    op.drop_table("users")
