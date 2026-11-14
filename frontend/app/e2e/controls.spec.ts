import type { Page } from "@playwright/test";
import { test, expect, eachTheme, lightOnly, only } from "./support";

const PAGES = [
  { path: "/", ready: "Cited context" },
  { path: "/t", ready: "Dossiers" },
  { path: "/t/Jesus", ready: "Jesus" },
  { path: "/machines", ready: "For machines" },
] as const;

eachTheme(() => {
  for (const { path, ready } of PAGES) {
    test(
      `every control is square and primary buttons are unique, ${path}`,
      only("mobile-390", "tablet-768", "desktop-1440"),
      async ({ page, open }) => {
        await open(path, {
          ready: page.getByRole("heading", { level: 1 }).filter({ hasText: ready }).first(),
        });
        const report = await page.evaluate(() => {
          const shown = [...document.querySelectorAll("*")].filter(
            (el) => el.checkVisibility() && el.getBoundingClientRect().width > 0,
          );
          const squared = [
            "button:not([aria-describedby])",
            "[role=radiogroup]",
            // A visually hidden radio is not a control a sighted user sees, and Chromium gives native radios a round default.
            "input:not(.sr-only)",
            "[role=toolbar]",
            "[role=tooltip]",
            "pre",
            "a[class*=border]",
          ].join(",");
          const rounded = shown
            .filter((el) => el.matches(squared))
            .map((el) => ({ el, radius: getComputedStyle(el).borderTopLeftRadius }))
            .filter(({ radius }) => radius !== "0px")
            .map(({ el, radius }) => `${el.tagName}.${el.className} ${radius}`);
          const dots = shown
            .filter((el) => el.matches("button[aria-describedby]:not([data-info-text])"))
            .map((el) => getComputedStyle(el).borderTopLeftRadius);
          const accent = getComputedStyle(document.documentElement)
            .getPropertyValue("--color-accent")
            .trim();
          const probe = document.createElement("i");
          probe.style.color = accent;
          document.body.append(probe);
          const accentRgb = getComputedStyle(probe).color;
          probe.remove();
          const filled = shown.filter(
            (el) => el.matches("button, a") && getComputedStyle(el).backgroundColor === accentRgb,
          ).length;
          return { rounded, dots, filled };
        });
        expect(report.rounded).toEqual([]);
        for (const r of report.dots) {
          expect(r).not.toBe("0px");
        }
        expect(report.filled).toBeLessThanOrEqual(1);
      },
    );
  }
});

lightOnly(() => {
  test(
    "Build a dossier and Clear filter share a height",
    only("mobile-390", "desktop-1440"),
    async ({ page, open }) => {
      // No suggestions, so the empty state keeps its Build button.
      await page.route(/\/api\/v1\/search(\?[^/]*)?$/, async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ query: "Zzyzx nothing", results: [] }),
        });
      });
      await open("/t");
      await page.getByRole("combobox", { name: "Filter dossiers by title" }).fill("Zzyzx nothing");
      const build = page.getByRole("link", { name: /Build a dossier for/ });
      await expect(build).toBeVisible();
      const clear = page.getByRole("button", { name: "Clear filter" });
      const [a, b] = [await build.boundingBox(), await clear.boundingBox()];
      expect(a?.height).toBeCloseTo(b?.height ?? -1, 0);
      expect(a?.y).toBeCloseTo(b?.y ?? -1, 0);
    },
  );

  test(
    "the dossier toolbar row shares one height",
    only("tablet-768", "tablet-1024", "desktop-1440", "desktop-1920"),
    async ({ page, open }) => {
      await open("/t/Jesus");
      const toolbar = page.getByRole("button", { name: "JSON", exact: true }).locator("..");
      const heights = await toolbar.evaluate((el) =>
        [...el.querySelectorAll("button, [role=radiogroup]")]
          .filter((b) => b.getBoundingClientRect().width > 0 && !b.hasAttribute("aria-describedby"))
          .map((b) => Math.round(b.getBoundingClientRect().height * 10) / 10),
      );
      expect(heights.length).toBeGreaterThanOrEqual(4);
      expect(new Set(heights).size).toBe(1);
    },
  );
});

const ALLOWED_COPY_LABELS = ["Copy", "Copy URL", "Copy config", "Copy as context"];

/** The distinct texts of the visible buttons that start with "Copy", sorted. */
function visibleCopyLabels(page: Page): Promise<string[]> {
  return page.evaluate(() =>
    [
      ...new Set(
        Array.from(document.querySelectorAll("button"))
          .filter((b) => b.offsetParent !== null)
          .map((b) => b.innerText.trim().replace(/\s+/g, " "))
          .filter((t) => /^copy/i.test(t)),
      ),
    ].toSorted(),
  );
}

// The For machines page has its own label test in machines.spec.ts.
test.describe("Copy labels", () => {
  test(
    "Home uses only the label scheme",
    only("mobile-390", "desktop-1440"),
    async ({ page, open }) => {
      await open("/");
      await expect
        .poll(() => visibleCopyLabels(page))
        .toEqual(expect.arrayContaining(["Copy URL", "Copy as context", "Copy config"]));
      for (const label of await visibleCopyLabels(page)) {
        expect(ALLOWED_COPY_LABELS, label).toContain(label);
      }
    },
  );

  // The toolbar's Copy as context gives way to the bottom bar under 600px; both use the same words.
  for (const [where, tag, expected] of [
    ["with the toolbar", only("desktop-1440"), ["Copy URL", "Copy as context"]],
    ["with the bottom bar", only("mobile-390"), ["Copy as context"]],
  ] as const) {
    test(`a dossier ${where} uses only the label scheme`, tag, async ({ page, open }) => {
      await open("/t/Jesus");
      await expect
        .poll(() => visibleCopyLabels(page))
        .toEqual(expect.arrayContaining([...expected]));
      for (const label of await visibleCopyLabels(page)) {
        expect(ALLOWED_COPY_LABELS, label).toContain(label);
      }
    });
  }
});
