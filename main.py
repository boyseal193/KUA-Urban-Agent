"""K.U.A. FastAPI application.

Hardened with:
  * Request-ID middleware (x-request-id propagated on every response)
  * Global exception handler — no raw 500s without a JSON body
  * /, /health, /health/database, /health/pipeline, /health/full
  * Structured DatabaseSetupError / StoreError responses (503 / 502)
  * Async job endpoints: enqueue, list, get, cancel, retry
  * /jobs/cleanup admin endpoint to sweep stale jobs
"""

from __future__ import annotations

import os
import re
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from fastapi.responses import StreamingResponse

from kua_auth import router as auth_router
from database import supabase
from scraper import scrape_listing_text, scrape_idealista_search_urls
from extractor import extract_property_from_text
from economics import calculate_economics
from auto_scoring import calculate_auto_scores
from scoring import score_property
from memo import generate_ic_memo
from location import geocode_address
from excel_exporter import export_scan_to_excel

from jobs.logging_util import configure_logging, get_logger

configure_logging(os.getenv("LOG_LEVEL", "INFO"))

# Module-level logger for endpoint-level performance diagnostics (Phase 12/14).
log = get_logger("main", "app")

app = FastAPI(
    title="TruTrastero AI Backend / K.U.A.",
    description=(
        "FastAPI backend for the K.U.A. (Klave Urban Agent) acquisitions intelligence platform."
    ),
    version="1.1.0",
)


@app.on_event("startup")
def _warm_schema_cache_on_startup() -> None:
    """Prime the schema-health cache once at boot so the first write / worker
    claim does not pay the probe cost inline. Best-effort; never fails boot."""
    try:
        from jobs.db_health import warm_schema_cache

        warm_schema_cache()
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("schema cache warm failed (non-fatal): %s", exc)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
_DEFAULT_ORIGINS = ",".join(
    [
        "https://honest-trust-production-fcdb.up.railway.app",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
)

_origins = [
    o.strip()
    for o in os.environ.get("FRONTEND_ORIGINS", _DEFAULT_ORIGINS).split(",")
    if o.strip()
]

_origin_regex = r"^https://(honest-trust|kua-frontend)[a-z0-9-]*\.up\.railway\.app$"

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-request-id"],
)


# ---------------------------------------------------------------------------
# Request-ID + access log middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    request.state.request_id = request_id
    started = time.monotonic()
    log = get_logger(request_id, request.url.path)
    try:
        response = await call_next(request)
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        log.exception("Unhandled error in request: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error_type": type(exc).__name__,
                "message": str(exc)[:500] or "Internal server error",
                "request_id": request_id,
                "elapsed_ms": elapsed_ms,
                "retryable": False,
            },
            headers={"x-request-id": request_id},
        )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    response.headers["x-request-id"] = request_id
    log.info("%s %s -> %s (%sms)", request.method, request.url.path, response.status_code, elapsed_ms)
    return response


app.include_router(auth_router, prefix="/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# K.U.A. Laundry Acquisition vertical
#
# The router already carries prefix="/laundry", so we MUST NOT pass prefix=
# here — that would create /laundry/laundry/scans. Any import failure is
# trapped and surfaced via GET /debug/routes + GET /laundry/_diag so a
# missing dependency or table is diagnosable in production without shell
# access.
# ---------------------------------------------------------------------------
_LAUNDRY_MOUNT: dict = {"ok": False, "error": None, "route_count": 0}
try:
    from laundry.api import router as laundry_router  # noqa: E402
    app.include_router(laundry_router)
    _LAUNDRY_MOUNT.update({
        "ok": True,
        "error": None,
        "route_count": len(laundry_router.routes),
        "prefix": getattr(laundry_router, "prefix", ""),
    })
    print(f"[laundry] OK — registered {_LAUNDRY_MOUNT['route_count']} routes under /laundry", flush=True)
except Exception as _laundry_exc:  # noqa: BLE001 — must never crash boot
    import traceback as _tb
    _LAUNDRY_MOUNT.update({
        "ok": False,
        "error": f"{type(_laundry_exc).__name__}: {_laundry_exc}",
        "traceback": _tb.format_exc(),
    })
    print(f"[laundry] FAILED to mount router: {_LAUNDRY_MOUNT['error']}", flush=True)
    print(_LAUNDRY_MOUNT["traceback"], flush=True)

    @app.get("/laundry/_diag", include_in_schema=False)
    def _laundry_diag():
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "service": "kua-laundry",
                "router_loaded": False,
                "error": _LAUNDRY_MOUNT["error"],
                "traceback": _LAUNDRY_MOUNT.get("traceback") if os.getenv("EXPOSE_LAUNDRY_TRACEBACK") else None,
            },
        )


