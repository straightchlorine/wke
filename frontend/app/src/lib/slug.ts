/**
 * Characters a `/t/{slug}` path keeps as they are, as Wikipedia does in /wiki/Mary,_mother_of_Jesus.
 * The router is configured with the same list, so a link built here matches the address bar.
 */
export const PATH_LITERAL_CHARACTERS = [",", ":", ";", "@", "$"] as const;

/**
 * Turns an article title into a `/t/{slug}` path segment by replacing only spaces with underscores,
 * as Wikipedia does. It leaves percent-encoding to the router, or to `slugPath` for a written URL.
 */
export function slugify(title: string): string {
  return title.replace(/ /g, "_");
}

/** Returns the `/t/{slug}` path for a title, percent-encoded the way the router writes it. */
export function slugPath(title: string): string {
  let encoded = encodeURIComponent(slugify(title));
  for (const char of PATH_LITERAL_CHARACTERS) {
    encoded = encoded.replaceAll(encodeURIComponent(char), char);
  }
  return `/t/${encoded}`;
}

/**
 * Turns a slug back into a title by decoding any percent-encoding and then turning underscores into
 * spaces.
 * MediaWiki treats an underscore and a space in a title as the same character, so no real title
 * changes meaning.
 */
export function unslugify(slug: string): string {
  let decoded = slug;
  try {
    decoded = decodeURIComponent(slug);
  } catch {
    // A slug the router already decoded can contain a lone "%", which is not valid
    // percent-encoding.
    // Keep the slug as given instead of throwing.
  }
  return decoded.replace(/_/g, " ");
}
