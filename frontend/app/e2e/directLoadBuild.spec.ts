import type { Page } from "@playwright/test";
import { freeze } from "./buildFixture";
import { buildButton, expect, lightOnly, only, test } from "./support";

const BUILDING = "Building this dossier now.";

/** Counts the build requests (POST /api/v1/dossiers) the page sends. */
function countBuildRequests(page: Page): () => number {
  let count = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && /\/api\/v1\/dossiers(\?|$)/.test(request.url())) {
      count += 1;
    }
  });
  return () => count;
}

/** Waits until the page has asked the API about the title and the stored dossier, then lets it settle. */
async function waitForLookups(page: Page, pageId: number) {
  await page.waitForResponse(new RegExp(`/api/v1/dossiers/${pageId}(\\?|$)`));
  await page.waitForLoadState("networkidle");
}

lightOnly(() => {
  test.describe("a direct load of a title with no stored dossier", only("desktop-1440"), () => {
    test("shows the title, a sentence and a Build button, and sends no build request", async ({
      page,
      open,
    }) => {
      await freeze(page);
      const builds = countBuildRequests(page);
      const looked = waitForLookups(page, 214796);
      await open("/t/Lizzie_Borden", { ready: buildButton(page) });
      await looked;

      await expect(page.getByRole("heading", { level: 1, name: "Lizzie Borden" })).toBeVisible();
      await expect(
        page.getByText("This topic is not built yet. Build it to read its dossier."),
      ).toBeVisible();
      await expect(page.getByText(BUILDING)).toHaveCount(0);
      expect(builds()).toBe(0);
    });

    test("is noindex and has no canonical", async ({ page, open }) => {
      await freeze(page);
      await open("/t/Lizzie_Borden", { ready: buildButton(page) });
      await expect(page.locator('meta[name="robots"]')).toHaveAttribute(
        "content",
        "noindex,follow",
      );
      await expect(page.locator('link[rel="canonical"]')).toHaveCount(0);
    });

    test("reaches the Build button with the Tab key, shows a focus ring and builds on Enter", async ({
      page,
      open,
    }) => {
      await freeze(page);
      const builds = countBuildRequests(page);
      await open("/t/Lizzie_Borden", { ready: buildButton(page) });
      for (let stops = 0; stops < 30; stops += 1) {
        if (await buildButton(page).evaluate((el) => el === document.activeElement)) {
          break;
        }
        await page.keyboard.press("Tab");
      }
      await expect(buildButton(page)).toBeFocused();
      const ring = await buildButton(page).evaluate((el) => {
        const style = getComputedStyle(el);
        return { style: style.outlineStyle, width: style.outlineWidth };
      });
      expect(ring).toEqual({ style: "solid", width: "2px" });

      await page.keyboard.press("Enter");
      await expect(page.getByText(BUILDING)).toBeVisible();
      expect(builds()).toBe(1);
    });

    test("puts focus on the heading after Build is pressed by keyboard", async ({ page, open }) => {
      await freeze(page);
      await open("/t/Lizzie_Borden", { ready: buildButton(page) });
      await buildButton(page).focus();
      await page.keyboard.press("Enter");
      await expect(page.getByText(BUILDING)).toBeVisible();
      await expect(page.locator("main h1")).toBeFocused();
    });

    test("sends the build request once Build is pressed and shows the building view", async ({
      page,
      open,
    }) => {
      await freeze(page);
      const builds = countBuildRequests(page);
      await open("/t/Lizzie_Borden", { ready: buildButton(page) });
      expect(builds()).toBe(0);

      await buildButton(page).click();
      await expect(page.getByText(BUILDING)).toBeVisible();
      await expect(page.getByRole("button", { name: "Cancel" })).toBeVisible();
      await expect(buildButton(page)).toHaveCount(0);
      expect(builds()).toBe(1);
    });

    test("shows Build again, and sends no build request, after Home and Back", async ({
      page,
      open,
    }) => {
      await freeze(page);
      const builds = countBuildRequests(page);
      await open("/t/Lizzie_Borden", { ready: buildButton(page) });
      await page.getByRole("link", { name: "WKE, Wikipedia Knowledge Explorer, home" }).click();
      await expect(page).toHaveURL(/\/$/);
      await page.waitForLoadState("networkidle");
      const looked = waitForLookups(page, 214796);
      await page.goBack();
      await looked;

      await expect(page).toHaveURL(/\/t\/Lizzie_Borden/);
      await expect(buildButton(page)).toBeVisible();
      await expect(page.getByText(BUILDING)).toHaveCount(0);
      expect(builds()).toBe(0);
    });

    test("with no exact title match shows Build too, and Build leads to the not found answer", async ({
      page,
      open,
    }) => {
      const builds = countBuildRequests(page);
      await open("/t/Nonexistent_Title", { ready: buildButton(page) });
      await page.waitForLoadState("networkidle");
      expect(builds()).toBe(0);

      await buildButton(page).click();
      await expect(page.getByText("No article by that title")).toBeVisible();
      await expect(page.getByText("Did you mean")).toBeVisible();
      expect(builds()).toBe(1);
    });

    test("shows a failed title search as an error with Retry, not as unbuilt, and sends no build request", async ({
      page,
      open,
    }) => {
      let limited = true;
      await page.route(/\/api\/v1\/search(\?[^/]*)?$/, (route) => {
        if (!limited) {
          return route.fallback();
        }
        return route.fulfill({
          status: 429,
          contentType: "application/problem+json",
          body: JSON.stringify({
            type: "about:blank",
            title: "Too Many Requests",
            status: 429,
            code: "rate_limited",
            request_id: "spec-search-429",
          }),
        });
      });
      const builds = countBuildRequests(page);
      await open("/t/Jesus", { ready: page.getByText("Request ID: spec-search-429") });
      await expect(buildButton(page)).toHaveCount(0);
      await expect(page.getByText("This topic is not built yet")).toHaveCount(0);

      limited = false;
      await page.getByRole("button", { name: "Retry" }).click();
      await expect(page.locator('section[id^="s"] h2').first()).toBeVisible();
      expect(builds()).toBe(0);
    });

    test("opens a stored dossier without a build request", async ({ page, open }) => {
      const builds = countBuildRequests(page);
      await open("/t/Jesus", { ready: page.locator('section[id^="s"] h2').first() });
      await expect(buildButton(page)).toHaveCount(0);
      expect(builds()).toBe(0);
    });

    test("shows a failing dossier request as an error, not as unbuilt", async ({ page, open }) => {
      await page.route(/\/api\/v1\/dossiers\/(\d+)(\?[^/]*)?$/, (route) =>
        route.fulfill({
          status: 500,
          contentType: "application/problem+json",
          body: JSON.stringify({
            type: "about:blank",
            title: "Internal Server Error",
            status: 500,
            code: "internal",
            request_id: "spec-direct-500",
          }),
        }),
      );
      const builds = countBuildRequests(page);
      await open("/t/Lizzie_Borden", { ready: page.getByText("Request ID: spec-direct-500") });
      await expect(buildButton(page)).toHaveCount(0);
      expect(builds()).toBe(0);
    });
  });

  test.describe("arriving by a navigation inside the app", only("desktop-1440"), () => {
    test("a link to a title with no stored dossier builds it at once", async ({ page, open }) => {
      await freeze(page);
      const builds = countBuildRequests(page);
      await open("/t/", { ready: page.locator("table tbody tr").first() });
      await page.getByRole("link", { name: "Lizzie Borden", exact: true }).first().click();

      await expect(page).toHaveURL(/\/t\/Lizzie_Borden/);
      await expect(page.getByText(BUILDING)).toBeVisible();
      await expect(buildButton(page)).toHaveCount(0);
      expect(builds()).toBe(1);
    });

    test("a move to another title on the mounted page builds it at once", async ({
      page,
      open,
    }) => {
      await freeze(page);
      // The first title gets the not found answer, whose Did you mean links lead to other titles.
      await page.route(/\/api\/v1\/dossiers(\?[^/]*)?$/, async (route) => {
        const body: unknown = route.request().postDataJSON();
        const title = typeof body === "object" && body !== null && "title" in body && body.title;
        if (route.request().method() !== "POST" || title !== "Nonexistent Title") {
          await route.fallback();
          return;
        }
        await route.fulfill({
          status: 404,
          contentType: "application/problem+json",
          body: JSON.stringify({
            type: "about:blank",
            title: "Not Found",
            status: 404,
            code: "not_found",
            request_id: "spec-slug-move",
          }),
        });
      });
      await page.route(/\/api\/v1\/search(\?[^/]*)?$/, async (route) => {
        const query = new URL(route.request().url()).searchParams.get("q") ?? "";
        if (!/^nonexistent/i.test(query)) {
          await route.fallback();
          return;
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            query,
            results: [{ page_id: 214796, title: "Lizzie Borden", dossier_state: "none" }],
          }),
        });
      });
      await open("/t/Nonexistent_Title", { ready: buildButton(page) });
      await buildButton(page).click();
      // The first title's own build request goes out after its title search, so it must be over
      // before the count starts.
      await expect(page.getByText("No article by that title")).toBeVisible();
      const builds = countBuildRequests(page);
      await page.getByRole("link", { name: "Lizzie Borden" }).first().click();

      await expect(page).toHaveURL(/\/t\/Lizzie_Borden/);
      await expect(page.getByText(BUILDING)).toBeVisible();
      await expect(buildButton(page)).toHaveCount(0);
      expect(builds()).toBe(1);
    });

    test("the search on Home builds at once", async ({ page, open }) => {
      await freeze(page);
      await open("/");
      await page.getByLabel("Build a dossier for a topic").fill("Jesus");
      await page.getByRole("button", { name: "Build", exact: true }).click();

      await expect(page).toHaveURL(/\/t\/Jesus/);
      await expect(page.getByText(BUILDING)).toBeVisible();
      await expect(buildButton(page)).toHaveCount(0);
    });
  });
});