# ---------------------------------------------------------------------------
# Diagnostics: list every registered route in production for verification.
# ---------------------------------------------------------------------------
@app.get("/debug/routes", include_in_schema=False)
def debug_routes():
    routes = []
    for r in app.router.routes:
        path = getattr(r, "path", None)
        if not path:
            continue
        methods = sorted(list(getattr(r, "methods", []) or []))
        routes.append({"path": path, "methods": methods, "name": getattr(r, "name", None)})
    routes.sort(key=lambda x: x["path"])
    return {
        "service": "kua-backend",
        "total": len(routes),
        "laundry_mount": _LAUNDRY_MOUNT,
        "routes": routes,
    }


# ---------------------------------------------------------------------------
# Root / liveness
# ---------------------------------------------------------------------------
@app.get("/")
def home():
    return {"status": "running", "service": "kua-backend", "version": "1.1.0"}


@app.get("/health")
def health():
    """Cheap liveness probe — no Supabase round-trip."""
    return {"ok": True, "service": "kua-backend", "ts": time.time()}


# ---------------------------------------------------------------------------
# Property processing helpers (unchanged behaviour, defensive defaults)
# ---------------------------------------------------------------------------
def safe_float(value, default=None):
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        value = value.strip().lower()
        value = (
            value.replace(",", ".")
            .replace("m²", "")
            .replace("m2", "")
            .replace("meters", "")
            .replace("metres", "")
            .replace("€", "")
            .replace("eur", "")
            .strip()
        )
        nums = re.findall(r"\d+(?:\.\d+)?", value)
        if len(nums) >= 2:
            nums = [float(x) for x in nums[:2]]
            return round(sum(nums) / len(nums), 2)
        if len(nums) == 1:
            return float(nums[0])
    return default


def clean_property_data(data: dict):
    if not data:
        return {}
    cleaned = dict(data)
    cleaned["gba_m2"] = safe_float(cleaned.get("gba_m2"))
    cleaned["asking_price"] = safe_float(cleaned.get("asking_price"))
    cleaned["asking_rent_month"] = safe_float(cleaned.get("asking_rent_month"))
    cleaned["rent_per_m2"] = safe_float(cleaned.get("rent_per_m2"))
    cleaned["ceiling_height"] = safe_float(cleaned.get("ceiling_height"))
    cleaned["price_per_m2_nra"] = safe_float(cleaned.get("price_per_m2_nra"))
    cleaned["nra_efficiency"] = safe_float(cleaned.get("nra_efficiency"))
    if cleaned.get("city") is None:
        cleaned["city"] = "Barcelona"
    if cleaned.get("price_per_m2_nra") is None:
        cleaned["price_per_m2_nra"] = 15
    if cleaned.get("nra_efficiency") is None:
        cleaned["nra_efficiency"] = 0.75
    if cleaned.get("loading_access") is None:
        cleaned["loading_access"] = False
    return cleaned


def is_valid_property_data(data: dict):
    if not data:
        return False, "No extracted property data"
    if data.get("gba_m2") is None or data.get("gba_m2") <= 0:
        return False, "Missing or invalid GBA"
    if data.get("asking_price") is None and data.get("asking_rent_month") is None:
        return False, "Missing both asking price and asking rent"
    return True, None


def assign_deal_status(score: dict):
    """Map a scored property onto its lifecycle bucket.

    Thresholds (philosophy kua-2.0):
        ≥ 75 → approved_candidate
        ≥ 40 → manual_review
        else → rejected

    A hard ``deal_killer`` always overrides regardless of score.
    """
    if not isinstance(score, dict):
        return "rejected"
    score_value = score.get("score", 0)
    deal_killer = score.get("deal_killer")
    if deal_killer:
        return "rejected"
    try:
        score_value = int(score_value)
    except (TypeError, ValueError):
        score_value = 0
    if score_value >= 75:
        return "approved_candidate"
    if score_value >= 40:
        return "manual_review"
    return "rejected"


def generate_rejection_note(property_data: dict, economics: dict, score: dict):
    pd = property_data or {}
    ec = economics or {}
    sc = score or {}
    return f"""
# REJECTION SUMMARY

Property: {pd.get("address")}, {pd.get("city")}
Verdict: {sc.get("verdict")}
Score: {sc.get("score")}/100
Classification: {sc.get("classification")}
Deal killer: {sc.get("deal_killer") or "Score below investment threshold"}

Key metrics:
- GBA: {pd.get("gba_m2")} m²
- Asking price: €{pd.get("asking_price")}
- EBITDA: €{ec.get("ebitda")}
- EBITDA yield: {ec.get("ebitda_yield")}
- True EBITDA yield: {ec.get("true_ebitda_yield")}
- Payback years: {ec.get("payback_years")}
- True payback years: {ec.get("true_payback_years")}

Reason:
This deal was rejected automatically because it does not meet the minimum TruTrastero investment threshold. It remains saved in the rejected history for manual review.
""".strip()


