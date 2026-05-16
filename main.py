import os
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import supabase
from scraper import scrape_listing_text, scrape_idealista_search_urls
from extractor import extract_property_from_text
from economics import calculate_economics
from auto_scoring import calculate_auto_scores
from scoring import score_property
from memo import generate_ic_memo
from location import geocode_address
from excel_exporter import export_scan_to_excel


app = FastAPI(title="TruTrastero AI Backend / K.U.A.")

# -----------------------------------------------------------------------------
# CORS — required for the K.U.A. Next.js frontend.
#
# In production the Next.js Route Handlers proxy every browser request through
# /api/proxy/*, so the browser never calls FastAPI directly and CORS is
# technically optional. We still enable it so the API can be exercised from
# local tooling (Postman, curl, Insomnia) and from any future first-party
# frontends.
#
# Configure the allowed origins via FRONTEND_ORIGINS env var, comma-separated.
# Default whitelists Next.js dev + a wildcard for previews.
# -----------------------------------------------------------------------------
_default_origins = "http://localhost:3000,http://127.0.0.1:3000"
_origins = [
    o.strip()
    for o in os.environ.get("FRONTEND_ORIGINS", _default_origins).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.get("/")
def home():
    return {"status": "running", "message": "TruTrastero AI Backend is live"}


def safe_float(value, default=None):
    if value is None:
        return default

    if isinstance(value, bool):
        return default

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        value = value.strip().lower()
        value = value.replace(",", ".")
        value = value.replace("m²", "")
        value = value.replace("m2", "")
        value = value.replace("meters", "")
        value = value.replace("metres", "")
        value = value.replace("€", "")
        value = value.replace("eur", "")
        value = value.strip()

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
    score_value = score.get("score", 0)
    verdict = score.get("verdict")
    deal_killer = score.get("deal_killer")

    if deal_killer:
        return "rejected"

    if verdict == "YES" and score_value >= 80:
        return "approved_candidate"

    if score_value >= 60:
        return "manual_review"

    return "rejected"


def generate_rejection_note(property_data: dict, economics: dict, score: dict):
    return f"""
# REJECTION SUMMARY

Property: {property_data.get("address")}, {property_data.get("city")}
Verdict: {score.get("verdict")}
Score: {score.get("score")}/100
Classification: {score.get("classification")}
Deal killer: {score.get("deal_killer") or "Score below investment threshold"}

Key metrics:
- GBA: {property_data.get("gba_m2")} m²
- Asking price: €{property_data.get("asking_price")}
- EBITDA: €{economics.get("ebitda")}
- EBITDA yield: {economics.get("ebitda_yield")}
- True EBITDA yield: {economics.get("true_ebitda_yield")}
- Payback years: {economics.get("payback_years")}
- True payback years: {economics.get("true_payback_years")}

Reason:
This deal was rejected automatically because it does not meet the minimum TruTrastero investment threshold. It remains saved in the rejected history for manual review.
""".strip()


def run_full_pipeline(data: dict, source: str = "auto"):
    data = clean_property_data(data)

    valid, error = is_valid_property_data(data)
    if not valid:
        return {
            "success": False,
            "error": error,
            "extracted": data,
        }

    full_address = f"{data.get('address') or data.get('neighbourhood') or data.get('city')}, {data.get('city')}, Spain"
    coordinates = geocode_address(full_address)

    data["latitude"] = coordinates["lat"]
    data["longitude"] = coordinates["lng"]

    economics = calculate_economics(
        gba_m2=data.get("gba_m2"),
        rent_per_m2=data.get("rent_per_m2"),
        price_per_m2_nra=data.get("price_per_m2_nra"),
        nra_efficiency=data.get("nra_efficiency"),
        asking_price=data.get("asking_price"),
        asking_rent_month=data.get("asking_rent_month"),
    )

    auto_scores = calculate_auto_scores(data, economics)

    final_score = score_property({
        "extracted": data,
        "economics": economics,
        "auto_scores": auto_scores,
    })

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

    property_response = supabase.table("properties").insert(property_insert).execute()
    property_id = property_response.data[0]["id"]

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

    # Persist auto_scores alongside the final score so the frontend
    # score-breakdown radar can render even for historical deals.
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
    }


