import type { Page, Request } from "@playwright/test";
import { test, expect, eachTheme } from "./support";
import { contrastOf } from "./contrast";

/** The title in a build request's JSON body, or null. */
function postedTitle(request: Request): unknown {
  const body: unknown = request.postDataJSON();
  return typeof body === "object" && body !== null && "title" in body ? body.title : null;
}

const searchBox = (page: Page) =>
  page.getByRole("combobox", { name: "Build a dossier for a topic" });

eachTheme(() => {
  test.describe("Home search suggestions", () => {
    test("lists up to 5 titles after 3 characters and a quiet moment", async ({ page, open }) => {
      await page.clock.install();
      await open("/", { ready: searchBox(page) });
      const box = searchBox(page);
      const searches: string[] = [];
      page.on("request", (request) => {
        if (request.url().includes("/api/v1/search")) searches.push(request.url());
      });
      await box.click();
      await box.pressSequentially("je");
      await page.clock.runFor(500);
      expect(searches).toHaveLength(0);
      await expect(box).toHaveAttribute("aria-expanded", "false");
      await box.pressSequentially("sus", { delay: 40 });
      const options = page.getByRole("option");
      await expect(options.first()).toBeVisible();
      expect(await options.count()).toBeLessThanOrEqual(5);
      expect(await options.count()).toBeGreaterThan(1);
      await expect(box).toHaveAttribute("aria-expanded", "true");
      // One request for the whole burst of typing, not one per key.
      expect(searches).toHaveLength(1);
      expect(
        await page.getByRole("listbox").evaluate((el) => getComputedStyle(el).backgroundColor),
      ).not.toMatch(/rgba\(0, 0, 0, 0\)/);
      expect(await contrastOf(page, '[role="option"] span')).toBeGreaterThanOrEqual(4.5);
    });

    test("arrow keys move the highlight, Enter builds the highlighted title", async ({
      page,
      open,
    }) => {
      await open("/", { ready: searchBox(page) });
      const box = searchBox(page);
      await box.fill("jesus");
      const options = page.getByRole("option");
      await expect(options.first()).toBeVisible();
      await box.press("ArrowDown");
      const first = options.nth(0);
      await expect(first).toHaveAttribute("aria-selected", "true");
      const firstId = await first.getAttribute("id");
      await expect(box).toHaveAttribute("aria-activedescendant", firstId ?? "");
      await box.press("ArrowDown");
      await expect(options.nth(1)).toHaveAttribute("aria-selected", "true");
      await expect(first).toHaveAttribute("aria-selected", "false");
      expect(
        await contrastOf(page, '[role="option"][aria-selected="true"] span'),
      ).toBeGreaterThanOrEqual(4.5);
      await box.press("ArrowUp");
      await box.press("ArrowUp");
      const last = options.nth((await options.count()) - 1);
      await expect(last).toHaveAttribute("aria-selected", "true");
      const title = (await last.locator("span.truncate").first().innerText()).trim();
      const posted = page.waitForRequest(
        (request) => request.method() === "POST" && request.url().includes("/api/v1/dossiers"),
      );
      await box.press("Enter");
      const request = await posted;
      expect(postedTitle(request)).toBe(title);
    });

    test("Escape closes the list and keeps the text; a click on a title builds it", async ({
      page,
      open,
    }) => {
      await open("/", { ready: searchBox(page) });
      const box = searchBox(page);
      await box.fill("jesus");
      await expect(page.getByRole("option").first()).toBeVisible();
      await box.press("Escape");
      await expect(page.getByRole("option")).toHaveCount(0);
      await expect(box).toHaveAttribute("aria-expanded", "false");
      await expect(box).toHaveValue("jesus");
      await box.press("ArrowDown");
      await expect(page.getByRole("option").first()).toBeVisible();
      await expect(box).toHaveAttribute("aria-expanded", "true");
      await box.press("Escape");
      await expect(page.getByRole("option")).toHaveCount(0);
      await box.press("x");
      await box.press("Backspace");
      await expect(page.getByRole("option").first()).toBeVisible();
      const target = page.getByRole("option").nth(2);
      const title = (await target.locator("span.truncate").first().innerText()).trim();
      const posted = page.waitForRequest(
        (request) => request.method() === "POST" && request.url().includes("/api/v1/dossiers"),
      );
      await target.click();
      expect(postedTitle(await posted)).toBe(title);
    });

    test("built and not built suggestions share one chip width and weight", async ({
      page,
      open,
    }) => {
      await open("/", { ready: searchBox(page) });
      await searchBox(page).fill("jesus");
      const options = page.getByRole("option");
      await expect(options.first()).toBeVisible();
      const chips = await options.evaluateAll((els) =>
        els.map((el) => {
          const chip = el.querySelector("span.shrink-0 > span")!;
          const cs = getComputedStyle(chip);
          return {
            text: chip.textContent,
            width: Math.round(chip.getBoundingClientRect().width),
            size: cs.fontSize,
            weight: cs.fontWeight,
          };
        }),
      );
      expect(chips.length).toBeGreaterThan(1);
      expect(chips.map((c) => c.text)).toContain("Not built");
      expect(new Set(chips.map((c) => c.width)).size).toBe(1);
      expect(new Set(chips.map((c) => c.weight + c.size)).size).toBe(1);
    });
  });

  test("a title with no dossier says what Enter does, in the row and the live region", async ({
    page,
    open,
  }) => {
    await open("/", { ready: searchBox(page) });
    const box = searchBox(page);
    await box.fill("jesus");
    const options = page.getByRole("option");
    await expect(options.first()).toBeVisible();
    await expect(options.nth(1)).toContainText("Enter builds it");
    await expect(options.nth(1)).toContainText("Not built");
    await box.press("ArrowDown");
    await box.press("ArrowDown");
    await expect(options.nth(1)).toHaveAttribute("aria-selected", "true");
    await expect(page.locator("#live-region")).toHaveText(
      "Mary, mother of Jesus, not built yet, Enter builds it",
    );
    expect(
      await contrastOf(page, '[role="option"][aria-selected="true"] span'),
    ).toBeGreaterThanOrEqual(4.5);
  });

  test("a Ready title ranks first even when the API lists it after unbuilt look-alikes", async ({
    page,
    open,
  }) => {
    await open("/", { ready: searchBox(page) });
    const rows = [
      { page_id: 11, title: "Lizzie Borden House", description: "Museum", dossier_state: "none" },
      { page_id: 12, title: "Lizzie Borden Trial", description: "Trial", dossier_state: "none" },
      { page_id: 13, title: "Lizzie Borden (film)", dossier_state: "none" },
      {
        page_id: 14,
        title: "Lizzie Borden",
        description: "American woman",
        dossier_state: "ready",
      },
      { page_id: 15, title: "Lizzie Borden in popular culture", dossier_state: "none" },
    ];
    await page.route(/\/api\/v1\/search(\?[^/]*)?$/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ query: "lizzie b", results: rows }),
      });
    });
    const box = searchBox(page);
    await box.fill("Lizzie B");
    const options = page.getByRole("option");
    await expect(options).toHaveCount(5);
    const titles = await options.evaluateAll((els) =>
      els.map((el) => el.querySelector("span.truncate")?.textContent ?? ""),
    );
    expect(titles[0]).toBe("Lizzie Borden");
    expect(titles.slice(1)).toEqual([
      "Lizzie Borden House",
      "Lizzie Borden Trial",
      "Lizzie Borden (film)",
      "Lizzie Borden in popular culture",
    ]);
    await expect(options.first()).not.toContainText("Not built");
    await expect(page.locator("#live-region")).toHaveText("5 suggestions");
    await box.press("ArrowDown");
    await box.press("ArrowDown");
    await expect(page.locator("#live-region")).toHaveText(
      "Lizzie Borden House, not built yet, Enter builds it",
    );
  });

  test("a stored dossier that Wikipedia also ranks is offered once, first, Ready", async ({
    page,
    open,
  }) => {
    await open("/", { ready: searchBox(page) });
    const box = searchBox(page);
    const searches: string[] = [];
    const lists: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes("/api/v1/search")) searches.push(request.url());
      if (/\/api\/v1\/dossiers\?/.test(request.url())) lists.push(request.url());
    });
    await box.click();
    await box.pressSequentially("API", { delay: 40 });
    const options = page.getByRole("option");
    await expect(options).toHaveCount(5);
    const titles = await options.evaluateAll((els) =>
      els.map((el) => el.querySelector("span.truncate")?.textContent),
    );
    expect(titles[0]).toBe("API");
    await expect(options.first()).not.toContainText("Not built");
    await expect(options.first()).toContainText("Ready");
    await expect(options.nth(1)).toContainText("Not built");
    await expect(page.locator("#live-region")).toHaveText("5 suggestions");
    // One request per source for the whole burst of typing.
    expect(searches).toHaveLength(1);
    expect(lists).toHaveLength(1);
    expect(lists[0]).toContain("q=API");
  });

  test("a title in both lists is offered once", async ({ page, open }) => {
    await open("/", { ready: searchBox(page) });
    await page.route(/\/api\/v1\/search(\?[^/]*)?$/, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          query: "API",
          results: [
            { page_id: 43545213, title: "Metal (API)", description: null, dossier_state: "none" },
            { page_id: 27697009, title: "API", description: null, dossier_state: "ready" },
          ],
          did_you_mean: null,
        }),
      }),
    );
    const box = searchBox(page);
    await box.fill("API");
    const options = page.getByRole("option");
    await expect(options).toHaveCount(2);
    await expect(options.first()).toContainText("API");
    await expect(options.first()).toContainText("Ready");
    await expect(options.nth(1)).toContainText("Metal (API)");
  });
});