def run_full_pipeline(data: dict, source: str = "auto"):
    data = clean_property_data(data)

    valid, error = is_valid_property_data(data)
    if not valid:
        return {"success": False, "error": error, "extracted": data}

    full_address = (
        f"{data.get('address') or data.get('neighbourhood') or data.get('city')}, "
        f"{data.get('city')}, Spain"
    )
    from geocoding import resolve_coordinates

    lat, lng, _geo_source = resolve_coordinates(
        address=data.get("address") or data.get("neighbourhood"),
        city=data.get("city") or "Barcelona",
        neighbourhood=data.get("neighbourhood"),
    )
    coordinates = {"lat": lat, "lng": lng}

    data["latitude"] = coordinates.get("lat")
    data["longitude"] = coordinates.get("lng")

    economics = calculate_economics(
        gba_m2=data.get("gba_m2"),
        rent_per_m2=data.get("rent_per_m2"),
        price_per_m2_nra=data.get("price_per_m2_nra"),
        nra_efficiency=data.get("nra_efficiency"),
        asking_price=data.get("asking_price"),
        asking_rent_month=data.get("asking_rent_month"),
    )

    auto_scores = calculate_auto_scores(data, economics)

    final_score = score_property(
        {"extracted": data, "economics": economics, "auto_scores": auto_scores}
    )

    deal_status = assign_deal_status(final_score)

    property_insert = {
        "source": source,
        "listing_url": data.get("listing_url"),
        "address": data.get("address"),
        "city": data.get("city"),
        "neighbourhood": data.get("neighbourhood"),
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
        "gba_m2": data.get("gba_m2"),
        "asking_price": data.get("asking_price"),
        "asking_rent_month": data.get("asking_rent_month"),
        "rent_per_m2": data.get("rent_per_m2"),
        "ceiling_height": data.get("ceiling_height"),
        "loading_access": data.get("loading_access"),
        "access_type": data.get("access_type"),
        "floor_level": data.get("floor_level"),
        "building_type": data.get("building_type"),
        "current_use": data.get("current_use"),
        "description": data.get("description"),
        "score": final_score.get("score"),
        "verdict": final_score.get("verdict"),
        "classification": final_score.get("classification"),
        "status": "analysed",
        "deal_status": deal_status,
    }

    from jobs.properties_store import upsert_from_pipeline

    upsert = upsert_from_pipeline(
        property_insert=property_insert,
        extracted=data,
        job_id=None,
    )
    if not upsert.get("success") or not upsert.get("property_id"):
        return {
            "success": False,
            "error": upsert.get("error") or "Supabase did not return property id",
        }
    property_id = upsert["property_id"]
    was_duplicate = upsert.get("was_duplicate", False)

    if deal_status in ["approved_candidate", "manual_review"]:
        memo_text = generate_ic_memo(
            property_data={**property_insert, "id": property_id},
            economics=economics,
            score=final_score,
        )
    else:
        memo_text = generate_rejection_note(
            property_data={**property_insert, "id": property_id},
            economics=economics,
            score=final_score,
        )

    enriched_score = dict(final_score)
    if isinstance(auto_scores, dict) and "auto_scores" in auto_scores:
        enriched_score.setdefault("auto_scores", auto_scores.get("auto_scores"))

    analysis_insert = {
        "property_id": property_id,
        "input": data,
        "economics": economics,
        "score": enriched_score,
        "verdict": final_score.get("verdict"),
        "classification": final_score.get("classification"),
        "deal_killer": final_score.get("deal_killer"),
        "ic_memo": memo_text,
    }
    supabase.table("analyses").insert(analysis_insert).execute()

    return {
        "property_id": property_id,
        "extracted": data,
        "coordinates": coordinates,
        "auto_scores": auto_scores,
        "economics": economics,
        "score": final_score,
        "deal_status": deal_status,
        "ic_memo": memo_text,
        "success": True,
        "duplicate": was_duplicate,
        "dedupe_key": upsert.get("dedupe_key"),
    }


# ---------------------------------------------------------------------------
# Single-listing analyse
# ---------------------------------------------------------------------------
@app.post("/analyse")
def analyse(payload: dict):
    url = (payload or {}).get("url")
    raw_text = (payload or {}).get("text") or (payload or {}).get("raw_text")

    if not url and not raw_text:
        return {"success": False, "error": "Provide either url or text/raw_text"}

    if url:
        scraped = scrape_listing_text(url)
        if not scraped.get("success"):
            return scraped
        raw_text = scraped.get("raw_text", "")
        data = extract_property_from_text(raw_text) or {}
        data["listing_url"] = url
        result = run_full_pipeline(data, source="url_auto")
        result["scrape_preview"] = (raw_text or "")[:1000]
        result["source_url"] = url
        return result

    data = extract_property_from_text(raw_text) or {}
    return run_full_pipeline(data, source="text_auto")


