import { useState } from "react";
import type { ApiError, TopicCandidate } from "../../api/generated";
import { requestDossierView } from "../../api/dossier";
import type { Budget } from "../budget";
import { toProblem } from "../errors";
import { slugify } from "../slug";
import { fetchDidYouMean } from "./useDossier";
import { useOpenDossier } from "./useOpenDossier";

/** Why a build request failed, with the matching titles a follow-up search found for a not_found answer. */
export interface BuildError {
  problem: ApiError;
  didYouMean?: TopicCandidate[];
  /** The API's corrected title for a misspelt query. */
  suggestion?: string | null;
}

/**
 * Requests the dossier for a title and opens its route once the API names it.
 * A not_found answer carries no candidates, so a search for the top matches follows it.
 */
export function useBuildDossier(budget: Budget) {
  const openDossier = useOpenDossier(budget);
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState<BuildError | null>(null);

  async function build(title: string) {
    const trimmed = title.trim();
    if (!trimmed || building) {
      return;
    }
    setBuilding(true);
    setError(null);
    try {
      const result = await requestDossierView(trimmed);
      if (result.error) {
        setError({ problem: result.error });
        if (result.error.code === "not_found") {
          const { candidates, suggestion } = await fetchDidYouMean(trimmed);
          setError({ problem: result.error, didYouMean: candidates, suggestion });
        }
        return;
      }
      const data = result.data;
      if (data == null) {
        throw new Error("empty build response");
      }
      // A built dossier names its topic. A queued job carries the article's title or none, so the typed title is the fallback.
      openDossier(slugify("schema_version" in data ? data.topic.title : (data.title ?? trimmed)));
    } catch (caught) {
      setError({ problem: toProblem(caught) });
    } finally {
      setBuilding(false);
    }
  }

  return { building, error, build };
}
