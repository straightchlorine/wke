import { useEffect, useEffectEvent, useReducer } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { searchTopics } from "../../api/generated";
import type { ApiError, TopicCandidate } from "../../api/generated";
import { dossierQueryOptions } from "../../api/queries";
import type { DossierView } from "../../api/dossier";
import type { Budget } from "../budget";
import { jobFailedProblem } from "../errors";
import { resolveDossier, toDidYouMean } from "./resolveDossier";
import type { DidYouMean, ResolveOutcome } from "./resolveDossier";
import { usePolledJob } from "./usePolledJob";

export type BuildPhase = "resolving" | "building" | "built" | "error";

export interface UseDossierResult {
  phase: BuildPhase;
  /** The build error, once phase is "error". */
  problem: ApiError | null;
  /** Populated when problem.code is "not_found": the top matches from search. */
  didYouMean: TopicCandidate[];
  /** The API's own spelling suggestion for a not_found title; null when it gave none. */
  suggestion: string | null;
  /** True when the title search was rate limited, so a not_found shows no suggestions for that reason. */
  suggestionsPaused: boolean;
  /** The latest polled snapshot of the build job; null until a build request returns one. */
  job: ReturnType<typeof usePolledJob>["job"];
  /** Stops polling client-side and returns to "error" with a cancelled problem. */
  cancelBuild: () => void;
  /** Re-runs the build request from scratch. */
  retry: () => void;
  /** The resolved page id, once known. */
  pageId: number | null;
  /** The dossier at the current budget, once the page id is known. */
  dossier: DossierView | undefined;
  dossierError: unknown;
  dossierLoading: boolean;
  refetchDossier: () => void;
  /**
   * Shown above the cached dossier when a request was rate limited.
   * It is set only if that dossier was already cached for this page and budget.
   */
  rateLimitNote: string | null;
}

/**
 * Returns the top title matches and the API's spelling suggestion for a title that failed to
 * resolve. Home's build form uses it because it has no search result of its own.
 */
export async function fetchDidYouMean(title: string): Promise<DidYouMean> {
  return toDidYouMean((await searchTopics({ query: { q: title } })).data);
}

const CANCELLED_PROBLEM: ApiError = {
  type: "about:blank",
  title: "Cancelled",
  status: 0,
  code: "internal",
  request_id: "",
  detail: "Build cancelled. The server may still finish it and keep the result.",
};

/** Everything the hook knows about one title. Another title starts again from `initialState`. */
interface State {
  title: string;
  phase: BuildPhase;
  problem: ApiError | null;
  didYouMean: TopicCandidate[];
  suggestion: string | null;
  suggestionsPaused: boolean;
  jobId: string | null;
  pageId: number | null;
  rateLimitNote: string | null;
  /** Counts the build requests made for this title, so bumping it re-runs the resolve effect. */
  attempt: number;
  /** True once a vanished job has been requested again, which happens only once. */
  jobRestarted: boolean;
}

type Action =
  | { type: "resolved"; title: string; outcome: ResolveOutcome }
  | { type: "retry"; title: string }
  | { type: "jobDone"; pageId: number }
  | { type: "failed"; problem: ApiError }
  | { type: "jobError"; problem: ApiError };

function initialState(title: string): State {
  return {
    title,
    phase: "resolving",
    problem: null,
    didYouMean: [],
    suggestion: null,
    suggestionsPaused: false,
    jobId: null,
    pageId: null,
    rateLimitNote: null,
    attempt: 0,
    jobRestarted: false,
  };
}

function failed(state: State, problem: ApiError): State {
  return { ...state, phase: "error", problem };
}

