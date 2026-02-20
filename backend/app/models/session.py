from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SessionState(str, Enum):
    WAITING_FOR_CALL = "waiting_for_call"
    ACTIVE = "active"
    ENDED = "ended"


@dataclass
class Session:
    code: str
    state: SessionState = SessionState.WAITING_FOR_CALL
    start_url: str = "https://www.google.com"
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    # Cookies forwarded from the user's browser
    cookies: list[dict] = field(default_factory=list)

    # Set when VAPI call connects
    vapi_call_id: str | None = None

    # Browser service instance (set when browser starts)
    browser_service: Any = None

    # WebSocket connection for the extension
    websocket: Any = None

    # Screenshot streaming task
    screenshot_task: asyncio.Task | None = None

    def touch(self) -> None:
        self.last_activity = time.time()
