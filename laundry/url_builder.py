"""
K.U.A. — automatic search-URL generator for laundromat sourcing.

Acquisition sourcing prioritises *finding opportunities* over perfect filters.
URLs are built progressively: start broad (city-wide commercial rentals), apply
neighbourhood / size / ground-floor preferences in the pipeline — never stack
every Idealista filter in a single URL.

When a URL returns zero listings, ``resolve_search_url`` walks a fallback ladder
(target neighbourhood → district → Barcelona → metropolitan area) and validates
listing counts before the worker is queued.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

log = logging.getLogger("kua.laundry.url_builder")


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------
class UnsupportedFilterError(ValueError):
    """A provider declines to build a URL for the given filter combination."""


# Fallback hierarchy (narrow → wide). Used when escalating after 0 listings.
FALLBACK_LEVELS = (
    "target_neighbourhood",
    "district",
    "barcelona",
    "metropolitan",
)


@dataclass
class UrlBuildRequest:
    acquisition_type: str = "rent"
    property_type: str = "empty_commercial"
    city: str = "Barcelona"
    province: Optional[str] = None
    neighbourhoods: List[str] = field(default_factory=list)
    max_size_sqm: Optional[float] = 80.0
    min_size_sqm: Optional[float] = None
    max_price_eur: Optional[float] = None
    max_rent_month_eur: Optional[float] = None
    ground_floor_only: bool = True
    listing_limit: int = 20
    extra_filters: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict) -> "UrlBuildRequest":
        data = dict(data or {})
        return cls(
            acquisition_type=str(data.get("acquisition_type") or "rent").lower(),
            property_type=str(data.get("property_type") or "empty_commercial").lower(),
            city=str(data.get("city") or "Barcelona"),
            province=(str(data["province"]).lower() if data.get("province") else None),
            neighbourhoods=list(data.get("neighbourhoods") or data.get("neighbourhood_filters") or []),
            max_size_sqm=_safe_float(data.get("max_size_sqm")),
            min_size_sqm=_safe_float(data.get("min_size_sqm")),
            max_price_eur=_safe_float(data.get("max_price_eur") or data.get("max_price")),
            max_rent_month_eur=_safe_float(data.get("max_rent_month_eur") or data.get("max_rent")),
            ground_floor_only=bool(data.get("ground_floor_only", True)),
            listing_limit=int(data.get("listing_limit") or 20),
            extra_filters={str(k): str(v) for k, v in (data.get("extra_filters") or {}).items()},
        )


@dataclass
class SearchDiagnostics:
    generated_url: str
    listing_count: Optional[int] = None
    discovered_count: Optional[int] = None
    source_available_count: Optional[int] = None
    requested_limit: Optional[int] = None
    fallback_level: str = "barcelona"
    stage: int = 1
    applied_filters: Dict[str, str] = field(default_factory=dict)
    removed_filters: List[str] = field(default_factory=list)
    pipeline_filters: Dict[str, Any] = field(default_factory=dict)
    search_broadened: bool = False
    broadening_reason: Optional[str] = None
    attempts: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_url": self.generated_url,
            "listing_count": self.listing_count,
            "discovered_count": self.discovered_count,
            "source_available_count": self.source_available_count,
            "requested_limit": self.requested_limit,
            "fallback_level": self.fallback_level,
            "stage": self.stage,
            "applied_filters": self.applied_filters,
            "removed_filters": self.removed_filters,
            "pipeline_filters": self.pipeline_filters,
            "search_broadened": self.search_broadened,
            "broadening_reason": self.broadening_reason,
            "attempts": self.attempts,
        }


@dataclass
class UrlBuildResult:
    provider: str
    url: str
    description: str
    filters_applied: Dict[str, str]
    warnings: List[str] = field(default_factory=list)
    diagnostics: Optional[SearchDiagnostics] = None

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "provider": self.provider,
            "url": self.url,
            "description": self.description,
            "filters_applied": self.filters_applied,
            "warnings": self.warnings,
        }
        if self.diagnostics:
            out["search_diagnostics"] = self.diagnostics.to_dict()
            out["search_broadened"] = self.diagnostics.search_broadened
            out["broadening_reason"] = self.diagnostics.broadening_reason
        return out


@dataclass
class _CandidateSpec:
    fallback_level: str
    stage: int
    neighbourhood_slug: Optional[str] = None
    max_size_sqm: Optional[float] = None
    include_ground_floor: bool = False
    include_price: bool = False
    label: str = ""
    removed: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_float(v) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def slugify(value: str) -> str:
    if not value:
        return ""
    txt = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    txt = txt.lower().replace("'", "").replace("&", "and")
    txt = re.sub(r"[^a-z0-9]+", "-", txt).strip("-")
    return txt


def _first_neighbourhood_slug(req: UrlBuildRequest) -> Optional[str]:
    for raw in req.neighbourhoods:
        slug = _IDEALISTA_BCN_NEIGHBOURHOODS.get(raw.strip().lower())
        if slug:
            return slug
    return None


def _pipeline_filters(req: UrlBuildRequest) -> Dict[str, Any]:
    """Filters applied downstream in the underwriting pipeline (not in URL)."""
    pf: Dict[str, Any] = {}
    if req.neighbourhoods:
        pf["neighbourhoods"] = list(req.neighbourhoods)
    if req.max_size_sqm:
        pf["max_size_sqm"] = float(req.max_size_sqm)
    if req.min_size_sqm:
        pf["min_size_sqm"] = float(req.min_size_sqm)
    if req.ground_floor_only:
        pf["ground_floor_preference"] = True
    if req.max_price_eur:
        pf["max_price_eur"] = float(req.max_price_eur)
    if req.max_rent_month_eur:
        pf["max_rent_month_eur"] = float(req.max_rent_month_eur)
    return pf


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------
Provider = Callable[[UrlBuildRequest], UrlBuildResult]
_REGISTRY: Dict[str, Provider] = {}


def register_provider(key: str, fn: Provider) -> None:
    _REGISTRY[key.lower()] = fn


def get_provider(key: Optional[str]) -> Tuple[str, Provider]:
    key = (key or "idealista").lower()
    if key not in _REGISTRY:
        raise UnsupportedFilterError(
            f"Unknown provider '{key}'. Available: {sorted(_REGISTRY)}"
        )
    return key, _REGISTRY[key]


def list_providers() -> List[Dict[str, str]]:
    return [{"key": k, "label": _PROVIDER_LABELS.get(k, k.title())} for k in sorted(_REGISTRY)]


_PROVIDER_LABELS = {
    "idealista": "Idealista",
    "fotocasa": "Fotocasa",
    "habitaclia": "Habitaclia",
    "google_maps": "Google Maps",
    "custom": "Custom search",
}


# ---------------------------------------------------------------------------
# Idealista constants
# ---------------------------------------------------------------------------
_IDEALISTA_VERTICAL = {
    "existing_laundromat": "locales",
    "empty_commercial": "locales",
    "retail": "locales",
    "mixed_use": "locales",
    "industrial": "naves",
}

_IDEALISTA_CITY_SLUGS = {
    "barcelona": "barcelona-barcelona",
    "l'hospitalet": "l-hospitalet-de-llobregat-barcelona",
    "hospitalet": "l-hospitalet-de-llobregat-barcelona",
    "madrid": "madrid-madrid",
    "valencia": "valencia-valencia",
    "sevilla": "sevilla-sevilla",
}

_IDEALISTA_METRO_SLUGS = {
    "barcelona": "barcelona-barcelona",
}

_IDEALISTA_BCN_NEIGHBOURHOODS = {
    "raval": "el-raval-barcelona",
    "el raval": "el-raval-barcelona",
    "sant antoni": "sant-antoni-barcelona",
    "poble sec": "el-poble-sec-barcelona",
    "el poble sec": "el-poble-sec-barcelona",
    "clot": "el-clot-barcelona",
    "el clot": "el-clot-barcelona",
    "hospitalet": "l-hospitalet-de-llobregat-barcelona",
    "l'hospitalet": "l-hospitalet-de-llobregat-barcelona",
    "sants": "sants-barcelona",
    "gracia": "gracia-barcelona",
    "gràcia": "gracia-barcelona",
    "eixample": "eixample-barcelona",
}


# ---------------------------------------------------------------------------
# Idealista URL construction (progressive — never stack all filters)
# ---------------------------------------------------------------------------
def _idealista_city_slug(req: UrlBuildRequest, *, fallback_level: str) -> str:
    if fallback_level == "metropolitan":
        return _IDEALISTA_METRO_SLUGS.get(
            (req.city or "Barcelona").strip().lower(),
            "barcelona-barcelona",
        )
    city_lookup = (req.city or "Barcelona").strip().lower()
    slug = req.extra_filters.get("city_slug") or _IDEALISTA_CITY_SLUGS.get(city_lookup)
    if not slug:
        slug = slugify(req.city) or "barcelona-barcelona"
    return slug


def _build_idealista_from_spec(req: UrlBuildRequest, spec: _CandidateSpec) -> UrlBuildResult:
    warnings: List[str] = []
    applied: Dict[str, str] = {}

    if req.acquisition_type not in ("rent", "buy"):
        raise UnsupportedFilterError(
            f"acquisition_type must be 'rent' or 'buy' (got {req.acquisition_type!r})"
        )

    section = "alquiler" if req.acquisition_type == "rent" else "venta"
    vertical = _IDEALISTA_VERTICAL.get(req.property_type, "locales")
    if req.property_type not in _IDEALISTA_VERTICAL:
        warnings.append(
            f"unknown property_type '{req.property_type}', defaulted to commercial premises"
        )

    applied["section"] = section
    applied["vertical"] = vertical
    applied["fallback_level"] = spec.fallback_level
    applied["stage"] = str(spec.stage)

    city_slug = _idealista_city_slug(req, fallback_level=spec.fallback_level)
    applied["city_slug"] = city_slug

    neighbourhood_path = ""
    if spec.neighbourhood_slug:
        neighbourhood_path = f"/{spec.neighbourhood_slug}"
        applied["neighbourhood"] = spec.neighbourhood_slug

    filter_parts: List[str] = []
    if spec.max_size_sqm and spec.max_size_sqm > 0:
        filter_parts.append(f"metros-cuadrados-menos-de_{int(round(spec.max_size_sqm))}")
        applied["max_size_sqm"] = str(int(round(spec.max_size_sqm)))

    if spec.include_price:
        if req.acquisition_type == "buy" and req.max_price_eur and req.max_price_eur > 0:
            filter_parts.append(f"precio-hasta_{int(round(req.max_price_eur))}")
            applied["max_price_eur"] = str(int(round(req.max_price_eur)))
        if req.acquisition_type == "rent" and req.max_rent_month_eur and req.max_rent_month_eur > 0:
            filter_parts.append(f"precio-hasta_{int(round(req.max_rent_month_eur))}")
            applied["max_rent_month_eur"] = str(int(round(req.max_rent_month_eur)))

    # Ground-floor filter in Idealista URL when requested (planta-baja).
    if spec.include_ground_floor and vertical == "locales":
        filter_parts.append("planta-baja")
        applied["ground_floor"] = "url_filter"
    elif req.ground_floor_only:
        applied["ground_floor"] = "pipeline_preference"

    if spec.removed:
        applied["removed_from_url"] = ",".join(spec.removed)

    filter_segment = f"/con-{','.join(filter_parts)}" if filter_parts else ""
    url = (
        f"https://www.idealista.com/{section}-{vertical}/{city_slug}"
        f"{neighbourhood_path}{filter_segment}/"
    )

    stage_labels = {
        1: "city-wide commercial rentals",
        2: "target neighbourhood",
        3: "size filter",
        4: "ground floor preference (pipeline)",
    }
    stage_hint = stage_labels.get(spec.stage, spec.label or spec.fallback_level)

    desc = (
        f"Idealista · {section.upper()} · "
        f"{'commercial premises' if vertical == 'locales' else 'industrial units'} · "
        f"{req.city} · {stage_hint}"
    )
    if spec.max_size_sqm:
        desc += f" · ≤{int(spec.max_size_sqm)} m²"

    pipeline = _pipeline_filters(req)
    diagnostics = SearchDiagnostics(
        generated_url=url,
        fallback_level=spec.fallback_level,
        stage=spec.stage,
        applied_filters=dict(applied),
        removed_filters=list(spec.removed),
        pipeline_filters=pipeline,
    )

    if req.ground_floor_only and not spec.include_ground_floor:
        warnings.append(
            "Ground-floor URL filter removed — retrying with broader floor coverage."
        )
    if req.neighbourhoods and not spec.neighbourhood_slug:
        warnings.append(
            "Neighbourhood targeting applied in the pipeline — URL stays city-wide for coverage."
        )
    if req.max_size_sqm and not spec.max_size_sqm:
        warnings.append(
            f"Max size ({int(req.max_size_sqm)} m²) applied in the pipeline — not in the URL."
        )

    return UrlBuildResult(
        provider="idealista",
        url=url,
        description=desc,
        filters_applied=applied,
        warnings=warnings,
        diagnostics=diagnostics,
    )


def _idealista_escalation_ladder(req: UrlBuildRequest) -> List[_CandidateSpec]:
    """Ordered from narrowest intent to widest fallback (for 0-listing escalation)."""
    operator_max = int(req.max_size_sqm or 80)
    nh_slug = _first_neighbourhood_slug(req)
    ladder: List[_CandidateSpec] = []

    if nh_slug:
        ladder.append(_CandidateSpec(
            fallback_level="target_neighbourhood",
            stage=3,
            neighbourhood_slug=nh_slug,
            max_size_sqm=float(operator_max),
            include_ground_floor=False,
            label="neighbourhood + size",
        ))
        ladder.append(_CandidateSpec(
            fallback_level="target_neighbourhood",
            stage=3,
            neighbourhood_slug=nh_slug,
            max_size_sqm=100.0,
            include_ground_floor=False,
            removed=["ground_floor"],
            label="neighbourhood + max 100 m²",
        ))
        ladder.append(_CandidateSpec(
            fallback_level="target_neighbourhood",
            stage=3,
            neighbourhood_slug=nh_slug,
            max_size_sqm=120.0,
            include_ground_floor=False,
            removed=["ground_floor", f"max_size_{operator_max}"],
            label="neighbourhood + max 120 m²",
        ))
        ladder.append(_CandidateSpec(
            fallback_level="target_neighbourhood",
            stage=2,
            neighbourhood_slug=nh_slug,
            removed=["ground_floor", "max_size"],
            label="neighbourhood only",
        ))

    ladder.append(_CandidateSpec(
        fallback_level="district",
        stage=2,
        max_size_sqm=120.0,
        removed=["ground_floor", "neighbourhood", f"max_size_{operator_max}"],
        label="district / city + max 120 m²",
    ))
    ladder.append(_CandidateSpec(
        fallback_level="district",
        stage=2,
        max_size_sqm=100.0,
        removed=["ground_floor", "neighbourhood"],
        label="district / city + max 100 m²",
    ))
    ladder.append(_CandidateSpec(
        fallback_level="barcelona",
        stage=1,
        removed=["ground_floor", "neighbourhood", "max_size"],
        label="Barcelona commercial rentals",
    ))
    ladder.append(_CandidateSpec(
        fallback_level="metropolitan",
        stage=1,
        removed=["ground_floor", "neighbourhood", "max_size", "district"],
        label="metropolitan area",
    ))
    return ladder


def _idealista_widening_only_ladder(req: UrlBuildRequest) -> List[_CandidateSpec]:
    """Steps broader than the default city-wide search."""
    return [
        _CandidateSpec(
            fallback_level="metropolitan",
            stage=1,
            removed=["ground_floor", "neighbourhood", "max_size", "district"],
            label="metropolitan area",
        ),
    ]


def _idealista_primary_spec(req: UrlBuildRequest) -> _CandidateSpec:
    """Stage 1 — broad Barcelona commercial rentals; ground floor in URL when enabled."""
    include_gf = bool(req.ground_floor_only)
    return _CandidateSpec(
        fallback_level="barcelona",
        stage=4 if include_gf else 1,
        include_ground_floor=include_gf,
        label="Barcelona commercial rentals (ground floor)" if include_gf else "Barcelona commercial rentals (broad)",
    )


def _idealista_without_ground_floor_spec(req: UrlBuildRequest) -> _CandidateSpec:
    """Retry step when ground-floor URL returns zero listings."""
    return _CandidateSpec(
        fallback_level="barcelona",
        stage=1,
        include_ground_floor=False,
        removed=["ground_floor"],
        label="Barcelona commercial rentals (all floors)",
    )


def _build_idealista(req: UrlBuildRequest) -> UrlBuildResult:
    return _build_idealista_from_spec(req, _idealista_primary_spec(req))


# ---------------------------------------------------------------------------
# Other providers (broad-first, no ground-floor hard filter)
# ---------------------------------------------------------------------------
def _build_fotocasa(req: UrlBuildRequest) -> UrlBuildResult:
    if req.acquisition_type not in ("rent", "buy"):
        raise UnsupportedFilterError("acquisition_type must be 'rent' or 'buy'")
    section = "alquiler" if req.acquisition_type == "rent" else "comprar"
    vertical = "locales-comerciales" if req.property_type != "industrial" else "naves-industriales"
    city_slug = slugify(req.city) or "barcelona-capital"
    url = f"https://www.fotocasa.es/es/{section}/{vertical}/{city_slug}/todas-las-zonas/l"
    warnings = [
        "Fotocasa URL is city-wide — neighbourhood, size and floor preferences run in the pipeline.",
    ]
    if len(req.neighbourhoods) > 1:
        warnings.append("Multiple neighbourhoods → pipeline filter only.")
    diagnostics = SearchDiagnostics(
        generated_url=url,
        fallback_level="barcelona",
        stage=1,
        applied_filters={"section": section, "vertical": vertical, "city_slug": city_slug},
        pipeline_filters=_pipeline_filters(req),
    )
    return UrlBuildResult(
        provider="fotocasa",
        url=url,
        description=f"Fotocasa · {section.upper()} · {vertical.replace('-', ' ')} · {req.city} (broad)",
        filters_applied={"section": section, "vertical": vertical, "city_slug": city_slug},
        warnings=warnings,
        diagnostics=diagnostics,
    )


def _build_habitaclia(req: UrlBuildRequest) -> UrlBuildResult:
    if req.acquisition_type not in ("rent", "buy"):
        raise UnsupportedFilterError("acquisition_type must be 'rent' or 'buy'")
    section = "alquiler-locales-comerciales" if req.acquisition_type == "rent" else "locales-comerciales"
    city_slug = slugify(req.city) or "barcelona"
    url = f"https://www.habitaclia.com/{section}-en-{city_slug}.htm"
    warnings = ["Habitaclia URL is city-wide — filters run in the pipeline."]
    diagnostics = SearchDiagnostics(
        generated_url=url,
        fallback_level="barcelona",
        stage=1,
        applied_filters={"section": section, "city_slug": city_slug},
        pipeline_filters=_pipeline_filters(req),
    )
    return UrlBuildResult(
        provider="habitaclia",
        url=url,
        description=f"Habitaclia · {section.replace('-', ' ').upper()} · {req.city} (broad)",
        filters_applied={"section": section, "city_slug": city_slug},
        warnings=warnings,
        diagnostics=diagnostics,
    )


def _build_google_maps(req: UrlBuildRequest) -> UrlBuildResult:
    if req.property_type == "existing_laundromat":
        keyword = "laundromat OR lavandería autoservicio"
    else:
        keyword = "local comercial" if req.acquisition_type == "rent" else "local comercial venta"
    area = req.city or "Barcelona"
    query = f"{keyword} {area}".strip()
    url = f"https://www.google.com/maps/search/{quote_plus(query)}"
    diagnostics = SearchDiagnostics(
        generated_url=url,
        fallback_level="barcelona",
        stage=1,
        applied_filters={"keyword": keyword, "area": area},
        pipeline_filters=_pipeline_filters(req),
    )
    return UrlBuildResult(
        provider="google_maps",
        url=url,
        description=f"Google Maps · search '{query}'",
        filters_applied={"keyword": keyword, "area": area},
        warnings=["Google Maps is for human research — scraper will skip non-listing URLs"],
        diagnostics=diagnostics,
    )


def _build_custom(req: UrlBuildRequest) -> UrlBuildResult:
    template = req.extra_filters.get("template")
    if not template:
        raise UnsupportedFilterError(
            "custom provider requires extra_filters.template "
            "(supports {section} {city_slug} {max_size} {neighbourhood} placeholders)"
        )
    section = "alquiler" if req.acquisition_type == "rent" else "venta"
    nh = slugify(req.neighbourhoods[0]) if req.neighbourhoods else ""
    city_slug = req.extra_filters.get("city_slug") or slugify(req.city)
    url = (
        template
        .replace("{section}", section)
        .replace("{city_slug}", city_slug)
        .replace("{max_size}", str(int(req.max_size_sqm) if req.max_size_sqm else 80))
        .replace("{neighbourhood}", nh)
    )
    diagnostics = SearchDiagnostics(
        generated_url=url,
        fallback_level="custom",
        stage=1,
        applied_filters={"template": template},
        pipeline_filters=_pipeline_filters(req),
    )
    return UrlBuildResult(
        provider="custom",
        url=url,
        description=f"Custom template · {req.acquisition_type.upper()} · {req.city}",
        filters_applied={"template": template},
        diagnostics=diagnostics,
    )


register_provider("idealista", _build_idealista)
register_provider("fotocasa", _build_fotocasa)
register_provider("habitaclia", _build_habitaclia)
register_provider("google_maps", _build_google_maps)
register_provider("custom", _build_custom)


# ---------------------------------------------------------------------------
# Listing-count validation + fallback resolution
# ---------------------------------------------------------------------------
def _estimate_count(url: str) -> int:
    try:
        from laundry import scanner
        return scanner.estimate_listing_count(url)
    except Exception as exc:
        log.warning("listing count estimate failed for %s: %s", url, exc)
        return 0


def _attach_validation(
    result: UrlBuildResult,
    *,
    count: int,
    search_broadened: bool,
    broadening_reason: Optional[str],
    attempts: List[Dict[str, Any]],
) -> UrlBuildResult:
    diag = result.diagnostics or SearchDiagnostics(generated_url=result.url)
    diag.listing_count = count
    diag.search_broadened = search_broadened
    diag.broadening_reason = broadening_reason
    diag.attempts = attempts
    result.diagnostics = diag
    if search_broadened:
        result.warnings = list(result.warnings) + [
            "Search broadened automatically — "
            + (broadening_reason or "No listings found under original constraints")
        ]
    return result


def resolve_search_url(
    filters: Dict,
    provider: Optional[str] = None,
    *,
    validate: bool = True,
    min_listings: int = 1,
) -> UrlBuildResult:
    """Build a search URL and optionally validate listing count with auto-broadening."""
    provider_key, _ = get_provider(provider)
    req = UrlBuildRequest.from_dict(filters or {})

    if provider_key != "idealista":
        primary_fn = _REGISTRY[provider_key]
        primary = primary_fn(req)
        if not validate:
            return primary
        count = _estimate_count(primary.url)
        attempts = [{"url": primary.url, "count": count, "fallback_level": "barcelona", "stage": 1}]
        return _attach_validation(
            primary,
            count=count,
            search_broadened=False,
            broadening_reason=None,
            attempts=attempts,
        )

    primary_spec = _idealista_primary_spec(req)
    primary = _build_idealista_from_spec(req, primary_spec)
    attempts: List[Dict[str, Any]] = []

    if not validate:
        return primary

    # Start with ground-floor URL when enabled, then drop floor filter before widening geography.
    candidates: List[_CandidateSpec] = [primary_spec]
    if req.ground_floor_only:
        candidates.append(_idealista_without_ground_floor_spec(req))
    candidates.extend(_idealista_widening_only_ladder(req))
    candidates.extend(_idealista_escalation_ladder(req))
    original_url = primary.url
    chosen: Optional[UrlBuildResult] = None
    chosen_count = 0
    seen_urls: set[str] = set()

    for spec in candidates:
        built = _build_idealista_from_spec(req, spec)
        if built.url in seen_urls:
            continue
        seen_urls.add(built.url)
        count = _estimate_count(built.url)
        attempts.append({
            "url": built.url,
            "count": count,
            "fallback_level": spec.fallback_level,
            "stage": spec.stage,
            "removed_filters": spec.removed,
        })
        log.info(
            "URL validation level=%s stage=%s count=%s url=%s",
            spec.fallback_level, spec.stage, count, built.url,
        )
        if count >= min_listings:
            chosen = built
            chosen_count = count
            break

    if chosen is None:
        last_spec = candidates[-1]
        chosen = _build_idealista_from_spec(req, last_spec)
        chosen_count = attempts[-1]["count"] if attempts else 0

    broadened = chosen.url != original_url
    if broadened and req.ground_floor_only and "ground_floor" in (chosen.diagnostics.removed_filters if chosen.diagnostics else []):
        reason = "No ground-floor listings found — search retried without floor filter"
    elif broadened:
        reason = "No listings found under original constraints"
    else:
        reason = None

    if chosen.diagnostics:
        chosen.diagnostics.listing_count = chosen_count

    return _attach_validation(
        chosen,
        count=chosen_count,
        search_broadened=broadened,
        broadening_reason=reason,
        attempts=attempts,
    )


def discover_with_fallback(
    search_url: str,
    filters: Dict,
    provider: Optional[str] = None,
    *,
    limit: int = 20,
) -> Tuple[List[str], UrlBuildResult]:
    """Discover listing URLs; if the search URL yields 0, walk toward broader searches."""
    from laundry import scanner
    from laundry.limits import clamp_listing_limit

    req = UrlBuildRequest.from_dict(filters or {})
    listing_limit = clamp_listing_limit(limit)

    def _discover(url: str) -> scanner.DiscoverResult:
        return scanner.discover_listings(url, limit=listing_limit)

    def _attach_discovery(built: UrlBuildResult, result: scanner.DiscoverResult) -> None:
        if not built.diagnostics:
            return
        built.diagnostics.listing_count = result.discovered_count
        built.diagnostics.discovered_count = result.discovered_count
        built.diagnostics.source_available_count = result.source_available_count
        built.diagnostics.requested_limit = listing_limit

    discovery = _discover(search_url)
    urls = discovery.urls

    if urls:
        built = _build_idealista_from_spec(req, _idealista_primary_spec(req))
        if built.diagnostics:
            built.diagnostics.generated_url = search_url
        _attach_discovery(built, discovery)
        return urls, built

    log.info("Discovery returned 0 for %s — walking fallback ladder", search_url)

    if (provider or "idealista").lower() != "idealista":
        resolved = resolve_search_url(filters, provider=provider, validate=True, min_listings=1)
        discovery = _discover(resolved.url)
        urls = discovery.urls
        if urls:
            _attach_discovery(resolved, discovery)
        return urls, resolved

    attempts: List[Dict[str, Any]] = []
    seen_urls: set[str] = {search_url}

    candidate_specs: List[_CandidateSpec] = [_idealista_primary_spec(req)]
    if req.ground_floor_only:
        candidate_specs.append(_idealista_without_ground_floor_spec(req))
    candidate_specs.extend(_idealista_widening_only_ladder(req))
    candidate_specs.extend(_idealista_escalation_ladder(req))

    for spec in candidate_specs:
        built = _build_idealista_from_spec(req, spec)
        if built.url in seen_urls:
            continue
        seen_urls.add(built.url)
        count = _estimate_count(built.url)
        attempts.append({
            "url": built.url,
            "count": count,
            "fallback_level": spec.fallback_level,
            "stage": spec.stage,
            "removed_filters": spec.removed,
        })
        if count >= 1:
            discovery = _discover(built.url)
            urls = discovery.urls
            if urls:
                if built.diagnostics:
                    built.diagnostics.search_broadened = built.url != search_url
                    built.diagnostics.broadening_reason = (
                        "No listings found under original constraints"
                        if built.url != search_url else None
                    )
                    built.diagnostics.attempts = attempts
                _attach_discovery(built, discovery)
                return urls, built

    last = _build_idealista_from_spec(req, candidate_specs[-1])
    if last.diagnostics:
        last.diagnostics.search_broadened = last.url != search_url
        last.diagnostics.broadening_reason = (
            "No listings found under original constraints" if last.url != search_url else None
        )
        last.diagnostics.attempts = attempts
        last.diagnostics.requested_limit = listing_limit
    return [], last


def build_search_url(filters: Dict, provider: Optional[str] = None) -> UrlBuildResult:
    """Generate a provider-specific search URL (broad-first, no stacked filters)."""
    provider_key, fn = get_provider(provider)
    req = UrlBuildRequest.from_dict(filters or {})
    try:
        return fn(req)
    except UnsupportedFilterError:
        raise
    except Exception as exc:
        log.exception("URL builder %s crashed: %s", provider_key, exc)
        raise UnsupportedFilterError(f"{provider_key} URL builder failed: {exc}") from exc
