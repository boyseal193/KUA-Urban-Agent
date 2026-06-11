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

Worker entrypoint for URL scans: ``process_listing_url`` — always produces a
property row (full underwriting or ``extraction_failed`` partial card).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from laundry import (
    cache as laundry_cache,
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

EXTRACTION_FAILED = "extraction_failed"


def _matches_neighbourhood_filter(extracted: Dict[str, Any], location: Dict[str, Any],
                                    filters: Dict[str, Any]) -> bool:
    requested = [n.strip().lower() for n in (filters.get("neighbourhood_filters") or []) if n]
    if not requested:
        return True
    candidates = " ".join(
        str(v or "").lower() for v in (
            extracted.get("neighbourhood"), extracted.get("address"),
            location.get("neighbourhood"), location.get("matched_preferred_neighbourhood"),
        )
    )
    return any(r in candidates for r in requested)


def _log_extracted_fields(job_id: Optional[str], url: Optional[str], extracted: Dict[str, Any]) -> None:
    log.info(
        "pipeline.extracted_fields job_id=%s url=%s address=%s city=%s neighbourhood=%s "
        "size=%s rent=%s price=%s title=%s desc_len=%s",
        job_id,
        url,
        extracted.get("address"),
        extracted.get("city"),
        extracted.get("neighbourhood"),
        extracted.get("floor_area_m2"),
        extracted.get("asking_rent_month"),
        extracted.get("asking_price"),
        (extracted.get("title") or "")[:80] or None,
        len(extracted.get("description") or ""),
    )


def _persist_underwriting(
    *,
    result: Dict[str, Any],
    extracted: Dict[str, Any],
    economics: Dict[str, Any],
    scoring: Dict[str, Any],
    location: Dict[str, Any],
    due_diligence: Dict[str, Any],
    memo_md: str,
    listing_url: Optional[str],
    source: str,
    job_id: Optional[str],
) -> Tuple[bool, Optional[str]]:
    """Write property + analysis rows. Returns (ok, error_message)."""
    dedupe = normalization.make_dedupe_key(
        listing_url=listing_url,
        address=extracted.get("address"),
        city=extracted.get("city"),
        floor_area_m2=extracted.get("floor_area_m2"),
    )
    log.info(
        "pipeline.persist start job_id=%s url=%s dedupe=%s score=%s deal_status=%s",
        job_id,
        listing_url,
        dedupe[:12],
        scoring.get("score"),
        scoring.get("deal_status"),
    )

    ok, prop, err = store.upsert_property(
        extracted=extracted,
        economics=economics,
        scoring=scoring,
        location=location,
        dedupe_key=dedupe,
        listing_url=listing_url,
        source=source,
        job_id=job_id,
    )
    if not ok or not prop:
        msg = err or "property_upsert_failed"
        log.error(
            "pipeline.persist property FAILED job_id=%s url=%s error=%s",
            job_id, listing_url, msg,
        )
        return False, msg

    property_id = prop["id"]
    result["property_id"] = property_id
    result["duplicate"] = prop.get("duplicate", False)
    log.info(
        "pipeline.property_created job_id=%s property_id=%s url=%s duplicate=%s",
        job_id, property_id, listing_url, prop.get("duplicate"),
    )

    ana_ok, ana_id, ana_err = store.insert_analysis(
        property_id=property_id,
        extracted=extracted,
        economics=economics,
        scoring=scoring,
        location=location,
        due_diligence=due_diligence,
        memo_md=memo_md,
        assumptions_version=economics.get("assumptions_version", "2.0.0"),
    )
    if not ana_ok or not ana_id:
        msg = ana_err or "analysis_insert_failed"
        log.error(
            "pipeline.persist analysis FAILED job_id=%s property_id=%s error=%s",
            job_id, property_id, msg,
        )
        result["persist_warning"] = msg
        return False, msg

    result["analysis_id"] = ana_id
    log.info(
        "pipeline.persist complete job_id=%s property_id=%s analysis_id=%s memo_len=%s",
        job_id, property_id, ana_id, len(memo_md or ""),
    )
    return True, None


def _persist_extraction_failed(
    *,
    listing_url: str,
    job_id: Optional[str],
    extracted: Optional[Dict[str, Any]],
    error: Optional[str],
    source: str = "url_scan",
) -> Dict[str, Any]:
    """Create a partial property row when scrape/extraction/underwriting fails."""
    extracted = dict(extracted or {})
    ok, prop, err = store.create_partial_property(
        listing_url=listing_url,
        job_id=job_id,
        extracted=extracted,
        error=error,
        source=source,
    )
    if not ok or not prop:
        log.error(
            "pipeline.extraction_failed persist FAILED job_id=%s url=%s error=%s",
            job_id, listing_url, err,
        )
        return {
            "success": False,
            "extraction_failed": True,
            "url": listing_url,
            "error": err or error or "partial_property_failed",
            "extracted": extracted,
        }

    property_id = prop["id"]
    log.info(
        "pipeline.property_created job_id=%s property_id=%s url=%s status=%s",
        job_id, property_id, listing_url, EXTRACTION_FAILED,
    )
    scoring = {
        "deal_status": EXTRACTION_FAILED,
        "score": 0,
        "verdict": error or "Listing detail could not be extracted",
    }
    return {
        "success": True,
        "extraction_failed": True,
        "property_id": property_id,
        "url": listing_url,
        "error": error,
        "extracted": extracted,
        "scoring": scoring,
    }


def persist_extraction_failed(
    *,
    listing_url: str,
    job_id: Optional[str],
    extracted: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    source: str = "url_scan",
) -> Dict[str, Any]:
    """Public wrapper used by the worker on catastrophic listing errors."""
    return _persist_extraction_failed(
        listing_url=listing_url,
        job_id=job_id,
        extracted=extracted,
        error=error,
        source=source,
    )


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
    html: Optional[str] = None,
) -> Dict[str, Any]:
    overrides = overrides or {}
    filters = filters or {}

    log.info(
        "pipeline.analyse_listing start job_id=%s url=%s text_len=%s persist=%s",
        job_id, listing_url, len(raw_text or ""), persist,
    )

    extracted = normalization.normalize_extracted(
        extraction.extract_listing(raw_text or "", html=html, use_llm=use_llm)
    )
    _log_extracted_fields(job_id, listing_url, extracted)

    if filters.get("property_type"):
        extracted["property_type"] = extracted.get("property_type") or filters["property_type"]
    if filters.get("acquisition_type"):
        extracted["acquisition_type"] = extracted.get("acquisition_type") or filters["acquisition_type"]

    coords = None
    lat, lng, geo_source = loc_mod.resolve_coordinates(
        address=extracted.get("address"),
        city=extracted.get("city") or "Barcelona",
        neighbourhood=extracted.get("neighbourhood"),
    )

    location = loc_mod.gather_location_intel(
        lat=lat, lng=lng,
        address=extracted.get("address"),
        city=extracted.get("city"),
        neighbourhood=extracted.get("neighbourhood"),
    )
    location["geocode_source"] = geo_source
    location["geocode_approximate"] = geo_source in ("city_default", "neighbourhood") and not extracted.get("address")

    if not _matches_neighbourhood_filter(extracted, location, filters):
        log.info(
            "pipeline.analyse_listing skipped neighbourhood_filter job_id=%s url=%s",
            job_id, listing_url,
        )
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

    memo_key = laundry_cache.memo_cache_key(listing_url=listing_url, extracted=extracted)
    cached_memo = laundry_cache.get_memo(memo_key)
    if cached_memo:
        memo_md = cached_memo
    else:
        memo_md = memo_mod.generate_ic_memo(
            extracted=extracted, economics=economics, scoring=scoring,
            location=location, due_diligence=due_diligence,
        )
        laundry_cache.set_memo(memo_key, memo_md)

    result: Dict[str, Any] = {
        "success": True, "skipped": False,
        "extracted": extracted, "location": location, "economics": economics,
        "scoring": scoring, "due_diligence": due_diligence, "memo_md": memo_md,
    }

    if persist:
        ok, err = _persist_underwriting(
            result=result,
            extracted=extracted,
            economics=economics,
            scoring=scoring,
            location=location,
            due_diligence=due_diligence,
            memo_md=memo_md,
            listing_url=listing_url,
            source=source,
            job_id=job_id,
        )
        if not ok:
            if listing_url:
                return _persist_extraction_failed(
                    listing_url=listing_url,
                    job_id=job_id,
                    extracted=extracted,
                    error=err,
                    source=source,
                )
            result["success"] = False
            result["error"] = err
            result["persist_warning"] = err

    return result


