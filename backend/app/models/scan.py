"""Batch scans (Idealista sweeps)."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Scan(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "scans"

    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    search_url: Mapped[str] = mapped_column(Text, nullable=False)
    filters: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False, index=True
    )  # pending | running | completed | failed
    scanned_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    excel_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    items: Mapped[List["ScanHistory"]] = relationship(
        "ScanHistory",
        back_populates="scan",
        cascade="all, delete-orphan",
        order_by="ScanHistory.order_index",
    )


class ScanHistory(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "scan_history"

    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    scan: Mapped["Scan"] = relationship("Scan", back_populates="items")
