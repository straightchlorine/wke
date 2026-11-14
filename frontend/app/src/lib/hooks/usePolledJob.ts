import { useCallback, useEffect, useRef, useState } from "react";
import { getJob } from "../../api/generated";
import type { Job, ApiError } from "../../api/generated";
import { toProblem } from "../errors";
import { startVisiblePoll } from "./startVisiblePoll";

export interface UsePolledJobResult {
  job: Job | null;
  error: ApiError | null;
  /** True while a poll is scheduled or in flight. */
  polling: boolean;
  /** Stops polling. `job` keeps its last value, and the server job keeps running because the API cannot cancel one. */
  cancel: () => void;
}

const DONE_STATUSES = new Set<Job["status"]>(["done", "failed"]);

/**
 * Polls `GET /api/v1/jobs/{id}` at the job's own `poll_after_ms` until the job is `done` or
 * `failed`, a request fails, or `cancel` is called. Polling follows `startVisiblePoll`: a hidden
 * tab schedules no further polls, and one runs at once when the tab is shown again.
 */
export function usePolledJob(jobId: string | null | undefined): UsePolledJobResult {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [polling, setPolling] = useState(false);
  const stopPolling = useRef<(() => void) | null>(null);

  const cancel = useCallback(() => {
    stopPolling.current?.();
    setPolling(false);
  }, []);

  useEffect(() => {
    // The job and error must clear whenever jobId changes, so they reset in the effect that restarts polling.
    // oxlint-disable-next-line react/set-state-in-effect
    setJob(null);
    // oxlint-disable-next-line react/set-state-in-effect
    setError(null);
    if (!jobId) {
      setPolling(false);
      return undefined;
    }
    setPolling(true);

    const stop = startVisiblePoll(async (signal) => {
      try {
        const response = await getJob({ path: { job_id: jobId } });
        if (signal.aborted) {
          return null;
        }
        if (response.error) {
          setError(response.error);
          setPolling(false);
          return null;
        }
        const nextJob = response.data ?? null;
        setJob(nextJob);
        if (!nextJob || DONE_STATUSES.has(nextJob.status)) {
          setPolling(false);
          return null;
        }
        return nextJob.poll_after_ms;
      } catch (fetchError) {
        if (!signal.aborted) {
          setError(toProblem(fetchError));
          setPolling(false);
        }
        return null;
      }
    });
    stopPolling.current = stop;
    return stop;
  }, [jobId]);

  return { job, error, polling, cancel };
}
