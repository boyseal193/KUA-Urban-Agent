"""Listing limit configuration for laundry scans."""
from __future__ import annotations

import math
import os

DEFAULT_MAX_LISTINGS = 200
LISTINGS_PER_PAGE = max(1, int(os.getenv("LAUNDRY_LISTINGS_PER_PAGE", "30")))


def max_listings() -> int:
    raw = os.getenv("LAUNDRY_MAX_LISTINGS", str(DEFAULT_MAX_LISTINGS))
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_MAX_LISTINGS


MAX_LISTINGS = max_listings()


def clamp_listing_limit(value: object, *, default: int = 20) -> int:
    try:
        n = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, MAX_LISTINGS))


def search_max_pages(limit: int) -> int:
    """Pages to crawl for a requested listing limit."""
    needed = max(1, math.ceil(clamp_listing_limit(limit) / LISTINGS_PER_PAGE))
    env_cap = os.getenv("LAUNDRY_SEARCH_MAX_PAGES", "").strip()
    if env_cap:
        try:
            configured = max(1, int(env_cap))
        except ValueError:
            configured = needed
        return max(needed, configured)
    return needed


def availability_message(
    *,
    requested_limit: int,
    discovered_count: int,
    source_available_count: int | None = None,
) -> str | None:
    available = source_available_count if source_available_count is not None else discovered_count
    if requested_limit <= 0:
        return None
    if available >= requested_limit:
        return None
    if available <= 0:
        return None
    return f"Only {available} listings available from source"
