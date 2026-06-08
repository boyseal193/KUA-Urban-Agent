"""
SQLAlchemy models for the laundry vertical.

All tables are prefixed ``laundry_`` so they never collide with the storage
tables (``properties`` / ``analyses`` / ``scans`` etc.) created by
:mod:`app.models`. The models share the same ``Base`` declarative metadata so
``Base.metadata.create_all`` and the existing Alembic migration script will
both pick them up.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class LaundryProperty(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "laundry_properties"
    __table_args__ = (
        Index("ix_laundry_properties_deal_status", "deal_status"),
        Index("ix_laundry_properties_dedupe_key", "dedupe_key"),
    )

    source: Mapped[Optional[str]] = mapped_column(String(64))
    listing_url: Mapped[Optional[str]] = mapped_column(Text)
    address: Mapped[Optional[str]] = mapped_column(Text)
    city: Mapped[Optional[str]] = mapped_column(String(128))
    neighbourhood: Mapped[Optional[str]] = mapped_column(String(128))
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)

    property_type: Mapped[Optional[str]] = mapped_column(String(64))         # existing_laundromat | empty_commercial | retail | mixed_use | industrial
    acquisition_type: Mapped[Optional[str]] = mapped_column(String(16))      # buy | rent

    floor_area_m2: Mapped[Optional[float]] = mapped_column(Float)
    ceiling_height: Mapped[Optional[float]] = mapped_column(Float)
    asking_price: Mapped[Optional[float]] = mapped_column(Float)
    asking_rent_month: Mapped[Optional[float]] = mapped_column(Float)
    rent_per_m2: Mapped[Optional[float]] = mapped_column(Float)

    washer_count: Mapped[Optional[int]] = mapped_column(Integer)
    dryer_count: Mapped[Optional[int]] = mapped_column(Integer)

    ground_floor: Mapped[Optional[bool]] = mapped_column(Boolean)
    loading_access: Mapped[Optional[bool]] = mapped_column(Boolean)
    corner_unit: Mapped[Optional[bool]] = mapped_column(Boolean)
    water_available: Mapped[Optional[bool]] = mapped_column(Boolean)
    gas_available: Mapped[Optional[bool]] = mapped_column(Boolean)
    drainage_available: Mapped[Optional[bool]] = mapped_column(Boolean)
    three_phase_power: Mapped[Optional[bool]] = mapped_column(Boolean)

    description: Mapped[Optional[str]] = mapped_column(Text)

    score: Mapped[Optional[int]] = mapped_column(Integer)
    verdict: Mapped[Optional[str]] = mapped_column(String(64))
    classification: Mapped[Optional[str]] = mapped_column(String(64))
    confidence_band: Mapped[Optional[str]] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), default="analysed", nullable=False)
    deal_status: Mapped[str] = mapped_column(String(32), default="manual_review", nullable=False)

    dedupe_key: Mapped[Optional[str]] = mapped_column(String(64))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    deletion_reason: Mapped[Optional[str]] = mapped_column(Text)

    analyses: Mapped[List["LaundryAnalysis"]] = relationship(
        "LaundryAnalysis",
        back_populates="property",
        cascade="all, delete-orphan",
    )


class LaundryAnalysis(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "laundry_analyses"

    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("laundry_properties.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    input: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    location: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    economics: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    score: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    due_diligence: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    assumptions_used: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    verdict: Mapped[Optional[str]] = mapped_column(String(64))
    classification: Mapped[Optional[str]] = mapped_column(String(64))
    deal_killer: Mapped[Optional[str]] = mapped_column(Text)
    ic_memo: Mapped[Optional[str]] = mapped_column(Text)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    property: Mapped[LaundryProperty] = relationship("LaundryProperty", back_populates="analyses")


class LaundryScanJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "laundry_scan_jobs"

    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    job_type: Mapped[str] = mapped_column(String(32), default="area_search", nullable=False)
    property_type: Mapped[Optional[str]] = mapped_column(String(32))    # existing_laundromat | empty_commercial | retail | mixed_use
    acquisition_type: Mapped[Optional[str]] = mapped_column(String(16))  # buy | rent
    search_type: Mapped[str] = mapped_column(String(32), default="manual_url", nullable=False)  # automatic_scan | manual_url | area_search

    search_url: Mapped[Optional[str]] = mapped_column(Text)
    seed_text: Mapped[Optional[str]] = mapped_column(Text)
    filters: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    overrides: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    listing_limit: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    listings_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    listings_done: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    listings_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    approved_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    manual_review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    excel_path: Mapped[Optional[str]] = mapped_column(Text)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    steps: Mapped[List["LaundryScanStep"]] = relationship(
        "LaundryScanStep",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="LaundryScanStep.step_order",
    )


class LaundryScanStep(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "laundry_scan_steps"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("laundry_scan_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    listing_index: Mapped[Optional[int]] = mapped_column(Integer)
    listing_url: Mapped[Optional[str]] = mapped_column(Text)
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)

    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    error_type: Mapped[Optional[str]] = mapped_column(String(64))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    retryable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    job: Mapped[LaundryScanJob] = relationship("LaundryScanJob", back_populates="steps")


class LaundryGeneratedMemo(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "laundry_generated_memos"

    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("laundry_properties.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    analysis_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("laundry_analyses.id", ondelete="SET NULL"),
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(String(32), default="ic_memo", nullable=False)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    polished: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class LaundryExport(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "laundry_exports"

    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("laundry_scan_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    property_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("laundry_properties.id", ondelete="SET NULL"),
        nullable=True,
    )
    format: Mapped[str] = mapped_column(String(16), nullable=False)  # excel | csv | json | zip | memo | financial_model | full_package
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class LaundryAuditLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "laundry_audit_logs"

    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class LaundryDuplicate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "laundry_duplicates"
    __table_args__ = (
        UniqueConstraint("dedupe_key", "property_id", name="uq_laundry_dup_key_pid"),
    )

    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("laundry_properties.id", ondelete="CASCADE"),
        nullable=False,
    )


class LaundryError(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "laundry_errors"

    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("laundry_scan_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    listing_url: Mapped[Optional[str]] = mapped_column(Text)
    error_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    traceback: Mapped[Optional[str]] = mapped_column(Text)
    retryable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class LaundrySettings(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Operator-level overrides (one row per workspace; we use a singleton)."""

    __tablename__ = "laundry_settings"

    name: Mapped[str] = mapped_column(String(64), default="default", unique=True, nullable=False)
    overrides: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    notes: Mapped[Optional[str]] = mapped_column(Text)


__all__ = [
    "LaundryProperty",
    "LaundryAnalysis",
    "LaundryScanJob",
    "LaundryScanStep",
    "LaundryGeneratedMemo",
    "LaundryExport",
    "LaundryAuditLog",
    "LaundryDuplicate",
    "LaundryError",
    "LaundrySettings",
]
