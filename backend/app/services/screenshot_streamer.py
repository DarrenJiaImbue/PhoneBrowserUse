from __future__ import annotations

import json
import logging

from starlette.websockets import WebSocket, WebSocketState

logger = logging.getLogger(__name__)


async def send_live_url(websocket: WebSocket, live_url: str) -> None:
    """Send the browser-use cloud live viewer URL to the extension."""
    if websocket.client_state != WebSocketState.CONNECTED:
        return
    message = json.dumps({
        "type": "live_url",
        "url": live_url,
    })
    await websocket.send_text(message)
    logger.info("Sent live URL to extension: %s", live_url)


async def send_status(websocket: WebSocket, status: str, detail: str = "") -> None:
    """Send a status message over the WebSocket."""
    if websocket.client_state != WebSocketState.CONNECTED:
        return
    message = json.dumps({
        "type": "status",
        "status": status,
        "detail": detail,
    })
    await websocket.send_text(message)


async def send_session_ended(websocket: WebSocket) -> None:
    """Notify the extension that the session has ended."""
    if websocket.client_state != WebSocketState.CONNECTED:
        return
    message = json.dumps({"type": "session_ended"})
    await websocket.send_text(message)
