import { createElement } from "react";
import type { DossierView } from "../api/dossier";
import type { Budget } from "../lib/budget";
import { sectionGroupSummary, type CitationNotes } from "../lib/dossierPack";
import {
  clusterInfoText,
  completenessNote,
  missingSummaryDetail,
  nextBudgetUp,
  type SectionRow,
} from "../lib/dossierSections";
import type { FoldedText } from "../lib/hooks/useFoldedReading";
import { hasSubsections, sectionDepth, sectionHeadingTag } from "../lib/sectionDepth";
import { formatNumber } from "../lib/format";
import { CutRow, FoldRow } from "./CutRow";
import { InfoDot } from "./InfoDot";
import { MarginNote } from "./MarginNote";
import { ModelPanel } from "./ModelPanel";
import { PassageList } from "./PassageList";
import { sectionNoteRows } from "./sectionNoteRows";
import { SummaryLine } from "./SummaryLine";

export interface DossierSectionProps {
  dossier: DossierView;
  row: SectionRow;
  notes: CitationNotes;
  budget: Budget;
  /** The tokens included in the sections before this one. */
  tokenOffset: number;
  /** The id of the build job, named in a pending summary's line. */
  jobId: string | undefined;
  /** The passages of a left-out section, once the reader asked to read them in place. */
  foldedText: FoldedText | undefined;
  onShowAtBudget: (next: Budget) => void;
  onReadHere: () => void;
}

/** One section of the article: its heading, a line about what the budget kept, the summary or the reason for none, and the passages. */
export function DossierSection({
  dossier,
  row,
  notes,
  budget,
  tokenOffset,
  jobId,
  foldedText,
  onShowAtBudget,
  onReadHere,
}: DossierSectionProps) {
  const { section, index, id: sectionId, pack } = row;
  const isLead = section.label_source === "article_title" || index === 0;
  const hasModelSummary = section.summary_state === "done" && section.summary != null;
  const depth = sectionDepth(section);
  const noProse = section.chunk_ids.length === 0;
  const isParent = hasSubsections(dossier.sections, index);
  const completeness = completenessNote(section, pack, dossier.build.truncated);
  const groupSummary = sectionGroupSummary(dossier, section);
  const nextBudget = nextBudgetUp(budget);

  return (
    <section
      id={sectionId}
      // The scroll margin puts the heading, which sits below the section's top border and padding,
      // a gap under the sticky bars.
      className="scroll-mt-[calc(var(--dossier-stick,56px)_-_9px)] border-t-(length:--hairline) border-rule py-6 first:border-t-0"
    >
      <div className="flex items-baseline gap-x-2">
        {createElement(
          sectionHeadingTag(section),
          {
            tabIndex: -1,
            "data-section-heading": "",
            "data-depth": depth,
            className: `font-serif text-ink ${depth > 1 ? "text-18" : "text-22"}`,
          },
          `${index + 1} ${section.label}`,
        )}
      </div>
      {/*
        The InfoDot sits inside the same inline text run as the meta text, not as a separate flex
        item beside it. A flex item boundary is always a wrap point, which could leave the (i)
        alone on its own line. Inline, with no whitespace before it, it has no wrap point of its
        own and always rides with the last word.
      */}
      <p className="mt-1 text-12 text-ink-3">
        Wikipedia section: {section.label}
        {noProse ? (
          isParent ? (
            "; heading only, its text is in the subsections that follow"
          ) : section.summary_state === "no_prose" ? null : (
            "; no prose passages kept (lists and tables are not extracted)"
          )
        ) : (
          <>
            , {pack.includedTokens > 0 ? `${formatNumber(pack.includedTokens)} tokens, ` : ""}
            {pack.includedChunks.length} of {section.chunk_ids.length} passages
            {isLead && !hasModelSummary ? ", the lead has no model summary" : ""}
            {groupSummary ? `, ${groupSummary}` : ""}
          </>
        )}
        {tokenOffset > 0 ? (
          <span className="min-[600px]:hidden">, at {formatNumber(tokenOffset)} tokens</span>
        ) : null}
        {completeness ? <span data-role="completeness">. {completeness}</span> : null}
        <InfoDot
          label={`About this section's heading and grouping: ${section.label}`}
          text={clusterInfoText(dossier.build.analysis)}
        />
      </p>

      {hasModelSummary && section.summary ? (
        <ModelPanel
          summary={section.summary}
          chunkLinks={(section.summary.input_chunk_ids ?? [])
            .map((id) => {
              const chunkIndex = pack.includedChunks.findIndex((c) => c.id === id);
              return chunkIndex === -1 ? null : { id, index: chunkIndex + 1 };
            })
            .filter((c): c is { id: string; index: number } => c != null)}
          className="mt-3"
        />
      ) : section.summary_state === "no_prose" &&
        !(isParent && section.dropped_non_prose !== true) ? (
        <SummaryLine
          className="mt-3"
          detail="No prose passages kept: lists and tables are not extracted."
        />
      ) : !isLead && !noProse ? (
        <SummaryLine className="mt-3" detail={missingSummaryDetail(section, pack, jobId)} />
      ) : null}

      {pack.state === "folded" ? (
        <FoldRow
          className="mt-3"
          label={section.label}
          reason={
            nextBudget != null ? "Left out entirely at this budget." : "Does not fit even at 32k."
          }
          nextBudget={nextBudget ?? undefined}
          onShowAtBudget={nextBudget != null ? onShowAtBudget : undefined}
          onReadHere={onReadHere}
          expanded={foldedText != null}
        />
      ) : (
        <div
          data-role="source-text"
          className="mt-3 space-y-3 font-serif text-17 leading-[27px] text-ink"
        >
          <PassageList
            chunks={pack.includedChunks}
            citations={dossier.citations}
            numbers={notes.numbers}
          />
        </div>
      )}

      {pack.state === "folded" && foldedText && foldedText !== "loading" ? (
        <div className="mt-3 space-y-3 border-l-2 border-rule-strong bg-sunken p-3 font-serif text-17 leading-[27px] text-ink">
          <PassageList chunks={foldedText} citations={dossier.citations} numbers={notes.numbers} />
        </div>
      ) : pack.state === "folded" && foldedText === "loading" ? (
        <p className="mt-3 text-13 text-ink-3">Loading...</p>
      ) : null}

      {pack.state === "cut" && nextBudget ? (
        <CutRow
          className="mt-3"
          label={section.label}
          heldBackCount={pack.heldBackChunkIds.length}
          nextBudget={nextBudget}
          onShowAtBudget={onShowAtBudget}
        />
      ) : null}

      <MarginNote
        className="mt-3 max-[899px]:block min-[900px]:hidden"
        sectionLabel={section.label}
        rows={sectionNoteRows(dossier.build.analysis, section, pack, index)}
      />
    </section>
  );
}
