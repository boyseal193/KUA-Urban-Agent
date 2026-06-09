"""
K.U.A. — automatic search-URL generator for laundromat sourcing.

Why this exists
---------------
The laundromat scan form lets operators pick property type / buy-vs-rent /
target neighbourhoods / max sqm. They should not have to hand-craft a portal
search URL on top. This module converts those filters into a canonical
search URL for a configurable real-estate provider.

Architecture
------------
A *provider* is just a callable that accepts a :class:`UrlBuildRequest` and
returns either a string (the URL) or raises :class:`UnsupportedFilterError`.
Register more providers with :func:`register_provider`. The frontend selects
which provider to use; the backend falls back to ``idealista`` when none is
specified.

This module is *pure-Python*: no I/O, no network, no SQL. Safe to import from
the API layer, the worker, or unit tests.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

log = logging.getLogger("kua.laundry.url_builder")


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------
class UnsupportedFilterError(ValueError):
    """A provider declines to build a URL for the given filter combination."""


@dataclass
class UrlBuildRequest:
    """Inputs to the URL builder.

    Mirrors the laundry scan-form fields 1:1 so the frontend can pass its
    state object through with no remapping.
    """
    acquisition_type: str = "rent"              # buy | rent
    property_type: str = "empty_commercial"     # see PROPERTY_TYPES
    city: str = "Barcelona"
    province: Optional[str] = None              # auto-filled to "Barcelona" when city is Barcelona
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
class UrlBuildResult:
    provider: str
    url: str
    description: str
    filters_applied: Dict[str, str]
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "provider": self.provider,
            "url": self.url,
            "description": self.description,
            "filters_applied": self.filters_applied,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_float(v) -> Optional[float]:
    if v is None or isinstance(v, bool): return None
    try: return float(v)
    except (TypeError, ValueError): return None


def slugify(value: str) -> str:
    """Idealista-style URL slug — lowercase ASCII, hyphenated, no diacritics."""
    if not value: return ""
    txt = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    txt = txt.lower().replace("'", "").replace("&", "and")
    txt = re.sub(r"[^a-z0-9]+", "-", txt).strip("-")
    return txt


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


# Human-readable labels (frontend uses these in the dropdown).
_PROVIDER_LABELS = {
    "idealista": "Idealista",
    "fotocasa": "Fotocasa",
    "habitaclia": "Habitaclia",
    "google_maps": "Google Maps",
    "custom": "Custom search",
}


# ---------------------------------------------------------------------------
# Property type → Idealista vertical
# ---------------------------------------------------------------------------
# All laundromat-friendly property types ultimately map to "locales" (commercial
# units) on Idealista — except declared industrial units which use "naves".
_IDEALISTA_VERTICAL = {
    "existing_laundromat": "locales",
    "empty_commercial": "locales",
    "retail": "locales",
    "mixed_use": "locales",
    "industrial": "naves",
}

# Idealista city slugs — start with what we actually target. Operators can
# extend via `extra_filters={"city_slug": "madrid-madrid"}`.
_IDEALISTA_CITY_SLUGS = {
    "barcelona": "barcelona-barcelona",
    "l'hospitalet": "l-hospitalet-de-llobregat-barcelona",
    "hospitalet": "l-hospitalet-de-llobregat-barcelona",
    "madrid": "madrid-madrid",
    "valencia": "valencia-valencia",
    "sevilla": "sevilla-sevilla",
}

# Mapping of operator-facing neighbourhood names → Idealista path slug.
# Multi-neighbourhood searches degrade gracefully to a city-wide URL.
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
# Provider: Idealista (canonical)
# ---------------------------------------------------------------------------
def _build_idealista(req: UrlBuildRequest) -> UrlBuildResult:
    warnings: List[str] = []
    applied: Dict[str, str] = {}

    if req.acquisition_type not in ("rent", "buy"):
        raise UnsupportedFilterError(
            f"acquisition_type must be 'rent' or 'buy' (got {req.acquisition_type!r})"
        )
    section = "alquiler" if req.acquisition_type == "rent" else "venta"
    vertical = _IDEALISTA_VERTICAL.get(req.property_type, "locales")
    if req.property_type not in _IDEALISTA_VERTICAL:
        warnings.append(f"unknown property_type '{req.property_type}', defaulted to commercial premises")
    applied["section"] = section
    applied["vertical"] = vertical

    base_segment = f"{section}-{vertical}"

    city_lookup = (req.city or "Barcelona").strip().lower()
    city_slug = req.extra_filters.get("city_slug") or _IDEALISTA_CITY_SLUGS.get(city_lookup)
    if not city_slug:
        city_slug = slugify(req.city) or "barcelona-barcelona"
        warnings.append(f"city '{req.city}' not in built-in slug table, using '{city_slug}'")
    applied["city_slug"] = city_slug

    neighbourhood_path = ""
    if req.neighbourhoods:
        nh_slugs = []
        unknown = []
        for raw in req.neighbourhoods:
            slug = _IDEALISTA_BCN_NEIGHBOURHOODS.get(raw.strip().lower())
            if slug: nh_slugs.append(slug)
            else: unknown.append(raw)
        if unknown:
            warnings.append(
                "neighbourhood(s) not in Idealista path table — pipeline-level filter will still apply: "
                + ", ".join(unknown)
            )
        if len(nh_slugs) == 1:
            neighbourhood_path = f"/{nh_slugs[0]}"
            applied["neighbourhood"] = nh_slugs[0]
        elif len(nh_slugs) > 1:
            warnings.append(
                f"{len(nh_slugs)} neighbourhoods selected — Idealista path supports one; "
                "pipeline-level filter will narrow results"
            )
            applied["neighbourhoods_in_pipeline"] = ",".join(nh_slugs)

    filter_parts: List[str] = []
    if req.max_size_sqm and req.max_size_sqm > 0:
        filter_parts.append(f"metros-cuadrados-menos-de_{int(round(req.max_size_sqm))}")
    if req.min_size_sqm and req.min_size_sqm > 0:
        filter_parts.append(f"metros-cuadrados-mas-de_{int(round(req.min_size_sqm))}")
    if req.acquisition_type == "buy" and req.max_price_eur and req.max_price_eur > 0:
        filter_parts.append(f"precio-hasta_{int(round(req.max_price_eur))}")
    if req.acquisition_type == "rent" and req.max_rent_month_eur and req.max_rent_month_eur > 0:
        filter_parts.append(f"precio-hasta_{int(round(req.max_rent_month_eur))}")
    if req.ground_floor_only and vertical == "locales":
        filter_parts.append("planta-baja")

    applied["filters"] = ",".join(filter_parts) if filter_parts else ""

    filter_segment = ""
    if filter_parts:
        filter_segment = f"/con-{','.join(filter_parts)}"

    url = (
        f"https://www.idealista.com/{base_segment}/{city_slug}{neighbourhood_path}"
        f"{filter_segment}/"
    )

    desc = (
        f"Idealista · {section.upper()} · "
        f"{'commercial premises' if vertical == 'locales' else 'industrial units'} · "
        f"{req.city}"
        + (f" · ≤{int(req.max_size_sqm)} m²" if req.max_size_sqm else "")
        + (f" · ground floor" if req.ground_floor_only and vertical == 'locales' else "")
    )
    return UrlBuildResult(
        provider="idealista", url=url, description=desc,
        filters_applied=applied, warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Provider: Fotocasa (canonical)
# ---------------------------------------------------------------------------
def _build_fotocasa(req: UrlBuildRequest) -> UrlBuildResult:
    if req.acquisition_type not in ("rent", "buy"):
        raise UnsupportedFilterError("acquisition_type must be 'rent' or 'buy'")
    section = "alquiler" if req.acquisition_type == "rent" else "comprar"
    vertical = "locales-comerciales" if req.property_type != "industrial" else "naves-industriales"

    city_slug = slugify(req.city) or "barcelona-capital"
    nh_segment = ""
    if len(req.neighbourhoods) == 1:
        nh_segment = "/" + slugify(req.neighbourhoods[0])

    query: List[Tuple[str, str]] = []
    if req.max_size_sqm and req.max_size_sqm > 0:
        query.append(("maxSurface", str(int(req.max_size_sqm))))
    if req.min_size_sqm and req.min_size_sqm > 0:
        query.append(("minSurface", str(int(req.min_size_sqm))))
    if req.acquisition_type == "buy" and req.max_price_eur:
        query.append(("maxPrice", str(int(req.max_price_eur))))
    if req.acquisition_type == "rent" and req.max_rent_month_eur:
        query.append(("maxPrice", str(int(req.max_rent_month_eur))))
    if req.ground_floor_only:
        query.append(("floors", "ground"))

    qs = ("?" + "&".join(f"{quote_plus(k)}={quote_plus(v)}" for k, v in query)) if query else ""
    url = f"https://www.fotocasa.es/es/{section}/{vertical}/{city_slug}{nh_segment}/todas-las-zonas/l{qs}"

    warnings: List[str] = []
    if len(req.neighbourhoods) > 1:
        warnings.append("Fotocasa URL only encodes one neighbourhood; pipeline filter handles the rest")

    desc = f"Fotocasa · {section.upper()} · {vertical.replace('-', ' ')} · {req.city}"
    return UrlBuildResult(
        provider="fotocasa", url=url, description=desc,
        filters_applied={
            "section": section, "vertical": vertical, "city_slug": city_slug,
            "query": "&".join(f"{k}={v}" for k, v in query),
        },
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Provider: Habitaclia
# ---------------------------------------------------------------------------
def _build_habitaclia(req: UrlBuildRequest) -> UrlBuildResult:
    if req.acquisition_type not in ("rent", "buy"):
        raise UnsupportedFilterError("acquisition_type must be 'rent' or 'buy'")
    section = "alquiler-locales-comerciales" if req.acquisition_type == "rent" else "locales-comerciales"
    city_slug = slugify(req.city) or "barcelona"
    nh_segment = ""
    if len(req.neighbourhoods) == 1:
        nh_segment = "-" + slugify(req.neighbourhoods[0])
    parts: List[str] = []
    if req.max_size_sqm: parts.append(f"superficie-max-{int(req.max_size_sqm)}")
    if req.min_size_sqm: parts.append(f"superficie-min-{int(req.min_size_sqm)}")
    if req.acquisition_type == "buy" and req.max_price_eur:
        parts.append(f"precio-max-{int(req.max_price_eur)}")
    if req.acquisition_type == "rent" and req.max_rent_month_eur:
        parts.append(f"precio-max-{int(req.max_rent_month_eur)}")
    filter_segment = ("-" + "-".join(parts)) if parts else ""
    url = f"https://www.habitaclia.com/{section}-en-{city_slug}{nh_segment}{filter_segment}.htm"
    desc = f"Habitaclia · {section.replace('-', ' ').upper()} · {req.city}"
    warnings = (["Habitaclia URL only encodes one neighbourhood; pipeline filter handles the rest"]
                if len(req.neighbourhoods) > 1 else [])
    return UrlBuildResult(
        provider="habitaclia", url=url, description=desc,
        filters_applied={"section": section, "city_slug": city_slug, "filters": "-".join(parts)},
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Provider: Google Maps (research / on-the-ground discovery)
# ---------------------------------------------------------------------------
def _build_google_maps(req: UrlBuildRequest) -> UrlBuildResult:
    if req.property_type == "existing_laundromat":
        keyword = "laundromat OR lavandería autoservicio"
    else:
        keyword = "local comercial planta baja" if req.acquisition_type == "rent" else "local comercial venta"
    area = ", ".join(req.neighbourhoods) if req.neighbourhoods else req.city or "Barcelona"
    query = f"{keyword} {area}".strip()
    url = f"https://www.google.com/maps/search/{quote_plus(query)}"
    return UrlBuildResult(
        provider="google_maps", url=url,
        description=f"Google Maps · search '{query}'",
        filters_applied={"keyword": keyword, "area": area},
        warnings=["Google Maps is for human research — scraper will skip non-listing URLs"],
    )


# ---------------------------------------------------------------------------
# Provider: Custom (operator-supplied template)
# ---------------------------------------------------------------------------
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
    return UrlBuildResult(
        provider="custom", url=url,
        description=f"Custom template · {req.acquisition_type.upper()} · {req.city}",
        filters_applied={"template": template},
    )


# Register the canonical providers at import time.
register_provider("idealista", _build_idealista)
register_provider("fotocasa", _build_fotocasa)
register_provider("habitaclia", _build_habitaclia)
register_provider("google_maps", _build_google_maps)
register_provider("custom", _build_custom)


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
def build_search_url(filters: Dict, provider: Optional[str] = None) -> UrlBuildResult:
    """Generate a provider-specific search URL from operator filters.

    Raises :class:`UnsupportedFilterError` with a human-readable message if
    the filter combination cannot be turned into a URL.
    """
    provider_key, fn = get_provider(provider)
    req = UrlBuildRequest.from_dict(filters or {})
    try:
        return fn(req)
    except UnsupportedFilterError:
        raise
    except Exception as exc:  # pragma: no cover — defensive
        log.exception("URL builder %s crashed: %s", provider_key, exc)
        raise UnsupportedFilterError(f"{provider_key} URL builder failed: {exc}") from exc
