import type { Page } from "@playwright/test";
import { eachTheme, expect, only, settleLayout, test } from "./support";

// Inline links in running text keep their line height, so on a phone a tap at the centre or at either end of a link must still land on it.
// Links on adjacent lines share the gap between them, so no reach beyond the line is asserted here.
// The larger hit area of a standalone link is measured in e2e/tapTargets.spec.ts.

const SIZES = [
  [360, 800],
  [390, 844],
] as const;

const PAGES = [
  { path: "/machines", scope: "main p", min: 4, label: "For machines lede" },
  { path: "/t/", scope: "main p", min: 1, label: "Dossiers lede" },
  { path: "/t/Nonexistent_Title", scope: "main", min: 1, label: "Did you mean" },
] as const;

async function misses(page: Page, scope: string): Promise<string[]> {
  return page.evaluate(async (selector) => {
    // Measure only a settled layout: fonts loaded and every finite entrance animation or transition finished.
    // oxlint-disable-next-line unicorn/consistent-function-scoping -- the callback runs in the page, so its helpers cannot live outside it
    const settle = async () => {
      await document.fonts.ready;
      const finite = document
        .getAnimations()
        .filter((a) => Number.isFinite(a.effect?.getComputedTiming().endTime ?? 0));
      await Promise.allSettled(finite.map((a) => a.finished));
      await new Promise((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve(null))),
      );
    };
    await settle();
    document.documentElement.style.scrollBehavior = "auto";
    const out: string[] = [];
    const seen = new Set<Element>();
    for (const a of document.querySelectorAll(`${selector} a[href]`)) {
      if (seen.has(a) || a.closest("details:not([open])") || a.getClientRects().length === 0) {
        continue;
      }
      seen.add(a);
      a.scrollIntoView({ block: "center" });
      await settle();
      const r = a.getClientRects()[0]!;
      if (r.width < 2 || r.height < 2) {
        continue;
      }
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const points: Array<[string, number, number]> = [
        ["centre", cx, cy],
        ["left", r.left + 2, cy],
        ["right", r.right - 2, cy],
      ];
      for (const [name, x, y] of points) {
        const hit = document.elementFromPoint(x, y);
        if (hit == null || !(hit === a || a.contains(hit))) {
          out.push(`${(a.textContent ?? "").trim().slice(0, 24)}: ${name}`);
        }
      }
    }
    return out;
  }, scope);
}

eachTheme(() => {
  for (const [width, height] of SIZES) {
    test.describe(`${width}x${height}`, only("desktop-1440"), () => {
      test.use({ viewport: { width, height }, hasTouch: true, isMobile: true });

      for (const { path, scope, min, label } of PAGES) {
        test(`${label} links take a tap on the centre and both ends`, async ({ page, open }) => {
          await open(path);
          const links = page.locator(`${scope} a[href]`);
          await expect(links.first()).toBeVisible();
          // The suggestion list can arrive after the heading shows.
          await expect
            .poll(() => links.count(), { message: `${label} has links` })
            .toBeGreaterThanOrEqual(min);
          await settleLayout(page);
          expect(await misses(page, scope)).toEqual([]);
        });
      }
    });
  }
});
