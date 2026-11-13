import { expect, type Page } from "@playwright/test";

/** What trackErrors collected: console error texts and uncaught exception messages. */
export interface ErrorLog {
  console: string[];
  page: string[];
}

/**
 * Records console errors and uncaught exceptions so a render crash fails the test even when no other assertion would.
 * Call it before the page is opened, and pass the returned log to assertNoErrors once the page has settled.
 */
export function trackErrors(page: Page): ErrorLog {
  const log: ErrorLog = { console: [], page: [] };
  page.on("console", (message) => {
    if (message.type() === "error") {
      log.console.push(message.text());
    }
  });
  page.on("pageerror", (error) => {
    log.page.push(error.message);
  });
  return log;
}

/** Fails if the tracked page logged a console error or an uncaught exception. */
export function assertNoErrors(log: ErrorLog): void {
  expect(log.console).toEqual([]);
  expect(log.page).toEqual([]);
}

/** Fails unless the header and the h1 are visible, so a blank page cannot pass a test that only checks a string is absent. */
export async function expectShellRendered(page: Page): Promise<void> {
  await expect(page.locator("header")).toBeVisible();
  await expect(page.locator("h1")).toBeVisible();
}
