import { isDeepStrictEqual } from "node:util";
import { test as base, expect, type Locator, type Page } from "@playwright/test";
import { mockApi } from "./mockApi";

/** How long open() waits for a page's ready element. */
const PAGE_READY_TIMEOUT_MS = 15_000;

export { expect };

export const THEMES = ["light", "dark"] as const;
export type Theme = (typeof THEMES)[number];

export const PROJECT_NAMES = [
  "mobile-390",
  "tablet-768",
  "tablet-1024",
  "desktop-1440",
  "desktop-1920",
] as const;
export type ProjectName = (typeof PROJECT_NAMES)[number];

/** The viewport each Playwright project runs in, named after its width. */
export const VIEWPORTS: Record<ProjectName, { width: number; height: number }> = {
  "mobile-390": { width: 390, height: 844 },
  "tablet-768": { width: 768, height: 1024 },
  "tablet-1024": { width: 1024, height: 768 },
  "desktop-1440": { width: 1440, height: 900 },
  "desktop-1920": { width: 1920, height: 1080 },
};

/**
 * Limits a test or describe to the named projects: `test("...", only("desktop-1440"), async ...)`.
 * A test without it runs on every project; playwright.config.ts routes the tags through each project's grep.
 */
export function only(...projects: ProjectName[]): { tag: string[] } {
  return { tag: projects.map((project) => `@${project}`) };
}

/**
 * Returns the grep that keeps, for one project, the tests with no project tag and the tests tagged for it.
 * A tag matches whole, so "@desktop-144" never matches "@desktop-1440".
 */
export function projectGrep(project: ProjectName): RegExp {
  const anyTag = PROJECT_NAMES.join("|");
  return new RegExp(`^(?!.*@(?:${anyTag})(?![\\w-]))|@${project}(?![\\w-])`);
}

interface Options {
  /** The theme stored before the app loads; null leaves the app to pick its own. */
  theme: Theme | null;
  /** Stores the pause flag, which stops the live edit feed on Home. */
  paused: boolean;
  /** Installs the recorded API routes; turn it off for a test that routes everything itself. */
  mocked: boolean;
}

interface OpenOptions {
  /** Resizes the window before navigating. */
  viewport?: { width: number; height: number };
  /** What must be visible before the page counts as loaded; the first h1 by default. */
  ready?: Locator;
}

interface Fixtures {
  /** Opens a path, then waits for the ready locator, the web fonts and a stable layout. */
  open: (path: string, options?: OpenOptions) => Promise<void>;
}

/**
 * The Playwright test with the options above (set with `test.use`) applied to every page, and the `open` fixture.
 * The routes are installed before the test body runs, so a route the test adds afterwards wins.
 */
export const test = base.extend<Options & Fixtures>({
  theme: [null, { option: true }],
  paused: [false, { option: true }],
  mocked: [true, { option: true }],
  page: async ({ page, theme, paused, mocked }, use) => {
    if (theme !== null) {
      await page.addInitScript((value) => window.localStorage.setItem("wke-theme", value), theme);
    }
    if (paused) {
      await page.addInitScript(() => window.localStorage.setItem("wke-paused", "1"));
    }
    if (mocked) {
      await mockApi(page);
    }
    await use(page);
  },
  open: async ({ page, theme }, use) => {
    await use(async (path, options = {}) => {
      if (options.viewport) {
        await page.setViewportSize(options.viewport);
      }
      await page.goto(path);
      // A first render under a loaded machine can take longer than an assertion's default wait.
      await expect(options.ready ?? page.getByRole("heading", { level: 1 }).first()).toBeVisible({
        timeout: PAGE_READY_TIMEOUT_MS,
      });
      // The app sets data-theme once it has mounted.
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme ?? /^(light|dark)$/);
      await settleLayout(page);
    });
  },
});

/** Defines the tests once per theme, each run in a describe named after the theme with that theme stored. */
export function eachTheme(define: (theme: Theme) => void): void {
  for (const theme of THEMES) {
    test.describe(theme, () => {
      test.use({ theme });
      define(theme);
    });
  }
}

function twoFrames(page: Page): Promise<void> {
  return page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
      }),
  );
}

/**
 * Polls `read` once per two animation frames and returns the first value equal to the one before it.
 * It throws when the value still changes after the timeout.
 */
export async function settle<T>(
  page: Page,
  read: () => Promise<T>,
  timeoutMs = 10_000,
): Promise<T> {
  const deadline = Date.now() + timeoutMs;
  let last = await read();
  for (;;) {
    await twoFrames(page);
    const next = await read();
    if (isDeepStrictEqual(next, last)) {
      return next;
    }
    if (Date.now() > deadline) {
      throw new Error(`still changing after ${timeoutMs} ms: ${JSON.stringify(next)}`);
    }
    last = next;
  }
}

/** Waits until the scroll position has held for two animation frames, and returns it. */
export function settleScroll(page: Page, timeoutMs = 5_000): Promise<number> {
  return page.evaluate(
    (limit) =>
      new Promise<number>((resolve, reject) => {
        const start = performance.now();
        let last = window.scrollY;
        let held = 0;
        const check = () => {
          held = window.scrollY === last ? held + 1 : 0;
          last = window.scrollY;
          if (held >= 2) {
            resolve(last);
          } else if (performance.now() - start > limit) {
            reject(new Error(`scroll still moving after ${limit} ms, at ${last}`));
          } else {
            requestAnimationFrame(check);
          }
        };
        requestAnimationFrame(check);
      }),
    timeoutMs,
  );
}

/** Waits until an element's box has stopped moving, and returns it. */
export function settleBox(locator: Locator) {
  return settle(locator.page(), () => locator.boundingBox());
}

/** Waits for the web fonts, then until the document's size stops changing. */
export async function settleLayout(page: Page): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  await settle(page, () =>
    page.evaluate(() => [
      document.documentElement.scrollWidth,
      document.documentElement.scrollHeight,
    ]),
  );
}
