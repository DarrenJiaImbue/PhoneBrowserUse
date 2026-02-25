"""Browser-use benchmarks: Claude Sonnet, Gemini 2.5 Flash, BU 2.0.

Uses browser-use cloud mode (use_cloud=True) so both the browser and
orchestration run in browser-use's cloud — no local CDP round-trips.
"""

from __future__ import annotations

import os
import time
import traceback

import httpx
from browser_use import Agent, BrowserSession, ChatBrowserUse
from browser_use.llm.anthropic.chat import ChatAnthropic
from browser_use.llm.google.chat import ChatGoogle

from .config import (
    ANTHROPIC_API_KEY,
    BROWSER_USE_API_KEY,
    BU_BU2_MODEL,
    BU_CLAUDE_MODEL,
    BU_GEMINI_MODEL,
    GOOGLE_API_KEY,
    MAX_STEPS,
    TASK,
)


async def _run_with_llm(name: str, model_label: str, llm) -> dict:
    """Shared runner: create a cloud session, run the agent, return results."""
    session = BrowserSession(use_cloud=True)
    startup_s = 0.0
    action_s = 0.0
    try:
        # --- Startup: create cloud browser + create agent ---
        t0 = time.perf_counter()
        await session.start()

        # Print live viewer URL
        cloud_session_id = session._cloud_browser_client.current_session_id
        if cloud_session_id:
            api_key = os.environ.get("BROWSER_USE_API_KEY", BROWSER_USE_API_KEY)
            async with httpx.AsyncClient() as http:
                resp = await http.get(
                    f"https://api.browser-use.com/api/v2/browsers/{cloud_session_id}",
                    headers={"X-Browser-Use-API-Key": api_key},
                )
                if resp.is_success:
                    data = resp.json()
                    print(f"    Live viewer: {data.get('liveUrl', 'N/A')}")

        agent = Agent(task=TASK, llm=llm, browser_session=session)
        startup_s = round(time.perf_counter() - t0, 2)

        # --- Action: agent.run() ---
        t1 = time.perf_counter()
        history = await agent.run(max_steps=MAX_STEPS)
        action_s = round(time.perf_counter() - t1, 2)

        result_text = history.final_result() or ""
        return {
            "framework": "browser-use",
            "mode": "-",
            "name": name,
            "model": model_label,
            "startup_s": startup_s,
            "action_s": action_s,
            "result_text": result_text,
            "success": True,
            "error": None,
        }
    except Exception as exc:
        return {
            "framework": "browser-use",
            "mode": "-",
            "name": name,
            "model": model_label,
            "startup_s": startup_s,
            "action_s": action_s,
            "result_text": "",
            "success": False,
            "error": f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
        }
    finally:
        await session.stop()


async def run_browser_use_claude() -> dict:
    """Browser-use with Claude Sonnet."""
    llm = ChatAnthropic(model=BU_CLAUDE_MODEL, api_key=ANTHROPIC_API_KEY)
    return await _run_with_llm("bu-claude", BU_CLAUDE_MODEL, llm)


async def run_browser_use_gemini() -> dict:
    """Browser-use with Gemini 2.5 Flash."""
    llm = ChatGoogle(model=BU_GEMINI_MODEL, api_key=GOOGLE_API_KEY)
    return await _run_with_llm("bu-gemini", BU_GEMINI_MODEL, llm)


async def run_browser_use_bu2() -> dict:
    """Browser-use with BU 2.0 model."""
    llm = ChatBrowserUse(model=BU_BU2_MODEL, api_key=BROWSER_USE_API_KEY)
    return await _run_with_llm("bu-bu2", BU_BU2_MODEL, llm)
