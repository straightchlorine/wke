import { useRef, useState } from "react";
import type { DossierListItem, TrendingSnapshot, TrendingTopic } from "../api/generated";
import { budgetAlias, FITS_IN_HELP, type Budget } from "../lib/budget";
import { formatRefresh, mostReadStaleNote, pluralize } from "../lib/format";
import { slugify } from "../lib/slug";
import { isBuilt, viewsColumnCh } from "../lib/todaysIndex";
import { Button } from "./Button";
import { Chip, DossierStateChip } from "./Chip";
import { Entry } from "./Entry";
import { ErrorPanel } from "./ErrorPanel";
import { InfoDot } from "./InfoDot";

/** How many topics show before "Show all". */
const INDEX_PAGE_SIZE = 20;

// The list fills each column top to bottom before starting the next. PAGE_ROWS holds one page of
// topics at each breakpoint, and ALL_ROWS doubles the rows for "Show all".
const PAGE_ROWS =
  "sm:grid-flow-col sm:[grid-template-rows:repeat(10,48px)] lg:[grid-template-rows:repeat(7,48px)] xl:[grid-template-rows:repeat(5,48px)]";
const ALL_ROWS =
  "sm:grid-flow-col sm:[grid-template-rows:repeat(20,48px)] lg:[grid-template-rows:repeat(14,48px)] xl:[grid-template-rows:repeat(10,48px)]";
const COLUMNS = "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4";

function trendingSourceLabel(source: TrendingSnapshot["source"]): string {
  return source === "wikifeeds_mostread"
    ? "Wikimedia featured feed (most read)"
    : "Wikimedia Pageviews API, top articles";
}

export interface TodaysIndexProps {
  trending: TrendingSnapshot | undefined;
  /** The snapshot's topics, most read first. */
  topics: TrendingTopic[];
  isLoading: boolean;
  isError: boolean;
  /** The stored dossiers by page id; empty until the list has loaded. */
  dossierByPageId: Map<number, DossierListItem>;
  budget: Budget;
  /** True while the edit feed is disconnected; the rows then say "no edit data". */
  editsUnavailable: boolean;
  /** Page ids of the articles edited a moment ago, whose titles are drawn highlighted. */
  freshPageIds: Set<number>;
  /** Says when the snapshot is from, for the heading. */
  mostReadOn: string;
  /** The current time in milliseconds. */
  now: number;
  /** Called with a row's page id while the row is hovered or focused, and with null when it is not. */
  onHighlight: (pageId: number | null) => void;
}

