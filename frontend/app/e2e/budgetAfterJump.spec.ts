import type { Page } from "@playwright/test";
import { assertNoErrors, trackErrors } from "./errorTracking";
import { nearestHeading, openJesus, stickyBottom, waitForBudget } from "./readingSection";
import { expect, lightOnly, only, settleScroll, test } from "./support";

// A Contents click or a chip tap leaves #sN in the URL. A budget change
// afterwards rewrites only the search param and must hold the reader's
// place instead of scrolling back to that section.

const VIEWPORTS = [
  { name: "1440", width: 1440, height: 900, jump: 'nav[aria-label="Contents"]' },
  { name: "390", width: 390, height: 844, jump: 'nav[aria-label="Sections"]' },
] as const;

const SECTION_HEADINGS = 'section[id^="s"] [data-section-heading]';

const openAll = (page: Page, open: (path: string) => Promise<void>) => openJesus(page, open, 46);

// Scrolls section `id` to the top of the viewport and returns scrollY.
async function readOnTo(page: Page, id: string): Promise<number> {
  await page.evaluate((sectionId) => {
    const el = document.getElementById(sectionId);
    if (el) {
      window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY);
    }
  }, id);
  return settleScroll(page);
}

// True when the reader's place held: scrollY within 50 px of y, or the section within 50 px of top.
// Either counts, because the page reflows when the budget changes and the browser may keep the section rather than scrollY.
// A regression scrolls back to the section named in the URL hash instead.
async function held(page: Page, id: string, y: number, top: number): Promise<boolean> {
  const now = await page.evaluate(
    (sectionId) => ({
      y: window.scrollY,
      top: document.getElementById(sectionId)?.getBoundingClientRect().top ?? Number.NaN,
    }),
    id,
  );
  return Math.abs(now.y - y) <= 50 || Math.abs(now.top - top) <= 50;
}

function topOf(page: Page, id: string): Promise<number> {
  return page.evaluate(
    (sectionId) => document.getElementById(sectionId)?.getBoundingClientRect().top ?? Number.NaN,
    id,
  );
}

async function announced(page: Page): Promise<string> {
  return (await page.locator("#live-region").textContent()) ?? "";
}

// The reader's section and its offset must survive a budget change: the
// heading nearest the top is the same section (or the announced fallback
// when that section is gone) and sits within 8 px of where it was.
async function expectAnchored(
  page: Page,
  before: { n: number; top: number },
  budget: number,
): Promise<void> {
  await waitForBudget(page, budget);
  const after = await nearestHeading(page);
  if (after.n === before.n) {
    expect(Math.abs(after.top - before.top)).toBeLessThanOrEqual(8);
    return;
  }
  expect(after.n).toBeLessThan(before.n);
  expect(await announced(page)).toBe(
    `Section ${before.n} is not in this budget; showing section ${after.n}`,
  );
}

