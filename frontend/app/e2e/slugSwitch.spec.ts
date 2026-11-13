import type { Page } from "@playwright/test";
import { eachTheme, expect, test } from "./support";

/** Moves the router to another topic the way Back or a link would, without a page load. */
async function clientNavigate(page: Page, path: string) {
  await page.evaluate((to) => {
    window.history.pushState({}, "", to);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, path);
}

eachTheme(() => {
  test("moving to another topic leaves only that topic's page, once", async ({ page, open }) => {
    await open("/t/Jesus");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Jesus");
    await clientNavigate(page, "/t/Lizzie_Borden");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Lizzie Borden");
    await expect(page.locator('section[id^="s"] [data-section-heading]').first()).toBeVisible();
    await expect(page.locator("main")).toContainText("Lizzie Borden");
    // Exactly one h1 remains, and no heading still names the previous topic.
    await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
    await expect(page.getByRole("heading", { name: "Jesus" })).toHaveCount(0);
  });

  test("moving to another topic after a direct load puts focus on the new h1", async ({
    page,
    open,
  }) => {
    await open("/t/Jesus");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Jesus");
    await clientNavigate(page, "/t/Lizzie_Borden");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Lizzie Borden");
    await expect(page.getByRole("heading", { level: 1 })).toBeFocused();
  });

  test("returning to the first topic after a direct load puts focus on its h1", async ({
    page,
    open,
  }) => {
    await open("/t/Jesus");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Jesus");
    await clientNavigate(page, "/t/Lizzie_Borden");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Lizzie Borden");
    await clientNavigate(page, "/t/Jesus");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Jesus");
    await expect(page.getByRole("heading", { level: 1 })).toBeFocused();
  });
});
