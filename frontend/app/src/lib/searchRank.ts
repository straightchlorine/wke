import type { DossierListItem, TopicCandidate } from "../api/generated";

/**
 * Returns a new list with titles that already have a dossier ahead of the rest, keeping the input
 * order inside each group.
 */
export function rankBuiltFirst<T extends Pick<TopicCandidate, "dossier_state">>(
  candidates: readonly T[],
): T[] {
  const built = candidates.filter((candidate) => candidate.dossier_state !== "none");
  const unbuilt = candidates.filter((candidate) => candidate.dossier_state === "none");
  return [...built, ...unbuilt];
}

/**
 * Returns 0 when the title starts with the query or the query is empty, 1 when a later word starts
 * with it, and 2 otherwise.
 * For "liz", "Monster: The Lizzie Borden Story" is 1, and "Elizabeth Holmes" is 2 because the match
 * is inside a word.
 */
export function matchTier(title: string, query: string): 0 | 1 | 2 {
  const haystack = title.toLowerCase();
  const needle = query.trim().toLowerCase();
  if (haystack.startsWith(needle)) {
    return 0;
  }
  for (let at = haystack.indexOf(needle, 1); at !== -1; at = haystack.indexOf(needle, at + 1)) {
    if (!/[\p{L}\p{N}]/u.test(haystack.charAt(at - 1))) {
      return 1;
    }
  }
  return 2;
}

/**
 * Sorts rows into match tiers, keeping the input order inside each tier. With `wordStart`, tiers 0
 * and 1 count as one, so a title that starts with the query and a title with a later word starting
 * with it keep their input order.
 */
function byTier<T>(
  rows: readonly T[],
  titleOf: (row: T) => string,
  query: string,
  wordStart = false,
): T[] {
  const tierOf = (row: T) => {
    const tier = matchTier(titleOf(row), query);
    return wordStart && tier === 1 ? 0 : tier;
  };
  return [0, 1, 2].flatMap((tier) => rows.filter((row) => tierOf(row) === tier));
}

/**
 * Merges stored dossiers with Wikipedia's suggestions into at most `max` rows, with no title or
 * page id listed twice.
 * Stored titles come first, marked ready and ordered by `matchTier`, and each keeps the description
 * Wikipedia gave the same page.
 * Suggestions follow, built ones first, with titles that have a word starting with the query ahead
 * of the rest inside each group.
 */
export function mergeStoredFirst(
  query: string,
  stored: readonly Pick<DossierListItem, "page_id" | "title">[],
  suggestions: readonly TopicCandidate[],
  max: number,
): TopicCandidate[] {
  const seen = new Set<string>();
  const merged: TopicCandidate[] = [];
  for (const item of byTier(stored, (row) => row.title, query)) {
    const key = item.title.toLowerCase();
    if (seen.has(key) || merged.some((row) => row.page_id === item.page_id)) {
      continue;
    }
    seen.add(key);
    const same = suggestions.find(
      (row) => row.page_id === item.page_id || row.title.toLowerCase() === key,
    );
    merged.push({
      page_id: item.page_id,
      title: item.title,
      description: same?.description,
      dossier_state: "ready",
    });
  }
  for (const row of rankBuiltFirst(
    byTier(suggestions, (candidate) => candidate.title, query, true),
  )) {
    if (
      !seen.has(row.title.toLowerCase()) &&
      !merged.some((listed) => listed.page_id === row.page_id)
    ) {
      seen.add(row.title.toLowerCase());
      merged.push(row);
    }
  }
  return merged.slice(0, max);
}
