import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listDossiers, searchTopics } from "../../api/generated";
import type { TopicCandidate } from "../../api/generated";
import { mergeStoredFirst } from "../searchRank";

/** Quiet time after the last keystroke before the search runs. */
const DEBOUNCE_MS = 300;
/** Fewest characters that trigger a search. */
const MIN_CHARS = 3;
/** Most titles listed. */
const MAX_SUGGESTIONS = 5;
/** Stored dossiers fetched per query, so prefix matches survive the cap. */
const STORED_FETCH = 20;

const NONE: TopicCandidate[] = [];

export interface TopicSuggestions {
  /** The text the suggestions answer: the trimmed input once it has rested, or "" while it is too short. */
  term: string;
  /** Titles matching `term`, stored dossiers first; empty while the input has moved past `term`. */
  suggestions: TopicCandidate[];
}

/**
 * Suggests article titles for what the reader types, from Wikipedia's search and the stored dossiers.
 * It waits for the input to rest and for enough characters. A failure of one source leaves the other's titles.
 */
export function useTopicSuggestions(text: string): TopicSuggestions {
  const trimmed = text.trim();
  const [term, setTerm] = useState("");
  useEffect(() => {
    const timer = setTimeout(
      () => setTerm(trimmed.length >= MIN_CHARS ? trimmed : ""),
      DEBOUNCE_MS,
    );
    return () => clearTimeout(timer);
  }, [trimmed]);

  const query = useQuery({
    queryKey: ["search-suggestions", term],
    queryFn: async () => {
      // Wikipedia ranks by its own popularity, so a stored dossier shows up only by chance.
      // The dossier list is searched as well.
      const [wiki, stored] = await Promise.all([
        searchTopics({ query: { q: term, limit: MAX_SUGGESTIONS } }).catch(() => null),
        listDossiers({ query: { q: term, limit: STORED_FETCH } }).catch(() => null),
      ]);
      const wikiRows = wiki?.data?.results ?? null;
      const storedRows = stored?.data?.items ?? null;
      if (wikiRows == null && storedRows == null) {
        throw wiki?.error ?? stored?.error ?? new Error("search failed");
      }
      return mergeStoredFirst(term, storedRows ?? [], wikiRows ?? [], MAX_SUGGESTIONS);
    },
    enabled: term.length >= MIN_CHARS,
    retry: false,
    staleTime: 60_000,
  });

  // A stale list under a changed input would offer titles the reader has already typed past.
  return { term, suggestions: term === trimmed ? (query.data ?? NONE) : NONE };
}
