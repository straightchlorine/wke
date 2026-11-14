import type { QueryClient } from "@tanstack/react-query";
import { searchTopics } from "../../api/generated";
import type { ApiError, SearchTopicsResponses, TopicCandidate } from "../../api/generated";
import { getDossierView, requestDossierView } from "../../api/dossier";
import { dossierQueryOptions } from "../../api/queries";
import type { Budget } from "../budget";
import { networkErrorProblem } from "../errors";

const MAX_DID_YOU_MEAN = 3;

export interface DidYouMean {
  candidates: TopicCandidate[];
  suggestion: string | null;
}

/** Returns the top title matches and the API's spelling suggestion from a title search, both empty when it found nothing. */
export function toDidYouMean(data: SearchTopicsResponses[200] | undefined): DidYouMean {
  return {
    candidates: data?.results.slice(0, MAX_DID_YOU_MEAN) ?? [],
    suggestion: data?.did_you_mean ?? null,
  };
}

/** How a title resolved. A "built" page id is ready to fetch, and "building" carries the job to poll. */
export type ResolveOutcome =
  | { phase: "built"; pageId: number; rateLimitNote?: string }
  | { phase: "building"; jobId: string }
  | {
      phase: "error";
      problem: ApiError;
      /** Set only for a not_found problem. */
      didYouMean?: DidYouMean & { searchRateLimited: boolean };
    };

function fail(problem: ApiError): ResolveOutcome {
  return { phase: "error", problem };
}

/**
 * Returns a built outcome with a note when the dossier for this page and budget is already in the
 * cache, and null otherwise. A 429 must never hide a dossier that already exists.
 */
function cachedOnRateLimit(
  queryClient: QueryClient,
  pageId: number,
  budget: Budget,
  problem: ApiError,
): ResolveOutcome | null {
  if (!queryClient.getQueryData(dossierQueryOptions(pageId, budget).queryKey)) {
    return null;
  }
  return {
    phase: "built",
    pageId,
    rateLimitNote:
      problem.detail ?? "Too many build requests right now. Showing the dossier already built.",
  };
}

/**
 * Resolves a title to a page id, uses the dossier if one is already built, and otherwise requests
 * a build. A dossier found this way is stored in the query cache for `budget`.
 */
export async function resolveDossier(
  title: string,
  budget: Budget,
  queryClient: QueryClient,
): Promise<ResolveOutcome> {
  try {
    // The title search is a GET and does not count against the build rate limit.
    const search = await searchTopics({ query: { q: title } });
    const exact = search.data?.results.find((c) => c.title.toLowerCase() === title.toLowerCase());

    if (exact) {
      const built = await getDossierView({ path: { page_id: exact.page_id }, query: { budget } });
      if (!built.error && built.data) {
        queryClient.setQueryData(dossierQueryOptions(exact.page_id, budget).queryKey, built.data);
        return { phase: "built", pageId: exact.page_id };
      }
      // A 404 means the dossier is not built yet, so the build request below follows.
      if (built.error && built.error.status !== 404) {
        const cached =
          built.error.status === 429
            ? cachedOnRateLimit(queryClient, exact.page_id, budget, built.error)
            : null;
        return cached ?? fail(built.error);
      }
    }

    const result = await requestDossierView(title);
    if (result.error) {
      if (result.error.status === 429 && exact) {
        const cached = cachedOnRateLimit(queryClient, exact.page_id, budget, result.error);
        if (cached) {
          return cached;
        }
      }
      return {
        phase: "error",
        problem: result.error,
        didYouMean:
          result.error.code === "not_found"
            ? { ...toDidYouMean(search.data), searchRateLimited: search.error?.status === 429 }
            : undefined,
      };
    }
    const data = result.data;
    if (data == null) {
      return fail(networkErrorProblem());
    }
    return "schema_version" in data
      ? { phase: "built", pageId: data.topic.page_id }
      : { phase: "building", jobId: data.id };
  } catch {
    return fail(networkErrorProblem());
  }
}