# ---------------------------------------------------------------------------
# Structured error responses
# ---------------------------------------------------------------------------
def _setup_error_response(exc) -> JSONResponse:
    from jobs.errors import DatabaseSetupError

    if isinstance(exc, DatabaseSetupError):
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error_type": "DatabaseSetupError",
                "message": str(exc),
                "missing_tables": exc.missing_tables,
                "missing_columns": exc.missing_columns,
                "retryable": False,
                "setup_required": True,
            },
        )
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error_type": type(exc).__name__,
            "message": str(exc),
            "retryable": False,
        },
    )


def _store_error_response(exc) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={
            "success": False,
            "error_type": "StoreError",
            "message": str(exc),
            "retryable": getattr(exc, "retryable", False),
        },
    )


# ---------------------------------------------------------------------------
# Scan enqueue
# ---------------------------------------------------------------------------
def _enqueue_scan_job(
    *,
    job_type: str,
    search_url: str,
    filters: dict,
    limit: int,
    generate_excel: bool,
    created_by: Optional[str] = None,
    request_id: Optional[str] = None,
):
    from jobs import store
    from jobs.errors import DatabaseSetupError, StoreError

    try:
        job = store.create_job(
            job_type=job_type,
            search_url=search_url,
            filters=filters,
            listing_limit=limit,
            generate_excel=generate_excel,
            created_by=created_by,
            request_id=request_id,
        )
    except DatabaseSetupError as exc:
        return _setup_error_response(exc)
    except StoreError as exc:
        return _store_error_response(exc)

    return {
        "success": True,
        "async": True,
        "job_id": job["id"],
        "status": job["status"],
        "message": "Scan job queued. Poll GET /jobs/{job_id} for live progress.",
        "poll_url": f"/jobs/{job['id']}",
    }


@app.post("/scan/idealista")
def scan_idealista(payload: dict, request: Request):
    search_url = (payload or {}).get("search_url")
    limit = int((payload or {}).get("limit", 10))
    generate_excel = (payload or {}).get("generate_excel", True)
    filters_used = (payload or {}).get("filters_used", payload)
    created_by = (payload or {}).get("created_by")

    if not search_url:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error_type": "ValidationError",
                "message": "search_url is required",
                "retryable": False,
            },
        )

    return _enqueue_scan_job(
        job_type="idealista_url",
        search_url=search_url,
        filters=filters_used if isinstance(filters_used, dict) else {},
        limit=limit,
        generate_excel=bool(generate_excel),
        created_by=created_by,
        request_id=getattr(request.state, "request_id", None),
    )


@app.post("/scan/idealista/auto")
def scan_idealista_auto(payload: dict, request: Request):
    payload = payload or {}
    city_slug = payload.get("city_slug", "barcelona-barcelona")
    max_price = int(payload.get("max_price", 1000000))
    min_m2 = int(payload.get("min_m2", 200))
    max_m2 = int(payload.get("max_m2", 300))
    property_types = payload.get("property_types", ["locales", "naves"])
    ground_floor_only = payload.get("ground_floor_only", True)
    sale_only = payload.get("sale_only", True)
    limit = int(payload.get("limit", 10))
    generate_excel = payload.get("generate_excel", True)
    created_by = payload.get("created_by")

    filter_parts = [
        f"con-precio-hasta_{max_price}",
        f"metros-cuadrados-mas-de_{min_m2}",
        f"metros-cuadrados-menos-de_{max_m2}",
    ]
    if isinstance(property_types, list):
        filter_parts.extend(property_types)
    if ground_floor_only:
        filter_parts.append("en-planta-calle")
    if sale_only:
        filter_parts.append("venta-solo-inmueble")

    search_url = (
        f"https://www.idealista.com/en/venta-locales/"
        f"{city_slug}/{','.join(filter_parts)}/"
    )

    filters_used = {
        "city_slug": city_slug,
        "max_price": max_price,
        "min_m2": min_m2,
        "max_m2": max_m2,
        "property_types": property_types,
        "ground_floor_only": ground_floor_only,
        "sale_only": sale_only,
        "limit": limit,
    }

    return _enqueue_scan_job(
        job_type="idealista_auto",
        search_url=search_url,
        filters=filters_used,
        limit=limit,
        generate_excel=bool(generate_excel),
        created_by=created_by,
        request_id=getattr(request.state, "request_id", None),
    )


# ---------------------------------------------------------------------------
# Property + deals (legacy direct reads — kept for backward compat)
# ---------------------------------------------------------------------------
@app.post("/property/from-url")
def analyse_from_url(payload: dict):
    return analyse(payload)


@app.post("/property/extract")
def analyse_from_text(payload: dict):
    return analyse(payload)


@app.get("/property/{property_id}")
def get_property_detail(property_id: str, include_deleted: bool = False):
    query = supabase.table("properties").select("*").eq("id", property_id)
    if not include_deleted:
        query = query.is_("deleted_at", "null")
    property_result = query.execute().data
    if not property_result:
        return {"success": False, "error": "Property not found"}
    analysis_result = (
        supabase.table("analyses")
        .select("*")
        .eq("property_id", property_id)
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
    )
    return {
        "success": True,
        "property": property_result[0],
        "latest_analysis": analysis_result[0] if analysis_result else None,
    }


