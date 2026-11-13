import type { Section } from "../api/generated";
import type { SectionPack } from "../lib/dossierPack";
import { formatRange } from "../lib/format";
import { InfoDot } from "./InfoDot";
import type { RecordRowProps } from "./Record";

/**
 * Returns the rows of a section's note: how many of its passages the budget kept and, for the
 * ranking, either its position weight (a structural build) or the range of its passages'
 * similarity to the lead (an ML build, when the section has a kept passage).
 * `order` is the section's position, counted from 0.
 */
export function sectionNoteRows(
  analysis: "ml" | "structural",
  section: Section,
  pack: SectionPack,
  order: number,
): RecordRowProps[] {
  const rows: RecordRowProps[] = [];
  if (section.chunk_ids.length > 0) {
    rows.push({
      label: "Passages",
      value: `${pack.includedChunks.length} of ${section.chunk_ids.length}`,
      size: "normal",
    });
  }
  if (analysis === "structural") {
    rows.push({
      label: (
        <span>
          Position weight
          <InfoDot
            label={`About position weight: ${section.label}`}
            text="Sections ranked by their position in the article, earlier first (1/(1+order)). No similarity model ran for this dossier."
          />
        </span>
      ),
      value: (1 / (1 + order)).toFixed(2),
      size: "normal",
    });
  } else if (pack.relevanceRange) {
    rows.push({
      label: (
        <span>
          Similarity to lead
          <InfoDot
            label={`About similarity to lead: ${section.label}`}
            text="How close each passage shown is in meaning to the article's lead (its opening section), from 0 to 1, measured by the MiniLM model."
          />
        </span>
      ),
      value: formatRange(pack.relevanceRange[0], pack.relevanceRange[1]),
      size: "normal",
    });
  }
  return rows;
}
