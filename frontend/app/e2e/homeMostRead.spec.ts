import type { Page } from "@playwright/test";
import { test, expect, eachTheme } from "./support";
import { readFixtureJson } from "./buildFixture";

const LABEL = "svg[role='group'] text[data-plate-label]";

/** The font-variant-numeric of the first element matching the selector. */
function numerals(page: Page, selector: string): Promise<string> {
  return page
    .locator(selector)
    .first()
    .evaluate((el) => getComputedStyle(el).fontVariantNumeric);
}

const mostRead = (page: Page) => page.getByRole("heading", { name: /^Most read/ });

/** Serves the recorded trending list with the given next_refresh. */
async function routeTrending(page: Page, nextRefresh: string): Promise<void> {
  const trending = readFixtureJson<Record<string, unknown>>("trending.json");
  await page.route("**/api/v1/trending", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ...trending, next_refresh: nextRefresh }),
    });
  });
}

eachTheme(() => {
  test("most-read rows: the badge column is as narrow as a badge, views are right-aligned, rows run by views with no rank column", async ({
    page,
    open,
  }) => {
    await open("/", { ready: mostRead(page) });
    await expect(page.locator("[data-entry-chip]").first()).toBeVisible();
    const widths = await page
      .locator("[data-entry-chip]")
      .evaluateAll((els) => [
        ...new Set(els.map((el) => Math.round(el.getBoundingClientRect().width))),
      ]);
    expect(widths).toHaveLength(1);
    expect(widths[0]).toBeLessThanOrEqual(64);
    const views = page.locator("[data-entry-views]");
    const rights = await views.evaluateAll((els) =>
      els.slice(0, 5).map((el) => Math.round(el.getBoundingClientRect().right)),
    );
    expect(new Set(rights).size).toBe(1);
    // The row position is the rank, so there is no "#" column, and views never rise down the list.
    await expect(page.getByRole("button", { name: "#", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "About the rank" })).toHaveCount(0);
    const figures = await views.evaluateAll((els) =>
      els.map((el) => Number.parseInt((el.textContent ?? "").replaceAll(",", ""), 10)),
    );
    expect(figures.length).toBeGreaterThan(5);
    for (let i = 1; i < figures.length; i += 1) {
      expect(figures[i]).toBeLessThanOrEqual(figures[i - 1]!);
    }
  });

  test("the colour key is one row of swatch buttons inside the figure, with no names beside them", async ({
    page,
    open,
  }) => {
    await open("/", { ready: mostRead(page) });
    const figure = page.locator("figure").first();
    const key = figure.getByRole("group", { name: "Linked groups" });
    await expect(key).toBeVisible();
    await expect(figure.getByText("Linked group", { exact: true })).toHaveCount(0);
    expect(await key.evaluate((el) => (el instanceof HTMLElement ? el.innerText.trim() : ""))).toBe(
      "",
    );
    expect(await figure.locator("span[title]").count()).toBe(0);
    const buttons = key.getByRole("button");
    const count = await buttons.count();
    expect(count).toBeGreaterThan(2);
    for (let i = 0; i < count; i += 1) {
      await expect(buttons.nth(i)).toHaveAccessibleName(/^Articles related to .+/);
      const swatch = await buttons.nth(i).locator('span[aria-hidden="true"]').boundingBox();
      expect(Math.round(swatch!.width)).toBe(12);
      expect(Math.round(swatch!.height)).toBe(12);
    }
    const boxes = await buttons.evaluateAll((els) =>
      els.map((el) => {
        const { left, right, top } = el.getBoundingClientRect();
        return { left, right, top };
      }),
    );
    const frame = (await figure.boundingBox())!;
    expect(new Set(boxes.map((box) => Math.round(box.top))).size).toBe(1);
    for (const box of boxes) {
      expect(box.left).toBeGreaterThanOrEqual(frame.x);
      expect(box.right).toBeLessThanOrEqual(frame.x + frame.width);
    }
  });

  test("a refresh time that has passed reads Refresh overdue", async ({ page, open }) => {
    await routeTrending(page, "2020-01-01T03:00:00Z");
    await open("/", { ready: mostRead(page) });
    const caption = page.locator("main").getByText(/built,.*queued\./);
    await expect(caption).toContainText("Refresh overdue.");
    await expect(caption).not.toContainText("Refreshes");
  });

  test("a refresh time still ahead names its UTC time", async ({ page, open }) => {
    const ahead = new Date(Date.now() + 6 * 3_600_000);
    await routeTrending(page, ahead.toISOString());
    await open("/", { ready: mostRead(page) });
    const clock = `${String(ahead.getUTCHours()).padStart(2, "0")}:${String(ahead.getUTCMinutes()).padStart(2, "0")} UTC`;
    await expect(page.locator("main").getByText(/built,.*queued\./)).toContainText(
      `Refreshes ${clock}.`,
    );
  });

  // Digits are proportional by default, including in headings and graph labels.
  // Cells whose digits must line up, such as the views cell, are tabular.
  test("numerals: proportional in a title link and a graph label, tabular in a views cell", async ({
    page,
    open,
  }) => {
    await open("/", { ready: page.locator(LABEL).first() });
    const nums = {
      title: await numerals(page, "li:has([data-entry-views]) a"),
      label: await numerals(page, LABEL),
      views: await numerals(page, "[data-entry-views]"),
      heading: await numerals(page, "h1"),
    };
    expect(nums.title).toContain("proportional-nums");
    expect(nums.label).toContain("proportional-nums");
    expect(nums.heading).toContain("proportional-nums");
    expect(nums.views).toContain("tabular-nums");
  });
});