@app.get("/deals/top")
def get_top_deals(limit: int = 10):
    results = (
        supabase.table("properties")
        .select("*")
        .in_("deal_status", ["approved_candidate", "manual_review"])
        .is_("deleted_at", "null")
        .order("score", desc=True)
        .limit(limit)
        .execute()
    )
    return {"top_deals": results.data or []}


@app.get("/deals/manual-review")
def get_manual_review_deals(limit: int = 10):
    results = (
        supabase.table("properties")
        .select("*")
        .eq("deal_status", "manual_review")
        .is_("deleted_at", "null")
        .order("score", desc=True)
        .limit(limit)
        .execute()
    )
    return {"manual_review_deals": results.data or []}


@app.get("/deals/approved")
def get_approved_deals(limit: int = 10):
    results = (
        supabase.table("properties")
        .select("*")
        .eq("deal_status", "approved_candidate")
        .is_("deleted_at", "null")
        .order("score", desc=True)
        .limit(limit)
        .execute()
    )
    return {"approved_candidates": results.data or []}


@app.get("/deals/status/{deal_status}")
def get_deals_by_status(deal_status: str, limit: int = 10):
    results = (
        supabase.table("properties")
        .select("*")
        .eq("deal_status", deal_status)
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return {"deals": results.data or []}


@app.get("/deals/rejected")
def get_rejected_deals(limit: int = 10):
    results = (
        supabase.table("properties")
        .select("*")
        .eq("deal_status", "rejected")
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return {"rejected_deals": results.data or []}


def _storage_map_markers(*, limit: int = 500, backfill: bool = True) -> tuple[list, dict]:
    from geocoding import geocoding_status, resolve_coordinates

    rows = (
        supabase.table("properties")
        .select("id, address, city, neighbourhood, latitude, longitude, score, deal_status, verdict")
        .is_("deleted_at", "null")
        .order("score", desc=True)
        .limit(limit)
        .execute()
    ).data or []

    markers = []
    missing = []
    backfilled = 0

    for row in rows:
        lat = row.get("latitude")
        lng = row.get("longitude")
        if (lat is None or lng is None) and backfill:
            lat, lng, _src = resolve_coordinates(
                address=row.get("address"),
                city=row.get("city") or "Barcelona",
                neighbourhood=row.get("neighbourhood"),
            )
            if lat is not None and lng is not None:
                supabase.table("properties").update({
                    "latitude": lat,
                    "longitude": lng,
                }).eq("id", row["id"]).execute()
                backfilled += 1

        if lat is None or lng is None:
            missing.append({
                "id": row.get("id"),
                "address": row.get("address"),
                "city": row.get("city"),
                "neighbourhood": row.get("neighbourhood"),
            })
            continue

        markers.append({
            "id": row.get("id"),
            "vertical": "storage",
            "lat": float(lat),
            "lng": float(lng),
            "latitude": float(lat),
            "longitude": float(lng),
            "score": row.get("score"),
            "deal_status": row.get("deal_status"),
            "address": row.get("address"),
            "city": row.get("city"),
            "neighbourhood": row.get("neighbourhood"),
            "verdict": row.get("verdict"),
        })

    diagnostics = {
        "vertical": "storage",
        "total_properties": len(rows),
        "plotted": len(markers),
        "missing_coordinates": len(missing),
        "backfilled": backfilled,
        "missing_samples": missing[:10],
        **geocoding_status(),
    }
    return markers, diagnostics


@app.get("/map/markers")
def unified_map_markers(
    limit: int = 500,
    backfill: bool = True,
    vertical: Optional[str] = None,
):
    """Unified tactical map — storage + laundry properties with geocode backfill."""
    verticals = (vertical or "all").lower().split(",")
    include_storage = "all" in verticals or "storage" in verticals
    include_laundry = "all" in verticals or "laundry" in verticals

    markers: list = []
    diagnostics: dict = {"verticals": {}}

    if include_storage:
        storage_markers, storage_diag = _storage_map_markers(limit=limit, backfill=backfill)
        markers.extend(storage_markers)
        diagnostics["verticals"]["storage"] = storage_diag

    if include_laundry:
        try:
            from laundry import store as laundry_store
            laundry_markers, laundry_diag = laundry_store.list_laundry_map_markers(
                limit=limit, backfill=backfill,
            )
            markers.extend(laundry_markers)
            diagnostics["verticals"]["laundry"] = laundry_diag
        except Exception as exc:
            diagnostics["verticals"]["laundry"] = {"error": str(exc)}

    diagnostics["total_markers"] = len(markers)
    diagnostics["plotted"] = len(markers)
    diagnostics["missing_coordinates"] = sum(
        (d.get("missing_coordinates") or 0)
        for d in diagnostics["verticals"].values()
        if isinstance(d, dict)
    )
    from geocoding import geocoding_status
    diagnostics.update(geocoding_status())

    return {"success": True, "markers": markers, "diagnostics": diagnostics}


@app.get("/map/diagnostics")
def unified_map_diagnostics(limit: int = 500):
    payload = unified_map_markers(limit=limit, backfill=False)
    return {"success": True, "diagnostics": payload.get("diagnostics")}


# ---------------------------------------------------------------------------
# Property delete / restore / duplicates / admin
# ---------------------------------------------------------------------------
@app.delete("/properties/{property_id}")
def delete_property(property_id: str, request: Request, reason: Optional[str] = None):
    """Soft-delete a property. Cascades to analyses + memos via deleted_at."""
    from jobs import properties_store

    actor = getattr(request.state, "user_id", None) or "operator"
    request_id = getattr(request.state, "request_id", None)
    result = properties_store.soft_delete(
        property_id, deleted_by=actor, reason=reason, request_id=request_id
    )
    if not result.get("success"):
        if result.get("error") == "not_found":
            return JSONResponse(status_code=404, content={"success": False, "error": "Property not found"})
        return JSONResponse(status_code=500, content={"success": False, "error": result.get("error")})
    return result


@app.post("/properties/{property_id}/restore")
def restore_property(property_id: str, request: Request):
    from jobs import properties_store

    actor = getattr(request.state, "user_id", None) or "operator"
    request_id = getattr(request.state, "request_id", None)
    result = properties_store.restore(property_id, actor=actor, request_id=request_id)
    if not result.get("success"):
        if result.get("error") == "not_found":
            return JSONResponse(status_code=404, content={"success": False, "error": "Property not found"})
        if result.get("error") == "dedupe_key_conflict":
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "error": "dedupe_key_conflict",
                    "conflicting_property_id": result.get("conflicting_property_id"),
                    "message": "An active property with the same identity already exists",
                },
            )
        return JSONResponse(status_code=500, content={"success": False, "error": result.get("error")})
    return result


