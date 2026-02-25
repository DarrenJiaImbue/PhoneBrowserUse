"""Clear cloud profile cookies or simulate a completely new user.

Usage:
    .venv/bin/python clear_profile.py              # reset cookies only (same local ID)
    .venv/bin/python clear_profile.py --full        # nuke everything (new user flow)
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import httpx

API = "https://api.browser-use.com/api/v2"
PROFILE_MAP_PATH = Path(__file__).parent / "cloud_profiles.json"


def get_api_key() -> str:
    return os.environ.get("BROWSER_USE_API_KEY", "")


async def main(full: bool):
    api_key = get_api_key()
    if not api_key:
        print("ERROR: No BROWSER_USE_API_KEY found")
        sys.exit(1)

    headers = {"X-Browser-Use-API-Key": api_key}

    if not PROFILE_MAP_PATH.exists() or not json.loads(PROFILE_MAP_PATH.read_text()):
        if full:
            print("No existing profiles. Already clean.")
            return
        print("ERROR: No cloud_profiles.json found.")
        sys.exit(1)

    profile_map = json.loads(PROFILE_MAP_PATH.read_text())

    async with httpx.AsyncClient() as http:
        # Delete all cloud profiles
        for local_id, cloud_id in profile_map.items():
            resp = await http.get(f"{API}/profiles/{cloud_id}", headers=headers)
            if resp.is_success:
                data = resp.json()
                print(f"Profile:        {cloud_id} (local: {local_id[:8]}...)")
                print(f"Cookie domains: {data.get('cookieDomains', [])}")
            else:
                print(f"Profile {cloud_id} not found (maybe already deleted)")

            print(f"Deleting cloud profile {cloud_id}...")
            resp = await http.delete(f"{API}/profiles/{cloud_id}", headers=headers)
            if resp.is_success:
                print("Deleted.\n")
            else:
                print(f"Delete returned {resp.status_code}: {resp.text}\n")

        if full:
            # Nuke the mapping file — extension will generate a new local UUID,
            # backend will create a new cloud profile on first use
            PROFILE_MAP_PATH.write_text("{}")
            print("Cleared cloud_profiles.json.")
            print("\nFull reset complete. Next session will be a brand new user:")
            print("  - Extension generates a new local UUID")
            print("  - Backend creates a new cloud profile")
            print("  - Zero cookies, zero history")
        else:
            # Keep local IDs, create fresh cloud profiles
            new_map = {}
            for local_id in profile_map:
                print(f"Creating fresh cloud profile for {local_id[:8]}...")
                resp = await http.post(
                    f"{API}/profiles",
                    headers=headers,
                    json={"name": f"pbu-{local_id[:8]}"},
                )
                resp.raise_for_status()
                new_cloud_id = resp.json()["id"]
                new_map[local_id] = new_cloud_id
                print(f"New cloud profile: {new_cloud_id}")

            PROFILE_MAP_PATH.write_text(json.dumps(new_map, indent=2))
            print("\nCookies reset. Same local ID, fresh cloud profile.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Full reset: nuke local ID mapping too (new user flow)")
    args = parser.parse_args()
    asyncio.run(main(args.full))
