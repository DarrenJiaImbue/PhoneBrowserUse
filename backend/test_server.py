"""Test the backend server without Vapi.

Simulates the full flow by calling the real server endpoints:
1. Creates a session (with optional cookie forwarding)
2. Activates it via a fake validate_code webhook
3. Loops: sends your text instructions as execute_browser_action webhooks

Usage:
    # Start the server first: python -m app.main
    # Then in another terminal:
    python test_server.py
"""

import asyncio
import json
import sys
import uuid

import httpx
import websockets

SERVER = "http://localhost:8000"
WS_URL = "ws://localhost:8000"


async def main():
    async with httpx.AsyncClient(timeout=120) as client:
        # 1. Create session
        print("Creating session...")
        resp = await client.post(f"{SERVER}/api/session/create", json={
            "url": "https://www.google.com",
        })
        resp.raise_for_status()
        session = resp.json()
        code = session["code"]
        print(f"Session created: {code}")

        # 2. Connect WebSocket (in background to receive screenshots)
        screenshot_count = 0

        async def ws_listener():
            nonlocal screenshot_count
            try:
                async with websockets.connect(f"{WS_URL}/ws/{code}") as ws:
                    while True:
                        msg = json.loads(await ws.recv())
                        if msg["type"] == "screenshot":
                            screenshot_count += 1
                            if screenshot_count == 1:
                                print("[WS] First screenshot received")
                            elif screenshot_count % 20 == 0:
                                print(f"[WS] {screenshot_count} screenshots received")
                        elif msg["type"] == "status":
                            print(f"[WS] Status: {msg.get('status')}")
                        elif msg["type"] == "session_ended":
                            print("[WS] Session ended")
                            break
            except websockets.ConnectionClosed:
                pass
            except Exception as e:
                print(f"[WS] Error: {e}")

        ws_task = asyncio.create_task(ws_listener())

        # 3. Activate session via fake validate_code webhook
        fake_call_id = str(uuid.uuid4())
        print(f"Activating session (fake call_id: {fake_call_id[:8]}...)...")

        resp = await client.post(f"{SERVER}/api/vapi/webhook", json={
            "message": {
                "type": "tool-calls",
                "call": {"id": fake_call_id},
                "toolCallList": [{
                    "id": "tc_validate",
                    "function": {
                        "name": "validate_code",
                        "arguments": {"code": code},
                    },
                }],
            },
        })
        resp.raise_for_status()
        result = resp.json()
        print(f"Activate result: {result['results'][0].get('result', result['results'][0].get('error'))}\n")

        # 4. Interactive loop
        loop = asyncio.get_event_loop()
        print("Enter browser instructions (or 'quit' to exit):\n")

        while True:
            instruction = (await loop.run_in_executor(None, input, "> ")).strip()
            if instruction.lower() in ("quit", "exit", "q"):
                break
            if not instruction:
                continue

            # Determine which tool to call
            if instruction.startswith("http://") or instruction.startswith("https://"):
                tool_name = "go_to_website"
                args = {"url": instruction}
            elif instruction.lower() in ("describe", "look", "what do you see"):
                tool_name = "describe_current_page"
                args = {}
            else:
                tool_name = "execute_browser_action"
                args = {"instruction": instruction}

            print(f"[{tool_name}] Sending...")
            resp = await client.post(f"{SERVER}/api/vapi/webhook", json={
                "message": {
                    "type": "tool-calls",
                    "call": {"id": fake_call_id},
                    "toolCallList": [{
                        "id": f"tc_{uuid.uuid4().hex[:8]}",
                        "function": {
                            "name": tool_name,
                            "arguments": args,
                        },
                    }],
                },
            })
            resp.raise_for_status()
            result = resp.json()
            text = result["results"][0].get("result", result["results"][0].get("error"))
            print(f"\n--- Result ---\n{text}\n")

        # 5. Cleanup: send fake end-of-call
        print("Ending session...")
        await client.post(f"{SERVER}/api/vapi/webhook", json={
            "message": {
                "type": "end-of-call-report",
                "call": {"id": fake_call_id},
            },
        })
        ws_task.cancel()
        try:
            await ws_task
        except asyncio.CancelledError:
            pass
        print(f"Done. {screenshot_count} screenshots were streamed.")


if __name__ == "__main__":
    asyncio.run(main())
