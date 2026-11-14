import { test, expect, eachTheme, only } from "./support";
import { dossierBody } from "./mockApi";
import { withFreshness } from "./buildFixture";
import { trackErrors, assertNoErrors } from "./errorTracking";

// The glossary words in the page copy, the one footer landmark on dossier pages, and the freshness (i)
// that stays with its text.

eachTheme(() => {
  test.describe("wording and landmarks", () => {
    test("Home: the machine strip says passages", async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/", { ready: page.locator("figure").first() });
      await expect(page.locator("main")).not.toContainText("packed chunks");
      await expect(page.locator("main")).toContainText("sections, citations and passages");
      await expect(page.locator("main")).toContainText("sections grouped by topic");
      assertNoErrors(errors);
    });

    test("dossier: one contentinfo landmark outside main, in both states", async ({
      page,
      open,
    }) => {
      const errors = trackErrors(page);
      await open("/t/Jesus");
      await expect(page.locator('section[id^="s"] [data-section-heading]')).toHaveCount(46);
      const footer = page.getByRole("contentinfo");
      await expect(footer).toHaveCount(1);
      await expect(footer).toContainText("Jesus");
      expect(await footer.evaluate((el) => el.closest("main") === null)).toBe(true);
      await expect(page.locator("main")).not.toContainText(
        "Wikipedia Knowledge Explorer turns one Wikipedia article",
      );
      await page.getByRole("link", { name: "Dossiers", exact: true }).first().click();
      await expect(page.getByRole("contentinfo")).toHaveCount(1);
      assertNoErrors(errors);
    });

    test("dossier: no leaked words in the key, the lead meta or the Contents", async ({
      page,
      open,
    }) => {
      const errors = trackErrors(page);
      await open("/t/Jesus");
      await expect(page.locator('section[id^="s"] [data-section-heading]')).toHaveCount(46);
      const body = page.locator("main");
      await expect(body).not.toContainText("seed article");
      await expect(body).not.toContainText("the lead is its own");
      await expect(
        page
          .locator('nav[aria-label="Contents"], nav[aria-label="Sections"]')
          .getByText("heading", { exact: true }),
      ).toHaveCount(0);
      await expect(page.locator("section#s1")).toContainText("the lead has no model summary");
      await expect(
        page.locator('figure:has-text("Plate 1.") [role="tooltip"]').filter({ hasText: "Method" }),
      ).toContainText("similarity to this article");
      assertNoErrors(errors);
    });

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
    await page.route(/\/api\/v1\/dossiers\/1095706(\?[^/]*)?$/, async (route) => {
      const body = dossierBody(
        "dossier_1095706_8000.json",
        withFreshness({
          state: "fresh",
          source: "poll",
          edits_since: 0,
          checked_at: "2026-09-29T12:00:00Z",
        }),
      );
      await route.fulfill({ status: 200, contentType: "application/json", body });
    });
    await open("/t/Jesus");
    await expect(page.locator('section[id^="s"] [data-section-heading]')).toHaveCount(46);
    const chip = page
      .locator("[data-record-row]")
      .filter({ hasText: /^Freshness/ })
      .filter({ visible: true })
      .locator("button");
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
