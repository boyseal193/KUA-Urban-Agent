"""WebSocket routes."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, WebSocket, WebSocketException, status
from app.websocket.manager import WebSocketManager, channel_scan

router = APIRouter()


def get_ws_manager(websocket: WebSocket) -> WebSocketManager:
    return websocket.app.state.ws_manager


async def _auth_or_close(websocket: WebSocket) -> None:
    from app.core.config import get_settings
    from app.core.security import safe_decode

    settings = get_settings()
    token = websocket.query_params.get("token")
    if not token:
        token = websocket.cookies.get(settings.COOKIE_ACCESS_NAME)
    if not token:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")

    payload = safe_decode(settings, token)
    if not payload or payload.get("type") != "access":
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")


@router.websocket("/ws/live/{scan_id}")
async def websocket_live_scan(websocket: WebSocket, scan_id: uuid.UUID) -> None:
    """
    Live scan channel for the **storage** pipeline.

    Authenticate via query `?token=<access_jwt>` (browser WS cannot send cookies
    cross-origin in all cases; Next.js same-origin can use cookie).
    """
    await _auth_or_close(websocket)
    manager: WebSocketManager = get_ws_manager(websocket)
    ch = channel_scan(scan_id)
    await manager.connect(ch, websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        await manager.disconnect(ch, websocket)


@router.websocket("/ws/laundry/{job_id}")
async def websocket_laundry_scan(websocket: WebSocket, job_id: uuid.UUID) -> None:
    """Live channel for laundry scan jobs (separate channel namespace)."""
    await _auth_or_close(websocket)
    manager: WebSocketManager = get_ws_manager(websocket)
    ch = f"laundry-scan:{job_id}"
    await manager.connect(ch, websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        await manager.disconnect(ch, websocket)
