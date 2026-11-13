import type { ReactNode } from "react";
import type { DossierState } from "../lib/dossierState";
import { staleLabel } from "../lib/format";
import { InfoDot } from "./InfoDot";

export type ChipVariant = "built" | "queued" | "model" | "stale" | "current" | "unknown" | "quiet";

export interface ChipProps {
  children: ReactNode;
  variant: ChipVariant;
  /** Draws the chip at the shared control height, so it sits on one line with buttons. */
  control?: boolean;
  /** An explanation. The chip shows an (i) glyph at its right end and opens this text as a tooltip on hover and focus. */
  info?: string;
  className?: string;
}

const VARIANT_CLASSES: Record<ChipVariant, string> = {
  built: "text-ink-2 border-(length:--hairline) border-rule-strong bg-transparent",
  queued: "text-ink-2 bg-sunken border-0",
  model: "text-ink-2 bg-model border-(length:--hairline) border-rule-strong",
  stale: "text-ink-2 border-(length:--hairline) border-ink-2 bg-transparent",
  current: "text-accent-ink bg-wash border-0",
  unknown: "text-ink-2 border-(length:--hairline) border-rule-strong bg-transparent",
  quiet: "text-ink-3 border-(length:--hairline) border-rule bg-transparent",
};

/** A small label whose variant sets its colours. */
export function Chip({ children, variant, control = false, info, className = "" }: ChipProps) {
  const base = `inline-flex items-center rounded-1 text-12 whitespace-nowrap ${control ? "h-(--control-h) px-3" : "px-2 py-0.5"} ${VARIANT_CLASSES[variant]}`;
  if (info != null) {
    return (
      <InfoDot
        text={info}
        className={`inline-flex ${className}`}
        triggerClassName={`${base} no-underline!`}
      >
        {children}
        <InfoDot decorative text="" />
      </InfoDot>
    );
  }
  return <span className={`${base} ${className}`}>{children}</span>;
}

export type { DossierState };

const DOSSIER_STATE_CHIP: Record<
  Exclude<DossierState, "none">,
  { variant: "built" | "queued"; text: string }
> = {
  ready: { variant: "built", text: "Ready" },
  partial: { variant: "built", text: "Partial" },
  building: { variant: "queued", text: "Building" },
};

export interface DossierStateChipProps {
  state: DossierState;
  /** Shows a "Not built" chip for the "none" state instead of nothing. */
  showNone?: boolean;
  className?: string;
}

/** Renders a dossier's build state as a Chip, or nothing for "none" unless `showNone` is set. */
export function DossierStateChip({
  state,
  showNone = false,
  className = "",
}: DossierStateChipProps) {
  if (state === "none") {
    return showNone ? (
      <Chip variant="unknown" className={className}>
        Not built
      </Chip>
    ) : null;
  }
  const mapped = DOSSIER_STATE_CHIP[state];
  return (
    <Chip variant={mapped.variant} className={className}>
      {mapped.text}
    </Chip>
  );
}

/** How current a dossier is: the `freshness_state` the API reports. */
export type FreshnessState = "fresh" | "stale" | "unknown";

export interface FreshnessChipProps {
  /** The API's freshness state for the pinned revision. */
  state: FreshnessState;
  /** Edits since the pin. Null means the count is unknown, for example when only revision ids were compared. */
  editsSincePin?: number | null;
  /** Text shown when the dossier is current. */
  currentLabel?: ReactNode;
  /** Explains "Not checked" in a tooltip. Set false where the page already explains it once, such as a table column header. */
  showInfo?: boolean;
  /** Replaces the default "Not checked" explanation, for example when the edit feed is disconnected. */
  unknownText?: string;
  /** A tooltip for any state. It wins over `showInfo`. */
  info?: string;
  /** Draws the chip at control height, as `Chip` does. */
  control?: boolean;
  /** Draws "Not checked" in the quiet variant, for table rows where most rows carry it. */
  quiet?: boolean;
  /** Drops " since built" from the out-of-date label on narrow screens, where a row has no room for it. */
  shortOnPhone?: boolean;
  className?: string;
}

const STALE_TAIL = " since built";

/** Shows whether a pinned revision is out of date, current, or not checked. The out-of-date text comes from `staleLabel`. */
export function FreshnessChip({
  state,
  editsSincePin = null,
  currentLabel = "Up to date",
  showInfo = true,
  unknownText = "WKE has not seen an edit to this article since the dossier was built, so it cannot say whether the dossier is up to date.",
  info,
  control = false,
  quiet = false,
  shortOnPhone = false,
  className = "",
}: FreshnessChipProps) {
  if (state === "stale") {
    const label = staleLabel(editsSincePin);
    const cut = shortOnPhone && label.endsWith(STALE_TAIL);
    return (
      <Chip variant="stale" control={control} info={info} className={className}>
        {/* The label and its tail share one span, because as separate flex items the tail would lose its leading space. */}
        <span>
          {cut ? label.slice(0, -STALE_TAIL.length) : label}
          {cut ? <span className="max-md:hidden">{STALE_TAIL}</span> : null}
        </span>
      </Chip>
    );
  }
  if (state === "unknown") {
    return (
      <Chip
        variant={quiet ? "quiet" : "unknown"}
        control={control}
        info={info ?? (showInfo ? unknownText : undefined)}
        className={className}
      >
        Not checked
      </Chip>
    );
  }
  return (
    <Chip variant="current" control={control} info={info} className={className}>
      {currentLabel}
    </Chip>
  );
}