@app.post("/properties/bulk-delete")
def bulk_delete_properties(payload: dict, request: Request):
    """Soft-delete many properties at once.

    Safety guards (enforced server-side, even if the client skips them):
      * max 100 ids per request
      * batches of ≥ 10 require ``confirmation="DELETE"``
      * batches that would remove >50% of active properties are rejected
    """
    from jobs import properties_store

    ids = (payload or {}).get("ids") or []
    if not isinstance(ids, list) or not ids:
        return JSONResponse(status_code=400, content={"success": False, "error": "ids must be a non-empty list"})
    actor = getattr(request.state, "user_id", None) or "operator"
    reason = (payload or {}).get("reason") or "bulk_delete"
    confirmation = (payload or {}).get("confirmation")

    result = properties_store.bulk_soft_delete(
        ids, deleted_by=actor, reason=reason, confirmation=confirmation
    )
    if not result.get("success"):
        # 400 for caller-fixable issues, 422 for confirmation/percentage guards.
        status = 422 if result.get("error") in {
            "confirmation_required",
            "percentage_guard_tripped",
        } else 400
        return JSONResponse(status_code=status, content=result)
    return result


@app.post("/properties/active-ids")
def verify_active_property_ids(payload: dict):
    """Return ``{id: is_active}`` for every supplied property id.

    Used by the frontend to detect stale React-Query list entries — when an
    id resolves to ``false`` the client purges that card from every cache.
    """
    from jobs import properties_store

    ids = (payload or {}).get("ids") or []
    if not isinstance(ids, list):
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "ids must be an array"},
        )
    if not ids:
        return {"success": True, "active": {}}
    return {
        "success": True,
        "active": properties_store.filter_active_property_ids(ids),
    }


@app.get("/properties/duplicates")
def list_property_duplicates(limit: int = 50):
    from jobs import properties_store

    clusters = properties_store.find_duplicate_clusters(min_cluster_size=2, limit=limit)
    return {"success": True, "clusters": clusters, "count": len(clusters)}


@app.get("/properties/deleted")
def list_deleted_properties(limit: int = 100):
    from jobs import properties_store

    return {"success": True, "properties": properties_store.list_deleted(limit=limit)}


@app.get("/admin/stats")
def get_admin_stats():
    from jobs import properties_store

    return {"success": True, "stats": properties_store.admin_stats()}


@app.post("/admin/cleanup/test-data")
def admin_cleanup_test_data(request: Request):
    from jobs import properties_store

    actor = getattr(request.state, "user_id", None) or "operator"
    return properties_store.purge_test_data(actor=actor)


@app.post("/admin/cleanup/failed-jobs")
def admin_cleanup_failed_jobs(request: Request, older_than_days: int = 1):
    from jobs import properties_store

    actor = getattr(request.state, "user_id", None) or "operator"
    return properties_store.purge_failed_jobs(older_than_days=older_than_days, actor=actor)


