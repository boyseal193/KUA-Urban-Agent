"""Redis-backed cache helpers (graceful degradation if Redis is down)."""
from __future__ import annotations

import json
from typing import Any, Optional

import structlog
from redis.asyncio import Redis

log = structlog.get_logger(__name__)


async def cache_get_json(client: Optional[Redis], key: str) -> Optional[Any]:
    if not client:
        return None
    try:
        raw = await client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        log.warning("cache.get_failed", key=key, error=str(e))
        return None


async def cache_set_json(
    client: Optional[Redis],
    key: str,
    value: Any,
    *,
    ttl_seconds: int,
) -> None:
    if not client:
        return
    try:
        await client.setex(key, ttl_seconds, json.dumps(value, default=str))
    except Exception as e:
        log.warning("cache.set_failed", key=key, error=str(e))
