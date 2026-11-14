import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  dossierQueryOptions,
  dossiersListQueryOptions,
  trendingQueryOptions,
} from "../api/queries";
import type { ApiError, DossierListItem } from "../api/generated";
import { Button } from "../components/Button";
import type { DossierState } from "../components/Chip";
import { CountdownButton } from "../components/CountdownButton";
import { IndexPlate } from "../components/IndexPlate";
import { InfoDot } from "../components/InfoDot";
import { LedgerPanel, useLedgerSlots } from "../components/LedgerPanel";
import { MachineCells } from "../components/MachineCells";
import { ProblemPanel } from "../components/ProblemPanel";
import { SearchCombobox } from "../components/SearchCombobox";
import { Segmented } from "../components/Segmented";
import { Toast } from "../components/Toast";
import { TodaysCounters } from "../components/TodaysCounters";
import { TodaysIndex } from "../components/TodaysIndex";
import type { ConceptGraphHandle } from "../components/ConceptGraph";
import {
  BUDGET_OPTIONS,
  budgetToSegmentValue,
  homeBudgetHelp,
  parseBudget,
  type Budget,
} from "../lib/budget";
import { storedDossiersCounter } from "../lib/counters";
import { errorTitle, isServerDown, toProblem } from "../lib/errors";
import { mostReadWhen } from "../lib/format";
import { useBudget } from "../lib/hooks/useBudget";
import { useBuildDossier } from "../lib/hooks/useBuildDossier";
import { useLive } from "../lib/hooks/useLive";
import { useMediaQuery } from "../lib/hooks/useMediaQuery";
import { usePausedFeed } from "../lib/hooks/usePausedFeed";
import { useReducedMotion } from "../lib/hooks/useReducedMotion";
import { colorKeyGroups, toGraphNodes } from "../lib/indexGraph";
import { editsSeenCounter, feedIsDown } from "../lib/ledgerView";
import { publicBaseUrl } from "../lib/publicBaseUrl";
import { searchButtonLabel } from "../lib/searchButton";
import { slugify } from "../lib/slug";
import { freshPageIds as findFreshPageIds, isBuilt, sortByViews } from "../lib/todaysIndex";
import { homeJsonLd, useSeo } from "../lib/seo";
import { isTypingTarget } from "../lib/typingTarget";

interface HomeSearch {
  /** Absent input falls back to the budget stored in localStorage, then to the default. */
  budget?: Budget;
  /** Prefills the search box; the target of the site's SearchAction. */
  q?: string;
}

export const Route = createFileRoute("/")({
  validateSearch: (search: Record<string, unknown>): HomeSearch => {
    // The router parses an all-digit value into a number.
    const raw = search["q"];
    const q = typeof raw === "number" ? String(raw) : raw;
    return {
      budget: search["budget"] === undefined ? undefined : parseBudget(search["budget"]),
      q: typeof q === "string" && q.trim() !== "" ? q : undefined,
    };
  },
  component: Home,
});

const TICK_MS = 5_000;

/** Returns the message and the action shown in the empty graph frame when today's index failed to load. */
function plateError(problem: ApiError, retry: () => void) {
  return {
    line: isServerDown(problem)
      ? errorTitle(problem)
      : problem.code === "rate_limited"
        ? "Too many requests"
        : "Today's index could not be loaded",
    detail: isServerDown(problem) ? problem.detail : undefined,
    action:
      problem.retry_after != null ? (
        <CountdownButton seconds={problem.retry_after} onClick={retry} />
      ) : (
        <Button variant="small" onClick={retry}>
          Retry
        </Button>
      ),
  };
}

