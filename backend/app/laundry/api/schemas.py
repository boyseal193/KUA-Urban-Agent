"""Pydantic request/response models for the laundry vertical."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


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
    """Operator-facing scan request (matches the UI "Scan Options" panel).

    Field names mirror the modern operator vocabulary
    (``listing_url`` / ``raw_listing_text`` / ``run_in_background`` /
    ``llm_memo_polish``). The legacy names from the first frontend release
    (``search_url`` / ``seed_text`` / ``async_mode`` / ``polish_with_llm``)
    are still accepted via ``AliasChoices`` so deployed clients never break.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    property_type: Optional[PropertyTypeLiteral] = Field(default=None)
    acquisition_type: Optional[AcquisitionTypeLiteral] = Field(default=None)
    search_type: SearchTypeLiteral = Field(default="manual_url")

    listing_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("listing_url", "search_url", "url"),
        description="Listing URL, area / search-results URL, or seed page for automatic scans.",
    )
    raw_listing_text: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("raw_listing_text", "seed_text", "text"),
        description="Optional raw listing text — used when no scrapable URL is available.",
    )

    listing_limit: int = Field(default=20, ge=1, le=200)
    run_in_background: bool = Field(
        default=True,
        validation_alias=AliasChoices("run_in_background", "async_mode"),
        description="Queue the scan on the ARQ worker. Disable only for very small inline jobs.",
    )
    llm_memo_polish: bool = Field(
        default=False,
        validation_alias=AliasChoices("llm_memo_polish", "polish_with_llm"),
    )

    # Filters that constrain which listings reach the underwriter
    neighbourhood_filters: List[str] = Field(
        default_factory=list,
        description="If set, only listings whose city or neighbourhood matches one of these "
        "strings (case-insensitive substring) are processed.",
    )
    max_size_sqm: Optional[float] = Field(
        default=None,
        ge=0,
        description="Hard upper limit on floor area. Right-sized urban laundromats sit around "
        "60-80 m²; oversized properties are still analysed but flagged as oversized.",
    )

    # Free-form bag the underwriter can read directly
    filters: Dict[str, Any] = Field(default_factory=dict)
    overrides: Dict[str, Any] = Field(default_factory=dict)
    scoring_overrides: Dict[str, Any] = Field(
        default_factory=dict,
        description="Shorthand to override only the scoring weights / thresholds. "
        "Merged into ``overrides.scoring_weights`` / ``overrides.thresholds`` automatically.",
    )

    @model_validator(mode="after")
    def _absorb_into_filters_and_overrides(self) -> "ScanLaunchPayload":
        if self.neighbourhood_filters:
            self.filters.setdefault("neighbourhood_filters", self.neighbourhood_filters)
        if self.max_size_sqm is not None:
            self.filters.setdefault("max_size_sqm", self.max_size_sqm)
        if self.scoring_overrides:
            sw = self.scoring_overrides.get("scoring_weights")
            th = self.scoring_overrides.get("thresholds")
            if sw:
                self.overrides.setdefault("scoring_weights", {}).update(sw)
            if th:
                self.overrides.setdefault("thresholds", {}).update(th)
            # Any other top-level keys (e.g. business_profile) propagate as-is.
            for k, v in self.scoring_overrides.items():
                if k in ("scoring_weights", "thresholds"):
                    continue
                self.overrides.setdefault(k, v)
        return self

    # Convenience accessors so legacy call sites keep working ------------------
    @property
    def search_url(self) -> Optional[str]:  # pragma: no cover — alias
        return self.listing_url

    @property
    def seed_text(self) -> Optional[str]:  # pragma: no cover — alias
        return self.raw_listing_text

    @property
    def async_mode(self) -> bool:  # pragma: no cover — alias
        return self.run_in_background

    @property
    def polish_with_llm(self) -> bool:  # pragma: no cover — alias
        return self.llm_memo_polish


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
    filters: Dict[str, Any] = Field(default_factory=dict)
    polish_with_llm: bool = False


class ExportRequest(BaseModel):
    format: Literal["excel", "csv", "json", "zip", "memo", "financial_model", "full_package"]


class BulkRescoreRequest(BaseModel):
    deal_statuses: List[str] = Field(default_factory=lambda: ["manual_review", "approved_candidate"])
    limit: int = Field(default=100, ge=1, le=1000)


class SettingsPayload(BaseModel):
    overrides: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None
