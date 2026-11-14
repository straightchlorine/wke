import type { Ref } from "react";
import type { DossierView } from "../api/dossier";
import type { Section } from "../api/generated";
import type { Budget } from "../lib/budget";
import { citationNotes } from "../lib/dossierPack";
import { tokenOffsets, type SectionRow } from "../lib/dossierSections";
import { formatNumber } from "../lib/format";
import type { FoldedText } from "../lib/hooks/useFoldedReading";
import { DossierCitations } from "./DossierCitations";
import { DossierSection } from "./DossierSection";
import { InfoDot } from "./InfoDot";

export interface DossierArticleProps {
  dossier: DossierView;
  rows: readonly SectionRow[];
  budget: Budget;
  /** The id of the build job, named in a pending summary's line. */
  jobId: string | undefined;
  /** The passages of the left-out sections the reader opened, by section id. */
  foldedTexts: Record<string, FoldedText>;
  onShowAtBudget: (next: Budget) => void;
  onReadHere: (section: Section) => void;
  ref?: Ref<HTMLElement>;
}

/** The dossier text: a line on what it is, every section, and the citations. */
export function DossierArticle({
  dossier,
  rows,
  budget,
  jobId,
  foldedTexts,
  onShowAtBudget,
  onReadHere,
  ref,
}: DossierArticleProps) {
  const notes = citationNotes(dossier);
  const offsets = tokenOffsets(rows);
  return (
    <article ref={ref} aria-label="Dossier text" className="min-w-0">
      <p className="mb-4 text-12 text-ink-3">
        This is the dossier part of the text the API returns; the header and the Sources list come
        on top. text/markdown, utf-8, about {formatNumber(dossier.budget.used_est_tokens)}{" "}
        <span className="whitespace-nowrap">
          tokens
          <InfoDot
            label="About the token count"
            text={`An estimate, not a tokenizer count: characters / 4 (${dossier.budget.estimator}).`}
          />
        </span>
      </p>

      {rows.map((row) => (
        <DossierSection
          key={row.section.id}
          dossier={dossier}
          row={row}
          notes={notes}
          budget={budget}
          tokenOffset={offsets[row.index] ?? 0}
          jobId={jobId}
          foldedText={foldedTexts[row.section.id]}
          onShowAtBudget={onShowAtBudget}
          onReadHere={() => onReadHere(row.section)}
        />
      ))}

      <DossierCitations notes={notes} />
    </article>
  );
}
