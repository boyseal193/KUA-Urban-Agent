"""Property + analysis (replaces Supabase `properties` / `analyses`)."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Property(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "properties"

    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    listing_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True, default="Barcelona")
    neighbourhood: Mapped[str | None] = mapped_column(String(128), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    gba_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    asking_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    asking_rent_month: Mapped[float | None] = mapped_column(Float, nullable=True)
    rent_per_m2: Mapped[float | None] = mapped_column(Float, nullable=True)

    ceiling_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    loading_access: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    access_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    floor_level: Mapped[str | None] = mapped_column(String(128), nullable=True)
    building_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    current_use: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verdict: Mapped[str | None] = mapped_column(String(32), nullable=True)
    classification: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="analysed", nullable=False)
    deal_status: Mapped[str] = mapped_column(String(32), default="manual_review", index=True)

    analyses: Mapped[List["Analysis"]] = relationship(
        "Analysis",
        back_populates="property",
        cascade="all, delete-orphan",
    )


class Analysis(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "analyses"

    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    input: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    economics: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    score: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    verdict: Mapped[str | None] = mapped_column(String(32), nullable=True)
    classification: Mapped[str | None] = mapped_column(String(128), nullable=True)
    deal_killer: Mapped[str | None] = mapped_column(Text, nullable=True)
    ic_memo: Mapped[str | None] = mapped_column(Text, nullable=True)

    property: Mapped["Property"] = relationship("Property", back_populates="analyses")
