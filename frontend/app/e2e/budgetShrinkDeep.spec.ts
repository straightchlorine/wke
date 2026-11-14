import { assertNoErrors, trackErrors } from "./errorTracking";
import { nearestHeading, stickyBottom, waitForBudget } from "./readingSection";
import { expect, lightOnly, only, settleScroll, test } from "./support";

// Switching to 2k from deep inside a long section keeps the reader in that section.
// If the section is shorter than the reader's depth, its heading lands on the landing line, 16px under the sticky bars.
// The Contents mark then names that section.

lightOnly(() => {
  test(
    "a 2k shrink from deep in a section lands its heading",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/t/Lizzie_Borden", {
        ready: page.locator("article section[id] [data-section-heading]").first(),
      });

      // Pick the tallest section.
      const tall = await page.evaluate(() => {
        let best = { id: "", height: 0 };
        const all = [...document.querySelectorAll<HTMLElement>("article section[id]")].filter(
          (el) => /^s\d+$/.test(el.id),
        );
        for (const section of all) {
          const height = section.getBoundingClientRect().height;
          if (height > best.height) {
            best = { id: section.id, height };
          }
        }
        return best;
      });
      expect(tall.height).toBeGreaterThan(900);
      // Scroll first so the bars are stuck to the top of the viewport. In flow at the top of the page they sit lower.
      await page.evaluate(() => window.scrollTo(0, 1500));
      await settleScroll(page);
      const sticky = await stickyBottom(page);
      const landing = sticky + 16;
      expect(landing).toBeLessThan(200);
      const depth = Math.round(tall.height - 400);
      await page.evaluate(
        ({ id, into, line }) => {
          const heading = document.querySelector(`#${id} [data-section-heading]`)!;
          window.scrollTo(0, heading.getBoundingClientRect().top + window.scrollY - line + into);
        },
        { id: tall.id, into: depth, line: landing },
      );
      await settleScroll(page);
      const before = await nearestHeading(page);
      expect(`s${before.n}`).toBe(tall.id);
      expect(before.top).toBeLessThan(landing - 300);

      await page.keyboard.press("1");
      await expect(page).toHaveURL(/budget=2000/);
      await waitForBudget(page, 2000);

      const after = await page.evaluate(
        ({ id }) => {
          const section = document.getElementById(id);
          const heading = section?.querySelector("[data-section-heading]");
          const current = document.querySelector(
            'nav[aria-label="Contents"] a[aria-current="location"]',
          );
          return {
            present: section != null,
            height: section?.getBoundingClientRect().height ?? 0,
            top: heading?.getBoundingClientRect().top ?? Number.NaN,
            current: current?.getAttribute("href") ?? null,
          };
        },
        { id: tall.id },
      );
      expect(after.present).toBe(true);
      // The section shrank below the reader's depth, so its heading, not its tail, sits at the landing line.
      expect(depth).toBeGreaterThan(after.height - 28);
      expect(Math.abs(after.top - landing)).toBeLessThanOrEqual(8);
      expect(after.current).toBe(`#${tall.id}`);
      expect(`s${(await nearestHeading(page)).n}`).toBe(tall.id);
      assertNoErrors(errors);
    },
  );
});
