"""Shared benchmark configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load env from backend/.env
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------
TASK = "Go to polymarket and place a bet of 100 dollars on the first market in the politics section. Stop when you reach a login."

MAX_STEPS = 50

# ---------------------------------------------------------------------------
# API keys (read once, reused by all benchmarks)
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
BROWSER_USE_API_KEY = os.environ.get("BROWSER_USE_API_KEY", "")
BROWSERBASE_API_KEY = os.environ.get("BROWSERBASE_API_KEY", "")
BROWSERBASE_PROJECT_ID = os.environ.get("BROWSERBASE_PROJECT_ID", "")

# ---------------------------------------------------------------------------
# Model identifiers
# ---------------------------------------------------------------------------
# browser-use LLM configs
BU_CLAUDE_MODEL = "claude-sonnet-4-6"
BU_GEMINI_MODEL = "gemini-2.5-flash"
BU_BU2_MODEL = "bu-2-0"

# stagehand model strings (provider/model format)
SH_CLAUDE_MODEL = "anthropic/claude-sonnet-4-6"
SH_GEMINI_MODEL = "google/gemini-2.5-flash"
