"""Lightweight scraper for laundromat-relevant listings.

Reuses the storage stack's ``scraper`` helpers wherever possible to avoid
duplicating Idealista handling. Falls back to a generic ``requests + bs4``
text dump when given an arbitrary URL.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from laundry import cache as page_cache
from laundry.limits import clamp_listing_limit, search_max_pages

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


@dataclass
class DiscoverResult:
    urls: List[str]
    discovered_count: int
    source_available_count: Optional[int] = None
    pages_fetched: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "urls": self.urls,
            "discovered_count": self.discovered_count,
            "source_available_count": self.source_available_count,
            "pages_fetched": self.pages_fetched,
        }


def fetch_listing_text(url: str) -> Dict[str, Any]:
    if not url:
        return {"success": False, "error": "empty_url"}

    cached = page_cache.get_listing_page(url)
    if cached:
        return cached

    try:
        try:
            from scraper import scrape_listing_text  # type: ignore

            res = scrape_listing_text(url)
            if isinstance(res, dict) and res.get("success"):
                payload = {
                    "success": True,
                    "url": url,
                    "raw_text": res.get("raw_text") or res.get("text") or "",
                    "html": res.get("html") or res.get("raw_html") or "",
                    "source": "storage_scraper",
                }
                page_cache.set_listing_page(url, payload)
                return payload
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
        payload = {
            "success": True,
            "url": url,
            "raw_text": text,
            "html": r.text,
            "source": "generic_html",
        }
        page_cache.set_listing_page(url, payload)
        return payload
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


def _search_page_url(base_url: str, page: int) -> str:
    if page <= 1:
        return base_url
    parsed = urlparse(base_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["pagina"] = [str(page)]
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def _merge_unique_urls(existing: List[str], batch: List[str], *, limit: int) -> List[str]:
    seen = {u.split("?")[0].rstrip("/").lower() for u in existing}
    out = list(existing)
    for url in batch:
        key = url.split("?")[0].rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(url)
        if len(out) >= limit:
            break
    return out


def discover_listings(search_url: str, *, limit: int = 20) -> DiscoverResult:
    """Discover listing detail URLs, paginating until ``limit`` is reached."""
    limit = clamp_listing_limit(limit)
    if not search_url:
        return DiscoverResult(urls=[], discovered_count=0, source_available_count=0, pages_fetched=0)

    urls: List[str] = []
    source_available_count: Optional[int] = None
    pages_fetched = 0
    max_pages = search_max_pages(limit)
    empty_streak = 0

    try:
        try:
            from scraper import scrape_idealista_search_urls  # type: ignore

            for page in range(1, max_pages + 1):
                page_url = _search_page_url(search_url, page)
                remaining = max(limit - len(urls), 0)
                if remaining <= 0:
                    break
                res = scrape_idealista_search_urls(page_url, limit=remaining)
                pages_fetched += 1
                if not isinstance(res, dict) or not res.get("success"):
                    empty_streak += 1
                    if page == 1:
                        break
                    if empty_streak >= 2:
                        break
                    continue
                batch = list(res.get("urls") or [])
                if page == 1:
                    parsed = _parse_total_from_html(str(res.get("html") or ""))
                    if parsed is not None and parsed > 0:
                        source_available_count = parsed
                if not batch:
                    empty_streak += 1
                    if empty_streak >= 2:
                        break
                    continue
                empty_streak = 0
                before = len(urls)
                urls = _merge_unique_urls(urls, batch, limit=limit)
                if len(urls) == before:
                    empty_streak += 1
                    if empty_streak >= 2:
                        break
                if len(urls) >= limit:
                    break

            if urls:
                discovered = len(urls)
                if source_available_count is None:
                    source_available_count = discovered
                log.info(
                    "discover_listings paginated search_url=%s found=%s limit=%s pages=%s source_total=%s",
                    search_url,
                    discovered,
                    limit,
                    pages_fetched,
                    source_available_count,
                )
                return DiscoverResult(
                    urls=urls[:limit],
                    discovered_count=discovered,
                    source_available_count=source_available_count,
                    pages_fetched=pages_fetched,
                )
        except Exception as exc:
            log.info("Idealista discovery unavailable, falling back: %s", exc)

        empty_streak = 0
        for page in range(1, max_pages + 1):
            page_url = _search_page_url(search_url, page)
            remaining = max(limit - len(urls), 0)
            if remaining <= 0:
                break
            r = requests.get(
                page_url,
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT_SEC,
            )
            r.raise_for_status()
            pages_fetched += 1
            if page == 1:
                parsed = _parse_total_from_html(r.text)
                if parsed is not None and parsed > 0:
                    source_available_count = parsed
            soup = BeautifulSoup(r.text, "lxml")
            batch = _extract_urls_from_soup(soup, limit=remaining)
            if not batch:
                empty_streak += 1
                if empty_streak >= 2:
                    break
                continue
            empty_streak = 0
            before = len(urls)
            urls = _merge_unique_urls(urls, batch, limit=limit)
            if len(urls) == before:
                empty_streak += 1
                if empty_streak >= 2:
                    break
            if len(urls) >= limit:
                break

        discovered = len(urls)
        if source_available_count is None:
            source_available_count = discovered
        return DiscoverResult(
            urls=urls[:limit],
            discovered_count=discovered,
            source_available_count=source_available_count,
            pages_fetched=pages_fetched,
        )
    except Exception as exc:
        log.warning("URL discovery failed for %s: %s", search_url, exc)
        discovered = len(urls)
        if source_available_count is None:
            source_available_count = discovered
        return DiscoverResult(
            urls=urls[:limit],
            discovered_count=discovered,
            source_available_count=source_available_count,
            pages_fetched=pages_fetched,
        )


def discover_listing_urls(search_url: str, *, limit: int = 20) -> List[str]:
    """Back-compat wrapper returning URL list only."""
    return discover_listings(search_url, limit=limit).urls


def estimate_listing_count(search_url: str, *, probe_limit: int = 5) -> int:
    """Estimate how many listings a search URL returns (for pre-flight validation)."""
    if not search_url:
        return 0
    try:
        try:
            from scraper import scrape_idealista_search_urls  # type: ignore

            res = scrape_idealista_search_urls(search_url, limit=probe_limit)
            if isinstance(res, dict) and res.get("success"):
                parsed = _parse_total_from_html(str(res.get("html") or ""))
                if parsed is not None and parsed > 0:
                    return parsed
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
