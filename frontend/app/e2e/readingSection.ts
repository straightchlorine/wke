import type { Locator, Page } from "@playwright/test";
import { withFreshness } from "./buildFixture";
import { dossierBody } from "./mockApi";
import { expect, settleScroll } from "./support";

const STICKY_BARS = '[data-dossier-toolbar], nav[aria-label="Sections"]';

/** Returns the bottom edge of the lowest sticky bar showing at the top of the page (the toolbar or the section-chip strip), or 0 when none shows. */
export function stickyBottom(page: Page): Promise<number> {
  return page.evaluate((selector) => {
    let bottom = 0;
    for (const bar of document.querySelectorAll<HTMLElement>(selector)) {
      if (getComputedStyle(bar).display !== "none") {
        bottom = Math.max(bottom, bar.getBoundingClientRect().bottom);
      }
    }
    return bottom;
  }, STICKY_BARS);
}

/**
 * Returns the section number and heading top of the last section heading at or up to 2px below the landing line, or of the first heading when none qualifies.
 * The landing line is 16px below the lowest displayed sticky bar, or 16px from the top when none shows.
 */
export function nearestHeading(page: Page): Promise<{ n: number; top: number }> {
  return page.evaluate((selector) => {
    let line = 16;
    for (const bar of document.querySelectorAll<HTMLElement>(selector)) {
      if (getComputedStyle(bar).display !== "none") {
        line = Math.max(line, bar.getBoundingClientRect().bottom + 16);
      }
    }
    let picked = { n: 0, top: 0 };
    let first = true;
    for (const section of document.querySelectorAll<HTMLElement>("article section[id]")) {
      const match = /^s(\d+)$/.exec(section.id);
      const h2 = section.querySelector("[data-section-heading]");
      if (!match || !h2) continue;
      const top = h2.getBoundingClientRect().top;
      if (first || top <= line + 2) picked = { n: Number(match[1]), top };
      first = false;
    }
    return picked;
  }, STICKY_BARS);
}

/**
 * Waits until the dossier built for `budget` tokens is on screen and the page has stopped scrolling.
 * The toolbar names the requested budget in its meter, so this also works where the toolbar is hidden.
 */
export async function waitForBudget(page: Page, budget: number): Promise<void> {
  await expect(page.locator("[data-dossier-toolbar]")).toContainText(
    `of ${budget.toLocaleString("en-US")} tokens`,
  );
  await settleScroll(page);
}

/** Opens the Jesus dossier and waits until `count` section headings are on the page. */
export async function openJesus(
  page: Page,
  open: (path: string) => Promise<void>,
  count: number,
): Promise<void> {
  await open("/t/Jesus");
  await expect(page.locator('section[id^="s"] [data-section-heading]')).toHaveCount(count);
}

/** Returns the visible Freshness row of the source record. */
export function freshnessRow(page: Page): Locator {
  return page
    .locator("[data-record-row]")
    .filter({ hasText: /^Freshness/ })
    .filter({ visible: true });
}

/** Returns the button of the visible Freshness row. */
export function freshnessChip(page: Page): Locator {
  return freshnessRow(page).locator("button");
}

/**
 * Serves the 1095706 dossier from fixture `name` with its freshness block patched.
 * The body is built when each request arrives, so a `patch` function is read again on every load.
 */
export async function mockFreshness(
  page: Page,
  name: string,
  patch: Record<string, unknown> | (() => Record<string, unknown>),
): Promise<void> {
  await page.route(/\/api\/v1\/dossiers\/1095706(\?[^/]*)?$/, async (route) => {
    const body = dossierBody(name, withFreshness(typeof patch === "function" ? patch() : patch));
    await route.fulfill({ status: 200, contentType: "application/json", body });
  });
}
