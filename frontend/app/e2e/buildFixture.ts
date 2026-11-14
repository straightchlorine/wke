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
