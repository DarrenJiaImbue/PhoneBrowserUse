"""Interactive script to test browser-use actions and measure timing."""

import asyncio
import time

from dotenv import load_dotenv

load_dotenv()

from browser_use import Agent, BrowserSession, ChatBrowserUse


async def main():
    llm = ChatBrowserUse(model="bu-2-0")

    print("Starting browser...")
    t = time.time()
    session = BrowserSession(headless=False, keep_alive=True, channel="chrome")
    await session.start()
    page = await session.get_current_page()
    await page.goto("https://www.google.com")
    print(f"Browser started in {time.time() - t:.1f}s\n")

    print("Enter instructions (or 'quit' to exit):\n")
    loop = asyncio.get_event_loop()

    while True:
        instruction = (await loop.run_in_executor(None, input, "> ")).strip()
        if instruction.lower() in ("quit", "exit", "q"):
            break
        if not instruction:
            continue

        print(f"Running: {instruction}")
        t = time.time()

        try:
            agent = Agent(
                task=instruction,
                llm=llm,
                browser_session=session,
            )
            result = await agent.run()
            elapsed = time.time() - t

            final = result.final_result()
            print(f"\n--- Result ({elapsed:.1f}s) ---")
            print(final or "(no result text)")
            print("---\n")
        except Exception as e:
            elapsed = time.time() - t
            print(f"\n--- Error ({elapsed:.1f}s) ---")
            print(f"{e}\n")

    print("Closing browser...")
    await session.kill()


if __name__ == "__main__":
    asyncio.run(main())
