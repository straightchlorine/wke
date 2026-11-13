import { queryOptions, skipToken } from "@tanstack/react-query";
import type { Budget } from "../lib/budget";
import { getDossierView } from "./dossier";
import { getTrending, listDossiers } from "./generated";

/** Returns the data of a generated client result and throws its error, so a query function can await it directly. */
export function unwrap<T>(result: { data?: T; error?: unknown }): T {
  if (result.error) {
    throw result.error;
  }
  if (result.data === undefined) {
    throw new Error("the API answered without a body");
  }
  return result.data;
}

/** The most dossiers one list request asks for. */
export const DOSSIERS_LIST_LIMIT = 100;

// Every page shows a failed request at once, with its own Retry button, so these queries
// do not retry by themselves.
const NO_RETRY = { retry: false } as const;

/**
 * The query for one dossier at one budget. Without a page id it is disabled.
 * Every reader of the same dossier and budget shares this key, so they share one cached request.
 */
export function dossierQueryOptions(pageId: number | null | undefined, budget: Budget) {
  return queryOptions({
    ...NO_RETRY,
    queryKey: ["dossier", pageId, budget],
    queryFn:
      pageId == null
        ? skipToken
        : async () =>
            unwrap(await getDossierView({ path: { page_id: pageId }, query: { budget } })),
  });
}

/** The query for the stored dossiers, as far as one list request reaches. */
export const dossiersListQueryOptions = queryOptions({
  ...NO_RETRY,
  queryKey: ["dossiers-list"],
  queryFn: async () => unwrap(await listDossiers({ query: { limit: DOSSIERS_LIST_LIMIT } })),
});

/** The query for the trending topics. */
export const trendingQueryOptions = queryOptions({
  ...NO_RETRY,
  queryKey: ["trending"],
  queryFn: async () => unwrap(await getTrending()),
});
