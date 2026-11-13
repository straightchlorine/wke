/**
 * Returns the origin that machine-readable links (JSON, Markdown, llms.txt, curl examples) are
 * built against.
 * It is the origin of `selfLink` when the API returned one, so links match the host the API
 * reports.
 * Otherwise it is this page's origin, or "" when there is no window.
 */
export function publicBaseUrl(selfLink?: string | null): string {
  if (selfLink) {
    try {
      return new URL(selfLink).origin;
    } catch {
      // The link is not a parseable absolute URL, so the page's own origin is used instead.
    }
  }
  return typeof window !== "undefined" ? window.location.origin : "";
}