/** The most-read list of the day: a heading, a note on where the data is from, and the topics in columns with their dossier state and views. */
export function TodaysIndex({
  trending,
  topics,
  isLoading,
  isError,
  dossierByPageId,
  budget,
  editsUnavailable,
  freshPageIds,
  mostReadOn,
  now,
  onHighlight,
}: TodaysIndexProps) {
  const [showAll, setShowAll] = useState(false);
  const linkRefs = useRef<Array<HTMLAnchorElement | null>>([]);

  const visibleTopics = showAll ? topics : topics.slice(0, INDEX_PAGE_SIZE);
  // The chip column is as narrow as the widest budget badge ("32k"); a state word ("Building") widens it.
  const chipWide = topics.some((topic) => !isBuilt(topic) && topic.dossier_state !== "none");
  const viewsCh = viewsColumnCh(topics);
  const builtCount = topics.filter(isBuilt).length;
  const refreshText = trending ? formatRefresh(trending.next_refresh, new Date(now)) : "";
  const staleNote = trending ? mostReadStaleNote(trending.date, new Date(now)) : null;

  function handleShowAll() {
    setShowAll(true);
    requestAnimationFrame(() => {
      linkRefs.current[INDEX_PAGE_SIZE]?.focus();
    });
  }

  function topicChip(topic: TrendingTopic) {
    if (!isBuilt(topic)) {
      return <DossierStateChip state={topic.dossier_state} />;
    }
    const item = dossierByPageId.get(topic.page_id);
    // A built chip needs a budget, which is unknown until the stored list loads, so show no chip until then.
    return item ? (
      <Chip variant="built" className="w-10 justify-center">
        <span className="sr-only">Fits in </span>
        {budgetAlias(item.largest_budget_filled)}
      </Chip>
    ) : null;
  }

  return (
    <div className="mt-12 border-t-(length:--hairline) border-ink pt-6">
      <h2 className="font-serif text-32 text-ink">
        {trending ? `Most read ${mostReadOn}` : "Most-read articles"}
      </h2>
      {trending ? (
        <p className="mt-1 max-w-(--container-prose) text-13 text-ink-2">
          en.wikipedia, UTC day, from {trendingSourceLabel(trending.source)}. {builtCount} of{" "}
          {topics.length} built, {topics.length - builtCount} queued.
          {refreshText ? ` ${refreshText}.` : ""} Ranks skip non-article pages.
          {staleNote ? ` Note: ${staleNote}.` : null}
          {isError ? " Could not reach the server; showing the list loaded earlier." : null}
        </p>
      ) : null}

      {isError && !trending ? (
        <ErrorPanel
          title="Today's index is unavailable"
          detail="The most-read list could not be loaded."
          className="mt-4"
        />
      ) : isLoading ? (
        <ol
          aria-hidden="true"
          className={`mt-4 grid ${COLUMNS} gap-x-8 border-t-(length:--hairline) border-ink ${PAGE_ROWS}`}
        >
          {Array.from({ length: INDEX_PAGE_SIZE }, (_, i) => (
            <li
              key={i}
              className="h-12 animate-pulse motion-reduce:animate-none border-b-(length:--hairline) border-rule py-1"
            >
              <div className="h-full w-full bg-sunken" />
            </li>
          ))}
        </ol>
      ) : !trending ? (
        <p className="mt-4 max-w-(--container-prose) text-13 text-ink-2">
          No index yet. The nightly job builds it at 03:00 UTC.
        </p>
      ) : (
        <>
          {/* The header repeats once per column and hides with its column. Only the first copy carries the info dot: the repeats are aria-hidden, and the dot would be squeezed to a sliver in their narrow chip cell. */}
          <div className={`mt-4 grid gap-x-8 text-12 text-ink-3 ${COLUMNS}`}>
            {[0, 1, 2, 3].map((col) => (
              <div
                key={col}
                aria-hidden={col > 0 ? true : undefined}
                className={
                  col === 1
                    ? "hidden flex-col sm:flex"
                    : col === 2
                      ? "hidden flex-col lg:flex"
                      : col === 3
                        ? "hidden flex-col xl:flex"
                        : "flex flex-col"
                }
              >
                <span className="flex items-center gap-x-2">
                  <span className="min-w-0 flex-1 truncate">Article, edits in the last hour</span>
                  <span
                    className={`flex shrink-0 items-center justify-center whitespace-nowrap ${chipWide ? "w-16" : "w-10"}`}
                  >
                    Fits in
                    {col === 0 ? (
                      <InfoDot text={FITS_IN_HELP} label="About Fits in" className="shrink-0" />
                    ) : null}
                  </span>
                  <span style={{ width: `${viewsCh}ch` }} className="shrink-0 text-right">
                    Views
                  </span>
                </span>
              </div>
            ))}
          </div>

          {/* Below the sm breakpoint the list is a single column. */}
          <ol
            className={`mt-1 grid ${COLUMNS} gap-x-8 border-t-(length:--hairline) border-ink ${showAll ? ALL_ROWS : PAGE_ROWS}`}
          >
            {visibleTopics.map((topic, index) => (
              <Entry
                key={topic.page_id}
                title={topic.title}
                slug={slugify(topic.title)}
                budget={budget}
                views={topic.views}
                fresh={freshPageIds.has(topic.page_id)}
                meta={
                  editsUnavailable ? (
                    <span>no edit data</span>
                  ) : topic.edits_last_hour != null ? (
                    <span>{pluralize(topic.edits_last_hour, "edit")}</span>
                  ) : null
                }
                chip={topicChip(topic)}
                chipWide={chipWide}
                viewsCh={viewsCh}
                onMouseEnter={() => onHighlight(topic.page_id)}
                onMouseLeave={() => onHighlight(null)}
                onFocus={() => onHighlight(topic.page_id)}
                onBlur={() => onHighlight(null)}
                linkRef={(el) => {
                  linkRefs.current[index] = el;
                }}
              />
            ))}
          </ol>
          {!showAll && topics.length > INDEX_PAGE_SIZE ? (
            <Button variant="secondary" onClick={handleShowAll} className="mt-3">
              Show all {topics.length}
            </Button>
          ) : null}
        </>
      )}
    </div>
  );
}
