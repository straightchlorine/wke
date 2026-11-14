import type { Page } from "@playwright/test";
import { withFreshness } from "./buildFixture";
import { dossierBody } from "./mockApi";
import { eachTheme, expect, only, test } from "./support";

// A freshness chip that carries an explanation holds its (i) inside, at the
// right end, and the whole chip is the tooltip trigger. No separate (i) sits
// beside a chip.

const LABEL = /^(Up to date|Out of date|Stale|Not checked)/;

/** Describes every visible freshness chip: its text, whether it is a tooltip trigger, where its (i) sits, and how many info buttons stand beside it. */
function chips(page: Page) {
  return page.evaluate((source) => {
    const label = new RegExp(source);
    // oxlint-disable-next-line unicorn/consistent-function-scoping -- the callback runs in the page, so its helpers cannot live outside it
    const visible = (el: Element) => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden";
    };
    // oxlint-disable-next-line unicorn/consistent-function-scoping -- the callback runs in the page, so its helpers cannot live outside it
    const own = (el: Element) => {
      const copy = el.cloneNode(true);
      if (!(copy instanceof Element)) {
        return "";
      }
      copy.querySelectorAll("[role=tooltip], [aria-hidden=true]").forEach((n) => n.remove());
      return (copy.textContent ?? "").trim();
    };
    return [...document.querySelectorAll("button.rounded-1, span.rounded-1")]
      .filter((el) => visible(el) && label.test(own(el)))
      .map((el) => {
        const box = el.getBoundingClientRect();
        const glyph = el.querySelector("span[aria-hidden=true]");
        const g = glyph?.getBoundingClientRect();
        const wrapper = el.parentElement!;
        const others = [...wrapper.parentElement!.querySelectorAll("button, .rounded-full")].filter(
          (n) =>
            !el.contains(n) &&
            !wrapper.contains(n) &&
            n.closest("td, [data-record-row], [data-top-dossier]") ===
              el.closest("td, [data-record-row], [data-top-dossier]"),
        );
        return {
          text: own(el),
          trigger: el.tagName === "BUTTON",
          hasGlyph: g != null,
          glyphInside:
            g != null &&
            g.left >= box.left &&
            g.right <= box.right &&
            g.top >= box.top &&
            g.bottom <= box.bottom,
          glyphAtRightEnd:
            g != null && box.right - g.right < 14 && g.left > box.left + box.width / 2,
          siblingInfoDots: wrapper.querySelectorAll(
            "button[aria-label^='About'], button[aria-label='More information']",
          ).length,
          neighbours: others.filter((n) => n.getAttribute("aria-label")?.startsWith("About"))
            .length,
        };
      });
  }, LABEL.source);
}

test.describe("freshness chips", only("desktop-1440"), () => {
  test.use({ paused: true });
  eachTheme(() => {
    test("Dossiers table: the column header explains Not checked once, so a row's chip is plain and has no (i) beside it", async ({
      page,
      open,
    }) => {
      await open("/t?freshness=not_checked");
      await expect(page.locator("tbody").getByText("Not checked").first()).toBeVisible();
      const found = await chips(page);
      expect(
        found.some((c) => c.text.startsWith("Not checked")),
        "the fixture has Not checked rows",
      ).toBe(true);
      for (const chip of found) {
        expect(chip.trigger, `${chip.text} carries no explanation of its own`).toBe(false);
        expect(chip.hasGlyph).toBe(false);
        expect(chip.siblingInfoDots, `${chip.text}: no (i) beside the chip`).toBe(0);
      }
      await expect(
        page.locator("thead").getByRole("button", { name: /Freshness|freshness/ }),
      ).toHaveCount(1);
    });

    test("Dossier source record: the Freshness row holds one chip with the (i) inside, hover and focus open its tooltip", async ({
      page,
      open,
    }) => {
      const body = dossierBody(
        "dossier_1095706_8000.json",
        withFreshness({
          state: "fresh",
          source: "poll",
          edits_since: 0,
          checked_at: "2026-09-28T16:18:40Z",
        }),
      );
      await page.route(/\/api\/v1\/dossiers\/1095706(\?[^/]*)?$/, async (route) => {
        await route.fulfill({ status: 200, contentType: "application/json", body });
      });
      await open("/t/Jesus");
      const row = page
        .locator("[data-record-row]")
        .filter({ hasText: /^Freshness/ })
        .filter({ visible: true });
      await expect(row).toHaveCount(1);
      const found = await chips(page);
      expect(found).toHaveLength(1);
      expect(found[0]).toMatchObject({
        text: "Up to date",
        trigger: true,
        glyphInside: true,
        glyphAtRightEnd: true,
        siblingInfoDots: 0,
      });
      const chip = row.locator("button");
      await chip.hover();
      await expect(page.getByRole("tooltip").filter({ visible: true })).toContainText(
        /Checked 2026-09-28, 16:18 UTC\. WKE asks Wikipedia for the newest revision/,
      );
      await page.mouse.move(2, 2);
      await expect(page.getByRole("tooltip").filter({ visible: true })).toHaveCount(0);
      await chip.focus();
      await expect(page.getByRole("tooltip").filter({ visible: true })).toContainText(
        /Checked 2026-09-28/,
      );
    });

    test("Home counters: the freshness chip is plain, with no (i) inside or beside it", async ({
      page,
      open,
    }) => {
      await open("/");
      await expect(page.locator("[data-top-dossier]")).toBeVisible();
      const found = await chips(page);
      expect(found.length).toBeGreaterThan(0);
      for (const chip of found) {
        expect(chip).toMatchObject({
          trigger: false,
          hasGlyph: false,
          siblingInfoDots: 0,
          neighbours: 0,
        });
      }
    });
  });
});
