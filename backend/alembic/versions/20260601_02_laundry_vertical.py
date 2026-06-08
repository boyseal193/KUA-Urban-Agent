"""Create laundry_* tables for the laundromat acquisition engine.

The schema is fully independent of the self-storage tables defined in the
initial revision; it can be dropped/recreated without affecting the storage
pipeline.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260601_02"
down_revision = "20260216_01"
branch_labels = None
depends_on = None


def _server_now() -> sa.text:
    return sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "laundry_properties",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_server_now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_server_now(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("listing_url", sa.Text(), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("neighbourhood", sa.String(length=128), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("property_type", sa.String(length=64), nullable=True),
        sa.Column("acquisition_type", sa.String(length=16), nullable=True),
        sa.Column("floor_area_m2", sa.Float(), nullable=True),
        sa.Column("ceiling_height", sa.Float(), nullable=True),
        sa.Column("asking_price", sa.Float(), nullable=True),
        sa.Column("asking_rent_month", sa.Float(), nullable=True),
        sa.Column("rent_per_m2", sa.Float(), nullable=True),
        sa.Column("washer_count", sa.Integer(), nullable=True),
        sa.Column("dryer_count", sa.Integer(), nullable=True),
        sa.Column("ground_floor", sa.Boolean(), nullable=True),
        sa.Column("loading_access", sa.Boolean(), nullable=True),
        sa.Column("corner_unit", sa.Boolean(), nullable=True),
        sa.Column("water_available", sa.Boolean(), nullable=True),
        sa.Column("gas_available", sa.Boolean(), nullable=True),
        sa.Column("drainage_available", sa.Boolean(), nullable=True),
        sa.Column("three_phase_power", sa.Boolean(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("verdict", sa.String(length=64), nullable=True),
        sa.Column("classification", sa.String(length=64), nullable=True),
        sa.Column("confidence_band", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="analysed"),
        sa.Column("deal_status", sa.String(length=32), nullable=False, server_default="manual_review"),
        sa.Column("dedupe_key", sa.String(length=64), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deletion_reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_laundry_properties_deal_status", "laundry_properties", ["deal_status"])
    op.create_index("ix_laundry_properties_dedupe_key", "laundry_properties", ["dedupe_key"])
    op.create_index("ix_laundry_properties_deleted_at", "laundry_properties", ["deleted_at"])

    op.create_table(
        "laundry_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_server_now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_server_now(), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("laundry_properties.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("location", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("economics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("score", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("due_diligence", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("assumptions_used", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("verdict", sa.String(length=64), nullable=True),
        sa.Column("classification", sa.String(length=64), nullable=True),
        sa.Column("deal_killer", sa.Text(), nullable=True),
        sa.Column("ic_memo", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "laundry_scan_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_server_now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_server_now(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("job_type", sa.String(length=32), nullable=False, server_default="area_search"),
        sa.Column("property_type", sa.String(length=32), nullable=True),
        sa.Column("acquisition_type", sa.String(length=16), nullable=True),
        sa.Column("search_type", sa.String(length=32), nullable=False, server_default="manual_url"),
        sa.Column("search_url", sa.Text(), nullable=True),
        sa.Column("seed_text", sa.Text(), nullable=True),
        sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("listing_limit", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("progress_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("listings_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("listings_done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("listings_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("approved_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("manual_review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("excel_path", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_laundry_scan_jobs_status", "laundry_scan_jobs", ["status"])

    op.create_table(
        "laundry_scan_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_server_now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_server_now(), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("laundry_scan_jobs.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("listing_index", sa.Integer(), nullable=True),
        sa.Column("listing_url", sa.Text(), nullable=True),
        sa.Column("step_key", sa.String(length=64), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("error_type", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )

    op.create_table(
        "laundry_generated_memos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_server_now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_server_now(), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("laundry_properties.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("laundry_analyses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="ic_memo"),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("polished", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.create_table(
        "laundry_exports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_server_now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_server_now(), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("laundry_scan_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("laundry_properties.id", ondelete="SET NULL"), nullable=True),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )

    op.create_table(
        "laundry_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_server_now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_server_now(), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=True, index=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )

    op.create_table(
        "laundry_duplicates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_server_now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_server_now(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False, index=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("laundry_properties.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("dedupe_key", "property_id", name="uq_laundry_dup_key_pid"),
    )

    op.create_table(
        "laundry_errors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_server_now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_server_now(), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("laundry_scan_jobs.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("listing_url", sa.Text(), nullable=True),
        sa.Column("error_type", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("traceback", sa.Text(), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
    )

    op.create_table(
        "laundry_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_server_now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_server_now(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False, unique=True, server_default="default"),
        sa.Column("overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("notes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("laundry_settings")
    op.drop_table("laundry_errors")
    op.drop_table("laundry_duplicates")
    op.drop_table("laundry_audit_logs")
    op.drop_table("laundry_exports")
    op.drop_table("laundry_generated_memos")
    op.drop_table("laundry_scan_steps")
    op.drop_index("ix_laundry_scan_jobs_status", table_name="laundry_scan_jobs")
    op.drop_table("laundry_scan_jobs")
    op.drop_table("laundry_analyses")
    op.drop_index("ix_laundry_properties_deleted_at", table_name="laundry_properties")
    op.drop_index("ix_laundry_properties_dedupe_key", table_name="laundry_properties")
    op.drop_index("ix_laundry_properties_deal_status", table_name="laundry_properties")
    op.drop_table("laundry_properties")
