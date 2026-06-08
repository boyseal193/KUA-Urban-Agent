"""
End-to-end laundromat underwriting pipeline.

One ``analyse_listing`` call:

1. cleans / validates the extracted data
2. geocodes + pulls live location intel (Nominatim + Overpass; falls back to defaults)
3. runs the deterministic financial model
4. runs the scoring engine
5. builds the SWOT + due-diligence
6. renders the IC memo
7. persists everything to the laundry_* tables
8. tracks duplicates so re-scans surface them in the admin panel
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.laundry.ai.due_diligence import build_due_diligence
from app.laundry.ai.extraction import extract_listing
from app.laundry.ai.memo import generate_ic_memo, generate_rejection_note, llm_polish
from app.laundry.assumptions import default_assumptions, merge_overrides
from app.laundry.economics import calculate_economics
from app.laundry.models import LaundryAnalysis, LaundryProperty
from app.laundry.repository import (
    add_export,  # noqa: F401 (re-export-friendly)
    audit,
    get_property_by_dedupe_key,
    record_duplicate,
    save_memo,
)
from app.laundry.scanners.web import scrape_listing_text
from app.laundry.scoring import score_property
from app.laundry.services.location_service import gather_location_intel, geocode
from app.laundry.services.normalization import (
    assign_deal_status,
    clean_listing,
    dedupe_key,
    is_valid_listing,
)

log = structlog.get_logger(__name__)


class LaundryPipelineService:
    async def analyse_listing(
        self,
        db: AsyncSession,
        data: Dict[str, Any],
        *,
        source: str = "url_auto",
        overrides: Optional[Dict[str, Any]] = None,
        user_id: Optional[UUID] = None,
        polish_with_llm: bool = False,
    ) -> Dict[str, Any]:
        """Underwrite one listing and persist the full result."""
        cleaned = clean_listing(data)
        valid, error = is_valid_listing(cleaned)
        if not valid:
            return {"success": False, "error": error, "extracted": cleaned}

        # --- Geocode + location intel --------------------------------------
        address = " ".join(
            [
                cleaned.get("address") or "",
                cleaned.get("neighbourhood") or "",
                cleaned.get("city") or "",
            ]
        ).strip(", ")
        coords = await geocode(address, city=cleaned.get("city")) if address else {"lat": None, "lng": None}
        cleaned["latitude"] = coords["lat"]
        cleaned["longitude"] = coords["lng"]

        location = await gather_location_intel(
            lat=coords["lat"],
            lng=coords["lng"],
            neighbourhood=cleaned.get("neighbourhood"),
            city=cleaned.get("city"),
        )

        # --- Financial model + scoring -------------------------------------
        economics = calculate_economics(cleaned, overrides=overrides)
        score_result = score_property(
            {
                "extracted": cleaned,
                "location": location,
                "economics": economics,
            },
            overrides=overrides,
        )

        deal_status = assign_deal_status(score_result)

        # --- Due-diligence + memo ------------------------------------------
        due_diligence = build_due_diligence(
            property_data=cleaned,
            economics=economics,
            score_result=score_result,
            location=location,
        )

        if deal_status in ("approved_candidate", "manual_review"):
            memo_md = generate_ic_memo(
                property_data=cleaned,
                economics=economics,
                score=score_result,
                due_diligence=due_diligence,
            )
            if polish_with_llm:
                memo_md = await llm_polish(memo_md)
        else:
            memo_md = generate_rejection_note(
                property_data=cleaned,
                economics=economics,
                score=score_result,
            )

        # --- Persist -------------------------------------------------------
        dup_key = dedupe_key(cleaned)
        duplicate_hit = await get_property_by_dedupe_key(db, dup_key)

        property_obj = LaundryProperty(
            source=source,
            listing_url=cleaned.get("listing_url"),
            address=cleaned.get("address"),
            city=cleaned.get("city"),
            neighbourhood=cleaned.get("neighbourhood"),
            latitude=cleaned.get("latitude"),
            longitude=cleaned.get("longitude"),
            property_type=cleaned.get("property_type"),
            acquisition_type=cleaned.get("acquisition_type"),
            floor_area_m2=cleaned.get("floor_area_m2"),
            ceiling_height=cleaned.get("ceiling_height"),
            asking_price=cleaned.get("asking_price"),
            asking_rent_month=cleaned.get("asking_rent_month"),
            rent_per_m2=(
                round((cleaned.get("asking_rent_month") or 0) / (cleaned.get("floor_area_m2") or 1), 2)
                if cleaned.get("asking_rent_month") and cleaned.get("floor_area_m2")
                else None
            ),
            washer_count=cleaned.get("washer_count"),
            dryer_count=cleaned.get("dryer_count"),
            ground_floor=cleaned.get("ground_floor"),
            loading_access=cleaned.get("loading_access"),
            corner_unit=cleaned.get("corner_unit"),
            water_available=cleaned.get("water_available"),
            gas_available=cleaned.get("gas_available"),
            drainage_available=cleaned.get("drainage_available"),
            three_phase_power=cleaned.get("three_phase_power"),
            description=cleaned.get("description"),
            score=score_result.get("score"),
            verdict=score_result.get("verdict"),
            classification=score_result.get("classification"),
            confidence_band=score_result.get("confidence", {}).get("band"),
            status="analysed",
            deal_status=deal_status,
            dedupe_key=dup_key,
        )
        db.add(property_obj)
        await db.flush()

        analysis = LaundryAnalysis(
            property_id=property_obj.id,
            input=cleaned,
            location=location,
            economics=economics,
            score=score_result,
            due_diligence=due_diligence,
            assumptions_used=merge_overrides(default_assumptions(), overrides).to_dict(),
            verdict=score_result.get("verdict"),
            classification=score_result.get("classification"),
            deal_killer=score_result.get("classification") if deal_status == "rejected" else None,
            ic_memo=memo_md,
        )
        db.add(analysis)
        await db.flush()

        await save_memo(
            db,
            property_id=property_obj.id,
            analysis_id=analysis.id,
            markdown=memo_md,
            polished=polish_with_llm,
        )

        if duplicate_hit and duplicate_hit.id != property_obj.id:
            await record_duplicate(db, dedupe_key=dup_key, property_id=duplicate_hit.id)
            await record_duplicate(db, dedupe_key=dup_key, property_id=property_obj.id)

        await audit(
            db,
            actor_user_id=user_id,
            action="analyse",
            entity_type="laundry_property",
            entity_id=str(property_obj.id),
            payload={
                "source": source,
                "score": score_result.get("score"),
                "deal_status": deal_status,
            },
        )

        return {
            "success": True,
            "property_id": str(property_obj.id),
            "analysis_id": str(analysis.id),
            "extracted": cleaned,
            "coordinates": coords,
            "location": location,
            "economics": economics,
            "score": score_result,
            "due_diligence": due_diligence,
            "deal_status": deal_status,
            "ic_memo": memo_md,
            "duplicate_of": str(duplicate_hit.id) if duplicate_hit and duplicate_hit.id != property_obj.id else None,
        }

    async def analyse_url(
        self,
        db: AsyncSession,
        url: str,
        *,
        overrides: Optional[Dict[str, Any]] = None,
        user_id: Optional[UUID] = None,
        polish_with_llm: bool = False,
    ) -> Dict[str, Any]:
        scraped = await scrape_listing_text(url)
        if not scraped.get("success"):
            return scraped
        raw_text = scraped.get("raw_text", "")
        extracted = await extract_listing(raw_text)
        extracted["listing_url"] = url
        result = await self.analyse_listing(
            db,
            extracted,
            source="url_auto",
            overrides=overrides,
            user_id=user_id,
            polish_with_llm=polish_with_llm,
        )
        if isinstance(result, dict):
            result["source_url"] = url
            result["scrape_preview"] = raw_text[:1200]
        return result

    async def analyse_text(
        self,
        db: AsyncSession,
        text: str,
        *,
        overrides: Optional[Dict[str, Any]] = None,
        user_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        extracted = await extract_listing(text)
        return await self.analyse_listing(
            db,
            extracted,
            source="text_auto",
            overrides=overrides,
            user_id=user_id,
        )


def split_scan_results(results: list) -> Dict[str, Any]:
    successful = [
        r for r in results
        if isinstance(r, dict) and r.get("property_id")
    ]
    failed = [r for r in results if not (isinstance(r, dict) and r.get("property_id"))]
    approved = [r for r in successful if r.get("deal_status") == "approved_candidate"]
    review = [r for r in successful if r.get("deal_status") == "manual_review"]
    rejected = [r for r in successful if r.get("deal_status") == "rejected"]
    return {
        "successful_results": successful,
        "failed_results": failed,
        "approved_candidates": approved,
        "manual_review_deals": review,
        "top_deals": approved + review,
        "rejected_deals": rejected,
        "rejected_history": failed + rejected,
    }


pipeline_service = LaundryPipelineService()


__all__ = ["LaundryPipelineService", "pipeline_service", "split_scan_results"]
