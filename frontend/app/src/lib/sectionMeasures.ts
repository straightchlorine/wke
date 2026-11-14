import type { SectionRow } from "./dossierSections";

/** Where each section heading sits in the rendered layout, for the token ruler and the margin notes. */
export interface SectionMeasures {
  /** Maps a token offset to a position down the article, from 0 to 1, for the ruler. */
  breakpoints: Array<{ token: number; fraction: number }>;
  /** Each section's heading position down the article, from 0 to 1, by section id. */
  tickFractions: Map<string, number>;
  /** Each section's heading offset in px from the top of the margin rail, by section id. */
  offsetsPx: Map<string, number>;
  /** The article's bottom edge in px from the top of the margin rail. */
  railBottomPx: number;
}

/** What `measureSections` reads from the page. All positions are viewport tops in px. */
interface SectionMeasureInput {
  rows: readonly SectionRow[];
  usedTokens: number;
  /** The top of each section's heading, by section id. A section with no heading in the page has no entry. */
  headingTops: ReadonlyMap<string, number>;
  articleTop: number;
  articleHeight: number;
  /** The top of the margin rail, which starts below the graph and the records in the same column. */
  railTop: number;
}

/** The measures before the page has been laid out. */
export const NO_MEASURES: SectionMeasures = {
  breakpoints: [],
  tickFractions: new Map(),
  offsetsPx: new Map(),
  railBottomPx: 0,
};

/**
 * Turns the measured heading positions into the ruler's breakpoints and the margin rail's offsets.
 * The article's top is not section 1's heading, because an intro paragraph sits above it. So token 0
 * gets its fraction from the first heading, like every other section.
 */
export function measureSections({
  rows,
  usedTokens,
  headingTops,
  articleTop,
  articleHeight,
  railTop,
}: SectionMeasureInput): SectionMeasures {
  const breakpoints: SectionMeasures["breakpoints"] = [];
  const tickFractions = new Map<string, number>();
  const offsetsPx = new Map<string, number>();
  let cumulative = 0;
  for (const row of rows) {
    const headingTop = headingTops.get(row.id);
    if (headingTop != null) {
      const fraction = Math.min(1, Math.max(0, (headingTop - articleTop) / articleHeight));
      breakpoints.push({ token: cumulative, fraction });
      tickFractions.set(row.id, fraction);
      offsetsPx.set(row.id, Math.max(0, headingTop - railTop));
    }
    cumulative += row.pack.includedTokens;
  }
  breakpoints.push({ token: usedTokens, fraction: 1 });
  return {
    breakpoints,
    tickFractions,
    offsetsPx,
    railBottomPx: Math.max(0, articleTop + articleHeight - railTop),
  };
}
