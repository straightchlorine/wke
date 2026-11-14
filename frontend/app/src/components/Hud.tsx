import { useEffect } from "react";
import { Segmented, type SegmentedOption } from "./Segmented";
import { CopyButton } from "./CopyButton";
import { formatNumber } from "../lib/format";

/** The bar's height, without the device safe-area inset. */
const HUD_BAR_HEIGHT = "3.5rem";

export interface HudProps<T extends string> {
  budgetOptions: SegmentedOption<T>[];
  budgetValue: T;
  onBudgetChange: (value: T) => void;
  usedTokens: number;
  /** Produces (or fetches) the text the primary button copies. */
  getText: () => string | Promise<string | null> | null;
  /** Toast message after a successful copy. */
  message: string;
  /** Toast message when `getText` returns or resolves null. */
  fetchFailedMessage?: string;
  /** Receives the toast message for every outcome. */
  onCopy?: (message: string) => void;
  className?: string;
}

/** The fixed bottom bar of the dossier page: the budget switch and a button that copies the dossier as context. */
export function Hud<T extends string>({
  budgetOptions,
  budgetValue,
  onBudgetChange,
  usedTokens,
  getText,
  message,
  fetchFailedMessage,
  onCopy,
  className = "",
}: HudProps<T>) {
  // The page footer and the toast read this height, so the last links are not left under the bar.
  useEffect(() => {
    document.documentElement.style.setProperty(
      "--hud-h",
      `calc(${HUD_BAR_HEIGHT} + env(safe-area-inset-bottom))`,
    );
    return () => {
      document.documentElement.style.removeProperty("--hud-h");
    };
  }, []);
  return (
    <div
      role="toolbar"
      aria-label="Token budget and copy"
      style={{ height: HUD_BAR_HEIGHT }}
      className={`fixed inset-x-0 bottom-0 z-20 flex items-center gap-x-2 border-t-(length:--hairline) border-ink bg-sheet px-4 [padding-bottom:env(safe-area-inset-bottom)] ${className}`}
    >
      <Segmented
        ariaLabel="Token budget"
        name="hud-budget"
        options={budgetOptions}
        value={budgetValue}
        onChange={onBudgetChange}
        numberShortcuts
      />
      <CopyButton
        variant="primary"
        getText={getText}
        message={message}
        fetchFailedMessage={fetchFailedMessage}
        onCopy={onCopy}
        title={`${formatNumber(usedTokens)} dossier tokens`}
        ariaLabel={`Copy as context, ${formatNumber(usedTokens)} dossier tokens`}
        className="min-w-0 flex-1 flex-col justify-center gap-y-0 leading-tight"
      >
        {(copied) =>
          copied ? (
            "Copied"
          ) : (
            <>
              Copy as context
              {/* The count is drawn by CSS from data-count, so it is not part of the button's text. */}
              <span
                aria-hidden="true"
                data-count={`${formatNumber(usedTokens)} dossier tokens`}
                className="text-12 font-normal opacity-80 after:content-[attr(data-count)]"
              />
            </>
          )
        }
      </CopyButton>
    </div>
  );
}
