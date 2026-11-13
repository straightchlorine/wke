import type { CSSProperties } from "react";
import { Link } from "@tanstack/react-router";
import { formatSignedDelta, formatUtcClockSeconds } from "../lib/format";
import type { Budget } from "../lib/budget";

export type LedgerUserKind = "registered" | "anonymous" | "bot";

export interface LedgerRowProps {
  ts: Date | string;
  subject: string;
  /** The dossier route's slug, when the title resolves to a tracked topic. */
  slug?: string;
  budget: Budget;
  /** Net byte delta; null when the API did not report one. */
  byteDelta: number | null;
  userKind: LedgerUserKind;
  /** Number of edits merged into this row. It stays 1 until another edit of the same title arrives. */
  runCount?: number;
  /** True when this row's page has a recent edit, which draws the row highlighted. */
  fresh?: boolean;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
  onFocus?: () => void;
  onBlur?: () => void;
}

/** One edit row: time, subject, signed byte delta and editor kind. */
function LedgerRow({
  ts,
  subject,
  slug,
  budget,
  byteDelta,
  userKind,
  runCount = 1,
  fresh = false,
  onMouseEnter,
  onMouseLeave,
  onFocus,
  onBlur,
}: LedgerRowProps) {
  // A fresh row sits on stamp-wash, where ink-3 falls under 4.5:1 in dark.
  const quiet = fresh ? "text-ink-2" : "text-ink-3";
  const repeats = runCount > 1 ? <span className={quiet}> x{runCount}</span> : null;
  const subjectClass = `truncate ${fresh ? "font-medium text-stamp" : "text-ink"}`;
  return (
    <tr
      className={fresh ? "bg-stamp-wash transition-colors duration-(--motion-base)" : ""}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <td className={`h-(--ledger-row) w-16 py-0 pr-2 align-middle text-12 ${quiet} tabular-nums`}>
        {formatUtcClockSeconds(ts)}
      </td>
      <td className="h-(--ledger-row) max-w-0 py-0 pr-2 align-middle">
        {slug ? (
          <Link
            to="/t/$slug"
            params={{ slug }}
            search={{ budget }}
            title={subject}
            onFocus={onFocus}
            onBlur={onBlur}
            className={`relative block [@media(pointer:coarse)]:before:absolute [@media(pointer:coarse)]:before:inset-x-0 [@media(pointer:coarse)]:before:-inset-y-3 [@media(pointer:coarse)]:before:content-[''] ${subjectClass}`}
          >
            {subject}
            {repeats}
          </Link>
        ) : (
          <span title={subject} className={`block ${subjectClass}`}>
            {subject}
            {repeats}
          </span>
        )}
      </td>
      <td
        className="h-(--ledger-row) w-20 py-0 pr-2 text-right align-middle text-12 text-ink-2 tabular-nums"
        title={runCount > 1 ? "Total size change across these edits, in bytes" : undefined}
      >
        {byteDelta == null
          ? "-"
          : runCount > 1
            ? `net ${formatSignedDelta(byteDelta)}`
            : formatSignedDelta(byteDelta)}
      </td>
      <td
        className={`hidden h-(--ledger-row) w-24 py-0 align-middle text-12 ${quiet} min-[600px]:table-cell`}
      >
        {userKind}
      </td>
    </tr>
  );
}

/** The height of one slot in px; the panel counts how many fit. */
export const LEDGER_ROW_PX = 26;
/** Slots reserved for the "+N more" row and the marker row. A notice row takes one more, which this does not count. */
export const LEDGER_FIXED_SLOTS = 2;
/** Slots used before the panel has been measured. */
export const LEDGER_DEFAULT_SLOTS = 9;

const TABLE_STYLE: CSSProperties & { "--ledger-row": string } = {
  "--ledger-row": `${LEDGER_ROW_PX}px`,
};

/** Returns how many slots fit in a height, never fewer than the fixed slots plus three. */
export function ledgerSlotsFor(heightPx: number): number {
  return Math.max(LEDGER_FIXED_SLOTS + 3, Math.floor(heightPx / LEDGER_ROW_PX));
}

