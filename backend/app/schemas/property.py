"""Property / analysis API shapes (API ↔ DB boundary)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AnalysePayload(BaseModel):
    url: Optional[str] = None
    text: Optional[str] = Field(None, description="Raw listing text")
    raw_text: Optional[str] = None

    model_config = {"extra": "ignore"}


class NoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=50_000)


class NoteOut(BaseModel):
    id: UUID
    property_id: UUID
    user_id: Optional[UUID]
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AnalysisOut(BaseModel):
    id: UUID
    property_id: UUID
    economics: Dict[str, Any]
    score: Dict[str, Any]
    verdict: Optional[str]
    classification: Optional[str]
    deal_killer: Optional[str]
    ic_memo: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class PropertyOut(BaseModel):
    id: UUID
    source: Optional[str]
    listing_url: Optional[str]
    address: Optional[str]
    city: Optional[str]
    neighbourhood: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    gba_m2: Optional[float]
    asking_price: Optional[float]
    asking_rent_month: Optional[float]
    rent_per_m2: Optional[float]
    score: Optional[int]
    verdict: Optional[str]
    classification: Optional[str]
    status: str
    deal_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PropertyDetailResponse(BaseModel):
    success: bool = True
    property: PropertyOut
    latest_analysis: Optional[AnalysisOut] = None
