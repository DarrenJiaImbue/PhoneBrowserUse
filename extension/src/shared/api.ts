import { SERVER_URL } from "./constants";
import type { SessionCreateResponse, SessionStatusResponse } from "./types";

export async function createSession(
  url?: string,
  profileId?: string
): Promise<SessionCreateResponse> {
  const res = await fetch(`${SERVER_URL}/api/session/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url: url ?? "https://www.google.com",
      profile_id: profileId,
    }),
  });
  if (!res.ok) {
    throw new Error(`Failed to create session: ${res.status}`);
  }
  return res.json();
}

export async function getSessionStatus(
  code: string
): Promise<SessionStatusResponse> {
  const res = await fetch(`${SERVER_URL}/api/session/${code}/status`);
  if (!res.ok) {
    throw new Error(`Failed to get session status: ${res.status}`);
  }
  return res.json();
}

export async function endSession(code: string): Promise<void> {
  await fetch(`${SERVER_URL}/api/session/${code}/end`, { method: "POST" });
}
