"""Idealista scraping — thin wrapper around legacy `scraper.py` (repo root)."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scraper import scrape_idealista_search_urls, scrape_listing_text  # noqa: E402

__all__ = ["scrape_idealista_search_urls", "scrape_listing_text"]