function reduce(state: State, action: Action): State {
  // An action for a title other than the stored one starts that title afresh.
  const current =
    "title" in action && action.title !== state.title ? initialState(action.title) : state;
  switch (action.type) {
    case "resolved": {
      const { outcome } = action;
      if (outcome.phase === "built") {
        return {
          ...current,
          phase: "built",
          pageId: outcome.pageId,
          rateLimitNote: outcome.rateLimitNote ?? null,
        };
      }
      if (outcome.phase === "building") {
        return { ...current, phase: "building", jobId: outcome.jobId };
      }
      return {
        ...failed(current, outcome.problem),
        didYouMean: outcome.didYouMean?.candidates ?? [],
        suggestion: outcome.didYouMean?.suggestion ?? null,
        suggestionsPaused: outcome.didYouMean?.searchRateLimited ?? false,
      };
    }
    case "retry":
      return { ...initialState(current.title), attempt: current.attempt + 1 };
    case "jobDone":
      return { ...current, phase: "built", pageId: action.pageId };
    case "failed":
      return failed(current, action.problem);
    default:
      // A job error. A 404 means the server no longer has the job, so the build is requested once
      // more without an error. A second 404 is shown.
      if (action.problem.status === 404 && !current.jobRestarted) {
        return { ...initialState(current.title), attempt: current.attempt + 1, jobRestarted: true };
      }
      return failed(current, action.problem);
  }
}

/**
 * Resolves a title to a page id, uses the dossier if one is already built, and otherwise requests
 * a build and polls its job. The dossier itself is a query that refetches when the budget changes.
 */
export function useDossier(title: string, budget: Budget): UseDossierResult {
  const [stored, dispatch] = useReducer(reduce, title, initialState);
  // The stored state may still belong to the previous title for the render after a change.
  const state = stored.title === title ? stored : initialState(title);
  const queryClient = useQueryClient();
  const { job, error: jobError, cancel: cancelPolling } = usePolledJob(state.jobId);

  // A budget change must not run the resolve again, because only the dossier query refetches for it.
  const resolve = useEffectEvent(() => resolveDossier(title, budget, queryClient));

  useEffect(() => {
    let cancelled = false;
    void resolve().then((outcome) => {
      if (!cancelled) {
        dispatch({ type: "resolved", title, outcome });
      }
    });
    return () => {
      cancelled = true;
    };
    // The effect body never reads attempt. retry() and a job 404 bump it to re-run the effect for an unchanged title.
    // oxlint-disable-next-line react/exhaustive-effect-dependencies
  }, [title, state.attempt]);

  // The polled job lives outside this hook's state, so its final status is copied into it here.
  useEffect(() => {
    if (job?.status === "done") {
      dispatch({ type: "jobDone", pageId: job.page_id });
    } else if (job?.status === "failed") {
      dispatch({ type: "failed", problem: job.error ?? jobFailedProblem() });
    }
  }, [job]);

  useEffect(() => {
    if (jobError) {
      dispatch({ type: "jobError", problem: jobError });
    }
  }, [jobError]);

  const dossierQuery = useQuery({
    ...dossierQueryOptions(state.pageId, budget),
    // A budget change is a new query key. Without the previous data the page falls back to loading,
    // collapses, and the browser clamps the reader to the top. The old dossier is kept for the same
    // page only, so another topic never borrows it.
    placeholderData: (previous, previousQuery) =>
      previousQuery?.queryKey[1] === state.pageId ? previous : undefined,
    // When the resolve finds an already-built dossier, it stores it in the query cache before this query is enabled.
    // A nonzero staleTime stops the query from fetching that data again when it mounts.
    staleTime: 30_000,
  });

  return {
    phase: state.phase,
    problem: state.problem,
    didYouMean: state.didYouMean,
    suggestion: state.suggestion,
    suggestionsPaused: state.suggestionsPaused,
    // The job's snapshot can outlive a title change by one render, so it is hidden until this title has a job.
    job: state.jobId == null ? null : job,
    cancelBuild: () => {
      cancelPolling();
      dispatch({ type: "failed", problem: CANCELLED_PROBLEM });
    },
    retry: () => dispatch({ type: "retry", title }),
    pageId: state.pageId,
    dossier: dossierQuery.data,
    dossierError: dossierQuery.error,
    dossierLoading: dossierQuery.isLoading,
    refetchDossier: () => void dossierQuery.refetch(),
    rateLimitNote: state.rateLimitNote,
  };
}
