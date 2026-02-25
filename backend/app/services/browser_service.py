from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from pathlib import Path

import anthropic
import httpx
from browser_use import Agent, BrowserSession, ChatBrowserUse
from browser_use.browser.cloud.cloud import CloudBrowserClient

from app.config import settings

logger = logging.getLogger(__name__)

# Monkey-patch: browser-use SDK serializes profile_id (snake_case) but the
# cloud API expects profileId (camelCase).  Pydantic's extra='forbid' prevents
# patching model_dump on instances, so we patch the class method instead.
_FIELD_REMAP = {
    "profile_id": "profileId",
    "cloud_profile_id": "profileId",
    "proxy_country_code": "proxyCountryCode",
    "cloud_proxy_country_code": "proxyCountryCode",
}

from browser_use.browser.cloud.views import CreateBrowserRequest

_original_model_dump = CreateBrowserRequest.model_dump


def _patched_model_dump(self, **kwargs):
    data = _original_model_dump(self, **kwargs)
    remapped = {_FIELD_REMAP.get(k, k): v for k, v in data.items()}
    # Strip None values so the API doesn't receive null for unset cloud params
    if kwargs.get("exclude_unset") or kwargs.get("exclude_none"):
        remapped = {k: v for k, v in remapped.items() if v is not None}
    return remapped


CreateBrowserRequest.model_dump = _patched_model_dump

# Maps extension-generated UUIDs → browser-use cloud profile IDs.
# Persisted to disk so mappings survive server restarts.
_PROFILE_MAP_PATH = Path(__file__).resolve().parent.parent.parent / "cloud_profiles.json"

_BU_API = "https://api.browser-use.com/api/v2"


def _get_api_key() -> str:
    return settings.browser_use_api_key or os.environ.get("BROWSER_USE_API_KEY", "")


def _load_profile_map() -> dict[str, str]:
    if _PROFILE_MAP_PATH.exists():
        return json.loads(_PROFILE_MAP_PATH.read_text())
    return {}


def _save_profile_map(m: dict[str, str]) -> None:
    _PROFILE_MAP_PATH.write_text(json.dumps(m, indent=2))


async def _ensure_cloud_profile(local_id: str) -> str:
    """Return the browser-use cloud profile ID for a local extension ID.

    Creates a new cloud profile on first encounter and caches the mapping.
    """
    profile_map = _load_profile_map()
    if local_id in profile_map:
        cloud_id = profile_map[local_id]
        logger.info(">>> PROFILE REUSE: local=%s -> cloud=%s", local_id, cloud_id)
        return cloud_id

    # Create a new profile on browser-use cloud
    api_key = _get_api_key()
    async with httpx.AsyncClient() as http:
        resp = await http.post(
            f"{_BU_API}/profiles",
            headers={"X-Browser-Use-API-Key": api_key},
            json={"name": f"pbu-{local_id[:8]}"},
        )
        resp.raise_for_status()
        cloud_profile_id = resp.json()["id"]

    profile_map[local_id] = cloud_profile_id
    _save_profile_map(profile_map)
    logger.info(
        "Created cloud profile %s for local ID %s", cloud_profile_id, local_id
    )
    return cloud_profile_id


class BrowserService:
    """Wraps browser-use library for browser automation with BU 2.0.

    Uses browser-use cloud mode so both the browser and orchestration
    run on browser-use's servers — no local CDP round-trips.
    """

    def __init__(self) -> None:
        self._session: BrowserSession | None = None
        self._llm = ChatBrowserUse(model="bu-2-0")
        self._anthropic = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._agent: Agent | None = None
        self._agent_task: asyncio.Task | None = None
        self._stopped = False
        self._live_url: str | None = None

    @property
    def live_url(self) -> str | None:
        return self._live_url

    async def start_browser(
        self,
        url: str = "https://www.google.com",
        profile_id: str | None = None,
    ) -> None:
        """Start a cloud browser session and navigate to the URL.

        If profile_id is provided, browser-use cloud will restore cookies
        and login state from a previous session with the same profile.
        """
        session_kwargs: dict = {
            "use_cloud": True,
            "keep_alive": True,
            "args": ["--homepage=https://www.google.com", "--new-tab-page=https://www.google.com"],
        }
        if profile_id:
            cloud_id = await _ensure_cloud_profile(profile_id)
            session_kwargs["cloud_profile_id"] = cloud_id
            logger.info(">>> STARTING BROWSER with cloud_profile_id=%s (local=%s)", cloud_id, profile_id)
        else:
            logger.info(">>> STARTING BROWSER with NO profile (profile_id was None)")
        logger.info(">>> BrowserSession kwargs: %s", {k: v for k, v in session_kwargs.items() if k != "args"})
        self._session = BrowserSession(**session_kwargs)
        await self._session.start()

        # Fetch the live viewer URL from browser-use cloud API
        try:
            cloud_session_id = self._session._cloud_browser_client.current_session_id
            if cloud_session_id:
                api_key = _get_api_key()
                async with httpx.AsyncClient() as http:
                    resp = await http.get(
                        f"https://api.browser-use.com/api/v2/browsers/{cloud_session_id}",
                        headers={"X-Browser-Use-API-Key": api_key},
                    )
                    if resp.is_success:
                        data = resp.json()
                        self._live_url = data.get("liveUrl")
                        logger.info("Live viewer URL: %s", self._live_url)
        except Exception:
            logger.exception("Failed to fetch live viewer URL")

        # Navigate to the requested page
        page = await self._session.get_current_page()
        await page.goto(url)
        logger.info("Cloud browser started and navigated to %s", url)

    async def execute_action(self, instruction: str) -> str:
        """Run a browser-use agent with a natural language instruction.

        The agent is kept alive across calls so it retains full context
        (page state, action history, conversation) from previous instructions.
        """
        if self._stopped:
            raise RuntimeError("Browser service has been stopped")
        if not self._session:
            raise RuntimeError("Browser not started")

        if self._agent is None:
            # First call — create the agent
            self._agent = Agent(
                task=instruction,
                llm=self._llm,
                browser_session=self._session,
            )
            logger.info("Created persistent agent for first task")
        else:
            # Follow-up call — inject new task, keeping message history
            self._agent.add_new_task(instruction)
            logger.info("Added follow-up task to persistent agent")

        self._agent_task = asyncio.create_task(self._agent.run())
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
            logger.info(">>> CLOSING cloud browser session...")
            try:
                # Explicitly stop the cloud browser via the API so cookies
                # are saved to the profile.  BrowserSession.stop() with
                # keep_alive=True skips the cloud stop_browser() call, so
                # we must call it ourselves first.
                cloud_client = self._session._cloud_browser_client
                session_id = cloud_client.current_session_id if cloud_client else None
                if session_id:
                    logger.info(">>> Stopping cloud browser %s to save cookies to profile...", session_id)
                    # Call the API directly instead of cloud_client.stop_browser()
                    # because the SDK's CloudBrowserResponse requires non-null
                    # liveUrl/cdpUrl, but the stop response returns nulls.
                    api_key = _get_api_key()
                    async with httpx.AsyncClient(timeout=15.0) as http:
                        resp = await http.patch(
                            f"{_BU_API}/browsers/{session_id}",
                            headers={"X-Browser-Use-API-Key": api_key, "Content-Type": "application/json"},
                            json={"action": "stop"},
                        )
                        resp.raise_for_status()
                    logger.info(">>> Cloud browser stopped — cookies saved to profile")
            except Exception as e:
                logger.warning(">>> Cloud browser stop failed: %s", e)
            try:
                await self._session.stop()
            except Exception:
                pass
            self._session = None
