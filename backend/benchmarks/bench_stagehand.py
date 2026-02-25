"""Stagehand benchmarks: DOM / Hybrid / CUA × Claude Sonnet / Gemini 2.5 Flash.

Uses server="remote" so the Node.js orchestration runs in Stagehand's cloud,
co-located with the Browserbase browser — no local CDP round-trips.
"""

from __future__ import annotations

import time
import traceback

from browserbase import AsyncBrowserbase
from stagehand import AsyncStagehand

from .config import (
    ANTHROPIC_API_KEY,
    BROWSERBASE_API_KEY,
    BROWSERBASE_PROJECT_ID,
    GOOGLE_API_KEY,
    MAX_STEPS,
    SH_CLAUDE_MODEL,
    SH_GEMINI_MODEL,
    TASK,
)


def _api_key_for_model(model_name: str) -> str:
    if model_name.startswith("anthropic/"):
        return ANTHROPIC_API_KEY
    if model_name.startswith("google/"):
        return GOOGLE_API_KEY
    return ""


def _short_model(model_name: str) -> str:
    """'anthropic/claude-sonnet-4-6' → 'claude-sonnet'."""
    if "claude" in model_name:
        return "claude-sonnet"
    if "gemini" in model_name:
        return "gemini-flash"
    return model_name


async def run_stagehand(mode: str, model_name: str) -> dict:
    """Run a single Stagehand benchmark.

    Parameters
    ----------
    mode : str
        One of "dom", "hybrid", "cua".
    model_name : str
        Provider-prefixed model, e.g. "anthropic/claude-sonnet-4-6".
    """
    name = f"sh-{mode}-{_short_model(model_name)}"
    model_label = _short_model(model_name)
    api_key = _api_key_for_model(model_name)

    client = AsyncStagehand(
        server="remote",
        model_api_key=api_key,
        browserbase_api_key=BROWSERBASE_API_KEY,
        browserbase_project_id=BROWSERBASE_PROJECT_ID,
    )

    session_id = None
    startup_s = 0.0
    action_s = 0.0
    try:
        # --- Startup: start session ---
        t0 = time.perf_counter()
        start_resp = await client.sessions.start(model_name=model_name)
        session_id = start_resp.data.session_id
        try:
            bb = AsyncBrowserbase(api_key=BROWSERBASE_API_KEY)
            debug_urls = await bb.sessions.debug(session_id)
            print(f"    Live viewer: {debug_urls.debugger_fullscreen_url}")
            await bb.close()
        except Exception:
            pass
        startup_s = round(time.perf_counter() - t0, 2)

        # --- Action: execute the agent task ---
        t1 = time.perf_counter()
        exec_resp = await client.sessions.execute(
            session_id,
            agent_config={
                "mode": mode,
                "model": {
                    "model_name": model_name,
                    "api_key": api_key,
                },
            },
            execute_options={
                "instruction": TASK,
                "max_steps": MAX_STEPS,
            },
            timeout=600.0,  # 10 min timeout for long-running agents
        )
        action_s = round(time.perf_counter() - t1, 2)

        # Extract result
        result_data = exec_resp.data.result
        result_text = result_data.message or ""
        success = result_data.completed and result_data.success

        return {
            "framework": "stagehand",
            "mode": mode,
            "name": name,
            "model": model_label,
            "startup_s": startup_s,
            "action_s": action_s,
            "result_text": result_text,
            "success": success,
            "error": None,
        }
    except Exception as exc:
        return {
            "framework": "stagehand",
            "mode": mode,
            "name": name,
            "model": model_label,
            "startup_s": startup_s,
            "action_s": action_s,
            "result_text": "",
            "success": False,
            "error": f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
        }
    finally:
        try:
            if session_id is not None:
                await client.sessions.end(session_id)
        except Exception:
            pass
        await client.close()
