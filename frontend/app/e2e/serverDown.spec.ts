import type { Page } from "@playwright/test";
import { test, expect, lightOnly, only } from "./support";

type Failure = "502" | "abort";

/**
 * Fails the given API calls until the returned switch is turned off.
 * Routes registered later win, so this sits on top of mockApi.
 */
async function failApi(page: Page, pattern: RegExp, failure: Failure) {
  const state = { down: true, hits: 0 };
  await page.route(pattern, async (route) => {
    if (!state.down) {
      await route.fallback();
      return;
    }
    state.hits += 1;
    if (failure === "abort") {
      await route.abort("connectionrefused");
      return;
    }
    await route.fulfill({
      status: 502,
      contentType: "text/html",
      body: "<html>Bad Gateway</html>",
    });
  });
  return state;
}

const HOME_CALLS = /\/api\/v1\/(trending|live|dossiers)(\?|$)/;
const ALL_CALLS = /\/api\/v1\//;

// The failure modes are not width dependent, so the tests run on the narrowest and one wide project.
test.describe("server down", only("mobile-390", "desktop-1440"), () => {
  lightOnly(() => {
    for (const failure of ["502", "abort"] as const) {
      test.describe(failure, () => {
        test("Home: the graph frame carries the message and Retry, the counters say unknown, Retry recovers", async ({
          page,
          open,
        }) => {
          const state = await failApi(page, HOME_CALLS, failure);
          const frame = page.locator("[data-plate-error]");
          await open("/", { ready: frame });
          await expect(frame.getByText("The server is unavailable")).toBeVisible();
          const detail = frame.getByText("Try again in a moment.");
          await expect(detail).toBeVisible();
          expect(await detail.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
          const box = (await frame.boundingBox())!;
          expect(Math.abs(box.width - box.height)).toBeLessThan(2);
          await expect(page.getByText("Wikipedia is unavailable")).toHaveCount(0);
          await expect(page.getByText("None built yet")).toHaveCount(0);

          const text = await page.getByRole("group", { name: "Today's counters" }).innerText();
          expect(text).toMatch(/Dossiers stored[\s\S]*unknown/);
          expect(text).toMatch(/Top dossier today[\s\S]*unknown/);
          expect(text).not.toContain("...");
          expect(text).not.toMatch(/built today/);

          const before = state.hits;
          state.down = false;
          await frame.getByRole("button", { name: "Retry" }).click();
          await expect(frame).toHaveCount(0);
          expect(state.hits).toBeGreaterThanOrEqual(before);
          await expect(page.getByText("Plate 1.")).toBeVisible();
        });

        test("Dossiers: chips read unknown above the error, Retry recovers", async ({
          page,
          open,
        }) => {
          const state = await failApi(page, /\/api\/v1\/dossiers(\?|$)/, failure);
          await open("/t/", { ready: page.getByText("Could not load dossiers.") });
          for (const label of [
            "All unknown",
            "Up to date unknown",
            "Out of date unknown",
            "Not checked unknown",
          ]) {
            await expect(page.getByText(label, { exact: true })).toBeVisible();
          }
          await expect(page.getByText(/^All 0$/)).toHaveCount(0);
          state.down = false;
          await page.getByRole("button", { name: "Retry" }).click();
          await expect(page.getByText(/^All \d+$/)).toBeVisible();
          await expect(page.getByText("Could not load dossiers.")).toHaveCount(0);
        });

        test("the dossier page says the server is unavailable and its detail fits; an unbuilt topic and machines do not blame Wikipedia", async ({
          page,
          open,
        }) => {
          await failApi(page, ALL_CALLS, failure);
          await open("/t/Lizzie_Borden", { ready: page.getByText("The server is unavailable") });
          const detail = page.getByText("Try again in a moment.");
          await expect(detail).toBeVisible();
          expect(await detail.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
          await expect(page.getByText("Wikipedia is unavailable")).toHaveCount(0);
          await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();

          await open("/t/No_Such_Article_Xyz", {
            ready: page.getByText("The server is unavailable"),
          });
          await open("/machines");
          await expect(page.getByText("Wikipedia is unavailable")).toHaveCount(0);
        });
      });
    }
  });
});
