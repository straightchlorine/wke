import { useEffect, useRef, useState, type RefObject } from "react";
import type { Budget } from "../lib/budget";
import { formatNumber, formatLiveEditsStatus, pluralize } from "../lib/format";
import type { PausedFeed } from "../lib/hooks/usePausedFeed";
import type { UseLiveResult } from "../lib/hooks/useLive";
import {
  announcedFeedState,
  feedIsDown,
  ledgerMarkerLabel,
  ledgerStatus,
  ledgerWindow,
} from "../lib/ledgerView";
import { announceLive } from "../lib/liveRegion";
import { Ledger, LEDGER_DEFAULT_SLOTS, ledgerSlotsFor } from "./Ledger";
import { Pause } from "./PauseButton";
import { SectionTitle } from "./SectionTitle";

/**
 * Counts the edit slots a panel has room for, from the height of the element that gets the returned `bodyRef`.
 * It counts again only when the body resizes, so incoming edits never change it.
 */
export function useLedgerSlots() {
  const bodyRef = useRef<HTMLDivElement>(null);
  const [slots, setSlots] = useState(LEDGER_DEFAULT_SLOTS);
  useEffect(() => {
    const el = bodyRef.current;
    if (!el || typeof ResizeObserver === "undefined") {
      return () => {};
    }
    const measure = () => setSlots(ledgerSlotsFor(el.clientHeight));
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    measure();
    return () => observer.disconnect();
  }, []);
  return { bodyRef, slots };
}

export interface LedgerPanelProps {
  live: UseLiveResult;
  feed: PausedFeed;
  /** The slots the panel's body has room for, from `useLedgerSlots`. */
  slots: number;
  /** The ref `useLedgerSlots` returned, for the panel's body. */
  bodyRef: RefObject<HTMLDivElement | null>;
  /** The current time in milliseconds. */
  now: number;
  budget: Budget;
  /** Page ids of the articles edited a moment ago, whose rows are drawn highlighted. */
  freshPageIds: Set<number>;
  /** Called with a row's page id while the row is hovered or focused, and with null when it is not. */
  onHighlight: (pageId: number | null) => void;
}

/**
 * The live edit feed as a panel: a title with the feed's state, a pause button, the table of edits
 * and a footer line for edits the table could not show.
 * It also tells screen readers when the feed's state changes.
 */
export function LedgerPanel({
  live,
  feed,
  slots,
  bodyRef,
  now,
  budget,
  freshPageIds,
  onHighlight,
}: LedgerPanelProps) {
  const { paused, pausedSince, resumedAt } = feed;
  const editsUnavailable = feedIsDown(live.streamState);
  const disconnectedSince = live.lastEventAt ?? live.downSince;

  const announced = useRef<string | null>(null);
  useEffect(() => {
    const state = announcedFeedState({
      rateLimited: live.rateLimited,
      streamState: live.streamState,
      paused,
    });
    if (announced.current === state) {
      return;
    }
    announced.current = state;
    announceLive(formatLiveEditsStatus(state, disconnectedSince));
  }, [live.streamState, live.rateLimited, paused, disconnectedSince]);

  const status = ledgerStatus({
    paused,
    pausedSince,
    rateLimited: live.rateLimited,
    streamState: live.streamState,
    streamError: live.streamError,
    lastEventAt: live.lastEventAt,
    downSince: live.downSince,
    rowCount: live.rows.length,
    now,
  });
  const count = status.kind === "count" ? status.text : null;
  const notice = status.kind === "notice" ? status.text : null;
  const { shownRows, moreCount, markerIndex } = ledgerWindow({
    rows: live.rows,
    editsSeenSincePageLoad: live.editsSeenSincePageLoad,
    slots,
    hasNotice: notice != null,
  });

  return (
    <div
      data-ledger-panel=""
      className="relative mt-6 h-[328px] lg:h-auto lg:min-h-[220px] lg:flex-1"
    >
      <div className="absolute inset-0 flex flex-col">
        <div className="flex min-h-(--control-h) shrink-0 items-center justify-between gap-x-2">
          <SectionTitle
            count={
              count != null ? (
                <span data-ledger-status="" title={count}>
                  {count}
                </span>
              ) : undefined
            }
          >
            Edits as they land, times UTC
          </SectionTitle>
          <Pause
            paused={paused}
            onToggle={feed.toggle}
            disabled={editsUnavailable || live.rateLimited}
            title={
              live.rateLimited
                ? "The server asked for a pause. Edits resume shortly."
                : live.missedWhilePaused > 0
                  ? `${pluralize(live.missedWhilePaused, "edit")} arrived while paused`
                  : undefined
            }
          />
        </div>
        <div ref={bodyRef} className="mt-1 min-h-0 flex-1 overflow-hidden">
          {live.rateLimited && live.rows.length === 0 ? (
            <p
              data-ledger-status=""
              title={notice ?? undefined}
              className="h-6 truncate text-13 text-ink-3"
            >
              {notice}
            </p>
          ) : (
            <Ledger
              slots={slots}
              notice={notice ?? undefined}
              moreCount={moreCount}
              markerIndex={markerIndex}
              earlierLabel="earlier edits below"
              markerLabel={ledgerMarkerLabel({
                editsUnavailable,
                disconnectedSince,
                paused,
                pausedSince,
                resumedAt,
                loadTime: live.loadTime,
              })}
              rows={shownRows.map((row) => {
                const pageId = row.pageId;
                return {
                  ts: row.ts,
                  subject: row.title,
                  slug: row.slug ?? undefined,
                  budget,
                  byteDelta: row.byteDelta,
                  userKind: row.userKind,
                  runCount: row.runCount,
                  fresh: pageId != null && freshPageIds.has(pageId),
                  onMouseEnter: pageId != null ? () => onHighlight(pageId) : undefined,
                  onMouseLeave: pageId != null ? () => onHighlight(null) : undefined,
                  onFocus: pageId != null ? () => onHighlight(pageId) : undefined,
                  onBlur: pageId != null ? () => onHighlight(null) : undefined,
                };
              })}
            />
          )}
        </div>
        <p data-ledger-footer="" className="h-6 shrink-0 pt-1 text-12 text-ink-3">
          {live.overflowCount > 0
            ? `+${formatNumber(live.overflowCount)} more since the last update`
            : null}
        </p>
      </div>
    </div>
  );
}
