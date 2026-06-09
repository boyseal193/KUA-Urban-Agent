"""Lightweight scraper for laundromat-relevant listings.

Reuses the storage stack's ``scraper`` helpers wherever possible to avoid
duplicating Idealista handling. Falls back to a generic ``requests + bs4``
text dump when given an arbitrary URL.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("kua.laundry.scanner")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
TIMEOUT_SEC = 18.0

_COUNT_PATTERNS = (
    re.compile(r"(\d[\d\s.]*)\s+(?:locales|inmuebles|resultados|anuncios)", re.I),
    re.compile(r"\"(?:total|numFound|listingCount)\"\s*:\s*(\d+)", re.I),
    re.compile(r"data-total-results=\"(\d+)\"", re.I),
)


def fetch_listing_text(url: str) -> Dict[str, Any]:
    if not url:
        return {"success": False, "error": "empty_url"}
    try:
        try:
            from scraper import scrape_listing_text  # type: ignore

            res = scrape_listing_text(url)
            if isinstance(res, dict) and res.get("success"):
                return {
                    "success": True,
                    "url": url,
                    "raw_text": res.get("raw_text") or res.get("text") or "",
                    "html": res.get("html") or res.get("raw_html") or "",
                    "source": "storage_scraper",
                }
        except Exception as exc:
            log.info("Storage scraper unavailable, falling back to generic: %s", exc)

        r = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
            timeout=TIMEOUT_SEC,
            allow_redirects=True,
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = " ".join(soup.get_text(" ").split())
        return {
            "success": True,
            "url": url,
            "raw_text": text,
            "html": r.text,
            "source": "generic_html",
        }
    except Exception as exc:
        log.warning("Scrape failed for %s: %s", url, exc)
        return {"success": False, "url": url, "error": str(exc)}


def _parse_total_from_html(html: str) -> Optional[int]:
    for pattern in _COUNT_PATTERNS:
        m = pattern.search(html)
        if m:
            raw = m.group(1).replace(".", "").replace(" ", "").strip()
            try:
                return int(raw)
            except ValueError:
                continue
    return None


def _extract_urls_from_soup(soup: BeautifulSoup, *, limit: int) -> List[str]:
    urls: List[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/inmueble/" in href or href.startswith("/inmueble"):
            if href.startswith("/"):
                href = "https://www.idealista.com" + href
            href = href.split("?")[0]
            if href not in urls:
                urls.append(href)
            if len(urls) >= limit:
                break
        elif href.startswith("/inmueble") or "/local" in href or "/lavanderia" in href:
            if href.startswith("/"):
                href = "https://www.idealista.com" + href
            if href not in urls:
                urls.append(href)
            if len(urls) >= limit:
                break
    return urls


def discover_listing_urls(search_url: str, *, limit: int = 20) -> List[str]:
    if not search_url:
        return []
    try:
        try:
            from scraper import scrape_idealista_search_urls  # type: ignore

            res = scrape_idealista_search_urls(search_url, limit=limit)
            if isinstance(res, dict) and res.get("success"):
                return list(res.get("urls") or [])[:limit]
        except Exception as exc:
            log.info("Idealista discovery unavailable, falling back: %s", exc)

        r = requests.get(
            search_url,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SEC,
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        return _extract_urls_from_soup(soup, limit=limit)
    except Exception as exc:
        log.warning("URL discovery failed for %s: %s", search_url, exc)
        return []


def estimate_listing_count(search_url: str, *, probe_limit: int = 5) -> int:
    """Estimate how many listings a search URL returns (for pre-flight validation)."""
    if not search_url:
        return 0
    try:
        try:
            from scraper import scrape_idealista_search_urls  # type: ignore

            res = scrape_idealista_search_urls(search_url, limit=probe_limit)
            if isinstance(res, dict) and res.get("success"):
                urls = list(res.get("urls") or [])
                if urls:
                    return max(len(urls), int(res.get("count") or len(urls)))
                return 0
        except Exception as exc:
            log.info("Idealista count probe unavailable, falling back: %s", exc)

        r = requests.get(
            search_url,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SEC,
        )
        r.raise_for_status()
        html = r.text
        parsed_total = _parse_total_from_html(html)
        if parsed_total is not None and parsed_total > 0:
            return parsed_total
        soup = BeautifulSoup(html, "lxml")
        urls = _extract_urls_from_soup(soup, limit=probe_limit)
        return len(urls)
    except Exception as exc:
        log.warning("Listing count estimate failed for %s: %s", search_url, exc)
        return 0
