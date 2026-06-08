"""Lightweight scraper for laundromat-relevant listings.

Reuses the storage stack's ``scraper`` helpers wherever possible to avoid
duplicating Idealista handling. Falls back to a generic ``requests + bs4``
text dump when given an arbitrary URL.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("kua.laundry.scanner")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
TIMEOUT_SEC = 18.0


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
                    "source": "storage_scraper",
                }
        except Exception as exc:
            log.info("Storage scraper unavailable, falling back to generic: %s", exc)

        r = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
                          timeout=TIMEOUT_SEC, allow_redirects=True)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        for tag in soup(["script", "style", "noscript"]): tag.decompose()
        text = " ".join(soup.get_text(" ").split())
        return {"success": True, "url": url, "raw_text": text, "source": "generic_html"}
    except Exception as exc:
        log.warning("Scrape failed for %s: %s", url, exc)
        return {"success": False, "url": url, "error": str(exc)}


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

        r = requests.get(search_url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SEC)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        urls: List[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("/inmueble") or "/local" in href or "/lavanderia" in href:
                if href.startswith("/"):
                    href = "https://www.idealista.com" + href
                if href not in urls:
                    urls.append(href)
                if len(urls) >= limit: break
        return urls
    except Exception as exc:
        log.warning("URL discovery failed for %s: %s", search_url, exc)
        return []