export interface LedgerProps {
  rows: LedgerRowProps[];
  /**
   * Index after which the marker row (e.g. "listening since HH:MM:SS UTC")
   * sits: the boundary between the events replayed on load and any that
   * have arrived live since. 0 puts it before all of them.
   */
  markerIndex?: number;
  markerLabel?: string;
  /** Shown at the marker row's right edge when replayed rows follow it. */
  earlierLabel?: string;
  /** The "+N more" row after the live rows and before the marker: the oldest arrivals, which are not shown. 0 leaves no such row. */
  moreCount?: number;
  /** A one-line state of the feed ("Live edits paused since 12:03"), as the first row; it takes one of the slots. */
  notice?: string;
  /**
   * The number of rows to fill, shared by the notice row, the marker row, the "+N more" row and the edit rows.
   * At least one edit row always shows, so a smaller value makes the table taller than this.
   */
  slots?: number;
  className?: string;
}

function BlankRow() {
  return (
    <tr aria-hidden="true">
      <td colSpan={4} className="h-(--ledger-row) p-0">
        &nbsp;
      </td>
    </tr>
  );
}

/**
 * A table of fixed-height slots, so it keeps the same height with no edits, a full feed or a paused one.
 * The notice, the "+N more" row, the marker row and the edit rows share the slots, and blank rows after the last edit fill the rest.
 * A visually hidden `<thead>` lets screen readers announce each cell with its column.
 */
export function Ledger({
  rows,
  markerIndex,
  markerLabel,
  earlierLabel,
  moreCount = 0,
  notice,
  slots = LEDGER_DEFAULT_SLOTS,
  className = "",
}: LedgerProps) {
  const editRows = Math.max(
    1,
    slots - (notice ? 1 : 0) - (markerLabel ? 1 : 0) - (moreCount > 0 ? 1 : 0),
  );
  const shown = rows.slice(0, editRows);
  const at = markerIndex ?? shown.length;
  const before = shown.slice(0, at);
  const after = shown.slice(at);
  const blanks = Array.from({ length: editRows - shown.length }, (_, i) => i);
  return (
    <table
      aria-label="Edits as they land, times UTC"
      style={TABLE_STYLE}
      className={`w-full border-collapse text-left text-13 ${className}`}
    >
      <thead className="sr-only">
        <tr>
          <th scope="col">Time, UTC</th>
          <th scope="col">Article</th>
          <th scope="col">Bytes</th>
          <th scope="col">Editor</th>
        </tr>
      </thead>
      <tbody>
        {notice ? (
          <tr>
            <td
              colSpan={4}
              data-ledger-status=""
              title={notice}
              className="h-(--ledger-row) max-w-0 truncate p-0 align-middle text-13 text-ink-3"
            >
              {notice}
            </td>
          </tr>
        ) : null}
        {before.map((row, index) => (
          <LedgerRow key={`${row.subject}-${index}`} {...row} />
        ))}
        {moreCount > 0 ? (
          <tr>
            <td colSpan={4} className="h-(--ledger-row) p-0 align-middle text-12 text-ink-3">
              +{moreCount} more edits not shown
            </td>
          </tr>
        ) : null}
        {markerLabel ? (
          <tr>
            <td
              colSpan={4}
              className="h-(--ledger-row) border-y-(length:--hairline) border-rule p-0 align-middle text-12 text-ink-3"
            >
              <span className="flex items-baseline justify-between gap-x-3">
                <span className="min-w-0 truncate">{markerLabel}</span>
                {after.length > 0 && earlierLabel ? (
                  <span className="shrink-0">{earlierLabel}</span>
                ) : null}
              </span>
            </td>
          </tr>
        ) : null}
        {after.map((row, index) => (
          <LedgerRow key={`${row.subject}-${at + index}`} {...row} />
        ))}
        {blanks.map((i) => (
          <BlankRow key={`blank-${i}`} />
        ))}
      </tbody>
    </table>
  );
}
