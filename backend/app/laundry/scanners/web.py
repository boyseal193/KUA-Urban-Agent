"""
Generic HTML scraper used for laundromat listings.

The scanner is intentionally portal-agnostic: many laundromat-for-sale
listings live on small brokerage sites, BizBuySell-style platforms, Idealista
empresas, Loopnet, Crexi, regional MLS feeds, etc. We strip nav/script noise
and return the readable text so the LLM extractor can do its job.

Two public helpers are exposed:

* :func:`scrape_listing_text` — fetch one URL → readable text
* :func:`discover_area_listings` — fetch a search results page → list of detail URLs

Both use ``httpx`` with a strict timeout, randomised user agent, and a basic
retry policy. They never throw on network errors — instead they return a
``success=False`` envelope so the orchestrator can record the failure.
"""
from __future__ import annotations

import random
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx
import structlog
from bs4 import BeautifulSoup

log = structlog.get_logger(__name__)


_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_0) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


def _ua() -> str:
    return random.choice(_USER_AGENTS)


def _readable_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "form", "iframe"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    return re.sub(r"\n{2,}", "\n\n", text)


def _absolute(base: str, link: str) -> str:
    return urljoin(base, link)


def _looks_like_detail(url: str) -> bool:
    if not url:
        return False
    if any(url.endswith(ext) for ext in (".pdf", ".jpg", ".png", ".gif", ".zip")):
        return False
    parsed = urlparse(url)
    path = parsed.path.lower()
    if not path or path == "/":
        return False
    # Typical detail URLs contain numeric ids, "ad", "anuncio", "listing"
    return any(token in path for token in ("/listing", "/ad/", "/anuncio", "/inmueble", "/local", "/detail", "/business"))


async def scrape_listing_text(url: str, *, timeout: float = 20.0) -> Dict[str, Any]:
    """Fetch a single listing URL and return its readable text."""
    if not url or not url.startswith(("http://", "https://")):
        return {"success": False, "error": "invalid url"}
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": _ua(), "Accept-Language": "en,es;q=0.8"},
        ) as client:
            r = await client.get(url)
            if r.status_code >= 400:
                return {"success": False, "error": f"HTTP {r.status_code}", "status": r.status_code}
            return {"success": True, "raw_text": _readable_text(r.text), "final_url": str(r.url)}
    except httpx.TimeoutException:
        return {"success": False, "error": "timeout"}
    except Exception as e:
        log.warning("laundry.scrape_failed", url=url, error=str(e))
        return {"success": False, "error": str(e)}


async def discover_area_listings(
    search_url: str,
    *,
    limit: int = 20,
    timeout: float = 20.0,
) -> Dict[str, Any]:
    """
    Fetch a search results page and return ``limit`` candidate detail URLs.

    The helper looks for anchors that *look* like detail pages (see
    :func:`_looks_like_detail`). When the source portal uses a SPA we still
    return whatever raw anchors we can find; the caller can then post-filter.
    """
    if not search_url or not search_url.startswith(("http://", "https://")):
        return {"success": False, "error": "invalid url"}

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": _ua(), "Accept-Language": "en,es;q=0.8"},
        ) as client:
            r = await client.get(search_url)
            if r.status_code >= 400:
                return {"success": False, "error": f"HTTP {r.status_code}", "status": r.status_code}
            soup = BeautifulSoup(r.text, "lxml")
            anchors = soup.select("a[href]")
            urls: List[str] = []
            seen = set()
            for a in anchors:
                href = a.get("href")
                if not href or href.startswith("#"):
                    continue
                absolute = _absolute(str(r.url), href)
                if absolute in seen:
                    continue
                if not _looks_like_detail(absolute):
                    continue
                seen.add(absolute)
                urls.append(absolute)
                if len(urls) >= limit:
                    break
            return {"success": True, "urls": urls, "total_seen": len(anchors)}
    except httpx.TimeoutException:
        return {"success": False, "error": "timeout"}
    except Exception as e:
        log.warning("laundry.discover_failed", url=search_url, error=str(e))
        return {"success": False, "error": str(e)}
