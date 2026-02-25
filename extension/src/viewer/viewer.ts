import { createSession, endSession } from "../shared/api";
import { getOrCreateProfileId } from "../shared/profile";
import { WebSocketManager } from "../shared/websocket";
import type { WsMessage } from "../shared/types";

// DOM elements
const screens = {
  instructions: document.getElementById("screen-instructions")!,
  live: document.getElementById("screen-live")!,
  ended: document.getElementById("screen-ended")!,
};

const sessionCodeEl = document.getElementById("session-code")!;
const phoneNumberEl = document.getElementById("phone-number")!;
const connectionStatusEl = document.getElementById("connection-status")!;
const liveFrameEl = document.getElementById("live-frame") as HTMLIFrameElement;
const btnNewSession = document.getElementById("btn-new-session")!;
const errorBanner = document.getElementById("error-banner")!;
const errorText = document.getElementById("error-text")!;

let wsManager: WebSocketManager | null = null;

// Detect if running inside an iframe (overlay mode)
if (window.parent !== window) {
  document.body.classList.add("in-iframe");
}

// Track current session code for cleanup
let currentCode: string | null = null;

async function cleanupAndClose(): Promise<void> {
  if (currentCode) {
    endSession(currentCode).catch(() => {});
    currentCode = null;
  }
  if (wsManager) {
    wsManager.close();
    wsManager = null;
  }
  liveFrameEl.src = "";
  window.parent.postMessage({ action: "pbu_close_overlay" }, "*");
}

// Close overlay button
const btnCloseOverlay = document.getElementById("btn-close-overlay");
if (btnCloseOverlay) {
  btnCloseOverlay.addEventListener("click", () => cleanupAndClose());
}

// Listen for cleanup request from parent (backdrop click)
window.addEventListener("message", (event) => {
  if (event.data?.action === "pbu_cleanup") {
    if (currentCode) {
      endSession(currentCode).catch(() => {});
      currentCode = null;
    }
    if (wsManager) {
      wsManager.close();
      wsManager = null;
    }
  }
});

function showScreen(name: keyof typeof screens): void {
  Object.values(screens).forEach((el) => el.classList.remove("active"));
  screens[name].classList.add("active");
}

function showError(message: string): void {
  errorText.textContent = message;
  errorBanner.classList.remove("hidden");
  setTimeout(() => errorBanner.classList.add("hidden"), 8000);
}

function formatPhoneNumber(phone: string): string {
  const digits = phone.replace(/\D/g, "");
  if (digits.length === 11 && digits.startsWith("1")) {
    return `+1 (${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7)}`;
  }
  return phone;
}

function handleWsMessage(msg: WsMessage): void {
  switch (msg.type) {
    case "live_url":
      if (msg.url) {
        liveFrameEl.src = msg.url;
        if (!screens.live.classList.contains("active")) {
          showScreen("live");
        }
      }
      break;

    case "status":
      if (msg.status === "active") {
        connectionStatusEl.textContent = "Connected! Browser session is active.";
        connectionStatusEl.className = "status connected";
      }
      break;

    case "session_ended":
      showScreen("ended");
      liveFrameEl.src = "";
      if (wsManager) {
        wsManager.close();
        wsManager = null;
      }
      break;

    case "screenshot":
      // Legacy fallback — ignored now that we use live URL
      break;

    case "pong":
      break;
  }
}

function handleWsDisconnect(): void {
  // Reconnect is handled automatically by WebSocketManager
}

// Read session params from URL query string
const params = new URLSearchParams(window.location.search);
const code = params.get("code");
const phone = params.get("phone");

if (code && phone) {
  currentCode = code;

  // Show instructions immediately with the provided code/phone
  sessionCodeEl.textContent = code;
  phoneNumberEl.textContent = formatPhoneNumber(phone);
  showScreen("instructions");

  // Open WebSocket
  wsManager = new WebSocketManager(code, handleWsMessage, handleWsDisconnect);
  wsManager.connect();
} else {
  showError("Missing session parameters. Please start a session from the extension popup.");
}

// "Start New Session" button — re-open the popup isn't possible, so create a new session directly
btnNewSession.addEventListener("click", async () => {
  // Clean up old session
  if (currentCode) {
    endSession(currentCode).catch(() => {});
    currentCode = null;
  }
  if (wsManager) {
    wsManager.close();
    wsManager = null;
  }

  try {
    const profileId = await getOrCreateProfileId();
    const session = await createSession(undefined, profileId);

    currentCode = session.code;
    sessionCodeEl.textContent = session.code;
    phoneNumberEl.textContent = formatPhoneNumber(session.phone_number);
    showScreen("instructions");

    wsManager = new WebSocketManager(
      session.code,
      handleWsMessage,
      handleWsDisconnect
    );
    wsManager.connect();
  } catch (err) {
    console.error("Failed to create session", err);
    showError(
      "Could not connect to the server. Please check that the server is running and try again."
    );
  }
});
