const LIVE_REGION_ID = "live-region";

/**
 * Announces text through the single polite live region that `__root.tsx` mounts, so no caller needs
 * its own.
 */
export function announceLive(text: string): void {
  if (typeof document === "undefined") {
    return;
  }
  const region = document.getElementById(LIVE_REGION_ID);
  if (region) {
    region.textContent = text;
  }
}