function Home() {
  const search = Route.useSearch();
  const [budget, setBudget] = useBudget(search.budget);
  const reducedMotion = useReducedMotion();
  useSeo({
    title: "WKE: Wikipedia Knowledge Explorer",
    path: "/",
    suffix: false,
    jsonLd: homeJsonLd(),
  });

  const feed = usePausedFeed();
  const [now, setNow] = useState(() => Date.now());
  const [searchInput, setSearchInput] = useState(search.q ?? "");
  const [activeSuggestionState, setActiveSuggestionState] = useState<DossierState | null>(null);
  const { building, error: buildError, build } = useBuildDossier(budget);
  const [toast, setToast] = useState<string | null>(null);
  const [toastNonce, setToastNonce] = useState(0);

  const graphRef = useRef<ConceptGraphHandle>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const { bodyRef: ledgerBodyRef, slots: ledgerSlots } = useLedgerSlots();
  const coarsePointer = useMediaQuery("(pointer: coarse)");

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), TICK_MS);
    return () => clearInterval(t);
  }, []);

  // "/" focuses search unless the user is already typing in a field.
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "/") {
        return;
      }
      if (isTypingTarget(event.target)) {
        return;
      }
      event.preventDefault();
      searchInputRef.current?.focus();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  const trendingQuery = useQuery({
    ...trendingQueryOptions,
    placeholderData: keepPreviousData,
  });
  const dossiersQuery = useQuery(dossiersListQueryOptions);

  const trending = trendingQuery.data;
  const trendingProblem = trendingQuery.isError ? toProblem(trendingQuery.error) : null;
  const topics = useMemo(() => trending?.topics ?? [], [trending]);
  const indexTopics = useMemo(() => sortByViews(topics), [topics]);
  const nodes = useMemo(() => toGraphNodes(topics), [topics]);
  const edges = useMemo(() => trending?.edges ?? [], [trending]);
  const colorKey = useMemo(() => colorKeyGroups(nodes, edges), [nodes, edges]);
  const dossierByPageId = useMemo(() => {
    const map = new Map<number, DossierListItem>();
    for (const item of dossiersQuery.data?.items ?? []) {
      map.set(item.page_id, item);
    }
    return map;
  }, [dossiersQuery.data]);

  const highlight = useCallback((pageId: number | null) => graphRef.current?.highlight(pageId), []);
  const resolveTopic = useCallback(
    (title: string) => {
      const topic = topics.find((t) => t.title === title);
      return topic ? { pageId: topic.page_id, slug: slugify(topic.title) } : undefined;
    },
    [topics],
  );
  const onPing = useCallback((pageId: number, ring: boolean) => {
    graphRef.current?.ping(pageId, ring);
  }, []);

  const live = useLive({
    resolveTopic,
    onPing,
    paused: feed.paused,
    reducedMotion,
    maxRows: ledgerSlots - 1,
  });
  // While the edit feed is down or unreachable, an edit count of 0 is not a measurement, so every
  // per-topic edit figure gives way to "no edit data".
  const editsUnavailable = feedIsDown(live.streamState);
  const freshPageIds = useMemo(() => findFreshPageIds(live.rows, now), [live.rows, now]);

  const topTopic = useMemo(() => indexTopics.find(isBuilt), [indexTopics]);
  const topDossierQuery = useQuery(dossierQueryOptions(topTopic?.page_id, budget));

  // Every CopyButton on this page reports its message through here, so the Toast shows again, via
  // the nonce, even for the same text copied twice in a row.
  function handleCopy(message: string) {
    setToastNonce((n) => n + 1);
    setToast(message);
  }

  const edits = editsSeenCounter({
    unavailable: editsUnavailable,
    count: live.editsSeenSincePageLoad,
    loadTime: live.loadTime,
    now,
  });
  // A failed request cannot show that no dossier exists, so the page says "unknown" instead of "None built yet".
  const topUnknown = dossiersQuery.isError || trendingQuery.isError;
  const mostReadOn = trending ? mostReadWhen(trending.date, new Date(now)) : "";

  return (
    <div className="py-8">
      {/* At >= lg the graph frame spans all three rows of column 2, so both columns end at the same height.
          Below lg the items stack in source order. At >= lg the edit panel also takes the height column 1
          has left, and its slots are counted from that, so the panel never changes size as edits arrive. */}
      <div className="grid grid-cols-1 lg:grid-cols-[560fr_784fr] lg:grid-rows-[auto_auto_1fr] lg:gap-x-8">
        <div className="lg:col-start-1 lg:row-start-1">
          <h1 tabIndex={-1} className="text-balance font-serif text-36 text-ink lg:text-44">
            Cited context from Wikipedia, for people and for LLMs.
          </h1>
          <p className="mt-4 max-w-(--container-prose) font-serif text-16 text-ink-2 lg:text-18 [@media(pointer:coarse)]:max-lg:leading-6">
            WKE turns any Wikipedia article into a dossier: sections grouped by topic and cited to
            one revision, packed to a token budget, available as a page,{" "}
            <a
              href="/machines#markdown"
              className="hit-coarse text-accent underline decoration-1 underline-offset-2"
            >
              Markdown
            </a>
            ,{" "}
            <a
              href="/machines#json"
              className="hit-coarse text-accent underline decoration-1 underline-offset-2"
            >
              JSON
            </a>{" "}
            or an{" "}
            <a
              href="/machines"
              className="hit-coarse text-accent underline decoration-1 underline-offset-2"
            >
              MCP tool
            </a>
            .
          </p>
        </div>

        <div className="mt-6 lg:col-start-1 lg:row-start-2">
          <form
            className="flex h-11 gap-x-2"
            onSubmit={(event) => {
              event.preventDefault();
              void build(searchInput);
            }}
          >
            <SearchCombobox
              ref={searchInputRef}
              value={searchInput}
              onChange={setSearchInput}
              onPick={(title) => {
                setSearchInput(title);
                void build(title);
              }}
              placeholder="Build a dossier for a topic"
              ariaLabel="Build a dossier for a topic"
              onActiveStateChange={setActiveSuggestionState}
            />
            <Button type="submit" variant="primary" waiting={building} className="h-11!">
              {searchButtonLabel(activeSuggestionState)}
            </Button>
          </form>

          <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-2">
            <span className="text-13 text-ink-2 pointer-coarse:inline-flex pointer-coarse:min-h-11 pointer-coarse:items-center pointer-coarse:pr-2">
              <span id="budget-label">Token budget</span>
              <InfoDot text={homeBudgetHelp(coarsePointer)} label="About the token budget" />
            </span>
            {/* The control fills the row on a phone and stays as wide as its content, beside the label, on wider screens. */}
            <Segmented
              ariaLabel="Token budget"
              name="budget"
              options={BUDGET_OPTIONS}
              value={budgetToSegmentValue(budget)}
              onChange={(value) => setBudget(parseBudget(value))}
              numberShortcuts
              stretch
              className="max-[599px]:w-full max-[599px]:[--control-h:44px]"
            />
          </div>
          <p className="mt-1 text-12 text-ink-3">
            Text is usually ready within a minute the first time. Model summaries follow within a
            few minutes.
            <span className="whitespace-nowrap [@media(hover:none)]:hidden">
              {" "}
              Press <kbd>/</kbd> to search.
            </span>
          </p>

          {buildError ? (
            <ProblemPanel
              problem={buildError.problem}
              budget={budget}
              onRetry={() => void build(searchInput)}
              didYouMean={buildError.didYouMean}
              suggestion={buildError.suggestion}
              className="mt-3"
            />
          ) : null}
        </div>

        <IndexPlate
          trending={trending}
          nodes={nodes}
          edges={edges}
          editsUnavailable={editsUnavailable}
          mostReadOn={mostReadOn}
          graphRef={graphRef}
          budget={budget}
          isLoading={trendingQuery.isLoading}
          error={
            trendingQuery.isError && !trending && trendingProblem
              ? plateError(trendingProblem, () => void trendingQuery.refetch())
              : null
          }
          colorKey={colorKey}
        />

        <div className="mt-8 flex min-h-0 flex-col lg:col-start-1 lg:row-start-3">
          <TodaysCounters
            stored={storedDossiersCounter(dossiersQuery.data, dossiersQuery.isError)}
            builtToday={live.counters?.dossiers_built_today}
            edits={{ ...edits, unavailable: editsUnavailable }}
            top={
              topTopic
                ? {
                    topic: topTopic,
                    item: dossierByPageId.get(topTopic.page_id),
                    view: topDossierQuery.data,
                    viewFailed: topDossierQuery.isError,
                  }
                : undefined
            }
            topUnknown={topUnknown}
            budget={budget}
            onCopy={handleCopy}
          />
          <LedgerPanel
            live={live}
            feed={feed}
            slots={ledgerSlots}
            bodyRef={ledgerBodyRef}
            now={now}
            budget={budget}
            freshPageIds={freshPageIds}
            onHighlight={highlight}
          />
        </div>
      </div>

      <TodaysIndex
        trending={trending}
        topics={indexTopics}
        isLoading={trendingQuery.isLoading}
        isError={trendingQuery.isError}
        dossierByPageId={dossierByPageId}
        budget={budget}
        editsUnavailable={editsUnavailable}
        freshPageIds={freshPageIds}
        mostReadOn={mostReadOn}
        now={now}
        onHighlight={highlight}
      />

      <MachineCells
        origin={publicBaseUrl(topDossierQuery.data?.links.self)}
        pageId={topTopic?.page_id ?? null}
        budget={budget}
        onCopy={handleCopy}
      />

      <Toast message={toast} onDismiss={() => setToast(null)} nonce={toastNonce} />
    </div>
  );
}
