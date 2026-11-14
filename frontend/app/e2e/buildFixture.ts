import type { Page } from "@playwright/test";
import { readFixture } from "./mockApi";

/** Parses a recorded fixture as the shape the caller names; the caller owns that shape. */
// oxlint-disable-next-line typescript/no-unnecessary-type-parameters -- JSON has no checkable shape; the type parameter is the caller's claim about the fixture
export function readFixtureJson<T>(name: string): T {
  return JSON.parse(readFixture(name));
}

/** An edit for `dossierBody` that overwrites fields of the fixture's freshness block. */
export function withFreshness(
  patch: Record<string, unknown>,
): (flat: Record<string, unknown>) => void {
  return (flat) => {
    const freshness = flat["freshness"];
    if (typeof freshness !== "object" || freshness === null) {
      throw new Error("the fixture has no freshness block");
    }
    Object.assign(freshness, patch);
  };
}

/** A running job for the Jesus build at the given progress. */
function job(progress: { done: number; total: number }) {
  return {
    id: "c490910fa024be34",
    page_id: 1095706,
    rev_id: 1385149975,
    title: "Jesus",
    status: "running",
    stage: "summarize",
    progress,
    queue_position: 1,
    poll_after_ms: 60000,
    partial_available: true,
    result_url: null,
    error: null,
    created_at: "2026-09-28T16:15:41Z",
    started_at: null,
    updated_at: "2026-09-28T16:15:41Z",
    finished_at: null,
  };
}

/**
 * Routes a Jesus build that stays on the summarize stage at `progress`, over the mocked API; `delayMs` holds each dossier fetch back.
 * Call it after the mocked API is installed, so these routes win.
 */
export async function freeze(page: Page, progress = { done: 3, total: 8 }, delayMs = 0) {
  await page.route(/\/api\/v1\/dossiers\/(\d+)(\?[^/]*)?$/, async (route) => {
    if (route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    if (delayMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
    await route.fulfill({
      status: 404,
      contentType: "application/problem+json",
      body: JSON.stringify({
        type: "about:blank",
        title: "Not Found",
        status: 404,
        detail: "No dossier has been built for page 1095706.",
        code: "not_built",
        request_id: "spec-build-view",
      }),
    });
  });
  await page.route(/\/api\/v1\/dossiers(\?[^/]*)?$/, async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      headers: { location: "/api/v1/jobs/c490910fa024be34" },
      body: JSON.stringify({
        ...job(progress),
        status: "queued",
        stage: "resolve",
        partial_available: false,
      }),
    });
  });
  await page.route(/\/api\/v1\/jobs\/c490910fa024be34(\?[^/]*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(job(progress)),
    });
  });
}

/** Options for `routeBuildJob`. */
interface BuildJobOptions {
  /** Id of the job the POST answers with and the GET serves. */
  jobId: string;
  /** The `poll_after_ms` every response carries. */
  pollAfterMs: number;
  /** The `request_id` of the not-built 404. */
  requestId: string;
  /** The poll at which the job reports done; absent keeps it running for good. */
  doneAtPoll?: number;
  /** The `progress.done` of the job reported at the given poll count. */
  progressDone: (polls: number) => number;
}

/**
 * Routes a not-built Jesus dossier, the 202 POST and the job GET, and counts the job polls.
 * The mocked API already holds this dossier, so the 404 is what starts the build flow.
 * Once the job reports done the 404 falls through to the mocked API's own dossier.
 */
export async function routeBuildJob(
  page: Page,
  { jobId, pollAfterMs, requestId, doneAtPoll, progressDone }: BuildJobOptions,
): Promise<{ polls: () => number }> {
  let polls = 0;
  let dossierReady = false;
  const base = {
    id: jobId,
    page_id: 1095706,
    rev_id: 1385149975,
    title: "Jesus",
    queue_position: 1,
    poll_after_ms: pollAfterMs,
    result_url: null,
    error: null,
    created_at: "2026-09-28T16:15:41Z",
    started_at: null,
    updated_at: "2026-09-28T16:15:41Z",
  };
  await page.route(/\/api\/v1\/dossiers\/(\d+)(\?[^/]*)?$/, async (route) => {
    if (route.request().method() !== "GET" || dossierReady) {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 404,
      contentType: "application/problem+json",
      body: JSON.stringify({
        type: "about:blank",
        title: "Not Found",
        status: 404,
        detail: "No dossier has been built for page 1095706.",
        code: "not_built",
        request_id: requestId,
      }),
    });
  });
  await page.route(/\/api\/v1\/dossiers(\?[^/]*)?$/, async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      headers: { location: `/api/v1/jobs/${jobId}` },
      body: JSON.stringify({
        ...base,
        status: "queued",
        stage: "resolve",
        progress: { done: 0, total: 8 },
        partial_available: false,
        finished_at: null,
      }),
    });
  });
  await page.route(new RegExp(`/api/v1/jobs/${jobId}(\\?[^/]*)?$`), async (route) => {
    polls += 1;
    const status = doneAtPoll !== undefined && polls >= doneAtPoll ? "done" : "running";
    if (status === "done") {
      dossierReady = true;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...base,
        status,
        stage: "summarize",
        progress: { done: progressDone(polls), total: 8 },
        partial_available: status === "running",
        finished_at: status === "done" ? "2026-09-28T16:15:50Z" : null,
      }),
    });
  });
  return { polls: () => polls };
}
