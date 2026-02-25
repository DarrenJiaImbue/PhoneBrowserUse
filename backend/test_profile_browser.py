"""Open a cloud browser with your profile and print the live URL.

Usage:
    .venv/bin/python test_profile_browser.py          # opens browser, waits for you to press Enter, then stops (saving cookies)
    .venv/bin/python test_profile_browser.py --url https://mail.google.com   # navigate to a specific URL
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# Trigger the monkey-patch
import app.services.browser_service  # noqa: F401

from browser_use import BrowserSession
import httpx

API = "https://api.browser-use.com/api/v2"


def get_api_key() -> str:
    return os.environ.get("BROWSER_USE_API_KEY", "")


def load_cloud_profile_id() -> str:
    profile_map_path = Path(__file__).parent / "cloud_profiles.json"
    if not profile_map_path.exists():
        print("ERROR: No cloud_profiles.json found. Run the app first to create a profile.")
        sys.exit(1)
    profile_map = json.loads(profile_map_path.read_text())
    if not profile_map:
        print("ERROR: cloud_profiles.json is empty.")
        sys.exit(1)
    local_id, cloud_id = next(iter(profile_map.items()))
    print(f"Local profile:  {local_id}")
    print(f"Cloud profile:  {cloud_id}")
    return cloud_id


async def check_profile(cloud_id: str) -> None:
    api_key = get_api_key()
    async with httpx.AsyncClient() as http:
        resp = await http.get(
            f"{API}/profiles/{cloud_id}",
            headers={"X-Browser-Use-API-Key": api_key},
        )
        if resp.is_success:
            data = resp.json()
            print(f"Profile name:   {data.get('name')}")
            print(f"Cookie domains: {data.get('cookieDomains', [])}")
            print(f"Last used at:   {data.get('lastUsedAt')}")
            print(f"Updated at:     {data.get('updatedAt')}")
        else:
            print(f"WARNING: Could not fetch profile: {resp.status_code}")


async def main(url: str) -> None:
    cloud_id = load_cloud_profile_id()
    print()
    await check_profile(cloud_id)
    print()

    # Start cloud browser with profile
    print("Starting cloud browser with profile...")
    session = BrowserSession(
        use_cloud=True,
        keep_alive=True,
        cloud_profile_id=cloud_id,
    )
    await session.start()

    session_id = session._cloud_browser_client.current_session_id
    api_key = get_api_key()

    # Get live URL
    async with httpx.AsyncClient() as http:
        resp = await http.get(
            f"{API}/browsers/{session_id}",
            headers={"X-Browser-Use-API-Key": api_key},
        )
        if resp.is_success:
            live_url = resp.json().get("liveUrl")
            print(f"\n{'='*60}")
            print(f"LIVE URL: {live_url}")
            print(f"{'='*60}\n")

    # Navigate to URL
    if url != "https://www.google.com":
        page = await session.get_current_page()
        await page.goto(url)
        print(f"Navigated to {url}")

    print("Browser is running. Do whatever you need in the live viewer.")
    print("Press Enter when done to stop the browser and save cookies to profile...\n")

    await asyncio.get_event_loop().run_in_executor(None, input)

    # Stop the cloud browser via API (saves cookies to profile)
    print("\nStopping cloud browser (saving cookies to profile)...")
    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.patch(
            f"{API}/browsers/{session_id}",
            headers={"X-Browser-Use-API-Key": api_key, "Content-Type": "application/json"},
            json={"action": "stop"},
        )
        if resp.is_success:
            print("Cloud browser stopped — cookies saved!")
        else:
            print(f"WARNING: Stop returned {resp.status_code}: {resp.text}")

    # Clean up SDK session
    try:
        await session.stop()
    except Exception:
        pass

    # Check profile after
    print()
    print("Profile after session:")
    await check_profile(cloud_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://www.google.com", help="URL to navigate to")
    args = parser.parse_args()
    asyncio.run(main(args.url))
