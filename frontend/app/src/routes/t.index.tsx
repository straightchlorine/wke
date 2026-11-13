import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { searchTopics } from "../api/generated";
import { DOSSIERS_LIST_LIMIT, dossiersListQueryOptions } from "../api/queries";
import type { DossierListItem } from "../api/generated";
import { isTypingTarget } from "../lib/typingTarget";
import { Record } from "../components/Record";
import { InfoDot } from "../components/InfoDot";
import { SectionTitle } from "../components/SectionTitle";
import { Segmented, type SegmentedOption } from "../components/Segmented";
import { Button, buttonClasses } from "../components/Button";
import { ErrorPanel } from "../components/ErrorPanel";
import { DossierTable } from "../components/DossierTable";
import { SearchCombobox } from "../components/SearchCombobox";
import { FreshnessChip } from "../components/Chip";
import { slugify } from "../lib/slug";
import { budgetAlias } from "../lib/budget";
import { readStoredBudget } from "../lib/hooks/useBudget";
import { useSeo } from "../lib/seo";
import { announceLive } from "../lib/liveRegion";

const FRESHNESS_HELP =
  "Up to date: same revision as Wikipedia now. Out of date: edited on Wikipedia since built. Not checked: no edit data since built. Not checked rows show only under All or Not checked.";

type Freshness = "all" | "current" | "stale" | "not_checked";

const FRESHNESS_VALUES: Freshness[] = ["all", "current", "stale", "not_checked"];

interface DossiersSearch {
  q?: string;
  freshness?: Freshness;
}

function isFreshness(value: unknown): value is Freshness {
  return typeof value === "string" && (FRESHNESS_VALUES as string[]).includes(value);
}

export const Route = createFileRoute("/t/")({
  validateSearch: (search: Record<string, unknown>): DossiersSearch => {
    // The router parses an all-digit value into a number.
    const raw = search["q"];
    const q = typeof raw === "number" ? String(raw) : raw;
    return {
      q: typeof q === "string" && q !== "" ? q : undefined,
      freshness: isFreshness(search["freshness"]) ? search["freshness"] : undefined,
    };
  },
  component: Dossiers,
});

/** The shortest shared prefix that makes a title a suggestion: below it a match is coincidence, as "bletchly" and "Backrooms" share only "b". */
const DID_YOU_MEAN_MIN_COMMON = 2;

// Enough placeholder rows to fill a desktop screen. With fewer, the footer would jump when the real
// rows replace them.
const SKELETON_ROWS = 15;

function bySortDate(a: DossierListItem, b: DossierListItem): number {
  return new Date(b.built_at).getTime() - new Date(a.built_at).getTime();
}

function commonPrefixLength(query: string, title: string): number {
  const q = query.toLowerCase();
  const t = title.toLowerCase();
  let common = 0;
  while (common < q.length && common < t.length && q[common] === t[common]) {
    common++;
  }
  return common;
}

