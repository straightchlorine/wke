import type { Chunk, Citation } from "../api/generated";
import { citationFor, citationHref } from "./dossierPack";

/** The citation marker shown after a passage: its number and where it links. */
export interface PassageMarker {
  n: number;
  href: string;
}

/**
 * Returns, for each passage of one section, its citation marker, or null where it shows none.
 * A section can hold many passages from the same citation, and a marker on every one of them is noise.
 * So only the first passage of each citation carries one, and a passage whose citation has no number carries none.
 */
export function passageMarkers(
  chunks: readonly Chunk[],
  citations: Citation[],
  numbers: ReadonlyMap<string, number>,
): Array<PassageMarker | null> {
  const seen = new Set<string>();
  return chunks.map((chunk) => {
    const citation = citationFor(citations, chunk);
    const n = numbers.get(chunk.citation_id);
    const first = citation != null && !seen.has(citation.id);
    if (citation) {
      seen.add(citation.id);
    }
    return citation != null && n != null && first ? { n, href: citationHref(citation) } : null;
  });
}

/** Splits a passage into its text up to and including the last space, and the last word after it. Trailing whitespace is dropped. */
export function splitLastWord(text: string): { head: string; lastWord: string } {
  const trimmed = text.trimEnd();
  const lastSpace = trimmed.lastIndexOf(" ");
  return lastSpace === -1
    ? { head: "", lastWord: trimmed }
    : { head: trimmed.slice(0, lastSpace + 1), lastWord: trimmed.slice(lastSpace + 1) };
}
