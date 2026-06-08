"""Pydantic request/response models for the laundry vertical."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


PropertyTypeLiteral = Literal[
    "existing_laundromat",
    "empty_commercial",
    "retail",
    "mixed_use",
    "industrial",
]
AcquisitionTypeLiteral = Literal["buy", "rent"]
SearchTypeLiteral = Literal["automatic_scan", "manual_url", "area_search"]


class ScanLaunchPayload(BaseModel):
    """Operator-facing scan request (matches the UI "Scan Options" panel)."""

    property_type: Optional[PropertyTypeLiteral] = Field(default=None)
    acquisition_type: Optional[AcquisitionTypeLiteral] = Field(default=None)
    search_type: SearchTypeLiteral = Field(default="manual_url")
    search_url: Optional[str] = Field(default=None, description="Listing or search-results URL")
    seed_text: Optional[str] = Field(default=None, description="Raw listing text for text-based scans")
    filters: Dict[str, Any] = Field(default_factory=dict)
    overrides: Dict[str, Any] = Field(default_factory=dict)
    listing_limit: int = Field(default=20, ge=1, le=200)
    async_mode: bool = Field(default=True, description="Run via ARQ worker (default true)")
    polish_with_llm: bool = Field(default=False)


class ScanJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    search_type: str
    property_type: Optional[str]
    acquisition_type: Optional[str]
    search_url: Optional[str]
    listing_limit: int
    progress_pct: float
    listings_total: int
    listings_done: int
    listings_failed: int
    approved_count: int
    manual_review_count: int
    rejected_count: int
    excel_path: Optional[str]
    error_message: Optional[str]
    created_at: Optional[Any] = None
    started_at: Optional[Any] = None
    finished_at: Optional[Any] = None


class PropertyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: Optional[str]
    listing_url: Optional[str]
    address: Optional[str]
    city: Optional[str]
    neighbourhood: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    property_type: Optional[str]
    acquisition_type: Optional[str]
    floor_area_m2: Optional[float]
    asking_price: Optional[float]
    asking_rent_month: Optional[float]
    washer_count: Optional[int]
    dryer_count: Optional[int]
    score: Optional[int]
    verdict: Optional[str]
    classification: Optional[str]
    confidence_band: Optional[str]
    deal_status: str
    status: str
    created_at: Optional[Any] = None
    deleted_at: Optional[Any] = None


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    property_id: UUID
    input: Dict[str, Any]
    location: Dict[str, Any]
    economics: Dict[str, Any]
    score: Dict[str, Any]
    due_diligence: Dict[str, Any]
    assumptions_used: Dict[str, Any]
    verdict: Optional[str]
    classification: Optional[str]
    deal_killer: Optional[str]
    ic_memo: Optional[str]
    created_at: Optional[Any] = None


class PropertyDetailResponse(BaseModel):
    success: bool = True
    property: PropertyOut
    latest_analysis: Optional[AnalysisOut] = None


class AnalyseInlinePayload(BaseModel):
    url: Optional[str] = None
    text: Optional[str] = None
    overrides: Dict[str, Any] = Field(default_factory=dict)
    polish_with_llm: bool = False


class ExportRequest(BaseModel):
    format: Literal["excel", "csv", "json", "zip", "memo", "financial_model", "full_package"]


class BulkRescoreRequest(BaseModel):
    deal_statuses: List[str] = Field(default_factory=lambda: ["manual_review", "approved_candidate"])
    limit: int = Field(default=100, ge=1, le=1000)


class SettingsPayload(BaseModel):
    overrides: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None
