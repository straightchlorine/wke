import type { DossierView } from "../api/dossier";
import type { Chunk, Citation, Section } from "../api/generated";
import { joinList } from "./format";

export interface SectionPack {
  section: Section;
  /**
   * The section's chunks the current budget actually returned (with
   * text, tokens and relevance). At a reduced budget the API omits
   * held-back chunks from the response entirely, so this can be a
   * strict subset of section.chunk_ids.
   */
  includedChunks: Chunk[];
  /**
   * Ids the section lists that the current budget did not return. The API sends only the id of a
   * held-back chunk, with no text, tokens or relevance.
   */
  heldBackChunkIds: string[];
  /**
   * "full" when every listed chunk was returned, "cut" when the budget left some out, and "folded"
   * when it left all of them out.
   */
  state: "full" | "cut" | "folded";
  includedTokens: number;
  /**
   * [min, max] relevance over includedChunks only. At a reduced
   * budget this does not cover the section's held-back chunks, since
   * the API never sends their relevance.
   */
  relevanceRange: [number, number] | null;
}

/** Resolves a section's chunk_ids to Chunk objects in the section's own order. */
export function sectionChunks(dossier: DossierView, section: Section): Chunk[] {
  const byId = new Map(dossier.chunks.map((chunk) => [chunk.id, chunk]));
  return section.chunk_ids
    .map((id) => byId.get(id))
    .filter((chunk): chunk is Chunk => chunk != null);
}

/**
 * Splits a section's chunks by the budget's included_chunk_ids, returning full/cut/folded state.
 */
export function packSection(dossier: DossierView, section: Section): SectionPack {
  const includedIds = new Set(dossier.budget.included_chunk_ids);
  const heldBackChunkIds = section.chunk_ids.filter((id) => !includedIds.has(id));
  const includedChunks = sectionChunks(dossier, section).filter((chunk) =>
    includedIds.has(chunk.id),
  );
  const state: SectionPack["state"] =
    heldBackChunkIds.length === 0 ? "full" : includedChunks.length === 0 ? "folded" : "cut";
  const relevances = includedChunks.map((chunk) => chunk.relevance);
  return {
    section,
    includedChunks,
    heldBackChunkIds,
    state,
    includedTokens: includedChunks.reduce((sum, chunk) => sum + chunk.est_tokens, 0),
    relevanceRange:
      relevances.length > 0 ? [Math.min(...relevances), Math.max(...relevances)] : null,
  };
}

/** A citation with its note number and, when it is anchored to a section, that section. */
export interface CitationNote {
  citation: Citation;
  n: number;
  /**
   * The section heading the citation is anchored to; null when the citation has no anchor, such as
   * the lead or a related article.
   */
  section: string | null;
}

export interface CitationNotes {
  /** Maps a citation id to the number shown in its [n] marker and its note. */
  numbers: Map<string, number>;
  /** Seed citations the text cites, numbered 1..N with no gaps. */
  cited: CitationNote[];
  /** Related articles, numbered after the cited ones. */
  related: CitationNote[];
}

/**
 * Turns a section anchor into reading text: percent-decoded, underscores to spaces, a pair of
 * surrounding double quotes and outer whitespace removed.
 */
export function humaniseAnchor(anchor: string): string {
  let decoded = anchor;
  try {
    decoded = decodeURIComponent(anchor);
  } catch {
    // A malformed escape: keep the anchor as the API sent it.
  }
  return decoded
    .replace(/_/g, " ")
    .replace(/^"(.*)"$/, "$1")
    .trim();
}

/**
 * The address a citation links to: the section anchor when it has one, else the pinned revision.
 */
export function citationHref(citation: Citation): string {
  return citation.url ?? citation.pin.permalink;
}

/**
 * Numbers the citations: seed citations that a passage points at come first, then the related
 * articles, each in the order the API lists them and with no gaps. A seed citation no passage
 * points at gets no number.
 */
export function citationNotes(dossier: Pick<DossierView, "citations" | "chunks">): CitationNotes {
  const referenced = new Set(dossier.chunks.map((chunk) => chunk.citation_id));
  const sectionOf = (citation: Citation): string | null => {
    if (!citation.anchor) return null;
    const heading = dossier.chunks
      .find((chunk) => chunk.citation_id === citation.id && chunk.heading_path.length > 0)
      ?.heading_path.at(-1);
    return heading ?? humaniseAnchor(citation.anchor);
  };
  const numbers = new Map<string, number>();
  const note = (citation: Citation): CitationNote => {
    const n = numbers.size + 1;
    numbers.set(citation.id, n);
    return { citation, n, section: sectionOf(citation) };
  };
  const cited = dossier.citations
    .filter((c) => c.role === "seed" && referenced.has(c.id))
    .map(note);
  const related = dossier.citations.filter((c) => c.role === "related").map(note);
  return { numbers, cited, related };
}

/** Resolves the citation a chunk points at. */
export function citationFor(citations: Citation[], chunk: Chunk): Citation | null {
  return citations.find((citation) => citation.id === chunk.citation_id) ?? null;
}

/**
 * Says which groups a section's passages fall in, as "passages in group 2 of 5", or returns null
 * when the build ran no grouping or the section has no grouped passage. The API numbers groups from
 * 0, so the displayed number is one higher. The total is one more than the highest group number
 * among the returned passages.
 */
export function sectionGroupSummary(dossier: DossierView, section: Section): string | null {
  if (dossier.build.analysis !== "ml") return null;
  const allIds = dossier.chunks.map((c) => c.cluster_id).filter((id): id is number => id != null);
  const total = allIds.length > 0 ? Math.max(...allIds) + 1 : 0;
  const groups = [
    ...new Set(
      sectionChunks(dossier, section)
        .map((c) => c.cluster_id)
        .filter((id): id is number => id != null),
    ),
  ]
    .toSorted((a, b) => a - b)
    .map((id) => id + 1);
  if (groups.length === 0) return null;
  if (groups.length === 1) return `passages in group ${groups[0]} of ${total}`;
  return `passages split across groups ${joinList(groups)} of ${total}`;
}