def process_listing_url(
    *,
    url: str,
    overrides: Optional[Dict[str, Any]] = None,
    filters: Optional[Dict[str, Any]] = None,
    use_llm: bool = False,
    job_id: Optional[str] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    """Scrape listing detail → extract → persist property (or extraction_failed card)."""
    log.info("pipeline.found_listing_url job_id=%s url=%s", job_id, url)

    cached_extracted = laundry_cache.get_extracted(url)
    if cached_extracted:
        log.info("pipeline.cache hit extracted job_id=%s url=%s", job_id, url)
        if not extraction.has_usable_fields(cached_extracted):
            return _persist_extraction_failed(
                listing_url=url,
                job_id=job_id,
                extracted=cached_extracted,
                error="insufficient_extracted_fields",
            )
        return analyse_listing(
            raw_text=cached_extracted.get("_raw_text") or "",
            html=cached_extracted.get("_html") or "",
            listing_url=url,
            source="url_scan",
            overrides=overrides,
            filters=filters,
            use_llm=False,
            job_id=job_id,
            persist=persist,
        )

    fetched = scanner.fetch_listing_text(url)
    if not fetched.get("success"):
        err = fetched.get("error") or "scrape_failed"
        log.warning("pipeline.scrape_failed job_id=%s url=%s error=%s", job_id, url, err)
        return _persist_extraction_failed(
            listing_url=url,
            job_id=job_id,
            extracted={},
            error=err,
        )

    raw_text = fetched.get("raw_text") or ""
    html = fetched.get("html") or ""
    log.info(
        "pipeline.scraped_listing job_id=%s url=%s text_len=%s html_len=%s source=%s",
        job_id, url, len(raw_text), len(html), fetched.get("source"),
    )

    extracted = normalization.normalize_extracted(
        extraction.extract_listing(raw_text, html=html, use_llm=use_llm)
    )
    _log_extracted_fields(job_id, url, extracted)
    cache_payload = dict(extracted)
    cache_payload["_raw_text"] = raw_text[:8000] if raw_text else ""
    cache_payload["_html"] = ""
    laundry_cache.set_extracted(url, cache_payload)

    if not extraction.has_usable_fields(extracted):
        log.warning(
            "pipeline.insufficient_fields job_id=%s url=%s — creating extraction_failed card",
            job_id, url,
        )
        return _persist_extraction_failed(
            listing_url=url,
            job_id=job_id,
            extracted=extracted,
            error="insufficient_extracted_fields",
        )

    return analyse_listing(
        raw_text=raw_text,
        html=html,
        listing_url=url,
        source="url_scan",
        overrides=overrides,
        filters=filters,
        use_llm=False,  # already extracted above
        job_id=job_id,
        persist=persist,
    )


def analyse_url(*, url: str, overrides=None, filters=None,
                 use_llm: bool = True, job_id: Optional[str] = None,
                 persist: bool = True) -> Dict[str, Any]:
    """Back-compat wrapper — prefer ``process_listing_url`` in the worker."""
    return process_listing_url(
        url=url,
        overrides=overrides,
        filters=filters,
        use_llm=use_llm,
        job_id=job_id,
        persist=persist,
    )


def analyse_area(*, search_url: str, limit: int = 20, overrides=None,
                  filters=None, job_id: Optional[str] = None) -> Dict[str, Any]:
    urls = scanner.discover_listing_urls(search_url, limit=limit)
    results = []
    approved = manual = rejected = failed = skipped = extraction_failed = 0
    for url in urls:
        try:
            res = process_listing_url(
                url=url, overrides=overrides, filters=filters,
                job_id=job_id, persist=True,
            )
            results.append(res)
            if res.get("extraction_failed"):
                extraction_failed += 1
                continue
            if not res.get("success"):
                failed += 1
                continue
            if res.get("skipped"):
                skipped += 1
                continue
            ds = (res.get("scoring") or {}).get("deal_status")
            if ds == "approved_candidate":
                approved += 1
            elif ds == "manual_review":
                manual += 1
            else:
                rejected += 1
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
            "extraction_failed": extraction_failed,
        },
    }
