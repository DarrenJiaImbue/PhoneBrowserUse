import { createSession } from "../shared/api";

const btnStart = document.getElementById("btn-start") as HTMLButtonElement;
const statusEl = document.getElementById("status")!;

btnStart.addEventListener("click", async () => {
  btnStart.disabled = true;
  statusEl.textContent = "Creating session...";
  statusEl.className = "status";

  try {
    // Get the current tab's URL
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const currentUrl = tab?.url || undefined;

    // Gather all browser cookies to forward to the server
    const rawCookies = await chrome.cookies.getAll({});
    const cookies = rawCookies.map((c) => ({
      name: c.name,
      value: c.value,
      domain: c.domain,
      path: c.path,
      secure: c.secure,
      httpOnly: c.httpOnly,
      sameSite: c.sameSite === "no_restriction" ? "None" : c.sameSite === "lax" ? "Lax" : "Strict",
      expires: c.expirationDate ?? -1,
    }));

    const session = await createSession(currentUrl, cookies);

    // Inject content script into active tab and open overlay
    const tabId = tab!.id!;
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content.js"],
    });
    await chrome.tabs.sendMessage(tabId, {
      action: "open_overlay",
      code: session.code,
      phone: session.phone_number,
    });

    // Close the popup
    window.close();
  } catch (err) {
    console.error("Failed to create session", err);
    statusEl.textContent = "Could not connect to server. Is it running?";
    statusEl.className = "status error";
    btnStart.disabled = false;
  }
});