@app.post("/admin/cleanup/orphans")
def admin_cleanup_orphans(request: Request):
    from jobs import properties_store

    actor = getattr(request.state, "user_id", None) or "operator"
    return properties_store.purge_orphans(actor=actor)


@app.post("/property/memo/{property_id}")
def generate_memo(property_id: str):
    property_result = (
        supabase.table("properties")
        .select("*")
        .eq("id", property_id)
        .is_("deleted_at", "null")
        .execute()
        .data
    )
    if not property_result:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "Property not found or deleted"},
        )

    analysis_result = (
        supabase.table("analyses")
        .select("*")
        .eq("property_id", property_id)
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
    )
    if not analysis_result:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "No analysis found for this property"},
        )

    property_data = property_result[0]
    analysis_data = analysis_result[0]

    memo_text = generate_ic_memo(
        property_data=property_data,
        economics=analysis_data["economics"],
        score=analysis_data["score"],
    )

    supabase.table("analyses").update({"ic_memo": memo_text}).eq(
        "id", analysis_data["id"]
    ).execute()

    return {"property_id": property_id, "ic_memo": memo_text}


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------
@app.get("/health/full")
def health_full():
    from jobs.health import full_health

    return full_health()


@app.get("/health/database")
def health_database():
    from jobs.db_health import database_health

    result = database_health(force=True)
    status_code = 200 if result.get("success") else 503
    return JSONResponse(status_code=status_code, content=result)


@app.get("/health/pipeline")
def health_pipeline():
    from jobs.health import pipeline_health

    result = pipeline_health()
    status_code = 200 if result.get("ok") else 503
    return JSONResponse(status_code=status_code, content=result)


# ---------------------------------------------------------------------------
# Async job API — frontend polls these
# ---------------------------------------------------------------------------
@app.get("/jobs")
def list_scan_jobs(limit: int = 20, status: Optional[str] = None, offset: int = 0):
    """Lightweight scan history. Summary fields only — details live at
    GET /jobs/{id}. Supports offset pagination so history scales to 10k+ jobs.
    """
    from jobs import store
    from jobs.errors import DatabaseSetupError, StoreError

    t0 = time.perf_counter()
    try:
        jobs = store.list_jobs(limit=limit, status=status, offset=offset)
        total_ms = (time.perf_counter() - t0) * 1000.0
        if total_ms >= 10000.0:
            log.critical("GET /jobs total=%.0fms limit=%s offset=%s", total_ms, limit, offset)
        elif total_ms >= 3000.0:
            log.warning("GET /jobs total=%.0fms limit=%s offset=%s", total_ms, limit, offset)
        else:
            log.info("GET /jobs total=%.0fms rows=%d", total_ms, len(jobs))
        return {
            "success": True,
            "jobs": jobs,
            "count": len(jobs),
            "limit": max(1, min(int(limit or 20), 100)),
            "offset": max(0, int(offset or 0)),
            "next_offset": (
                max(0, int(offset or 0)) + len(jobs) if len(jobs) >= max(1, min(int(limit or 20), 100)) else None
            ),
            "elapsed_ms": round(total_ms, 1),
        }
    except DatabaseSetupError as exc:
        return _setup_error_response(exc)
    except StoreError as exc:
        return _store_error_response(exc)


@app.get("/jobs/{job_id}")
def get_scan_job(job_id: str):
    from jobs import store
    from jobs.errors import DatabaseSetupError, StoreError

    try:
        return store.build_job_response(job_id)
    except DatabaseSetupError as exc:
        return _setup_error_response(exc)
    except StoreError as exc:
        return _store_error_response(exc)
    except KeyError:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error_type": "NotFound",
                "message": f"Job not found: {job_id}",
                "retryable": False,
            },
        )


@app.post("/jobs/{job_id}/cancel")
def cancel_scan_job(job_id: str):
    from jobs import store
    from jobs.constants import JOB_CANCELLED, TERMINAL_JOB_STATUSES
    from jobs.errors import DatabaseSetupError, StoreError

    try:
        job = store.get_job(job_id)
    except KeyError:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error_type": "NotFound",
                "message": f"Job not found: {job_id}",
                "retryable": False,
            },
        )
    except DatabaseSetupError as exc:
        return _setup_error_response(exc)
    except StoreError as exc:
        return _store_error_response(exc)

    if job.get("status") in TERMINAL_JOB_STATUSES:
        return {"success": True, "job": job, "message": "Job already terminal"}

    try:
        updated = store.update_job(
            job_id, status=JOB_CANCELLED, finished_at=store._now()
        )
        return {"success": True, "job": updated}
    except StoreError as exc:
        return _store_error_response(exc)


