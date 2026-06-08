"""End-to-end underwriting pipeline for a single laundromat listing.

Orchestration order:
    1. Fetch raw text (URL → scrape, raw text → passthrough)
    2. Extract fields (heuristic + optional LLM)
    3. Normalize
    4. Geocode + location intel
    5. Economics
    6. Score
    7. Due diligence
    8. Memo (Markdown)
    9. Persist (laundry_properties + laundry_analyses)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from laundry import (
    due_diligence as dd_mod,
    economics as econ_mod,
    extraction,
    location as loc_mod,
    memo as memo_mod,
    normalization,
    scanner,
    scoring as scoring_mod,
    store,
)

log = logging.getLogger("kua.laundry.pipeline")


def _matches_neighbourhood_filter(extracted: Dict[str, Any], location: Dict[str, Any],
                                    filters: Dict[str, Any]) -> bool:
    requested = [n.strip().lower() for n in (filters.get("neighbourhood_filters") or []) if n]
    if not requested: return True
    candidates = " ".join(
        str(v or "").lower() for v in (
            extracted.get("neighbourhood"), extracted.get("address"),
            location.get("neighbourhood"), location.get("matched_preferred_neighbourhood"),
        )
    )
    return any(r in candidates for r in requested)


def analyse_listing(
    *,
    raw_text: str,
    listing_url: Optional[str] = None,
    source: str = "manual_text",
    overrides: Optional[Dict[str, Any]] = None,
    filters: Optional[Dict[str, Any]] = None,
    use_llm: bool = True,
    job_id: Optional[str] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    overrides = overrides or {}
    filters = filters or {}

    extracted = normalization.normalize_extracted(extraction.extract_from_text(raw_text or "", use_llm=use_llm))

    if filters.get("property_type"):
        extracted["property_type"] = extracted.get("property_type") or filters["property_type"]
    if filters.get("acquisition_type"):
        extracted["acquisition_type"] = extracted.get("acquisition_type") or filters["acquisition_type"]

    coords = None
    if extracted.get("address"):
        coords = loc_mod.geocode(extracted["address"], city=extracted.get("city") or "Barcelona")
    lat, lng = (coords if coords else (None, None))

    location = loc_mod.gather_location_intel(
        lat=lat, lng=lng,
        address=extracted.get("address"),
        city=extracted.get("city"),
        neighbourhood=extracted.get("neighbourhood"),
    )

    if not _matches_neighbourhood_filter(extracted, location, filters):
        return {
            "success": True, "skipped": True,
            "reason": "neighbourhood_filter_no_match",
            "extracted": extracted, "location": location,
        }

    enriched_extracted = dict(extracted)
    enriched_extracted["_location"] = location
    economics = econ_mod.calculate_economics(enriched_extracted, overrides=overrides)

    scoring = scoring_mod.score_property(
        {"extracted": extracted, "location": location, "economics": economics},
        overrides=overrides, filters=filters,
    )

    due_diligence = dd_mod.build_due_diligence(
        extracted=extracted, economics=economics, scoring=scoring, location=location
    )

    memo_md = memo_mod.generate_ic_memo(
        extracted=extracted, economics=economics, scoring=scoring,
        location=location, due_diligence=due_diligence,
    )

    result: Dict[str, Any] = {
        "success": True, "skipped": False,
        "extracted": extracted, "location": location, "economics": economics,
        "scoring": scoring, "due_diligence": due_diligence, "memo_md": memo_md,
    }

    if persist:
        dedupe = normalization.make_dedupe_key(
            listing_url=listing_url, address=extracted.get("address"),
            city=extracted.get("city"), floor_area_m2=extracted.get("floor_area_m2"),
        )
        ok, prop, err = store.upsert_property(
            extracted=extracted, economics=economics, scoring=scoring, location=location,
            dedupe_key=dedupe, listing_url=listing_url, source=source, job_id=job_id,
        )
        if ok and prop:
            result["property_id"] = prop["id"]
            result["duplicate"] = prop.get("duplicate", False)
            ana_ok, ana_id, ana_err = store.insert_analysis(
                property_id=prop["id"], extracted=extracted, economics=economics,
                scoring=scoring, location=location, due_diligence=due_diligence,
                memo_md=memo_md, assumptions_version=economics.get("assumptions_version", "2.0.0"),
            )
            if ana_ok: result["analysis_id"] = ana_id
            else: result["persist_warning"] = ana_err
        else:
            result["persist_warning"] = err or "property_upsert_failed"

    return result


def analyse_url(*, url: str, overrides=None, filters=None,
                 use_llm: bool = True, job_id: Optional[str] = None,
                 persist: bool = True) -> Dict[str, Any]:
    fetched = scanner.fetch_listing_text(url)
    if not fetched.get("success"):
        return {"success": False, "error": fetched.get("error") or "scrape_failed", "url": url}
    return analyse_listing(
        raw_text=fetched.get("raw_text") or "",
        listing_url=url, source="url_scan",
        overrides=overrides, filters=filters,
        use_llm=use_llm, job_id=job_id, persist=persist,
    )


def analyse_area(*, search_url: str, limit: int = 20, overrides=None,
                  filters=None, job_id: Optional[str] = None) -> Dict[str, Any]:
    urls = scanner.discover_listing_urls(search_url, limit=limit)
    results = []
    approved = manual = rejected = failed = skipped = 0
    for url in urls:
        try:
            res = analyse_url(url=url, overrides=overrides, filters=filters,
                              job_id=job_id, persist=True)
            results.append(res)
            if not res.get("success"): failed += 1; continue
            if res.get("skipped"): skipped += 1; continue
            ds = (res.get("scoring") or {}).get("deal_status")
            if ds == "approved_candidate": approved += 1
            elif ds == "manual_review": manual += 1
            else: rejected += 1
        except Exception as exc:
            log.exception("Area analyse failed for %s: %s", url, exc)
            failed += 1
            results.append({"success": False, "url": url, "error": str(exc)})
    return {
        "success": True, "search_url": search_url,
        "discovered_count": len(urls), "results": results,
        "summary": {
            "approved": approved, "manual_review": manual,
            "rejected": rejected, "skipped": skipped, "failed": failed,
        },
    }
