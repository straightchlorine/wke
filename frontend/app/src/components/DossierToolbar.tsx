import { useState } from "react";
import type { DossierView } from "../api/dossier";
import {
  BUDGET_OPTIONS,
  budgetToSegmentValue,
  dossierBudgetHelp,
  parseBudget,
  type Budget,
} from "../lib/budget";
import { mcpDossierCall } from "../lib/endpoints";
import { formatNumber } from "../lib/format";
import { useMediaQuery } from "../lib/hooks/useMediaQuery";
import type { DossierExports } from "../lib/hooks/useDossierExports";
import type { SectionTotals } from "../lib/dossierSections";
import { Button } from "./Button";
import { CodeBlock } from "./CodeBlock";
import { CopyButton } from "./CopyButton";
import { InfoDot } from "./InfoDot";
import { Meter } from "./Meter";
import { Segmented } from "./Segmented";

export interface DossierToolbarProps {
  dossier: DossierView;
  budget: Budget;
  onBudgetChange: (next: Budget) => void;
  totals: SectionTotals;
  /** The dossier's sections, counting the ones the page leaves out for having no prose. */
  sectionCount: number;
  exports: DossierExports;
  /** Called with the message of every successful copy. */
  onCopy: (message: string) => void;
}

/** The sticky toolbar: the budget control, what that budget holds, and the download and copy buttons. The MCP button opens the tool call under it. */
export function DossierToolbar({
  dossier,
  budget,
  onBudgetChange,
  totals,
  sectionCount,
  exports,
  onCopy,
}: DossierToolbarProps) {
  const coarsePointer = useMediaQuery("(pointer: coarse)");
  const [mcpOpen, setMcpOpen] = useState(false);
  const mcpCall = mcpDossierCall(dossier.topic.title, budget, "json");
  const usedFraction =
    dossier.budget.requested > 0 ? dossier.budget.used_est_tokens / dossier.budget.requested : 0;
  return (
    <>
      <div
        data-dossier-toolbar
        className="sticky top-0 z-20 flex min-h-(--toolbar-h) flex-wrap items-center gap-x-2 gap-y-2 border-b-(length:--hairline) border-ink bg-sunken px-2 max-[599px]:hidden"
      >
        <span className="text-13 text-ink-2 pointer-coarse:pr-2">
          {/* The label text drops out on narrower screens to leave room for Copy as context on the same row. The InfoDot's own label keeps the control meaningful. */}
          <span className="max-[899px]:hidden">Token budget</span>
          <InfoDot
            className="max-[899px]:ml-0"
            label="About the token budget"
            text={dossierBudgetHelp(dossier.budget.estimator, coarsePointer)}
          />
        </span>
        <Segmented
          ariaLabel="Token budget"
          name="budget"
          options={BUDGET_OPTIONS}
          value={budgetToSegmentValue(budget)}
          onChange={(value) => onBudgetChange(parseBudget(value))}
          numberShortcuts
        />
        <Meter
          className="min-w-40 max-w-72 min-[900px]:flex-1"
          label={`${formatNumber(dossier.budget.used_est_tokens)} of ${formatNumber(dossier.budget.requested)} tokens, ${totals.shown} of ${sectionCount} sections`}
          info={
            <InfoDot
              label="About passages in this budget"
              text={`${totals.includedPassages} of ${totals.totalPassages} passages included at this budget.`}
            />
          }
          fraction={usedFraction}
        />
        <Button variant="secondary" onClick={() => void exports.downloadMarkdown()}>
          <span className="max-[899px]:hidden">Download .md</span>
          <span className="min-[900px]:hidden">Download</span>
        </Button>
        <Button variant="secondary" onClick={exports.downloadJson}>
          JSON
        </Button>
        <Button variant="secondary" aria-expanded={mcpOpen} onClick={() => setMcpOpen((v) => !v)}>
          MCP
        </Button>
        <CopyButton
          variant="primary"
          className="ml-auto"
          title={`${formatNumber(dossier.budget.used_est_tokens)} dossier tokens`}
          getText={exports.fetchAsContext}
          message={exports.copyMessage}
          fetchFailedMessage="Copy failed. Try Download instead"
          onCopy={onCopy}
        >
          {(copied) =>
            copied
              ? `Copied ${formatNumber(dossier.budget.used_est_tokens)} dossier tokens`
              : "Copy as context"
          }
        </CopyButton>
      </div>

      {mcpOpen ? (
        <CodeBlock
          className="mt-2"
          heading="MCP tool call"
          code={mcpCall}
          copy={{ id: "mcp-copy", message: "Copied MCP tool call" }}
          onCopy={onCopy}
        />
      ) : null}
    </>
  );
}
