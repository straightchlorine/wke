import type { Locator, Page } from "@playwright/test";
import { test, expect, eachTheme } from "./support";

function notBuiltHeading(page: Page): Locator {
  return page.getByRole("heading", { level: 1, name: "No article by that title" });
}

eachTheme(() => {
  test.describe("not-found search", () => {
    test("the not-built page mounts the Home search under Did you mean", async ({ page, open }) => {
      await open("/t/Nonexistent_Title", {
        ready: notBuiltHeading(page),
      });
      await expect(page).toHaveTitle(/^No article by that title/);
      await expect(
        page.getByText('No article titled "Nonexistent Title" on en.wikipedia.'),
      ).toBeVisible();
      await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
      const box = page.getByRole("combobox", { name: "Search for a topic" });
      await expect(box).toBeVisible();
      const heading = await page.getByText("Did you mean").first().boundingBox();
      const field = await box.boundingBox();
      expect((field?.y ?? 0) > (heading?.y ?? 0)).toBe(true);
      await box.fill("jesus");
      const options = page.getByRole("option");
      await expect(options.first()).toBeVisible();
      await expect(options.first()).toContainText("Jesus");
      await expect(options.nth(1)).toContainText("Enter builds it");
      await expect(options.nth(1)).toContainText("Not built");
      await expect(page.locator("#live-region")).toHaveText(/suggestions?/);
      await box.press("ArrowDown");
      await box.press("Enter");
      await expect(page).toHaveURL(/\/t\/Jesus/);
    });

    test("the not-built page: an unhighlighted Enter opens the typed title", async ({
      page,
      open,
    }) => {
      await open("/t/Nonexistent_Title");
      const box = page.getByRole("combobox", { name: "Search for a topic" });
      await box.fill("Kamchatka");
      await expect(page.getByRole("option").first()).toBeVisible();
      await box.press("Escape");
      await box.press("Enter");
      await expect(page).toHaveURL(/\/t\/Kamchatka/);
    });

    test("the plain 404 lists suggestions after 3 letters and Enter opens the pick", async ({
      page,
      open,
    }) => {
      await open("/nope/nothing");
      const box = page.getByRole("combobox", { name: "Search for a topic" });
      await box.fill("jes");
      const options = page.getByRole("option");
      await expect(options.first()).toBeVisible();
      await expect(options.nth(1)).toContainText("Enter builds it");
      await expect(options.nth(1)).toContainText("Not built");
      await expect(page.locator("#live-region")).toHaveText(/suggestions?/);
      await box.press("ArrowDown");
      await box.press("ArrowDown");
      await expect(page.locator("#live-region")).toHaveText(
        "Mary, mother of Jesus, not built yet, Enter builds it",
      );
      await box.press("Enter");
      await expect(page).toHaveURL(/\/t\/Mary,_mother_of_Jesus/);
    });
  });

  test("the plain 404 page links to Today's index and not to Home", async ({ page, open }) => {
    await open("/nope/nothing");
    await expect(
      page.getByRole("main").getByRole("link", { name: "Today's index", exact: true }),
    ).toHaveAttribute("href", "/");
    await expect(
      page.getByRole("main").getByRole("link", { name: "Home", exact: true }),
    ).toHaveCount(0);
  });

  test("a search button says Build, and the not-found pages agree with Home", async ({
    page,
    open,
  }) => {
    await open("/");
    await expect(page.getByRole("button", { name: "Build", exact: true })).toBeVisible();
    await open("/nope/nothing", {
      ready: page.getByRole("heading", { level: 1, name: "Page not found" }),
    });
    await expect(page.getByRole("button", { name: "Build", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Open", exact: true })).toHaveCount(0);
  });

  test.describe("Did you mean rows", () => {
    test("say Enter builds it on a keyboard device", async ({ page, open }) => {
      await open("/t/Nonexistent_Title", { ready: notBuiltHeading(page) });
      const rows = page.locator("main [data-record-row]");
      await expect(rows.first()).toBeVisible();
      const texts = await rows.allTextContents();
      for (const text of texts) {
        expect(text).toMatch(/Not built|Ready|Partial|Building/);
      }
      // The glossary line, never "click": a keyboard device builds with Enter.
      expect(texts.some((text) => text.includes("Enter builds it"))).toBe(true);
      expect(texts.some((text) => text.includes("click builds it"))).toBe(false);
    });

    test.describe("on a touch screen", () => {
      test.use({ hasTouch: true, isMobile: true, viewport: { width: 390, height: 844 } });

      test("say what a tap does", async ({ page, open }) => {
        await open("/t/Nonexistent_Title", { ready: notBuiltHeading(page) });
        const texts = await page.locator("main [data-record-row]").allTextContents();
        expect(texts.some((text) => text.includes("tap builds it"))).toBe(true);
        expect(texts.some((text) => text.includes("click builds it"))).toBe(false);
      });
    });
  });
});
