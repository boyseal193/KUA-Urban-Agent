"""Scan batch schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ScanIdealistaPayload(BaseModel):
    search_url: str
    limit: int = Field(default=10, ge=1, le=200)
    generate_excel: bool = True
    filters_used: Dict[str, Any] = Field(default_factory=dict)
    async_mode: bool = Field(
        default=False,
        description="If true, enqueue background job and return scan_id for WebSocket feed",
    )


class ScanIdealistaAutoPayload(BaseModel):
    city_slug: str = "barcelona-barcelona"
    max_price: int = 1_000_000
    min_m2: int = 200
    max_m2: int = 300
    property_types: list[str] = Field(default_factory=lambda: ["locales", "naves"])
    ground_floor_only: bool = True
    sale_only: bool = True
    limit: int = 10
    generate_excel: bool = True
    async_mode: bool = False


class ScanJobStarted(BaseModel):
    success: bool = True
    scan_id: UUID
    websocket_url: str
    message: str = "Scan enqueued; subscribe to websocket for live updates"


class ScanStatusOut(BaseModel):
    id: UUID
    status: str
    scanned_count: int
    search_url: str
    error_message: Optional[str]
    excel_path: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
