from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request

from app.services.browser_service import BrowserService
from app.services.screenshot_streamer import (
    send_session_ended,
    send_status,
    stream_screenshots,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vapi", tags=["vapi"])

# session_manager is injected at startup from main.py
session_manager = None


@router.post("/webhook")
async def vapi_webhook(request: Request):
    body = await request.json()
    message = body.get("message", {})
    msg_type = message.get("type", "")

    if msg_type == "tool-calls":
        return await _handle_tool_calls(message)
    elif msg_type == "end-of-call-report":
        return await _handle_end_of_call(message)

    # Ignore noisy Vapi status messages
    return {"results": []}


async def _handle_tool_calls(message: dict) -> dict:
    tool_calls = message.get("toolCallList", [])
    results = []

    for tc in tool_calls:
        tool_call_id = tc.get("id", "")
        function = tc.get("function", {})
        name = function.get("name", "")
        args = function.get("arguments", {})

        # Parse arguments if they come as a string
        if isinstance(args, str):
            import json
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}

        try:
            result = await _dispatch_tool(name, args, message)
            results.append({
                "toolCallId": tool_call_id,
                "result": result,
            })
        except Exception as e:
            logger.exception("Tool call error: %s", name)
            results.append({
                "toolCallId": tool_call_id,
                "error": str(e),
            })

    return {"results": results}


async def _dispatch_tool(name: str, args: dict, message: dict) -> str:
    call_id = message.get("call", {}).get("id", "")
    if name == "validate_code":
        return await _validate_code(args, message)
    elif name == "execute_browser_action":
        return await _execute_browser_action(args, call_id)
    elif name == "describe_current_page":
        return await _describe_current_page(args, call_id)
    elif name == "go_to_website":
        return await _go_to_website(args, call_id)
    else:
        return f"Unknown tool: {name}"


async def _validate_code(args: dict, message: dict) -> str:
    code = args.get("code", "").strip()
    if not code or len(code) != 6 or not code.isdigit():
        return "That doesn't seem like a valid code. Please ask the user for their 6-digit code shown on their screen."

    call_id = message.get("call", {}).get("id", "unknown")
    session = session_manager.activate_session(code, call_id)

    if session is None:
        return "That code is not valid or has already been used. Please ask the user to check their screen and try again."

    # Start browser on the session's start URL, with user's cookies if provided.
    # Each session code gets a persistent browser profile so logins survive.
    browser_svc = BrowserService()
    await browser_svc.start_browser(
        session.start_url,
        cookies=session.cookies,
        profile_id=code,
    )
    session.browser_service = browser_svc

    # Start screenshot streaming if WebSocket is connected
    if session.websocket:
        await send_status(session.websocket, "active")
        session.screenshot_task = asyncio.create_task(
            stream_screenshots(browser_svc, session.websocket, code)
        )
        logger.info("Screenshot streaming task created for session %s", code)
    else:
        logger.warning("No WebSocket connected for session %s, skipping screenshots", code)

    return (
        "Code verified successfully! I can now see a browser with Google open. "
        "What would you like me to help you find or do on the internet?"
    )


async def _execute_browser_action(args: dict, call_id: str) -> str:
    instruction = args.get("instruction", "").strip()
    if not instruction:
        return "I didn't catch what you'd like me to do. Could you say that again?"

    session = session_manager.get_session_by_call_id(call_id)
    if not session or not session.browser_service:
        return "I'm sorry, but I don't have an active browser session."

    session.touch()

    try:
        description = await session.browser_service.execute_action(instruction)
        return description
    except Exception as e:
        logger.exception("Browser action failed: %s", instruction)
        return f"I had trouble doing that. Let me describe what I can see instead."


async def _describe_current_page(args: dict, call_id: str) -> str:
    session = session_manager.get_session_by_call_id(call_id)
    if not session or not session.browser_service:
        return "I don't have an active browser session right now."

    session.touch()

    try:
        return await session.browser_service.describe_page()
    except Exception as e:
        logger.exception("Page description failed")
        return "I'm having trouble seeing the page right now."


async def _go_to_website(args: dict, call_id: str) -> str:
    url = args.get("url", "").strip()
    if not url:
        return "I didn't catch the website address. Could you say it again?"

    # Add https:// if no scheme provided
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    session = session_manager.get_session_by_call_id(call_id)
    if not session or not session.browser_service:
        return "I don't have an active browser session right now."

    session.touch()

    try:
        description = await session.browser_service.navigate_to(url)
        return description
    except Exception as e:
        logger.exception("Navigation failed: %s", url)
        return f"I had trouble going to that website. Could you check the address?"


async def _handle_end_of_call(message: dict) -> dict:
    call_id = message.get("call", {}).get("id", "")
    logger.info("End-of-call received for call_id: %s", call_id)

    # Find session by call ID and clean up
    found = False
    for code, session in list(session_manager._sessions.items()):
        logger.info("  Checking session %s with call_id %s", code, session.vapi_call_id)
        if session.vapi_call_id == call_id:
            found = True
            if session.websocket:
                await send_session_ended(session.websocket)
            await session_manager.end_session(code)
            logger.info("Call ended, session %s cleaned up", code)
            break

    if not found:
        logger.warning("No session found for call_id: %s", call_id)

    return {}
