"""
End-to-end underwriting pipeline.

Imports domain logic from the repository root (`economics`, `scoring`, etc.)
by injecting that directory into `sys.path` at runtime.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.memo_service import memo_service
from app.ai.extraction import extract_listing
from app.models.property import Analysis, Property
from app.services.property_normalization import (
    assign_deal_status,
    clean_property_data,
    generate_rejection_note,
    is_valid_property_data,
)
from app.scanners.idealista import scrape_listing_text, scrape_idealista_search_urls

log = structlog.get_logger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from economics import calculate_economics  # noqa: E402
from auto_scoring import calculate_auto_scores  # noqa: E402
from scoring import score_property  # noqa: E402
from location import geocode_address  # noqa: E402


class PipelineService:
    async def run_pipeline(
        self,
        db: AsyncSession,
        data: Dict[str, Any],
        *,
        source: str = "auto",
    ) -> Dict[str, Any]:
        data = clean_property_data(data)
        valid, error = is_valid_property_data(data)
        if not valid:
            return {"success": False, "error": error, "extracted": data}

        full_address = (
            f"{data.get('address') or data.get('neighbourhood') or data.get('city')}, "
            f"{data.get('city')}, Spain"
        )
        coordinates = geocode_address(full_address)
        data["latitude"] = coordinates["lat"]
        data["longitude"] = coordinates["lng"]

        economics = calculate_economics(data)
        auto_scores = calculate_auto_scores(data, economics)
        final_score = score_property(
            {
                "extracted": data,
                "economics": economics,
                "auto_scores": auto_scores,
            }
        )
        deal_status = assign_deal_status(final_score)

        prop = Property(
            source=source,
            listing_url=data.get("listing_url"),
            address=data.get("address"),
            city=data.get("city"),
            neighbourhood=data.get("neighbourhood"),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            gba_m2=data.get("gba_m2"),
            asking_price=data.get("asking_price"),
            asking_rent_month=data.get("asking_rent_month"),
            rent_per_m2=data.get("rent_per_m2"),
            ceiling_height=data.get("ceiling_height"),
            loading_access=data.get("loading_access"),
            access_type=data.get("access_type"),
            floor_level=data.get("floor_level"),
            building_type=data.get("building_type"),
            current_use=data.get("current_use"),
            description=data.get("description"),
            score=final_score.get("score"),
            verdict=final_score.get("verdict"),
            classification=final_score.get("classification"),
            status="analysed",
            deal_status=deal_status,
        )
        db.add(prop)
        await db.flush()

        property_insert = {
            **{c.name: getattr(prop, c.name) for c in prop.__table__.columns},
            "id": str(prop.id),
        }

        if deal_status in ("approved_candidate", "manual_review"):
            memo_text = await memo_service.generate_ic_memo(
                property_data={**property_insert, "id": str(prop.id)},
                economics=economics,
                score=final_score,
            )
        else:
            memo_text = generate_rejection_note(
                property_data={**property_insert, "id": str(prop.id)},
                economics=economics,
                score=final_score,
            )

        enriched_score = dict(final_score)
        if isinstance(auto_scores, dict) and "auto_scores" in auto_scores:
            enriched_score.setdefault("auto_scores", auto_scores.get("auto_scores"))

        analysis = Analysis(
            property_id=prop.id,
            input=data,
            economics=economics,
            score=enriched_score,
            verdict=final_score.get("verdict"),
            classification=final_score.get("classification"),
            deal_killer=final_score.get("deal_killer"),
            ic_memo=memo_text,
        )
        db.add(analysis)

        await db.flush()
        await db.refresh(prop)

        return {
            "property_id": str(prop.id),
            "extracted": data,
            "coordinates": coordinates,
            "auto_scores": auto_scores,
            "economics": economics,
            "score": final_score,
            "deal_status": deal_status,
            "ic_memo": memo_text,
        }

    async def analyse_url(self, db: AsyncSession, url: str) -> Dict[str, Any]:
        scraped = scrape_listing_text(url)
        if not scraped.get("success"):
            return scraped
        raw_text = scraped.get("raw_text", "")
        data = extract_listing(raw_text)
        data["listing_url"] = url
        result = await self.run_pipeline(db, data, source="url_auto")
        result["scrape_preview"] = raw_text[:1000]
        result["source_url"] = url
        return result

    async def analyse_text(self, db: AsyncSession, raw_text: str) -> Dict[str, Any]:
        data = extract_listing(raw_text)
        return await self.run_pipeline(db, data, source="text_auto")


def split_scan_results(results: List[dict]) -> Dict[str, Any]:
    successful_results = [
        r
        for r in results
        if isinstance(r, dict) and r.get("property_id") and r.get("score")
    ]
    failed_results = [
        r
        for r in results
        if not (isinstance(r, dict) and r.get("property_id") and r.get("score"))
    ]
    approved_candidates = [
        r for r in successful_results if r.get("deal_status") == "approved_candidate"
    ]
    manual_review_deals = [
        r for r in successful_results if r.get("deal_status") == "manual_review"
    ]
    rejected_deals = [
        r for r in successful_results if r.get("deal_status") == "rejected"
    ]
    top_deals = approved_candidates + manual_review_deals
    rejected_history = failed_results + rejected_deals
    return {
        "successful_results": successful_results,
        "failed_results": failed_results,
        "approved_candidates": approved_candidates,
        "manual_review_deals": manual_review_deals,
        "top_deals": top_deals,
        "rejected_deals": rejected_deals,
        "rejected_history": rejected_history,
    }


pipeline_service = PipelineService()

__all__ = ["pipeline_service", "split_scan_results"]
