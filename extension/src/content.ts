// Content script: injects a viewer overlay iframe onto the current page.

if (!(window as any).__pbu_content_loaded) {
  (window as any).__pbu_content_loaded = true;

  let overlay: HTMLDivElement | null = null;

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg.action === "open_overlay") {
      createOverlay(msg.code, msg.phone);
      sendResponse({ success: true });
    }
    return false;
  });

  // Listen for close messages from the viewer iframe
  window.addEventListener("message", (event) => {
    if (event.data?.action === "pbu_close_overlay") {
      removeOverlay();
    }
  });

  function createOverlay(code: string, phone: string): void {
    if (overlay) return;

    overlay = document.createElement("div");
    overlay.id = "pbu-overlay";
    overlay.style.cssText = `
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      z-index: 2147483647;
      background: rgba(0, 0, 0, 0.5);
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      overscroll-behavior: contain;
    `;

    // Prevent scroll/wheel events from reaching the page underneath
    overlay.addEventListener("wheel", (e) => e.preventDefault(), { passive: false });
    overlay.addEventListener("touchmove", (e) => e.preventDefault(), { passive: false });

    const iframe = document.createElement("iframe");
    const viewerUrl = chrome.runtime.getURL(
      `viewer.html?code=${code}&phone=${encodeURIComponent(phone)}`
    );
    iframe.src = viewerUrl;
    iframe.style.cssText = `
      width: 90vw;
      height: 90vh;
      border: none;
      border-radius: 12px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    `;

    // Close overlay when clicking the backdrop — tell the viewer to clean up first
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) {
        iframe.contentWindow?.postMessage({ action: "pbu_cleanup" }, "*");
        removeOverlay();
      }
    });

    overlay.appendChild(iframe);
    document.body.appendChild(overlay);
  }

  function removeOverlay(): void {
    if (overlay) {
      overlay.remove();
      overlay = null;
    }
  }
}
