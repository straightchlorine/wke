import { readFixture } from "./mockApi";
import { expect, lightOnly, only, test } from "./support";

const LONG =
  "Chairman of the Standing Committee of the National People's Congress of the People's Republic of China";

/** The recorded trending list with the title of its second topic replaced by LONG. */
function trendingWithLongTitle(): string {
  // Each topic has one "title", so the second one seen is the second most-read topic.
  let titlesSeen = 0;
  const trending: unknown = JSON.parse(readFixture("trending.json"), (key, value: unknown) => {
    if (key !== "title") {
      return value;
    }
    titlesSeen += 1;
    return titlesSeen === 2 ? LONG : value;
  });
  return JSON.stringify(trending);
}

test.describe("Phone edit titles", only("desktop-1440"), () => {
  lightOnly(() => {
    for (const [width, height] of [
      [390, 844],
      [360, 800],
      [1440, 900],
    ] as const) {
      test(`a long most-read title at ${width}: ${width < 768 ? "two lines, the row grows, chip and figure centred" : "one line, the row keeps its height"}`, async ({
        page,
        open,
      }) => {
        await page.route("**/api/v1/trending", (route) =>
          route.fulfill({
            status: 200,
            contentType: "application/json",
            body: trendingWithLongTitle(),
          }),
        );
        const row = page.locator("li", {
          has: page.locator("a[title^='Chairman of the Standing']"),
        });
        await open("/", { viewport: { width, height }, ready: row });
        const m = await row.evaluate((li) => {
          const title = li.querySelector<HTMLElement>("a > span")!;
          const chip = li.querySelector<HTMLElement>("[data-entry-chip]")!.getBoundingClientRect();
          const views = li
            .querySelector<HTMLElement>("[data-entry-views]")!
            .getBoundingClientRect();
          const rect = li.getBoundingClientRect();
          const line = parseFloat(getComputedStyle(title).lineHeight);
          return {
            rowHeight: rect.height,
            lines: Math.round(title.getBoundingClientRect().height / line),
            chipOff: Math.abs(chip.top + chip.height / 2 - (rect.top + rect.height / 2)),
            viewsOff: Math.abs(views.top + views.height / 2 - (rect.top + rect.height / 2)),
          };
        });
        if (width < 768) {
          expect(m.lines).toBe(2);
          expect(m.rowHeight).toBeGreaterThan(48);
        } else {
          expect(m.lines).toBe(1);
          expect(m.rowHeight).toBeCloseTo(48, 0);
        }
        expect(m.chipOff).toBeLessThanOrEqual(1.5);
        expect(m.viewsOff).toBeLessThanOrEqual(1.5);
      });
    }
  });
});
