import type { Page } from "@playwright/test";
import { assertNoErrors, trackErrors } from "./errorTracking";
import { waitForBudget } from "./readingSection";
import { expect, lightOnly, only, settleScroll, test } from "./support";

// Returning to a budget already visited, with no scroll in between, puts the
// page back at the exact spot it had there; a scroll by the reader forgets it.

async function pressBudgetKey(page: Page, key: string, budget: number) {
  await page.keyboard.press(key);
  await expect(page).toHaveURL(new RegExp(`budget=${budget}`));
  await waitForBudget(page, budget);
}

lightOnly(() => {
  test(
    "1 then 3 then 2 restores the exact scroll position",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/t/Lizzie_Borden");
      await page.evaluate(() => window.scrollTo(0, 3368));
      const start = await settleScroll(page);
      expect(start).toBeGreaterThan(3000);
      await pressBudgetKey(page, "1", 2000);
      await pressBudgetKey(page, "3", 32000);
      await pressBudgetKey(page, "2", 8000);
      expect(await page.evaluate(() => window.scrollY)).toBe(start);
      // A second trip to 2k and back restores the same spot.
      await pressBudgetKey(page, "1", 2000);
      await pressBudgetKey(page, "2", 8000);
      expect(await page.evaluate(() => window.scrollY)).toBe(start);
      assertNoErrors(errors);
    },
  );

  test(
    "a scroll by the reader clears the saved positions",
    only("desktop-1440"),
    async ({ page, open }) => {
      await open("/t/Lizzie_Borden");
      await page.evaluate(() => window.scrollTo(0, 3368));
      await settleScroll(page);
      await pressBudgetKey(page, "1", 2000);
      await page.mouse.move(700, 500);
      const atTwoK = await page.evaluate(() => window.scrollY);
      await page.mouse.wheel(0, 240);
      await expect.poll(() => page.evaluate(() => window.scrollY)).not.toBe(atTwoK);
      await settleScroll(page);
      await pressBudgetKey(page, "2", 8000);
      // The wheel scroll drops the saved spots, so the page anchors on the reader's section instead of returning to the old position.
      expect(await page.evaluate(() => window.scrollY)).not.toBe(3368);
    },
  );
});
