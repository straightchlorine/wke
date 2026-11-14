import type { Page } from "@playwright/test";
import { test, expect, lightOnly, only } from "./support";
import { freeze } from "./buildFixture";

interface Problems {
  console: string[];
  page: string[];
}

/** Listens for uncaught exceptions and console errors, ignoring the browser's own log of a failed /api/v1 request, which some visits trigger on purpose. */
function watch(page: Page): Problems {
  const problems: Problems = { console: [], page: [] };
  page.on("console", (message) => {
    if (message.type() !== "error") {
      return;
    }
    const expected404 =
      message.text().includes("Failed to load resource") &&
      message.location().url.includes("/api/v1/");
    if (!expected404) {
      problems.console.push(message.text());
    }
  });
  page.on("pageerror", (error) => {
    problems.page.push(`${error.name}: ${error.message}`);
  });
  return problems;
}

const VISITS: {
  name: string;
  path: string;
  ready: string | RegExp;
  prepare?: (page: Page) => Promise<void>;
}[] = [
  { name: "Home", path: "/", ready: /.+/ },
  { name: "Dossiers", path: "/t", ready: "Dossiers" },
  { name: "a dossier", path: "/t/Jesus", ready: "Jesus" },
  { name: "For machines", path: "/machines", ready: "For machines" },
  {
    name: "the not-built page",
    path: "/t/Nonexistent_Title",
    ready: /.+/,
  },
  { name: "the 404", path: "/no-such-page", ready: /.+/ },
  {
    name: "the building state",
    path: "/t/Jesus",
    ready: /.+/,
    prepare: (page) => freeze(page),
  },
];

lightOnly(() => {
  for (const visit of VISITS) {
    test(
      `${visit.name} raises no runtime error`,
      only("mobile-390", "tablet-768", "desktop-1440"),
      async ({ page, open }) => {
        // The fake clock lets the timers scheduled after first paint run at once.
        await page.clock.install();
        const problems = watch(page);
        await visit.prepare?.(page);
        await open(visit.path, {
          ready: page.getByRole("heading", { level: 1 }).filter({ hasText: visit.ready }).first(),
        });
        await page.clock.runFor(800);
        expect(problems.page).toEqual([]);
        expect(problems.console).toEqual([]);
      },
    );
  }
});

test("a ReferenceError on the page fails the watcher", async ({ page, open }) => {
  const problems = watch(page);
  await open("/machines");
  await page.evaluate(() => {
    setTimeout(() => {
      // @ts-expect-error deliberate undefined identifier
      void JOB_STAGES.length;
    }, 0);
  });
  await expect.poll(() => problems.page.length).toBeGreaterThan(0);
  expect(problems.page[0]).toContain("JOB_STAGES is not defined");
});
