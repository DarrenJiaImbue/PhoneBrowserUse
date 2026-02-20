from __future__ import annotations

import asyncio
import base64
import json
import logging
import tempfile
from pathlib import Path

import anthropic
from browser_use import Agent, BrowserSession, ChatBrowserUse

from app.config import settings

logger = logging.getLogger(__name__)

# Persistent profile directory — each user gets their own subdirectory
# keyed by session code. Profiles survive server restarts so logins persist.
PROFILES_DIR = Path(__file__).resolve().parent.parent.parent / "browser_profiles"
PROFILES_DIR.mkdir(exist_ok=True)


class BrowserService:
    """Wraps browser-use library for browser automation with BU 2.0."""

    def __init__(self) -> None:
        self._session: BrowserSession | None = None
        self._llm = ChatBrowserUse(model="bu-2-0")
        self._anthropic = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._agent_task: asyncio.Task | None = None
        self._stopped = False
        self._storage_state_path: str | None = None

    async def start_browser(
        self,
        url: str = "https://www.google.com",
        cookies: list[dict] | None = None,
        profile_id: str | None = None,
    ) -> None:
        session_kwargs = {
            "headless": True,
            "keep_alive": True,
            "channel": "chrome",
        }

        # Use a persistent profile so logins survive across sessions.
        # Cookies from the extension are loaded into the profile on first use,
        # then the profile itself maintains the login state going forward.
        if profile_id:
            profile_dir = PROFILES_DIR / profile_id
            profile_dir.mkdir(exist_ok=True)
            session_kwargs["user_data_dir"] = str(profile_dir)

        if cookies:
            self._storage_state_path = self._build_storage_state(cookies)
            logger.info("Loaded %d cookies into storage state", len(cookies))
            session_kwargs["storage_state"] = self._storage_state_path

        self._session = BrowserSession(**session_kwargs)
        await self._session.start()
        # Open the requested page
        page = await self._session.get_current_page()
        await page.goto(url)
        logger.info("Browser started and navigated to %s", url)

    @staticmethod
    def _build_storage_state(cookies: list[dict]) -> str:
        """Convert cookie dicts from the Chrome extension into a Playwright
        storage_state JSON file and return its path."""
        pw_cookies = []
        for c in cookies:
            pw_cookie = {
                "name": c["name"],
                "value": c["value"],
                "domain": c["domain"],
                "path": c.get("path", "/"),
                "secure": c.get("secure", False),
                "httpOnly": c.get("httpOnly", False),
                "sameSite": c.get("sameSite", "Lax"),
            }
            expires = c.get("expires", -1)
            if expires and expires > 0:
                pw_cookie["expires"] = expires
            pw_cookies.append(pw_cookie)

        state = {"cookies": pw_cookies, "origins": []}
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, prefix="pbu_cookies_"
        )
        json.dump(state, tmp)
        tmp.close()
        return tmp.name

    async def execute_action(self, instruction: str) -> str:
        """Run a browser-use agent with a natural language instruction.
        Returns the agent's own description of what happened."""
        if self._stopped:
            raise RuntimeError("Browser service has been stopped")
        if not self._session:
            raise RuntimeError("Browser not started")

        agent = Agent(
            task=instruction,
            llm=self._llm,
            browser_session=self._session,
        )
        self._agent_task = asyncio.create_task(agent.run())
        try:
            result = await self._agent_task
        except asyncio.CancelledError:
            logger.info("Agent task was cancelled (session ended)")
            raise RuntimeError("Browser session ended")
        finally:
            self._agent_task = None

        if self._stopped:
            raise RuntimeError("Browser service has been stopped")

        # Extract the agent's final result text
        final = result.final_result()
        if final:
            return final

        # Fallback: use vision to describe the page
        return await self.describe_page()

    async def navigate_to(self, url: str) -> str:
        """Navigate directly to a URL. Returns page description."""
        if not self._session:
            raise RuntimeError("Browser not started")

        page = await self._session.get_current_page()
        await page.goto(url)
        logger.info("Navigated to %s", url)

        return await self.describe_page()

    async def take_screenshot(self) -> str:
        """Take a screenshot and return base64-encoded JPEG."""
        if not self._session:
            raise RuntimeError("Browser not started")

        screenshot_bytes = await self._session.take_screenshot(
            format="jpeg", quality=70
        )
        return base64.b64encode(screenshot_bytes).decode("utf-8")

    async def describe_page(self) -> str:
        """Use Claude vision to describe the current page in 2-3 simple sentences."""
        screenshot_b64 = await self.take_screenshot()

        response = self._anthropic.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": screenshot_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Describe this web page in 2-3 simple sentences "
                                "for an elderly person who is listening over the phone. "
                                "Focus on what's visible and any key information. "
                                "Use plain, easy-to-understand language."
                            ),
                        },
                    ],
                }
            ],
        )

        return response.content[0].text

    async def stop(self) -> None:
        """Signal the service to stop and cancel any running agent task."""
        self._stopped = True
        if self._agent_task and not self._agent_task.done():
            self._agent_task.cancel()
            logger.info("Cancelled running agent task")

    async def close(self) -> None:
        await self.stop()
        if self._session:
            # Use stop() to allow StorageStateWatchdog to save cookies
            # back to the persistent profile before shutdown.
            try:
                await self._session.stop()
            except Exception:
                # Fall back to kill() if graceful stop fails
                try:
                    await self._session.kill()
                except Exception:
                    pass
            self._session = None
            logger.info("Browser closed")
        # Clean up temp cookie file
        if self._storage_state_path:
            import os
            try:
                os.unlink(self._storage_state_path)
            except OSError:
                pass
            self._storage_state_path = None