@app.post("/analyse")
def analyse(payload: dict):
    url = payload.get("url")
    raw_text = payload.get("text") or payload.get("raw_text")

    if not url and not raw_text:
        return {"success": False, "error": "Provide either url or text/raw_text"}

    if url:
        scraped = scrape_listing_text(url)

        if not scraped.get("success"):
            return scraped

        raw_text = scraped.get("raw_text", "")
        data = extract_property_from_text(raw_text)
        data["listing_url"] = url

        result = run_full_pipeline(data, source="url_auto")
        result["scrape_preview"] = raw_text[:1000]
        result["source_url"] = url
        return result

    data = extract_property_from_text(raw_text)
    return run_full_pipeline(data, source="text_auto")


def split_scan_results(results: list):
    successful_results = [
        r for r in results
        if isinstance(r, dict)
        and r.get("property_id")
        and r.get("score")
    ]

    failed_results = [
        r for r in results
        if not (
            isinstance(r, dict)
            and r.get("property_id")
            and r.get("score")
        )
    ]

    approved_candidates = [
        r for r in successful_results
        if r.get("deal_status") == "approved_candidate"
    ]

    manual_review_deals = [
        r for r in successful_results
        if r.get("deal_status") == "manual_review"
    ]

    rejected_deals = [
        r for r in successful_results
        if r.get("deal_status") == "rejected"
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


@app.post("/scan/idealista")
def scan_idealista(payload: dict):
    search_url = payload.get("search_url")
    limit = int(payload.get("limit", 10))
    generate_excel = payload.get("generate_excel", True)
    filters_used = payload.get("filters_used", payload)

    if not search_url:
        return {"success": False, "error": "search_url is required"}

    scraped_urls = scrape_idealista_search_urls(search_url, limit=limit)

    if not scraped_urls.get("success"):
        return scraped_urls

    results = []

    for url in scraped_urls.get("urls", []):
        try:
            result = analyse({"url": url})

            if isinstance(result, dict):
                result["source_url"] = url

            results.append(result)

        except Exception as e:
            results.append({
                "url": url,
                "success": False,
                "error": str(e),
            })

    grouped = split_scan_results(results)

    response = {
        "success": True,
        "search_url_used": search_url,
        "scanned_count": len(results),

        "approved_candidates_count": len(grouped["approved_candidates"]),
        "manual_review_count": len(grouped["manual_review_deals"]),
        "top_deals_count": len(grouped["top_deals"]),
        "rejected_count": len(grouped["rejected_history"]),

        "approved_candidates": grouped["approved_candidates"],
        "manual_review_deals": grouped["manual_review_deals"],
        "top_deals": grouped["top_deals"],
        "rejected_history": grouped["rejected_history"],
        "all_results": results,

        "excel_export_generated": False,
        "filters_used": filters_used,
    }

    if generate_excel:
        try:
            excel_path = export_scan_to_excel(
                results=grouped["successful_results"],
                search_url=search_url,
                filters_used=filters_used,
            )
            response["excel_export_generated"] = True
            response["excel_export_path"] = excel_path
        except TypeError:
            try:
                excel_path = export_scan_to_excel(grouped["successful_results"])
                response["excel_export_generated"] = True
                response["excel_export_path"] = excel_path
            except Exception as e:
                response["excel_export_generated"] = False
                response["excel_export_error"] = str(e)
        except Exception as e:
            response["excel_export_generated"] = False
            response["excel_export_error"] = str(e)

    return response


@app.post("/scan/idealista/auto")
def scan_idealista_auto(payload: dict):
    city_slug = payload.get("city_slug", "barcelona-barcelona")
    max_price = int(payload.get("max_price", 1000000))
    min_m2 = int(payload.get("min_m2", 200))
    max_m2 = int(payload.get("max_m2", 300))
    property_types = payload.get("property_types", ["locales", "naves"])
    ground_floor_only = payload.get("ground_floor_only", True)
    sale_only = payload.get("sale_only", True)
    limit = int(payload.get("limit", 10))
    generate_excel = payload.get("generate_excel", True)

    filter_parts = [
        f"con-precio-hasta_{max_price}",
        f"metros-cuadrados-mas-de_{min_m2}",
        f"metros-cuadrados-menos-de_{max_m2}",
    ]

    filter_parts.extend(property_types)

    if ground_floor_only:
        filter_parts.append("en-planta-calle")

    if sale_only:
        filter_parts.append("venta-solo-inmueble")

    filters_string = ",".join(filter_parts)

    search_url = (
        f"https://www.idealista.com/en/venta-locales/"
        f"{city_slug}/{filters_string}/"
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

    return scan_idealista({
        "search_url": search_url,
        "limit": limit,
        "generate_excel": generate_excel,
        "filters_used": filters_used,
    })


@app.post("/property/from-url")
def analyse_from_url(payload: dict):
    return analyse(payload)


@app.post("/property/extract")
def analyse_from_text(payload: dict):
    return analyse(payload)


@app.get("/property/{property_id}")
def get_property_detail(property_id: str):
    property_result = (
        supabase.table("properties")
        .select("*")
        .eq("id", property_id)
        .execute()
        .data
    )

    if not property_result:
        return {"success": False, "error": "Property not found"}

    analysis_result = (
        supabase.table("analyses")
        .select("*")
        .eq("property_id", property_id)
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
        .order("score", desc=True)
        .limit(limit)
        .execute()
    )

    return {"top_deals": results.data}


@app.get("/deals/manual-review")
def get_manual_review_deals(limit: int = 10):
    results = (
        supabase.table("properties")
        .select("*")
        .eq("deal_status", "manual_review")
        .order("score", desc=True)
        .limit(limit)
        .execute()
    )

    return {"manual_review_deals": results.data}


@app.get("/deals/approved")
def get_approved_deals(limit: int = 10):
    results = (
        supabase.table("properties")
        .select("*")
        .eq("deal_status", "approved_candidate")
        .order("score", desc=True)
        .limit(limit)
        .execute()
    )

    return {"approved_candidates": results.data}


@app.get("/deals/status/{deal_status}")
def get_deals_by_status(deal_status: str, limit: int = 10):
    results = (
        supabase.table("properties")
        .select("*")
        .eq("deal_status", deal_status)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    return {"deals": results.data}


@app.get("/deals/rejected")
def get_rejected_deals(limit: int = 10):
    results = (
        supabase.table("properties")
        .select("*")
        .eq("deal_status", "rejected")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    return {"rejected_deals": results.data}


@app.post("/property/memo/{property_id}")
def generate_memo(property_id: str):
    property_result = (
        supabase.table("properties")
        .select("*")
        .eq("id", property_id)
        .execute()
        .data
    )

    if not property_result:
        return {"error": "Property not found"}

    analysis_result = (
        supabase.table("analyses")
        .select("*")
        .eq("property_id", property_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
    )

    if not analysis_result:
        return {"error": "No analysis found for this property"}

    property_data = property_result[0]
    analysis_data = analysis_result[0]

    memo_text = generate_ic_memo(
        property_data=property_data,
        economics=analysis_data["economics"],
        score=analysis_data["score"],
    )

    supabase.table("analyses").update({
        "ic_memo": memo_text
    }).eq("id", analysis_data["id"]).execute()

    return {
        "property_id": property_id,
        "ic_memo": memo_text,
    }