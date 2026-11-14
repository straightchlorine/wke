import { useMemo, useRef, useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { rootNavState } from "./__root";
import { getStatus } from "../api/generated";
import { dossiersListQueryOptions, unwrap } from "../api/queries";
import { Colophon } from "../components/Colophon";
import { DossierArticle } from "../components/DossierArticle";
import { DossierBuilding } from "../components/DossierBuilding";
import { DossierContents } from "../components/DossierContents";
import { DossierDataRecords } from "../components/DossierDataRecords";
import { DossierHead } from "../components/DossierHead";
import { DossierOpening } from "../components/DossierOpening";
import { DossierProblem } from "../components/DossierProblem";
import { DossierToolbar } from "../components/DossierToolbar";
import { Hud } from "../components/Hud";
import { MarginNoteRail } from "../components/MarginNote";
import { RelatedPlate } from "../components/RelatedPlate";
import { Ruler } from "../components/Ruler";
import { SectionChips } from "../components/SectionChips";
import { SectionTitle } from "../components/SectionTitle";
import { sectionNoteRows } from "../components/sectionNoteRows";
import { SourceRecord } from "../components/SourceRecord";
import { Toast } from "../components/Toast";
import { BUDGET_OPTIONS, budgetToSegmentValue, parseBudget, type Budget } from "../lib/budget";
import { rulerEntries, sectionRows, sectionTitle, sectionTotals } from "../lib/dossierSections";
import { errorTitle } from "../lib/errors";
import { leadSentence } from "../lib/lede";
import { relatedGraphNodes, storedStateOf } from "../lib/relatedGraph";
import { splitNoProse, withoutNoProse } from "../lib/proseSections";
import { dossierDescription, dossierJsonLd, useSeo } from "../lib/seo";
import { sectionDepth } from "../lib/sectionDepth";
import { slugPath, unslugify } from "../lib/slug";
import { freshnessView, seedPin } from "../lib/sourceRecord";
import { useBudget } from "../lib/hooks/useBudget";
import { useBudgetScroll } from "../lib/hooks/useBudgetScroll";
import { useCurrentSection } from "../lib/hooks/useCurrentSection";
import { useDossier } from "../lib/hooks/useDossier";
import { useDossierExports } from "../lib/hooks/useDossierExports";
import { useFoldedReading } from "../lib/hooks/useFoldedReading";
import { useHeadingRefocus } from "../lib/hooks/useHeadingRefocus";
import { useSectionMeasures } from "../lib/hooks/useSectionMeasures";
import { useStickyOffset } from "../lib/hooks/useStickyOffset";

interface DossierSearch {
  budget: Budget;
}

export const Route = createFileRoute("/t/$slug")({
  validateSearch: (search: Record<string, unknown>): DossierSearch => ({
    budget: parseBudget(search["budget"]),
  }),
  component: Dossier,
});

/** How long the status and the list of stored dossiers stay fresh. */
const SIDE_QUERY_STALE_MS = 60_000;

function Dossier() {
  const { slug } = Route.useParams();
  const search = Route.useSearch();
  const navigate = useNavigate();
  // A budget pick rewrites only the search param. The router must not re-run the hash scroll that a
  // Contents click or chip tap left behind, which would snap the page back to that section, nor
  // reset the scroll.
  const writeBudgetParam = (next: Budget) => {
    void navigate({
      to: ".",
      search: (prev) => ({ ...prev, budget: next }),
      hash: true,
      replace: true,
      resetScroll: false,
      hashScrollIntoView: false,
    });
  };
  const [budget, setBudgetState] = useBudget(search.budget, writeBudgetParam);
  const title = useMemo(() => unslugify(slug), [slug]);

  const {
    phase,
    problem,
    didYouMean,
    suggestion,
    suggestionsPaused,
    job,
    cancelBuild,
    retry,
    pageId,
    dossier: fullDossier,
    dossierLoading,
    dossierError,
    refetchDossier,
    rateLimitNote,
  } = useDossier(title, budget);
  // The page shows prose. A section the build found no prose in is left out of the article, the
  // chips and the Contents rail, and the source record says so. The JSON download and the API's
  // Markdown are the API's own.
  const dossier = useMemo(
    () => (fullDossier ? withoutNoProse(fullDossier) : fullDossier),
    [fullDossier],
  );
  const noProseSections = useMemo(
    () => (fullDossier ? splitNoProse(fullDossier.sections).leftOut : []),
    [fullDossier],
  );
  const rows = useMemo(() => (dossier ? sectionRows(dossier) : []), [dossier]);

  // Freshness comes from a sample of Wikipedia's edits. While that sample is disconnected, "up to
  // date" would be a guess, so the chip says so.
  const statusQuery = useQuery({
    queryKey: ["status"],
    queryFn: async () => unwrap(await getStatus()),
    staleTime: SIDE_QUERY_STALE_MS,
    retry: false,
  });
  const editFeedDown = statusQuery.data?.watcher_connected === false;

  // Which related articles already have a dossier, for the related-articles graph.
  const storedQuery = useQuery({
    ...dossiersListQueryOptions,
    staleTime: SIDE_QUERY_STALE_MS,
  });

  const [toast, setToast] = useState<string | null>(null);
  const setBudget = useBudgetScroll(slug, budget, dossier, setBudgetState);
  const currentSectionId = useCurrentSection(dossier);
  useStickyOffset(dossier);
  const exports = useDossierExports(dossier, fullDossier, slug, budget, setToast);
  const { texts: foldedTexts, toggle: toggleFolded } = useFoldedReading(pageId, setToast);

  const articleRef = useRef<HTMLElement>(null);
  const railRef = useRef<HTMLDivElement>(null);
  const measures = useSectionMeasures(dossier, rows, articleRef, railRef);

  const notFound = phase === "error" && problem?.code === "not_found";
  const seoPath = slugPath(dossier ? dossier.topic.title : slug);
  const seoDescription = dossier ? dossierDescription(dossier) : undefined;
  useSeo({
    title: dossier ? dossier.topic.title : notFound ? errorTitle(problem) : title,
    description: seoDescription,
    path: seoPath,
    robots: dossier ? "index,follow" : "noindex,follow",
    type: dossier ? "article" : "website",
    modified: dossier ? seedPin(dossier)?.rev_timestamp : undefined,
    jsonLd:
      dossier && seoDescription
        ? dossierJsonLd(dossier, seoPath, dossier.topic.title, seoDescription)
        : undefined,
  });

  const [arrivedViaNavigation] = useState(() => !rootNavState.isInitialLoad);
  // The component is not remounted when the slug changes, so a move to another dossier is a navigation
  // too, and stays one when the reader returns to the first dossier.
  const [firstSlug] = useState(slug);
  const [leftFirstSlug, setLeftFirstSlug] = useState(false);
  if (slug !== firstSlug && !leftFirstSlug) {
    setLeftFirstSlug(true);
  }
  useHeadingRefocus(
    phase === "error" ? "error" : dossier ? "loaded" : "building",
    arrivedViaNavigation || leftFirstSlug,
  );

  if (phase === "error" && problem) {
    return (
      <DossierProblem
        problem={problem}
        title={title}
        budget={budget}
        didYouMean={didYouMean}
        suggestion={suggestion}
        suggestionsPaused={suggestionsPaused}
        onRetry={() => retry()}
      />
    );
  }

  // Until the API has answered with a job or a not-ready state, the page is only opening.
  if (!dossier && !job && (phase === "resolving" || dossierLoading)) {
    return <DossierOpening title={title} />;
  }

  if (!dossier) {
    return (
      <DossierBuilding
        title={title}
        job={job}
        loading={dossierLoading}
        loadFailed={Boolean(dossierError)}
        onCancel={() => {
          cancelBuild();
          void navigate({ to: "/" });
        }}
        onRetryLoad={refetchDossier}
      />
    );
  }

  const totals = sectionTotals(rows);
  // Every section of the article, with the ones the page leaves out for having no prose counted in,
  // so "shown of total" and "Left out" add up.
  const sectionCount = dossier.sections.length + noProseSections.length;
  const freshness = freshnessView(dossier.freshness, editFeedDown);
  const graphNodes = relatedGraphNodes(dossier, storedStateOf(storedQuery.data));

  return (
    <div className="w-full py-8 pb-20">
      <Toast message={toast} onDismiss={() => setToast(null)} aboveHud />

      <section className="border-b-(length:--hairline) border-rule-strong pb-6">
        <DossierHead
          title={dossier.topic.title}
          lede={dossier.topic.description || leadSentence(dossier) || undefined}
          asideColumns="lg:grid-cols-[1fr_360px] min-[1200px]:grid-cols-[1fr_640px] min-[1440px]:grid-cols-[1fr_760px]"
          aside={
            <SourceRecord
              dossier={dossier}
              rows={rows}
              noProseSections={noProseSections}
              budget={budget}
              freshness={freshness}
            />
          }
        >
          {rateLimitNote ? (
            <p className="mt-3 max-w-(--container-prose) border-(length:--hairline) border-rule-strong bg-sunken px-3 py-2 text-13 text-ink-2">
              {rateLimitNote}
            </p>
          ) : null}
        </DossierHead>
      </section>

      <DossierToolbar
        dossier={dossier}
        budget={budget}
        onBudgetChange={setBudget}
        totals={totals}
        sectionCount={sectionCount}
        exports={exports}
        onCopy={setToast}
      />

      <SectionChips
        items={rows.map(({ section, index, id, pack }) => ({
          id,
          label: `${index + 1} ${section.label}`,
          title: sectionTitle(section),
          held: pack.state === "folded",
          depth: sectionDepth(section),
        }))}
        currentId={currentSectionId}
        className="mt-2 max-[1340px]:flex min-[1340px]:hidden"
      />

      <div className="mt-6 grid grid-cols-1 gap-8 min-[600px]:grid-cols-[48px_minmax(520px,660px)] min-[900px]:grid-cols-[48px_minmax(480px,660px)_minmax(280px,1fr)] min-[1340px]:grid-cols-[220px_48px_minmax(480px,660px)_minmax(360px,1fr)]">
        <DossierContents
          dossier={dossier}
          rows={rows}
          currentId={currentSectionId}
          budget={budget}
          leftOutCount={totals.leftOut}
        />

        <div className="max-[599px]:hidden">
          <Ruler
            total={dossier.budget.requested}
            filled={dossier.budget.used_est_tokens}
            tickEvery={200}
            labelEvery={1000}
            sectionOffsets={rulerEntries(
              rows,
              dossier.budget.used_est_tokens,
              measures.tickFractions,
            )}
            breakpoints={measures.breakpoints}
            className="h-full"
          />
        </div>

        <DossierArticle
          ref={articleRef}
          dossier={dossier}
          rows={rows}
          budget={budget}
          jobId={job?.id}
          foldedTexts={foldedTexts}
          onShowAtBudget={setBudget}
          onReadHere={(section) => void toggleFolded(section)}
        />

        <aside className="min-w-0 max-[899px]:col-span-full max-[899px]:mt-8">
          <RelatedPlate dossier={dossier} nodes={graphNodes} budget={budget} />

          <DossierDataRecords dossier={dossier} budget={budget} onCopy={setToast} />

          <SectionTitle
            className="mt-6 max-[899px]:hidden"
            count={`${dossier.sections.length} sections`}
          >
            Section notes
          </SectionTitle>
          {/*
            The rail sets no height of its own unless the stacked notes outrun the article. This
            column sits in the same grid row as the article, so a taller aside would stretch the
            article and feed back into the measured bottom. The stack height depends only on the
            notes, so that feedback settles in one pass.
          */}
          <MarginNoteRail
            ref={railRef}
            className="mt-2 max-[899px]:hidden"
            bottom={measures.railBottomPx}
            notes={rows.map(({ section, index, id, pack }) => ({
              id: section.id,
              sectionLabel: `${index + 1} ${section.label}`,
              rows: sectionNoteRows(dossier.build.analysis, section, pack, index),
              top: measures.offsetsPx.get(id) ?? 0,
            }))}
          />
        </aside>
      </div>

      <Colophon article={{ url: dossier.links.wikipedia, label: dossier.topic.title }} />

      <Hud
        className="min-[600px]:hidden"
        budgetOptions={BUDGET_OPTIONS}
        budgetValue={budgetToSegmentValue(budget)}
        onBudgetChange={(value) => setBudget(parseBudget(value))}
        usedTokens={dossier.budget.used_est_tokens}
        getText={exports.fetchAsContext}
        message={exports.copyMessage}
        fetchFailedMessage="Copy failed. Try Download instead"
        onCopy={setToast}
      />
    </div>
  );
}
