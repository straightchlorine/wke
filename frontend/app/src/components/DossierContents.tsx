import { useNavigate } from "@tanstack/react-router";
import type { DossierView } from "../api/dossier";
import { budgetAlias, type Budget } from "../lib/budget";
import { isPlainLeftClick } from "../lib/clicks";
import {
  nextBudgetUp,
  sectionTitle,
  subsectionTokens,
  type SectionRow,
} from "../lib/dossierSections";
import { formatNumber } from "../lib/format";
import { focusSectionHeading } from "../lib/sectionJump";
import { hasSubsections, sectionDepth } from "../lib/sectionDepth";
import { SectionTitle } from "./SectionTitle";

export interface DossierContentsProps {
  dossier: DossierView;
  rows: readonly SectionRow[];
  /** The id of the section the reader is in, marked in the list. */
  currentId: string | null;
  budget: Budget;
  /** How many sections the budget leaves out. */
  leftOutCount: number;
}

/** The list of sections with the tokens each holds at the budget, as a rail that sticks beside the article. */
export function DossierContents({
  dossier,
  rows,
  currentId,
  budget,
  leftOutCount,
}: DossierContentsProps) {
  const navigate = useNavigate();
  return (
    <nav
      aria-label="Contents"
      className="max-[1340px]:hidden min-[1340px]:sticky min-[1340px]:top-16 min-[1340px]:max-h-[calc(100vh/var(--ui-zoom)-88px)] min-[1340px]:overflow-y-auto min-[1340px]:overscroll-contain thin-scroll"
    >
      <SectionTitle>Contents</SectionTitle>
      <ol className="mt-2">
        {rows.map(({ section, index, id: sectionId, pack }) => {
          const isCurrent = sectionId === currentId;
          return (
            <li
              key={section.id}
              data-depth={sectionDepth(section)}
              style={{ paddingInlineStart: `${(sectionDepth(section) - 1) * 12}px` }}
              className={pack.state === "folded" ? "text-ink-3" : ""}
            >
              {/* A plain anchor that calls navigate() on click, not a Link: Link sets aria-current="page"
                  on the entry whose hash matches the URL, and that value belongs to the nav link alone.
                  Like the chip strip, this list marks the section the reader is scrolled to with
                  aria-current="location", not the last hash that was tapped. */}
              <a
                href={`#${sectionId}`}
                aria-current={isCurrent ? "location" : undefined}
                onClick={(event) => {
                  if (!isPlainLeftClick(event)) {
                    return;
                  }
                  event.preventDefault();
                  void navigate({
                    to: ".",
                    search: true,
                    hash: sectionId,
                    hashScrollIntoView: { block: "start" },
                  }).then(() => focusSectionHeading(sectionId));
                }}
                className={`flex justify-between gap-x-2 py-1 text-13 [@media(pointer:coarse)]:py-[13px] ${isCurrent ? "text-accent font-medium shadow-[inset_2px_0_0_var(--color-accent)] pl-2 -ml-2" : ""}`}
              >
                <span title={sectionTitle(section)} className="truncate">
                  {index + 1} {section.label}
                </span>
                <span className="tabular-nums text-ink-3">
                  {pack.state === "folded" ? (
                    "left out"
                  ) : section.chunk_ids.length === 0 ? (
                    hasSubsections(dossier.sections, index) ? (
                      formatNumber(subsectionTokens(rows, index))
                    ) : (
                      <>
                        no prose<span className="sr-only"> passages kept</span>
                      </>
                    )
                  ) : (
                    formatNumber(pack.includedTokens)
                  )}
                </span>
              </a>
            </li>
          );
        })}
      </ol>
      {leftOutCount > 0 && nextBudgetUp(budget) ? (
        <p className="mt-2 text-12 text-ink-3">
          {leftOutCount} section{leftOutCount === 1 ? "" : "s"} left out at {budgetAlias(budget)}.
          They may return at a larger budget.
        </p>
      ) : null}
    </nav>
  );
}
