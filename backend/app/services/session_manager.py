from __future__ import annotations

import asyncio
import logging
import time

from app.config import settings
from app.models.session import Session, SessionState
from app.services.code_generator import CodeGenerator

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages session lifecycle: create, lookup, activate, cleanup."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._code_generator = CodeGenerator()

    def create_session(self) -> Session:
        code = self._code_generator.generate()
        session = Session(code=code)
        self._sessions[code] = session
        logger.info("Session created: %s", code)
        return session

    def get_session(self, code: str) -> Session | None:
        return self._sessions.get(code)

    def get_session_by_call_id(self, call_id: str) -> Session | None:
        """Find an active session by its Vapi call ID."""
        for session in self._sessions.values():
            if session.vapi_call_id == call_id and session.state == SessionState.ACTIVE:
                return session
        return None

    def activate_session(self, code: str, vapi_call_id: str) -> Session | None:
        session = self._sessions.get(code)
        if session is None or session.state != SessionState.WAITING_FOR_CALL:
            return None
        session.state = SessionState.ACTIVE
        session.vapi_call_id = vapi_call_id
        session.touch()
        logger.info("Session activated: %s (call: %s)", code, vapi_call_id)
        return session

    async def end_session(self, code: str) -> None:
        session = self._sessions.pop(code, None)
        if session is None:
            return

        session.state = SessionState.ENDED
        logger.info("Session ending: %s", code)

        # Cancel screenshot streaming first so it doesn't try to use a closing browser
        if session.screenshot_task and not session.screenshot_task.done():
            session.screenshot_task.cancel()
            try:
                await session.screenshot_task
            except asyncio.CancelledError:
                pass

        # Close browser (this also cancels any running agent task)
        if session.browser_service:
            try:
                await session.browser_service.close()
            except Exception:
                logger.exception("Error closing browser for session %s", code)

        # Close WebSocket
        if session.websocket:
            try:
                await session.websocket.close(1000, "Session ended")
            except Exception:
                pass

        self._code_generator.release(code)
        logger.info("Session cleaned up: %s", code)

    async def cleanup_expired(self) -> None:
        now = time.time()
        codes_to_remove: list[str] = []

        for code, session in self._sessions.items():
            if session.state == SessionState.WAITING_FOR_CALL:
                if now - session.created_at > settings.code_expiry_minutes * 60:
                    codes_to_remove.append(code)
            elif session.state == SessionState.ACTIVE:
                if now - session.last_activity > settings.session_timeout_minutes * 60:
                    codes_to_remove.append(code)

        for code in codes_to_remove:
            logger.info("Expiring session: %s", code)
            await self.end_session(code)

    @property
    def active_count(self) -> int:
        return len(self._sessions)
