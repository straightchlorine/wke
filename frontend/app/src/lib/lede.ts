import type { DossierView } from "../api/dossier";

// A period after one of these does not end a sentence.
const ABBREVIATIONS = new Set([
  "st",
  "mr",
  "mrs",
  "ms",
  "dr",
  "jr",
  "sr",
  "vs",
  "mt",
  "ca",
  "fl",
  "inc",
  "ltd",
  "co",
  "u.s",
  "e.g",
  "i.e",
  "approx",
]);

/**
 * Returns the first sentence of a passage exactly as written, or null when the passage has no
 * sentence end.
 */
export function firstSentence(text: string): string | null {
  const ends = /[.!?]["')\]]*(?=\s+["'(]*[A-Z0-9]|\s*$)/g;
  for (const match of text.matchAll(ends)) {
    const end = match.index + match[0].length;
    const before = text.slice(0, match.index).split(/\s+/).pop() ?? "";
    const word = before.replace(/^[("']+/, "").toLowerCase();
    const isInitial = /^[a-z]$/i.test(word);
    if (match[0].startsWith(".") && (ABBREVIATIONS.has(word) || isInitial)) {
      continue;
    }
    return text.slice(0, end).trim();
  }
  return null;
}

/**
 * Returns the first sentence of the first section's first passage, for a page whose topic has no
 * Wikipedia short description, or null when there is none.
 */
export function leadSentence(dossier: DossierView): string | null {
  const lead = dossier.sections[0];
  const chunkId = lead?.chunk_ids[0];
  const chunk = chunkId == null ? undefined : dossier.chunks.find((c) => c.id === chunkId);
  return chunk ? firstSentence(chunk.text) : null;
}
