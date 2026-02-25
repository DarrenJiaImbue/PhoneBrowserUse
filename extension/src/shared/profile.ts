/**
 * Manages a persistent cloud browser profile ID.
 *
 * On first use a UUID is generated and stored in chrome.storage.local.
 * Every subsequent session reuses the same ID so browser-use cloud
 * keeps cookies and logins across sessions.
 */

const STORAGE_KEY = "pbu_cloud_profile_id";

export async function getOrCreateProfileId(): Promise<string> {
  const result = await chrome.storage.local.get(STORAGE_KEY);
  if (result[STORAGE_KEY]) {
    console.log("[PBU] Using cloud profile ID:", result[STORAGE_KEY]);
    return result[STORAGE_KEY] as string;
  }

  const id = crypto.randomUUID();
  await chrome.storage.local.set({ [STORAGE_KEY]: id });
  console.log("[PBU] Created new cloud profile ID:", id);
  return id;
}
