import { Link } from "@tanstack/react-router";
import type { TopicCandidate } from "../api/generated";
import { Record } from "./Record";
import { DossierStateChip } from "./Chip";
import { useMediaQuery } from "../lib/hooks/useMediaQuery";
import { buildVerbHint } from "../lib/searchButton";
import { slugify } from "../lib/slug";
import type { Budget } from "../lib/budget";

export interface DidYouMeanProps {
  candidates: TopicCandidate[];
  budget: Budget;
  /** The API's suggested title for a misspelt query. It is shown first, ahead of the candidate list. */
  suggestion?: string | null;
}

/**
 * The "Did you mean" panel for a title that was not found or is ambiguous.
 * It shows the API's suggested title when there is one, then the top candidates, each linking to its dossier with its build state as a Chip.
 */
export function DidYouMean({ candidates, budget, suggestion }: DidYouMeanProps) {
  const buildVerb = buildVerbHint(useMediaQuery("(hover: none)") ? "touch" : "keyboard");
  const lead = suggestion?.trim() ? suggestion.trim() : null;
  return (
    <div>
      {lead ? (
        <p className="text-14 text-ink-2">
          Did you mean{" "}
          <Link
            to="/t/$slug"
            params={{ slug: slugify(lead) }}
            search={{ budget }}
            className="hit-44 inline-block text-accent underline"
          >
            {lead}
          </Link>
          ?
        </p>
      ) : (
        <p className="text-12 text-ink-2">Did you mean</p>
      )}
      <Record
        className="mt-1"
        label={lead && candidates.length > 0 ? "Other close titles" : undefined}
        rows={candidates.slice(0, 3).map((candidate) => ({
          label: (
            <Link
              to="/t/$slug"
              params={{ slug: slugify(candidate.title) }}
              search={{ budget }}
              className="hit-coarse inline-flex items-center text-accent underline max-md:min-h-11"
            >
              {candidate.title}
            </Link>
          ),
          value: (
            <DossierStateChip
              state={candidate.dossier_state}
              showNone
              className="w-19 justify-center"
            />
          ),
          sub: (
            <span className="text-ink-2">
              {candidate.dossier_state === "none"
                ? `${buildVerb}${candidate.description ? ` - ${candidate.description}` : ""}`
                : candidate.description}
            </span>
          ),
          size: "normal" as const,
        }))}
      />
    </div>
  );
}
