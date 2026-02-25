"""Entry point: python -m benchmarks.run_all

Runs selected benchmarks sequentially, prints a formatted table,
and saves results to benchmarks/results.json.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from .bench_browser_use import _run_with_llm
from .bench_stagehand import run_stagehand
from .config import ANTHROPIC_API_KEY, MAX_STEPS, TASK

from browser_use.llm.anthropic.chat import ChatAnthropic


def _truncate(text: str, width: int = 40) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) <= width:
        return text
    return text[: width - 3] + "..."


def _print_table(results: list[dict]) -> None:
    header = (
        f"{'Framework':<16}| {'Mode':<8}| {'Model':<20}| "
        f"{'Startup (s)':<13}| {'Action (s)':<12}| {'Success':<9}| Result"
    )
    sep = (
        "-" * 16 + "+" + "-" * 9 + "+" + "-" * 21 + "+"
        + "-" * 14 + "+" + "-" * 13 + "+" + "-" * 10 + "+" + "-" * 42
    )
    print()
    print(header)
    print(sep)
    for r in results:
        display = _truncate(r.get("error") or r.get("result_text") or "-")
        print(
            f"{r['framework']:<16}| {r['mode']:<8}| {r['model']:<20}| "
            f"{r['startup_s']:<13}| {r['action_s']:<12}| "
            f"{str(r['success']):<9}| {display}"
        )
    print()


async def main() -> None:
    results: list[dict] = []

    MODEL = "claude-sonnet-4-6"
    SH_MODEL = "anthropic/claude-sonnet-4-6"

    # ------------------------------------------------------------------
    # Browser-use with Claude Sonnet 4.6
    # ------------------------------------------------------------------
    print("\n>>> Running browser-use / Claude Sonnet 4.6 ...")
    llm = ChatAnthropic(model=MODEL, api_key=ANTHROPIC_API_KEY)
    result = await _run_with_llm("bu-sonnet", MODEL, llm)
    results.append(result)
    status = "OK" if result["success"] else "FAIL"
    print(f"    {status} — startup: {result['startup_s']}s, action: {result['action_s']}s")
    print(f"    Result: {_truncate(result.get('result_text') or result.get('error') or '-', 80)}")
    input("    Press Enter to continue to next benchmark...")

    # ------------------------------------------------------------------
    # Stagehand DOM with Claude Sonnet 4.6
    # ------------------------------------------------------------------
    print("\n>>> Running stagehand / dom / Claude Sonnet 4.6 ...")
    result = await run_stagehand(mode="dom", model_name=SH_MODEL)
    results.append(result)
    status = "OK" if result["success"] else "FAIL"
    print(f"    {status} — startup: {result['startup_s']}s, action: {result['action_s']}s")
    print(f"    Result: {_truncate(result.get('result_text') or result.get('error') or '-', 80)}")
    input("    Press Enter to continue to next benchmark...")

    # ------------------------------------------------------------------
    # Stagehand CUA with Claude Sonnet 4.6
    # ------------------------------------------------------------------
    print("\n>>> Running stagehand / cua / Claude Sonnet 4.6 ...")
    result = await run_stagehand(mode="cua", model_name=SH_MODEL)
    results.append(result)
    status = "OK" if result["success"] else "FAIL"
    print(f"    {status} — startup: {result['startup_s']}s, action: {result['action_s']}s")
    print(f"    Result: {_truncate(result.get('result_text') or result.get('error') or '-', 80)}")
    input("    Press Enter to continue to next benchmark...")

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    _print_table(results)

    # Save to JSON
    out_path = Path(__file__).resolve().parent / "results.json"
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"Results saved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