function Dossiers() {
  useSeo({
    title: "Dossiers",
    description:
      "Every dossier built in the last seven days, each pinned to the Wikipedia revision it was built from.",
    path: "/t/",
  });
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const titleFilter = search.q ?? "";
  const freshness = search.freshness ?? "all";
  const setTitleFilter = useCallback(
    (q: string) => {
      void navigate({
        search: (prev) => ({ ...prev, q: q === "" ? undefined : q }),
        replace: true,
        resetScroll: false,
        hashScrollIntoView: false,
      });
    },
    [navigate],
  );
  const setFreshness = useCallback(
    (next: Freshness) => {
      void navigate({
        search: (prev) => ({ ...prev, freshness: next === "all" ? undefined : next }),
        replace: true,
        resetScroll: false,
        hashScrollIntoView: false,
      });
    },
    [navigate],
  );
  const inputRef = useRef<HTMLInputElement>(null);
  // How many title suggestions are listed under the filter, and where the
  // list goes in flow: below the narrowed table, or in the empty panel.
  const [suggestionCount, setSuggestionCount] = useState(0);
  const [listSlot, setListSlot] = useState<HTMLElement | null>(null);

  // Back from a dossier mounts this page again with the list still in the query cache, so no
  // skeleton shifts the page under a restored scroll position.
  const dossiersQuery = useQuery(dossiersListQueryOptions);

  // "/" focuses the filter unless the key was typed into a field.
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "/" && !isTypingTarget(event.target)) {
        event.preventDefault();
        inputRef.current?.focus();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  const sorted = useMemo(
    () => (dossiersQuery.data?.items ?? []).toSorted(bySortDate),
    [dossiersQuery.data],
  );

  const hasMore = dossiersQuery.data?.next_cursor != null;

  const counts = useMemo(() => {
    const current = sorted.filter((item) => item.freshness_state === "fresh").length;
    const stale = sorted.filter((item) => item.freshness_state === "stale").length;
    const notChecked = sorted.filter((item) => item.freshness_state === "unknown").length;
    return { total: sorted.length, current, stale, notChecked };
  }, [sorted]);

  const didYouMean = useMemo(() => {
    const q = titleFilter.trim();
    if (q === "") {
      return [];
    }
    return sorted
      .map((item) => ({ item, common: commonPrefixLength(q, item.title) }))
      .filter((entry) => entry.common >= DID_YOU_MEAN_MIN_COMMON)
      .toSorted((a, b) => b.common - a.common)
      .slice(0, 3)
      .map((entry) => entry.item);
  }, [sorted, titleFilter]);

  const filtered = useMemo(() => {
    const q = titleFilter.trim().toLowerCase();
    return sorted.filter((item) => {
      const matchesTitle = q === "" || item.title.toLowerCase().includes(q);
      const matchesFreshness =
        freshness === "all" ||
        (freshness === "current"
          ? item.freshness_state === "fresh"
          : freshness === "stale"
            ? item.freshness_state === "stale"
            : item.freshness_state === "unknown");
      return matchesTitle && matchesFreshness;
    });
  }, [sorted, titleFilter, freshness]);

  const clearFilters = useCallback(() => {
    void navigate({ search: {}, replace: true, resetScroll: false, hashScrollIntoView: false });
    inputRef.current?.focus();
  }, [navigate]);

  // A failed list says "unknown": zero would claim there are no dossiers.
  const count = (n: number) => (dossiersQuery.data ? n : dossiersQuery.isError ? "unknown" : "...");
  const freshnessOptions: SegmentedOption<Freshness>[] = [
    { value: "all", label: `All ${hasMore ? `${DOSSIERS_LIST_LIMIT}+` : count(counts.total)}` },
    { value: "current", label: `Up to date ${count(counts.current)}` },
    { value: "stale", label: `Out of date ${count(counts.stale)}` },
    { value: "not_checked", label: `Not checked ${count(counts.notChecked)}` },
  ];

  const filtersActive = titleFilter.trim() !== "" || freshness !== "all";
  const scopeText = filtersActive
    ? `${filtered.length} of ${hasMore ? `${DOSSIERS_LIST_LIMIT}+` : counts.total}`
    : hasMore
      ? `Newest ${DOSSIERS_LIST_LIMIT} shown, newest build first, times UTC.`
      : "Newest build first, times UTC.";
  const trimmedQuery = titleFilter.trim();

  // Only asked when the filter matches nothing: the API's spelling
  // suggestion beats the local prefix guess, which stays as the fallback.
  const suggestionQuery = useQuery({
    queryKey: ["search-did-you-mean", trimmedQuery],
    queryFn: async () => {
      const result = await searchTopics({ query: { q: trimmedQuery, limit: 1 } });
      return result.data?.did_you_mean?.trim() || null;
    },
    enabled: filtered.length === 0 && trimmedQuery.length >= DID_YOU_MEAN_MIN_COMMON,
    retry: false,
    staleTime: 60_000,
  });
  const apiSuggestion = suggestionQuery.data ?? null;

  useEffect(() => {
    if (!dossiersQuery.data || !filtersActive) {
      return;
    }
    // One message for both counts: the live region holds a single text, so
    // a second announcement would overwrite the first.
    const suggestions =
      suggestionCount > 0
        ? `, ${suggestionCount} suggestion${suggestionCount === 1 ? "" : "s"}`
        : "";
    announceLive(`${filtered.length} of ${counts.total} dossiers match${suggestions}`);
  }, [dossiersQuery.data, filtersActive, filtered.length, counts.total, suggestionCount]);

  const openTitle = useCallback(
    (title: string) => {
      const trimmed = title.trim();
      if (trimmed === "") {
        return;
      }
      void navigate({
        to: "/t/$slug",
        params: { slug: slugify(trimmed) },
        search: { budget: readStoredBudget() },
      });
    },
    [navigate],
  );

  return (
    <div className="w-full py-8">
      <div className="border-b-(length:--hairline) border-rule-strong pb-6">
        <div>
          <h1 tabIndex={-1} className="font-serif text-36 text-ink lg:text-44">
            Dossiers
          </h1>
          <p className="mt-3 max-w-(--container-prose) font-serif text-16 text-ink-2 lg:text-18 [@media(pointer:coarse)]:max-lg:leading-6">
            Every dossier built in the last seven days, each pinned to the Wikipedia revision it was
            built from. Open one to read it, or fetch it as{" "}
            <Link
              to="/machines"
              className="hit-coarse whitespace-nowrap text-accent underline decoration-rule-strong decoration-1 underline-offset-[3px] hover:decoration-ink"
            >
              Markdown, JSON or an MCP tool
            </Link>
            .
          </p>
        </div>
      </div>

      <div className="py-6">
        <div className="mb-4 flex flex-wrap items-center gap-4">
          <label htmlFor="dossier-filter" className="sr-only">
            Filter dossiers by title
          </label>
          <span className="relative w-full flex-1 md:flex-[0_1_420px]">
            <SearchCombobox
              ref={inputRef}
              id="dossier-filter"
              ariaLabel="Filter dossiers by title"
              placeholder="Filter by title"
              compact
              value={titleFilter}
              disabled={!dossiersQuery.data}
              onChange={setTitleFilter}
              onPick={openTitle}
              onEscape={() => setTitleFilter("")}
              onOptionCount={setSuggestionCount}
              listContainer={suggestionCount > 0 ? listSlot : null}
              trailing={
                titleFilter !== "" ? (
                  <button
                    type="button"
                    onClick={() => {
                      setTitleFilter("");
                      inputRef.current?.focus();
                    }}
                    aria-label="Clear search"
                    className="absolute inset-y-0 right-0 flex w-(--control-h) items-center justify-center text-ink-3 before:absolute before:left-1/2 before:top-1/2 before:size-11 before:-translate-1/2 before:content-[''] hover:text-ink"
                  >
                    <X size={16} strokeWidth={1.6} aria-hidden="true" />
                  </button>
                ) : null
              }
            />
          </span>
          {/* Below md the segmented control fills the width of the search box, so the info dot
              would wrap onto its own line. There it moves up into a "Freshness" label line. */}
          <span className="flex w-full flex-wrap items-center gap-y-1 md:w-auto md:flex-nowrap">
            <span className="block w-full text-13 text-ink-2 md:hidden pointer-coarse:flex pointer-coarse:min-h-11 pointer-coarse:items-center">
              Freshness
              <InfoDot label="About the Freshness filter" text={FRESHNESS_HELP} />
            </span>
            <Segmented
              ariaLabel="Freshness"
              name="freshness"
              options={freshnessOptions}
              value={freshness}
              onChange={setFreshness}
              stretch
              className="w-full md:w-auto"
            />
            <span className="max-md:hidden">
              <InfoDot label="About the Freshness filter" text={FRESHNESS_HELP} />
            </span>
          </span>
          <span className="text-12 text-ink-3 md:ml-auto">
            {dossiersQuery.data ? scopeText : ""}
          </span>
        </div>

        {dossiersQuery.isError ? (
          <ErrorPanel
            title="Could not load dossiers."
            detail="The dossier list did not load."
            retry={
              <Button
                variant="secondary"
                onClick={() => {
                  void dossiersQuery.refetch();
                }}
              >
                Retry
              </Button>
            }
          />
        ) : !dossiersQuery.data ? (
          <DossierTable items={[]} loadingRows={SKELETON_ROWS} />
        ) : filtered.length > 0 ? (
          <>
            <DossierTable items={filtered} />
            {suggestionCount > 0 ? (
              <div className="mt-8">
                <SectionTitle>On Wikipedia</SectionTitle>
                <div ref={setListSlot} />
              </div>
            ) : null}
          </>
        ) : (
          <>
            <DossierTable items={[]} />
            <div className="border-b-(length:--hairline) border-rule py-6">
              <h2 className="font-serif text-22 text-ink">
                {trimmedQuery
                  ? `No built dossier matches "${trimmedQuery}".`
                  : "No built dossier matches this filter."}
              </h2>
              <p className="mt-2 max-w-(--container-prose) text-ink-2">
                The filter only searches{" "}
                {hasMore
                  ? `the newest ${DOSSIERS_LIST_LIMIT} dossiers already built`
                  : `the ${counts.total} dossiers already built`}
                .
              </p>
              {apiSuggestion ? (
                <p className="mt-4 text-14 text-ink-2">
                  Did you mean{" "}
                  <Link
                    to="/t/$slug"
                    params={{ slug: slugify(apiSuggestion) }}
                    search={{ budget: readStoredBudget() }}
                    className="text-accent underline decoration-rule-strong decoration-1 underline-offset-[3px] hover:decoration-ink"
                  >
                    {apiSuggestion}
                  </Link>
                  ?
                </p>
              ) : didYouMean.length > 0 ? (
                <Record
                  label="Closest built titles"
                  className="mt-4 max-w-(--container-prose)"
                  rows={didYouMean.map((item) => ({
                    label: (
                      <Link
                        to="/t/$slug"
                        params={{ slug: slugify(item.title) }}
                        search={{ budget: item.largest_budget_filled }}
                        className="text-accent underline decoration-rule-strong decoration-1 underline-offset-[3px] hover:decoration-ink"
                      >
                        {item.title}
                      </Link>
                    ),
                    value: (
                      <FreshnessChip
                        state={item.freshness_state}
                        editsSincePin={item.edits_since_pin}
                      />
                    ),
                    sub: `Fits in ${budgetAlias(item.largest_budget_filled)}`,
                    size: "normal" as const,
                  }))}
                />
              ) : null}
              {suggestionCount > 0 ? (
                <div className="mt-6">
                  <SectionTitle level={3}>On Wikipedia</SectionTitle>
                  <div ref={setListSlot} />
                </div>
              ) : null}
              <div className="mt-4 flex flex-wrap gap-3">
                {trimmedQuery && suggestionCount === 0 ? (
                  <Link
                    to="/t/$slug"
                    params={{ slug: slugify(trimmedQuery) }}
                    search={{ budget: readStoredBudget() }}
                    className={buttonClasses("primary")}
                  >
                    {`Build a dossier for "${trimmedQuery}"`}
                  </Link>
                ) : null}
                {/* Keeps the filter focused: a blur would close the suggestion rows and shift this button away mid-click. */}
                <Button
                  variant="secondary"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={clearFilters}
                >
                  Clear filter
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
