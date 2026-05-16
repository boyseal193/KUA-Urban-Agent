"""Optional pipeline audit trail per property."""
from __future__ import annotations

import uuid
from typing import Any, Dict

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PipelineStatusRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "pipeline_status"

    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    data: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