@app.post("/jobs/{job_id}/retry")
def retry_scan_job(job_id: str):
    from jobs import store
    from jobs.errors import DatabaseSetupError, StoreError

    try:
        job = store.requeue_for_retry(job_id)
        return {
            "success": True,
            "job": job,
            "message": "Job re-queued for the worker.",
        }
    except DatabaseSetupError as exc:
        return _setup_error_response(exc)
    except StoreError as exc:
        return _store_error_response(exc)
    except KeyError:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error_type": "NotFound",
                "message": f"Job not found: {job_id}",
                "retryable": False,
            },
        )


@app.post("/jobs/cleanup")
def cleanup_dead_jobs():
    """Force a dead-job sweep. Safe to call any time."""
    from jobs import store
    from jobs.errors import DatabaseSetupError, StoreError

    try:
        recovered = store.sweep_dead_jobs()
        return {"success": True, "recovered": recovered}
    except DatabaseSetupError as exc:
        return _setup_error_response(exc)
    except StoreError as exc:
        return _store_error_response(exc)


# ---------------------------------------------------------------------------
# Export endpoints
#
# Every endpoint:
#   * authenticates via the proxy → x-kua-user / x-kua-clearance / Bearer
#     (the proxy refuses to forward without a session, so by the time we
#     are reached, the request is already authenticated)
#   * regenerates from the database on cache miss — works even if the
#     Supabase storage bucket is not configured
#   * streams the artifact with the correct Content-Type + Content-Disposition
#   * returns a structured JSON error envelope on any failure
# ---------------------------------------------------------------------------
_EXPORT_FORMATS = ("excel", "csv", "json", "memo", "zip")


def _export_not_found_response(job_id: str, fmt: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "success": False,
            "error_type": "NotFound",
            "message": f"Export not available for job {job_id} (format={fmt}).",
            "retryable": True,
        },
    )


def _export_error_response(exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error_type": type(exc).__name__,
            "message": str(exc)[:500] or "Export generation failed.",
            "retryable": True,
        },
    )


def _stream_export(job_id: str, fmt: str):
    """Build a StreamingResponse for one job/format pair."""
    from jobs.exports_service import get_or_generate
    from jobs.errors import DatabaseSetupError, StoreError

    if fmt not in _EXPORT_FORMATS:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error_type": "BadRequest",
                "message": f"Unknown export format: {fmt!r}. Allowed: {list(_EXPORT_FORMATS)}.",
            },
        )
    try:
        result = get_or_generate(job_id, fmt)
    except DatabaseSetupError as exc:
        return _setup_error_response(exc)
    except StoreError as exc:
        return _store_error_response(exc)
    except KeyError:
        return _export_not_found_response(job_id, fmt)
    except Exception as exc:
        get_logger(job_id, "exports").exception("Export generation crash: %s", exc)
        return _export_error_response(exc)

    if result is None:
        return _export_not_found_response(job_id, fmt)

    data, mime, filename = result

    def _iter():
        # Chunk so even a 50MB zip streams politely.
        view = memoryview(data)
        chunk = 64 * 1024
        for i in range(0, len(view), chunk):
            yield bytes(view[i : i + chunk])

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Length": str(len(data)),
        "X-Export-Format": fmt,
        "Cache-Control": "private, no-store",
    }
    return StreamingResponse(_iter(), media_type=mime, headers=headers)


@app.get("/exports/{job_id}")
def list_exports_for_job(job_id: str):
    """List every export artifact known for a job (cached + missing)."""
    from jobs import exports_store

    try:
        rows = exports_store.list_exports(job_id)
    except Exception:
        rows = []
    # Always advertise all 5 supported formats so the UI can render every button.
    by_type = {r.get("export_type"): r for r in rows if isinstance(r, dict)}
    out = []
    for fmt in _EXPORT_FORMATS:
        row = by_type.get(fmt) or {}
        out.append(
            {
                "format": fmt,
                "status": row.get("status") or "on_demand",
                "size_bytes": row.get("size_bytes") or 0,
                "file_name": row.get("file_name"),
                "mime_type": row.get("mime_type"),
                "download_count": row.get("download_count") or 0,
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
                "url": f"/exports/{job_id}/{fmt}",
            }
        )
    return {"success": True, "job_id": job_id, "exports": out}


@app.post("/exports/{job_id}/regenerate")
def regenerate_exports(job_id: str):
    """Force a fresh regeneration of all export artifacts for a job.

    Useful when a previous auto-generation failed or the user wants the
    latest data after a re-scan.
    """
    from jobs.exports_service import generate_all_exports

    try:
        outcome = generate_all_exports(job_id)
        return {"success": True, "job_id": job_id, "outcome": outcome}
    except Exception as exc:
        return _export_error_response(exc)


@app.get("/exports/{job_id}/{fmt}")
def download_export(job_id: str, fmt: str):
    """Stream the requested export. Always works (cache or on-demand)."""
    return _stream_export(job_id, fmt.lower())
