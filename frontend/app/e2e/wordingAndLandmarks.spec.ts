import { test, expect, lightOnly, only } from "./support";
import { freshnessChip, mockFreshness } from "./readingSection";
import { trackErrors, assertNoErrors } from "./errorTracking";

// The For machines example wording, and the freshness (i) that stays with its text.

lightOnly(() => {
  test.describe("wording and landmarks", () => {
    test("For machines: an example that has not been requested does not say it is waiting", async ({
      page,
      open,
    }) => {
      // The handler never responds, so once the example is requested it stays in its waiting state.
      await page.route(/\/api\/v1\/dossiers\/\d+\.md(\?[^/]*)?$/, () => {});
      await open("/machines");
      const pre = page.locator("section#markdown pre").last();
      await expect(pre).toContainText("Loads when scrolled into view.");
      await expect(pre).not.toContainText("Waiting for the API");
      await page.locator("section#markdown").scrollIntoViewIfNeeded();
      await expect(pre).toContainText("Waiting for the API");
    });
  });
});

test(
  "dossier at 390: the freshness (i) sits inside its chip, on the row of the chip's text",
  only("mobile-390"),
  async ({ page, open }) => {
    const errors = trackErrors(page);
    // The recorded build has no freshness source; a polled one adds the "checked" time to the tooltip.
    await mockFreshness(page, "dossier_1095706_8000.json", {
      state: "fresh",
      source: "poll",
      edits_since: 0,
      checked_at: "2026-09-29T12:00:00Z",
    });
    await open("/t/Jesus");
    await expect(page.locator('section[id^="s"] [data-section-heading]')).toHaveCount(46);
    const chip = freshnessChip(page);
    const [chipBox, glyphBox, textBox] = await Promise.all([
      chip.boundingBox(),
      chip.locator("span[aria-hidden=true]").boundingBox(),
      chip.evaluate((el) => {
        const range = document.createRange();
        range.setStart(el.firstChild!, 0);
        range.setEnd(el.firstChild!, el.firstChild!.textContent!.length);
        const r = range.getBoundingClientRect();
        return { x: r.x, y: r.y, width: r.width, height: r.height };
      }),
    ]);
    expect(chipBox).not.toBeNull();
    expect(glyphBox).not.toBeNull();
    if (chipBox && glyphBox) {
      expect(
        Math.abs(glyphBox.y + glyphBox.height / 2 - (textBox.y + textBox.height / 2)),
      ).toBeLessThanOrEqual(6);
      expect(glyphBox.x).toBeGreaterThan(textBox.x);
      expect(glyphBox.x + glyphBox.width).toBeLessThanOrEqual(chipBox.x + chipBox.width);
    }
    assertNoErrors(errors);
  },
);