lightOnly(() => {
  for (const vp of VIEWPORTS) {
    test.describe(`budget change after a section jump (${vp.name})`, only("desktop-1440"), () => {
      test.use({ viewport: { width: vp.width, height: vp.height } });

      test("keys 1/2/3 and the segmented control keep the scroll position", async ({
        page,
        open,
      }) => {
        const errors = trackErrors(page);
        await page.clock.install();
        await openAll(page, open);

        await page.locator(`${vp.jump} a[href$="#s7"]`).click();
        await expect(page).toHaveURL(/#s7$/);
        await expect(page.locator("section#s7 [data-section-heading]")).toBeInViewport();

        const before = await readOnTo(page, "s8");
        expect(before).toBeGreaterThan(500);
        const topBefore = await topOf(page, "s8");
        await page.keyboard.press("3");
        await expect(page).toHaveURL(/budget=32000/);
        await waitForBudget(page, 32000);
        expect(await held(page, "s8", before, topBefore)).toBe(true);
        expect(await page.evaluate(() => document.activeElement === document.body)).toBe(false);

        await page.keyboard.press("1");
        await expect(page).toHaveURL(/budget=2000/);
        await waitForBudget(page, 2000);
        expect(await held(page, "s8", before, topBefore)).toBe(true);

        // A scroll within 400 ms of a restore counts as the page's own, so let the reader's scroll come later.
        await page.clock.fastForward(500);
        const furtherY = await readOnTo(page, "s10");
        const topFurther = await topOf(page, "s10");
        await page.getByRole("radio", { name: "8k", exact: true }).click({ force: true });
        await expect(page).toHaveURL(/budget=8000/);
        await waitForBudget(page, 8000);
        expect(await held(page, "s10", furtherY, topFurther)).toBe(true);
        expect(await page.evaluate(() => document.activeElement === document.body)).toBe(false);
        await expect(page).toHaveURL(/#s7$/);
        assertNoErrors(errors);
      });

      test("a budget key keeps the section being read, with and without a Contents jump", async ({
        page,
        open,
      }) => {
        const errors = trackErrors(page);
        await openAll(page, open);

        await readOnTo(page, "s5");
        const readingFive = await nearestHeading(page);
        expect(readingFive.n).toBe(5);
        await page.keyboard.press("1");
        await expect(page).toHaveURL(/budget=2000/);
        await expectAnchored(page, readingFive, 2000);
        expect(await page.evaluate(() => document.activeElement === document.body)).toBe(false);

        await page.keyboard.press("3");
        await expect(page).toHaveURL(/budget=32000/);
        await expectAnchored(page, readingFive, 32000);

        await page.locator(`${vp.jump} a[href$="#s7"]`).click();
        await expect(page).toHaveURL(/#s7$/);
        await settleScroll(page);
        const afterJump = await nearestHeading(page);
        expect(afterJump.n).toBe(7);
        await page.keyboard.press("1");
        await expect(page).toHaveURL(/budget=2000/);
        await expectAnchored(page, afterJump, 2000);
        await page.keyboard.press("2");
        await expect(page).toHaveURL(/budget=8000/);
        await expectAnchored(page, afterJump, 8000);
        assertNoErrors(errors);
      });

      test("2k from deep in section 13 at 8k stays in section 13, and the Contents mark agrees", async ({
        page,
        open,
      }) => {
        const errors = trackErrors(page);
        await openAll(page, open);

        await page.locator(`${vp.jump} a[href$="#s13"]`).click();
        await expect(page).toHaveURL(/#s13$/);
        await settleScroll(page);
        const height8k = await page
          .locator("section#s13")
          .evaluate((el) => el.getBoundingClientRect().height);
        expect(height8k).toBeGreaterThan(700);
        await page.evaluate(() => window.scrollBy(0, 600));
        await settleScroll(page);
        expect((await nearestHeading(page)).n).toBe(13);

        await page.keyboard.press("1");
        await expect(page).toHaveURL(/budget=2000/);
        await waitForBudget(page, 2000);
        const height2k = await page
          .locator("section#s13")
          .evaluate((el) => el.getBoundingClientRect().height);
        expect(height2k).toBeLessThan(height8k);
        expect((await nearestHeading(page)).n).toBe(13);
        await expect(page.locator('[aria-current="location"]').first()).toHaveText(/^13 /);
        assertNoErrors(errors);
      });

      test("a Contents jump lands the heading 16 px under the sticky bars", async ({
        page,
        open,
      }) => {
        await openAll(page, open);
        await page.locator(`${vp.jump} a[href$="#s9"]`).click();
        await expect(page).toHaveURL(/#s9$/);
        await settleScroll(page);
        const top = await page
          .locator("section#s9 [data-section-heading]")
          .evaluate((el) => el.getBoundingClientRect().top);
        const sticky = await stickyBottom(page);
        expect(Math.abs(top - (sticky + 16))).toBeLessThanOrEqual(2);
      });
    });
  }

  test(
    "a direct load of /t/X#s11 still lands the heading under the header",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/t/Jesus#s11", { viewport: { width: 1440, height: 900 } });
      await expect(page.locator(SECTION_HEADINGS)).toHaveCount(46, { timeout: 10_000 });
      const heading = page.locator("section#s11 [data-section-heading]");
      await expect(heading).toBeInViewport({ timeout: 10_000 });
      await expect
        .poll(() => heading.evaluate((el) => Math.round(el.getBoundingClientRect().top)))
        .toBeLessThan(200);
      const top = await heading.evaluate((el) => el.getBoundingClientRect().top);
      expect(top).toBeGreaterThan(40);
      assertNoErrors(errors);
    },
  );
});
