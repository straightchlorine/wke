import type { DossierView } from "../api/dossier";
import type { Section } from "../api/generated";
import type { Budget } from "./budget";
import { packSection, type SectionPack } from "./dossierPack";
import { sectionDepth } from "./sectionDepth";

/** A section of the dossier with its position, its element id and how much of it the budget kept. */
export interface SectionRow {
  section: Section;
  /** The section's place in the dossier, counted from 0. */
  index: number;
  /** The id of the section's element in the article: "s" and the position counted from 1. */
  id: string;
  pack: SectionPack;
}

/** Returns a row for every section of the dossier, packing each section once. */
export function sectionRows(dossier: DossierView): SectionRow[] {
  return dossier.sections.map((section, index) => ({
    section,
    index,
    id: `s${index + 1}`,
    pack: packSection(dossier, section),
  }));
}

/** Returns the tokens the subsections of the section at `index` add up to, for a section that has no text of its own. */
export function subsectionTokens(rows: readonly SectionRow[], index: number): number {
  const parent = rows[index];
  if (!parent) {
    return 0;
  }
  const depth = sectionDepth(parent.section);
  let total = 0;
  for (const child of rows.slice(index + 1)) {
    if (sectionDepth(child.section) <= depth) {
      break;
    }
    total += child.pack.includedTokens;
  }
  return total;
}

/**
 * What the budget kept of the dossier, in sections and in passages.
 * A section is one section of the Wikipedia article, and a passage is one of the API's chunks.
 */
export interface SectionTotals {
  /** The sections that show at least one passage. */
  shown: number;
  /** The sections the budget left out entirely. */
  leftOut: number;
  includedPassages: number;
  totalPassages: number;
}

/** Counts the sections and the passages the budget kept. */
export function sectionTotals(rows: readonly SectionRow[]): SectionTotals {
  const leftOut = rows.filter((row) => row.pack.state === "folded").length;
  return {
    shown: rows.length - leftOut,
    leftOut,
    includedPassages: rows.reduce((sum, row) => sum + row.pack.includedChunks.length, 0),
    totalPassages: rows.reduce((sum, row) => sum + row.section.chunk_ids.length, 0),
  };
}

/** Returns, for each section, the tokens included in the sections before it. */
export function tokenOffsets(rows: readonly SectionRow[]): number[] {
  let running = 0;
  return rows.map((row) => {
    const offset = running;
    running += row.pack.includedTokens;
    return offset;
  });
}

/** One labelled mark on the token ruler. */
export interface RulerEntry {
  id: string;
  label: string;
  /** Tokens included before the mark. */
  offset: number;
  /** The measured position of the mark, from 0 at the top to 1 at the bottom. Without it the ruler places the mark from its token offset. */
  fraction?: number;
}

/** The id of the ruler entry for the tokens that belong to no section. It has no heading, so no measured position. */
const OVERHEAD_ENTRY_ID = "overhead";

/**
 * Returns the ruler's labelled marks: one per section that holds tokens, and a last one for the
 * header, headings and summaries when the budget counts tokens beyond the sections' own.
 * A section with no included tokens has the same offset as the next section, so it gets no mark.
 */
export function rulerEntries(
  rows: readonly SectionRow[],
  usedTokens: number,
  fractions: ReadonlyMap<string, number>,
): RulerEntry[] {
  const offsets = tokenOffsets(rows);
  const entries: RulerEntry[] = [];
  for (const row of rows) {
    if (row.pack.includedTokens > 0) {
      entries.push({
        id: row.id,
        label: `${row.index + 1} ${row.section.label}`,
        offset: offsets[row.index] ?? 0,
        fraction: fractions.get(row.id),
      });
    }
  }
  const sectionTokens = rows.reduce((sum, row) => sum + row.pack.includedTokens, 0);
  if (usedTokens > sectionTokens) {
    entries.push({
      id: OVERHEAD_ENTRY_ID,
      label: "header, headings and summaries",
      offset: sectionTokens,
    });
  }
  return entries;
}

/** Returns the next larger budget, or null for the largest. */
export function nextBudgetUp(budget: Budget): Budget | null {
  if (budget === 2000) return 8000;
  if (budget === 8000) return 32000;
  return null;
}

/** Returns the hover title of a section: its heading path when it is nested, else its label. */
export function sectionTitle(section: Section): string {
  return section.heading_path && section.heading_path.length > 1
    ? section.heading_path.join(" > ")
    : section.label;
}

/**
 * Returns what the page says about the text of a section that has passages, or null when it says
 * nothing: that lists and tables are left out, or that the source text is complete.
 */
export function completenessNote(
  section: Section,
  pack: SectionPack,
  buildTruncated: boolean | undefined,
): string | null {
  if (section.chunk_ids.length === 0) {
    return null;
  }
  if (section.dropped_non_prose === true) {
    return "Lists and tables in this section are not included.";
  }
  if (section.dropped_non_prose === false && pack.state === "full" && !buildTruncated) {
    return "The source text below is complete.";
  }
  return null;
}

/** Returns the line that says why a section has no model summary, and what the budget kept of it. */
export function missingSummaryDetail(
  section: Section,
  pack: SectionPack,
  jobId: string | undefined,
): string {
  const reason =
    section.summary_state === "pending"
      ? `Summary pending: summarise stage${jobId != null ? `, job ${jobId}` : ""}.`
      : section.summary_state === "unavailable"
        ? "Summary unavailable: the build did not produce one for this section."
        : "Summary skipped: this section was not selected for summarising.";
  if (pack.state === "full") {
    return reason;
  }
  if (pack.state === "cut") {
    const shown = pack.includedChunks.length;
    return `${reason} ${shown} passage${shown === 1 ? "" : "s"} below. ${pack.heldBackChunkIds.length} left out at this budget.`;
  }
  return `${reason} This section is left out at this budget.`;
}

/**
 * Returns the tooltip on a section's heading line. The text for a structural build never claims
 * grouping that did not run, and the ML text says the build does not report k or the silhouette
 * score, which BuildInfo does not carry.
 */
export function clusterInfoText(analysis: "ml" | "structural"): string {
  if (analysis === "structural") {
    return "This heading is Wikipedia's own. No grouping ran for this build.";
  }
  return (
    "This heading is Wikipedia's own section heading, not a group label. The groups come from " +
    "K-means on all-MiniLM-L6-v2 embeddings, run separately over passages rather than sections. " +
    "The result (below) does not follow section boundaries. A section can hold passages from " +
    "more than one group. This build does not report k or the silhouette score."
  );
}
