"""In-memory WebSocket hub + optional Redis cross-process fan-out."""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any, DefaultDict, Dict, List, Optional, Set
from uuid import UUID

import structlog
from fastapi import WebSocket
from redis.asyncio import Redis

log = structlog.get_logger(__name__)


class WebSocketManager:
    """
    Channel-based pub/sub for live scans.

    * Same process: direct broadcast to connected clients.
    * Multi-worker: set REDIS_URL and call `publish_redis` from workers / scan loop.
    """

    def __init__(self, redis: Optional[Redis] = None) -> None:
        self._connections: DefaultDict[str, Set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._redis = redis
        self._pubsub_task: Optional[asyncio.Task] = None

    async def connect(self, channel: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[channel].add(ws)
        log.info("ws.connected", channel=channel)

    async def disconnect(self, channel: str, ws: WebSocket) -> None:
        async with self._lock:
            self._connections[channel].discard(ws)
        log.info("ws.disconnected", channel=channel)

    async def broadcast(self, channel: str, message: Dict[str, Any]) -> None:
        dead: List[WebSocket] = []
        payload = json.dumps(message, default=str)
        async with self._lock:
            targets = list(self._connections.get(channel, set()))
        for ws in targets:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(channel, ws)

    async def publish_redis(self, channel: str, message: Dict[str, Any]) -> None:
        if not self._redis:
            await self.broadcast(channel, message)
            return
        await self._redis.publish(f"ws:{channel}", json.dumps(message, default=str))

    async def start_redis_listener(self) -> None:
        if not self._redis:
            return

        async def _listen() -> None:
            pubsub = self._redis.pubsub()
            await pubsub.psubscribe("ws:*")
            async for msg in pubsub.listen():
                if msg["type"] != "pmessage":
                    continue
                try:
                    raw = msg["data"]
                    if isinstance(raw, (bytes, bytearray)):
                        raw = raw.decode("utf-8")
                    data = json.loads(raw)
                    ch = msg["channel"]
                    if isinstance(ch, (bytes, bytearray)):
                        ch = ch.decode("utf-8")
                    chan = ch.split(":", 1)[1]
                    await self.broadcast(chan, data)
                except Exception as e:
                    log.warning("ws.redis_parse_error", error=str(e))

        self._pubsub_task = asyncio.create_task(_listen())

    async def shutdown(self) -> None:
        if self._pubsub_task:
            self._pubsub_task.cancel()
        if self._redis:
            await self._redis.close()


def channel_scan(scan_id: UUID) -> str:
    return f"scan:{scan_id}"
