import { Link } from "@tanstack/react-router";
import type { ApiError, TopicCandidate } from "../api/generated";
import type { Budget } from "../lib/budget";
import { errorTitle } from "../lib/errors";
import { Colophon } from "./Colophon";
import { DossierHead } from "./DossierHead";
import { ProblemPanel } from "./ProblemPanel";

export interface DossierProblemProps {
  problem: ApiError;
  /** The title the page was opened with, from the address. */
  title: string;
  budget: Budget;
  /** Title matches for a topic the API did not find. */
  didYouMean: TopicCandidate[];
  suggestion: string | null;
  suggestionsPaused: boolean;
  onRetry: () => void;
}

/** The page for a dossier that could not be built: the problem, the ways on and a link back to the index. */
export function DossierProblem({
  problem,
  title,
  budget,
  didYouMean,
  suggestion,
  suggestionsPaused,
  onRetry,
}: DossierProblemProps) {
  const notFound = problem.code === "not_found";
  return (
    <div className="w-full py-8">
      <DossierHead title={notFound ? errorTitle(problem) : title} crumb={title} />
      <ProblemPanel
        className="mt-4"
        problem={problem}
        budget={budget}
        onRetry={onRetry}
        didYouMean={didYouMean}
        suggestion={suggestion}
        suggestionsPaused={suggestionsPaused}
        openSearch
        hideNotFoundTitle
        notFoundDetail={`No article titled "${title}".`}
      />
      <p className="mt-4 text-13 text-ink-2">
        <Link to="/" className="hit-44 inline-block text-accent underline">
          Back to today's index
        </Link>
      </p>
      <div className="mt-8">
        <Colophon />
      </div>
    </div>
  );
}
