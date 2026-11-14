import type { Page } from "@playwright/test";
import { expect, test } from "./support";

/** Moves the router to another topic the way Back or a link would, without a page load. */
async function clientNavigate(page: Page, path: string) {
  await page.evaluate((to) => {
    window.history.pushState({}, "", to);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, path);
}

test("moving between topics leaves only the current topic's page, focused on its h1", async ({
  page,
  open,
}) => {
  const h1 = page.getByRole("heading", { level: 1 });
  await open("/t/Jesus");
  await expect(h1).toHaveText("Jesus");
  await clientNavigate(page, "/t/Lizzie_Borden");
  await expect(h1).toHaveText("Lizzie Borden");
  await expect(page.locator('section[id^="s"] [data-section-heading]').first()).toBeVisible();
  await expect(page.locator("main")).toContainText("Lizzie Borden");
  // Exactly one h1 remains, and no heading still names the previous topic.
  await expect(h1).toHaveCount(1);
  await expect(page.getByRole("heading", { name: "Jesus" })).toHaveCount(0);
  await expect(h1).toBeFocused();
  await clientNavigate(page, "/t/Jesus");
  await expect(h1).toHaveText("Jesus");
  await expect(h1).toBeFocused();
});
