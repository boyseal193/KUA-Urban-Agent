"""In-process TTL cache for laundry pipeline hot paths.

Avoids re-scraping identical URLs within a worker process and skips redundant
memo generation when the same listing is retried.
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger("kua.laundry.cache")

_DEFAULT_TTL_SEC = int(os.getenv("LAUNDRY_CACHE_TTL_SEC", "3600"))
_MAX_ENTRIES = int(os.getenv("LAUNDRY_CACHE_MAX_ENTRIES", "512"))

_lock = threading.Lock()
_page_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_extract_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_memo_cache: Dict[str, Tuple[float, str]] = {}


def _norm_url(url: Optional[str]) -> str:
    return (url or "").strip().split("?")[0].rstrip("/").lower()


def _evict(cache: Dict[str, Tuple[float, Any]]) -> None:
    if len(cache) <= _MAX_ENTRIES:
        return
    oldest = sorted(cache.items(), key=lambda item: item[1][0])[: len(cache) - _MAX_ENTRIES]
    for key, _ in oldest:
        cache.pop(key, None)


def get_listing_page(url: str) -> Optional[Dict[str, Any]]:
    key = _norm_url(url)
    if not key:
        return None
    with _lock:
        row = _page_cache.get(key)
        if not row:
            return None
        expires, payload = row
        if time.monotonic() > expires:
            _page_cache.pop(key, None)
            return None
        log.debug("cache.page hit url=%s", url)
        return dict(payload)


def set_listing_page(url: str, payload: Dict[str, Any], *, ttl_sec: Optional[int] = None) -> None:
    key = _norm_url(url)
    if not key or not payload.get("success"):
        return
    ttl = ttl_sec if ttl_sec is not None else _DEFAULT_TTL_SEC
    with _lock:
        _page_cache[key] = (time.monotonic() + ttl, dict(payload))
        _evict(_page_cache)


def get_extracted(url: str) -> Optional[Dict[str, Any]]:
    key = _norm_url(url)
    if not key:
        return None
    with _lock:
        row = _extract_cache.get(key)
        if not row:
            return None
        expires, payload = row
        if time.monotonic() > expires:
            _extract_cache.pop(key, None)
            return None
        log.debug("cache.extract hit url=%s", url)
        return dict(payload)


def set_extracted(url: str, payload: Dict[str, Any], *, ttl_sec: Optional[int] = None) -> None:
    key = _norm_url(url)
    if not key or not payload:
        return
    ttl = ttl_sec if ttl_sec is not None else _DEFAULT_TTL_SEC
    with _lock:
        _extract_cache[key] = (time.monotonic() + ttl, dict(payload))
        _evict(_extract_cache)


def memo_cache_key(*, listing_url: Optional[str], extracted: Dict[str, Any]) -> str:
    norm = _norm_url(listing_url)
    if norm:
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()
    blob = "|".join(
        str(extracted.get(k) or "")
        for k in ("address", "city", "floor_area_m2", "asking_rent_month", "asking_price")
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def get_memo(key: str) -> Optional[str]:
    if not key:
        return None
    with _lock:
        row = _memo_cache.get(key)
        if not row:
            return None
        expires, memo = row
        if time.monotonic() > expires:
            _memo_cache.pop(key, None)
            return None
        return memo


def set_memo(key: str, memo_md: str, *, ttl_sec: Optional[int] = None) -> None:
    if not key or not memo_md:
        return
    ttl = ttl_sec if ttl_sec is not None else _DEFAULT_TTL_SEC
    with _lock:
        _memo_cache[key] = (time.monotonic() + ttl, memo_md)
        _evict(_memo_cache)
