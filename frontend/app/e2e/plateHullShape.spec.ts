import { fixtureObject } from "./fixtureObject";
import { expect, lightOnly, only, test } from "./support";

// At every desktop width a group of three or more dots keeps a two-dimensional outline instead of collapsing to a line under the stats chip.
// A two-dot group is drawn as a capsule, and no outline's short side may fall below MIN_HULL_SIDE_PX.

const MIN_HULL_SIDE_PX = 24;
const SIZES = [
  { width: 1024, height: 768 },
  { width: 1280, height: 800 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
];

// Every test here sets its own viewport, so it runs only on the desktop-1440 project.
test.describe("Home graph outlines", only("desktop-1440"), () => {
  lightOnly(() => {
    for (const { width, height } of SIZES) {
      test(`Home graph at ${width}: no group outline flatter than ${MIN_HULL_SIDE_PX} px`, async ({
        page,
        open,
      }) => {
        // A recorded day whose Lizzie Borden group lands under the stats chip.
        const base = fixtureObject("trending.json");
        const day = fixtureObject("trending-top-right-group.json");
        const baseTopics = Array.isArray(base.topics) ? base.topics : [];
        const dayTopics = Array.isArray(day.topics) ? day.topics : [];
        await page.route("**/api/v1/trending", (route) =>
          route.fulfill({
            contentType: "application/json",
            body: JSON.stringify({
              ...base,
              edges: day.edges,
              topics: dayTopics.map((topic, i) => ({ ...baseTopics[i], ...topic })),
            }),
          }),
        );
        await open("/", {
          viewport: { width, height },
          ready: page.locator("svg[role='group'] a > circle:first-of-type").first(),
        });
        const hulls = await page.evaluate(() =>
          [...document.querySelector("svg[role='group']")!.querySelectorAll("path")]
            .map((p) => p.getBoundingClientRect())
            .filter((b) => b.width > 20 || b.height > 20)
            .map((b) => ({ w: b.width, h: b.height })),
        );
        expect(hulls.length, "one outline per group of 2 or more: 5 polygons and 3 capsules").toBe(
          8,
        );
        for (const h of hulls) {
          expect(Math.min(h.w, h.h), "hull short side").toBeGreaterThanOrEqual(MIN_HULL_SIDE_PX);
        }
      });
    }
  });
});
