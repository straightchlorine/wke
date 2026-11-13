import type { ApiError, TopicCandidate } from "../api/generated";
import type { Budget } from "../lib/budget";
import { errorTitle } from "../lib/errors";
import { Button } from "./Button";
import { CountdownButton } from "./CountdownButton";
import { DidYouMean } from "./DidYouMean";
import { ErrorPanel } from "./ErrorPanel";
import { OpenTopicSearch } from "./OpenTopicSearch";

export interface ProblemPanelProps {
  problem: ApiError;
  budget: Budget;
  /** Starts the failed request again. */
  onRetry: () => void;
  /** Title matches found by a follow-up search after a not_found answer. A disambiguation answer carries its own candidates. */
  didYouMean?: TopicCandidate[];
  /** The API's corrected title for a misspelt query. */
  suggestion?: string | null;
  /** Tells the reader that the follow-up search was skipped, for a not_found answer with no matches to show. */
  suggestionsPaused?: boolean;
  /** Adds a topic search under a not_found answer. */
  openSearch?: boolean;
  /** The text for a not_found answer that has no detail of its own. */
  notFoundDetail?: string;
  /** Leaves the title out of a not_found answer, for a page whose h1 already says it. */
  hideNotFoundTitle?: boolean;
  className?: string;
}

/**
 * A panel for a failed build or load: the problem's title and detail, a countdown when the server
 * asked to wait, and a way on.
 * That way on is the matching titles for a not_found or disambiguation answer, and otherwise a Retry button.
 */
export function ProblemPanel({
  problem,
  budget,
  onRetry,
  didYouMean = [],
  suggestion = null,
  suggestionsPaused = false,
  openSearch = false,
  notFoundDetail,
  hideNotFoundTitle = false,
  className,
}: ProblemPanelProps) {
  const notFound = problem.code === "not_found";
  return (
    <ErrorPanel
      className={className}
      title={notFound && hideNotFoundTitle ? undefined : errorTitle(problem)}
      detail={notFound ? (problem.detail ?? notFoundDetail) : problem.detail}
      requestId={problem.request_id || undefined}
      tone={notFound ? "muted" : "alert"}
      countdown={
        problem.retry_after != null ? (
          <CountdownButton seconds={problem.retry_after} onClick={onRetry} />
        ) : null
      }
      retry={
        problem.code === "disambiguation" && problem.candidates && problem.candidates.length > 0 ? (
          <DidYouMean candidates={problem.candidates} budget={budget} />
        ) : notFound ? (
          <div>
            {didYouMean.length > 0 || suggestion != null ? (
              <DidYouMean candidates={didYouMean} suggestion={suggestion} budget={budget} />
            ) : suggestionsPaused ? (
              <p className="text-13 text-ink-2">Suggestions paused, try again in a moment</p>
            ) : null}
            {openSearch ? <OpenTopicSearch className="mt-4" /> : null}
          </div>
        ) : problem.retry_after == null ? (
          <Button variant="small" onClick={onRetry}>
            Retry
          </Button>
        ) : null
      }
    />
  );
}
