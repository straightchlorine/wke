import type { Page, Route } from "@playwright/test";
import { test, expect, lightOnly, only } from "./support";
import { dossierBody } from "./mockApi";
import { readFixtureJson, routeBuildJob } from "./buildFixture";
import { trackErrors, assertNoErrors, expectShellRendered } from "./errorTracking";

// Interaction behaviour checked in a real browser, grouped by area.
// Finer details are tested at unit level beside each component and hook.

interface BudgetFixture {
  budget: { used_est_tokens: number; requested: number };
}

const dossier = readFixtureJson<BudgetFixture>("dossier_1095706_8000.json");
// Home links to the dossier of its top trending topic, Lizzie Borden, so its budget figures come from this fixture and not from the Jesus one above.
const topDossier = readFixtureJson<BudgetFixture>("dossier_214796_8000.json");

const PHONE = { width: 390, height: 844 };
const DESKTOP = { width: 1440, height: 900 };

/** Makes the live edit feed report one edit to Lizzie Borden, the top trending topic. */
async function routeLizzie(page: Page): Promise<void> {
  await page.route("**/api/v1/live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        stream: "connected",
        server_time: new Date().toISOString(),
        cursor: 1,
        last_event_at: new Date().toISOString(),
        edits: [
          {
            cursor: 1,
            page_id: 214796,
            title: "Lizzie Borden",
            rev_new: 1377141498,
            rev_old: 1377141497,
            ts: new Date().toISOString(),
            user_kind: "registered",
            byte_delta: 12,
            diff_url: "https://en.wikipedia.org/w/index.php?diff=1377141498&oldid=1377141497",
          },
        ],
        counters: { edits_last_5m: 1, edits_last_1h: 1 },
      }),
    });
  });
}

const graph = (page: Page) => page.locator("svg[role='group']").first();

test.describe("Navigation", () => {
  test(
    "a nav click routes client-side, no document navigation",
    only("mobile-390", "desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/", { ready: graph(page) });
      // A real document navigation replaces window, dropping any property
      // set on it; client-side routing keeps it.
      await page.evaluate(() => {
        Reflect.set(window, "wkeMarker", true);
      });
      await page.getByRole("link", { name: "Dossiers" }).click();
      await expect(page).toHaveURL(/\/t\/?$/);
      expect(await page.evaluate(() => Reflect.has(window, "wkeMarker"))).toBe(true);
      await expectShellRendered(page);
      await expect(page.locator("footer")).toBeVisible();
      await expect(page.locator("main")).toBeVisible();
      assertNoErrors(errors);
    },
  );

  test(
    "a new route scrolls to top; document.title updates and focus moves to the h1",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/", { ready: graph(page) });

      await page.getByRole("link", { name: "Dossiers" }).click();
      await expect(page).toHaveURL(/\/t\/?$/);
      const scrollY = await page.evaluate(() => window.scrollY);
      expect(scrollY).toBe(0);
      await expect(page.locator("main h1")).toBeFocused();
      await expect(page).toHaveTitle(/Dossiers/);
      assertNoErrors(errors);
    },
  );

  test(
    "a direct dossier load does not draw the h1's focus ring",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/t/Jesus");
      // The building placeholder has its own h1 that also reads "Jesus". Waiting for a section heading makes the assertions read the loaded page's h1 instead.
      await expect(page.locator('section[id^="s"] h2').first()).toBeVisible();
      await expect(page.locator("main h1")).toHaveText(/Jesus/);
      const outlineStyle = await page
        .locator("main h1")
        .evaluate((el) => getComputedStyle(el).outlineStyle);
      expect(outlineStyle).toBe("none");
      assertNoErrors(errors);
    },
  );

  test(
    "navigating to a dossier from Home moves focus to its h1",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/", { ready: graph(page) });
      await page.getByRole("button", { name: "Open", exact: true }).click();
      await expect(page).toHaveURL(/\/t\//);
      await expect(page.locator("main h1")).toBeFocused();
      assertNoErrors(errors);
    },
  );

  test(
    "a section chip scrolls the page to its section (390)",
    only("mobile-390"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/t/Jesus", { viewport: PHONE });
      await expect(page.locator('section[id^="s"] h2')).toHaveCount(8);
      const chip = page.locator('nav[aria-label="Sections"] a[href$="#s21"]');
      await chip.click();
      await expect(page.locator("section#s21 h2")).toBeInViewport();
      await expect(page).toHaveURL(/#s21$/);
      assertNoErrors(errors);
    },
  );

  test(
    "a Contents link scrolls the page to its section (1440)",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/t/Jesus", { viewport: DESKTOP });
      await expect(page.locator('section[id^="s"] h2')).toHaveCount(8);
      await page.locator('nav[aria-label="Contents"] a[href$="#s21"]').click();
      await expect(page.locator("section#s21 h2")).toBeInViewport();
      assertNoErrors(errors);
    },
  );

  test("a URL loaded with a hash scrolls to that section once content mounts", async ({
    page,
    open,
  }) => {
    const errors = trackErrors(page);
    await open("/t/Jesus#s21");
    await expect(page.locator('section[id^="s"] h2')).toHaveCount(8, { timeout: 10_000 });
    await expect(page.locator("section#s21 h2")).toBeInViewport({ timeout: 10_000 });
    assertNoErrors(errors);
  });

  test(
    "Back restores the scroll position a hash jump left, Forward returns to it",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/t/Jesus", { viewport: DESKTOP });
      await expect(page.locator('section[id^="s"] h2')).toHaveCount(8);
      await page.locator('nav[aria-label="Contents"] a[href$="#s21"]').click();
      await expect(page.locator("section#s21 h2")).toBeInViewport();
      const scrolledY = await page.evaluate(() => window.scrollY);
      expect(scrolledY).toBeGreaterThan(0);

      const scrollY = () => page.evaluate(() => window.scrollY);
      await page.goBack();
      await expect.poll(scrollY).toBeLessThan(scrolledY);

      await page.goForward();
      await expect
        .poll(async () => Math.abs((await scrollY()) - scrolledY))
        .toBeLessThanOrEqual(50);
      assertNoErrors(errors);
    },
  );

  test(
    "exactly one aria-current=page per page: the nav link, not the wordmark or a breadcrumb",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);

      await open("/");
      await expect(page.locator('[aria-current="page"]')).toHaveCount(1);
      await expect(
        page
          .getByRole("navigation", { name: "Primary" })
          .getByRole("link", { name: "Today's index" }),
      ).toHaveAttribute("aria-current", "page");
      await expect(
        page.getByRole("link", { name: /WKE, Wikipedia Knowledge Explorer, home/ }),
      ).not.toHaveAttribute("aria-current", "page");

      await open("/t/Jesus");
      await expect(page.locator('section[id^="s"] h2')).toHaveCount(8);
      await expect(page.locator('[aria-current="page"]')).toHaveCount(0);
      await expect(
        page
          .getByRole("navigation", { name: "Breadcrumb" })
          .getByRole("link", { name: "Dossiers" }),
      ).not.toHaveAttribute("aria-current", "page");

      await open("/t/");
      const primary = page.getByRole("navigation", { name: "Primary" });
      await expect(primary.getByRole("link", { name: "Dossiers" })).toHaveAttribute(
        "aria-current",
        "page",
      );
      await expect(primary.getByRole("link", { name: "Today's index" })).not.toHaveAttribute(
        "aria-current",
        "page",
      );
      assertNoErrors(errors);
    },
  );

  test(
    "budget choice: ?budget= wins over localStorage, and every dossier link carries it",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await page.addInitScript(() => window.localStorage.setItem("wke-budget", "32000"));
      await open("/?budget=2000", { ready: graph(page) });
      await expect(page.getByRole("radio", { name: "2k", exact: true })).toBeChecked();

      await open("/t/");
      await expect(page.locator("table tbody tr")).toHaveCount(30);
      const firstRowLink = page
        .locator("table tbody tr")
        .first()
        .locator("td")
        .first()
        .locator("a");
      await expect(firstRowLink).toHaveAttribute("href", /\?budget=/);
      assertNoErrors(errors);
    },
  );
});

test.describe("Tooltips (InfoDot)", only("mobile-390"), () => {
  test.use({ hasTouch: true, viewport: PHONE });

  test("touch: tap toggles via data-open, tap elsewhere closes", async ({ page, open }) => {
    const errors = trackErrors(page);
    await open("/", { ready: graph(page) });

    const dot = page.locator("button[aria-label='About the token budget']").first();
    const wrapper = dot.locator("xpath=..");
    await expect(wrapper).toHaveAttribute("data-open", "false");
    await dot.tap();
    await expect(wrapper).toHaveAttribute("data-open", "true");
    await page.locator("h1").tap();
    await expect(wrapper).toHaveAttribute("data-open", "false");

    assertNoErrors(errors);
  });
});

// Below 600px the toolbar is hidden and the HUD's Copy button stands in.
// On a wider screen the toolbar button is selected by class, because its accessible name changes to the copied message after a click.
const COPY_BUTTONS = [
  {
    where: "the toolbar",
    tag: only("tablet-768", "desktop-1440"),
    phone: false,
  },
  { where: "the bottom bar", tag: only("mobile-390"), phone: true },
] as const;

function copyButton(page: Page, phone: boolean) {
  return phone
    ? page.getByLabel("Token budget and copy").getByRole("button")
    : page.locator("button.ml-auto");
}

test.describe("Copy actions", () => {
  for (const { where, tag, phone } of COPY_BUTTONS) {
    test(
      `Copy as context in ${where}: clipboard text and one Toast${phone ? "" : ", label swaps to a token count"}`,
      tag,
      async ({ page, context, open }) => {
        await context.grantPermissions(["clipboard-read", "clipboard-write"]);
        const errors = trackErrors(page);
        await open("/t/Jesus");
        await expect(page.locator('section[id^="s"] h2')).toHaveCount(8);

        const button = copyButton(page, phone);
        await button.click();

        // The bottom bar gets no copy label, so only the toolbar button swaps to the copied message.
        if (!phone) {
          await expect(button).toContainText(
            `Copied ${dossier.budget.used_est_tokens.toLocaleString("en-GB")} dossier tokens`,
          );
        }

        await expect(page.getByRole("status")).toHaveCount(1);
        await expect(page.getByRole("status")).toHaveText(
          new RegExp(
            `Copied as text/markdown, ${dossier.budget.used_est_tokens.toLocaleString("en-GB")} dossier tokens, revision \\d+`,
          ),
        );

        if (!phone) {
          await expect(button).toContainText("Copy as context", { timeout: 2500 });
        }

        const clipboardText = await page.evaluate(() => navigator.clipboard.readText());
        expect(clipboardText.length).toBeGreaterThan(0);
        assertNoErrors(errors);
      },
    );

    test(
      `clipboard refused in ${where}: toast says to press Ctrl+C and the fallback text is selected`,
      tag,
      async ({ page, open }) => {
        // No clipboard-write permission granted: navigator.clipboard.writeText rejects.
        const errors = trackErrors(page);
        await open("/t/Jesus");
        await expect(page.locator('section[id^="s"] h2')).toHaveCount(8);

        await copyButton(page, phone).click();
        await expect(page.getByRole("status")).toHaveText(
          "Copy failed. The text is selected: press Ctrl+C to copy it.",
        );
        const selectionLength = await page.evaluate(
          () => window.getSelection()?.toString().length ?? 0,
        );
        expect(selectionLength).toBeGreaterThan(0);

        expect(errors.console.filter((m) => !m.includes("Failed to load resource"))).toEqual([]);
        expect(errors.page).toEqual([]);
      },
    );
  }

  test(
    "the Top dossier tooltip states the revision and the API's own token count",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/", { ready: graph(page) });

      await page.getByRole("button", { name: /^pinned \d{4}-\d\d-\d\d, \d\d:\d\d UTC$/ }).hover();
      const tip = page.getByRole("tooltip").filter({ hasText: /^Revision \d+, / });
      await expect(tip).toBeVisible();
      await expect(tip).toHaveText(
        new RegExp(
          `, ${topDossier.budget.used_est_tokens.toLocaleString("en-US")} of ${topDossier.budget.requested.toLocaleString("en-US")} tokens$`,
        ),
      );
      assertNoErrors(errors);
    },
  );
});

test.describe("Budget selector", () => {
  test("a number key updates the URL budget", async ({ page, open }) => {
    const errors = trackErrors(page);
    await open("/", { ready: graph(page) });

    await page.locator("h1").click();
    await page.keyboard.press("1");
    await expect(page).toHaveURL(/budget=2000/);
    await expect(page.getByRole("radio", { name: "2k", exact: true })).toBeChecked();
    assertNoErrors(errors);
  });

  test(
    "the label reads Token budget, never bare Budget",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/", { ready: graph(page) });
      await expect(page.getByText("Token budget", { exact: true }).first()).toBeVisible();
      await expect(page.getByText(/^Budget$/)).toHaveCount(0);
      assertNoErrors(errors);
    },
  );

  test(
    "no reload on a budget change; URL uses replaceState so Back leaves the dossier",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/t/");
      await expect(page.locator("table tbody tr")).toHaveCount(30);
      // Loading the URL directly adds a second history entry, because Jesus is not in the dossier list to click.
      // The budget change below must not add a third.
      await open("/t/Jesus");
      await expect(page.locator('section[id^="s"] h2')).toHaveCount(8);

      await page.keyboard.press("1");
      await expect(page).toHaveURL(/budget=2000/);
      await page.goBack();
      await expect(page).toHaveURL(/\/t\/?$/);
      assertNoErrors(errors);
    },
  );

  test(
    "HUD (budget + Copy as context) shows on phones",
    only("mobile-390"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/t/Jesus", { viewport: PHONE });
      await expect(page.locator('section[id^="s"] h2')).toHaveCount(8);
      await expect(page.getByLabel("Token budget and copy")).toBeVisible();
      assertNoErrors(errors);
    },
  );
});

test.describe("Build flow", () => {
  test(
    "empty input does nothing; button is aria-disabled while the POST is in flight",
    only("mobile-390", "desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/", { ready: graph(page) });

      const before = page.url();
      await page.getByRole("button", { name: "Build" }).click();
      await expect(page).toHaveURL(before);

      // The build request is held until the test answers it, so the button can be read while the POST is in flight.
      const held: Route[] = [];
      await page.route(/\/api\/v1\/dossiers(\?[^/]*)?$/, async (route) => {
        if (route.request().method() === "POST") {
          held.push(route);
        } else {
          await route.fallback();
        }
      });
      await page.getByLabel("Build a dossier for a topic").fill("Jesus");
      await page.getByRole("button", { name: "Build" }).click();
      await expect(page.getByRole("button", { name: "Build" })).toHaveAttribute(
        "aria-disabled",
        "true",
      );
      await expect.poll(() => held.length).toBe(1);
      await held[0]!.fulfill({
        status: 200,
        contentType: "application/json",
        body: dossierBody("dossier_1095706_8000.json"),
      });
      assertNoErrors(errors);
    },
  );

  test(
    "202 shows the steps record at once, polls to done, then renders the dossier",
    only("mobile-390", "desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      const build = await routeBuildJob(page, {
        jobId: "spec-job-1",
        pollAfterMs: 60,
        requestId: "spec-not-built-1",
        doneAtPoll: 2,
        progressDone: (polls) => polls,
      });

      await open("/", { ready: graph(page) });
      await page.getByLabel("Build a dossier for a topic").fill("Jesus");
      await page.getByRole("button", { name: "Build" }).click();

      await expect(page).toHaveURL(/\/t\/Jesus/);
      await expect(page.getByText("Building this dossier now.")).toBeVisible();
      await expect(page.getByRole("status").filter({ hasText: /Building/ })).toBeVisible();

      await expect(page.locator('section[id^="s"] h2')).toHaveCount(8, { timeout: 5000 });
      expect(build.polls()).toBeGreaterThanOrEqual(2);
      // The 404 forced above makes the browser log a failed resource load, so those console messages are filtered out.
      expect(errors.console.filter((m) => !m.includes("Failed to load resource"))).toEqual([]);
      expect(errors.page).toEqual([]);
    },
  );

  test(
    "Cancel stops polling and returns to the form",
    only("mobile-390", "desktop-1440"),
    async ({ page, open }) => {
      await page.clock.install();
      const errors = trackErrors(page);
      const build = await routeBuildJob(page, {
        jobId: "spec-job-2",
        pollAfterMs: 200,
        requestId: "spec-not-built-2",
        progressDone: () => 1,
      });

      await open("/", { ready: graph(page) });
      await page.getByLabel("Build a dossier for a topic").fill("Jesus");
      await page.getByRole("button", { name: "Build" }).click();
      await expect(page).toHaveURL(/\/t\/Jesus/);
      await expect(page.getByText("Building this dossier now.")).toBeVisible();

      await page.getByRole("button", { name: "Cancel" }).click();
      await expect(page).toHaveURL(/\/$/);
      const pollsAtCancel = build.polls();
      await page.clock.runFor(500);
      await page.waitForLoadState("networkidle");
      expect(build.polls()).toBe(pollsAtCancel);
      // The 404 forced above makes the browser log a failed resource load, so those console messages are filtered out.
      expect(errors.console.filter((m) => !m.includes("Failed to load resource"))).toEqual([]);
      expect(errors.page).toEqual([]);
    },
  );

  test(
    "429 shows a Retry-After countdown, no automatic retry",
    only("mobile-390", "desktop-1440"),
    async ({ page, open }) => {
      await page.clock.install();
      const errors = trackErrors(page);
      await page.route(/\/api\/v1\/dossiers(\?[^/]*)?$/, async (route) => {
        if (route.request().method() !== "POST") {
          await route.fallback();
          return;
        }
        await route.fulfill({
          status: 429,
          contentType: "application/problem+json",
          body: JSON.stringify({
            type: "about:blank",
            title: "Too Many Requests",
            status: 429,
            code: "rate_limited",
            request_id: "spec-429",
            detail: "Too many builds.",
            retry_after: 5,
          }),
        });
      });

      await open("/", { ready: graph(page) });
      await page.getByLabel("Build a dossier for a topic").fill("Jesus");
      await page.getByRole("button", { name: "Build" }).click();

      const retryButton = page.getByRole("button", { name: /Retry in \d+ s/ });
      await expect(retryButton).toBeVisible();
      await expect(retryButton).toHaveAttribute("aria-disabled", "true");
      await page.clock.runFor(1100);
      await expect(page.getByRole("button", { name: /Retry in \d+ s/ })).toHaveText(
        /Retry in [0-4] s/,
      );

      expect(errors.console.filter((m) => !m.includes("Failed to load resource"))).toEqual([]);
      expect(errors.page).toEqual([]);
    },
  );

  test(
    "404 not_found: panel plus Did you mean, search text kept",
    only("mobile-390", "desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);

      await open("/", { ready: graph(page) });
      await page.getByLabel("Build a dossier for a topic").fill("Nonexistent Title");
      await page.getByRole("button", { name: "Build" }).click();

      await expect(page.getByText("Did you mean")).toBeVisible();
      await expect(page.getByRole("link", { name: "Jesus" })).toBeVisible();
      await expect(page.getByLabel("Build a dossier for a topic")).toHaveValue("Nonexistent Title");

      expect(errors.console.filter((m) => !m.includes("Failed to load resource"))).toEqual([]);
      expect(errors.page).toEqual([]);
    },
  );

  test(
    "409 disambiguation: panel lists the first three candidates with their build state",
    only("mobile-390", "desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/", { ready: graph(page) });
      await page.getByLabel("Build a dossier for a topic").fill("Mercury");
      await page.getByRole("button", { name: "Build" }).click();

      await expect(page.getByText("Several articles match", { exact: true })).toBeVisible();
      await expect(
        page.getByText("'Mercury' is a disambiguation page. Pick one of the candidates."),
      ).toBeVisible();
      await expect(page.getByText("Did you mean")).toBeVisible();
      await expect(page).toHaveURL(/\/$/);
      const links = page.getByRole("link", {
        name: /^(Freddie Mercury|Mercury \(planet\)|Mercury \(element\))$/,
      });
      await expect(links).toHaveText(["Freddie Mercury", "Mercury (planet)", "Mercury (element)"]);
      await expect(links.nth(1)).toHaveAttribute("href", /\/t\/Mercury_\(planet\)/);
      await expect(page.getByText("Mercury Records")).toHaveCount(0);
      await expect(page.getByText("Ready", { exact: true }).first()).toBeVisible();
      await expect(page.getByText("Not built", { exact: true }).first()).toBeVisible();
      await expect(page.getByLabel("Build a dossier for a topic")).toHaveValue("Mercury");

      expect(errors.console.filter((m) => !m.includes("Failed to load resource"))).toEqual([]);
      expect(errors.page).toEqual([]);
    },
  );
});

test.describe("Edit stream", () => {
  test(
    "each live edit row links to its dossier with the selected budget",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      // live.json's edits name none of trending.json's topics, so the live edits table finds no slug for them.
      // An edit to the top trending topic gives the row a dossier to link to.
      await routeLizzie(page);
      await open("/", { ready: graph(page) });
      await expect(page.locator("table tbody").getByText("Lizzie Borden").first()).toBeVisible();

      const links = page.locator("table tbody tr td a");
      const count = await links.count();
      expect(count).toBeGreaterThan(0);
      for (let i = 0; i < count; i++) {
        await expect(links.nth(i)).toHaveAttribute("href", /^\/t\/[^/?]+\?budget=\d+$/);
      }
      assertNoErrors(errors);
    },
  );

  test(
    "Pause swaps its own label to Resume, shows Paused since HH:MM UTC, persists across reload",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/", { ready: graph(page) });

      const pauseButton = page.getByRole("button", { name: "Pause" });
      await pauseButton.click();
      await expect(page.getByRole("button", { name: "Resume" })).toBeVisible();
      await expect(page.getByText(/^Live edits paused since \d{2}:\d{2} UTC$/)).toBeVisible();

      const stored = await page.evaluate(() => window.localStorage.getItem("wke-paused"));
      expect(stored).not.toBeNull();

      await page.reload();
      await expect(graph(page)).toBeVisible();
      await expect(page.getByRole("button", { name: "Resume" })).toBeVisible();
      assertNoErrors(errors);
    },
  );

  test("the Editor column is not drawn under 600px", only("mobile-390"), async ({ page, open }) => {
    const errors = trackErrors(page);
    await open("/", { viewport: PHONE, ready: graph(page) });
    await expect(page.getByText("registered").first()).toBeHidden();
    assertNoErrors(errors);
  });
});

test.describe("Graph", () => {
  test(
    "roving tabindex in rank order; Enter selects the focused node, a second Enter opens it",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/", { viewport: DESKTOP, ready: graph(page) });

      const anchors = page.locator("svg[role='group'] a");
      await expect(anchors.first()).toHaveAttribute("tabindex", "0");
      const count = await anchors.count();
      expect(await anchors.nth(1).getAttribute("tabindex")).toBe("-1");

      await anchors.first().focus();
      await page.keyboard.press("ArrowRight");
      await expect(anchors.nth(1)).toHaveAttribute("tabindex", "0");
      await expect(anchors.first()).toHaveAttribute("tabindex", "-1");

      const href = await anchors.nth(1).getAttribute("href");
      await page.keyboard.press("Enter");
      await expect(page.locator("[data-plate-ring]")).toHaveCount(1);
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(href!.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
      expect(count).toBeGreaterThan(1);
      assertNoErrors(errors);
    },
  );

  test(
    "the graph's aria-label stays under 25 words",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/", { viewport: DESKTOP, ready: graph(page) });
      const label = await page.locator("svg[role='group']").getAttribute("aria-label");
      expect(label).not.toBeNull();
      expect(label!.split(/\s+/).length).toBeLessThan(25);
      assertNoErrors(errors);
    },
  );

  test(
    "reduced motion: node fade-in has no transition",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await page.emulateMedia({ reducedMotion: "reduce" });
      await open("/", { ready: graph(page) });
      const transition = await page
        .locator("svg[role='group']")
        .evaluate((el) => getComputedStyle(el).transitionProperty);
      expect(transition).toBe("none");
      assertNoErrors(errors);
    },
  );
});

test.describe("Formatting", () => {
  test(
    "signed deltas use a true minus sign and record times are UTC",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/", { ready: graph(page) });

      // A signed byte delta starts with a plus sign or the true minus sign, never a hyphen.
      await expect(page.getByText(/^[+\u2212]\d/).first()).toBeVisible();

      // The record line shows the revision timestamp on the UTC clock, not local time.
      await expect(
        page.getByRole("button", { name: /^pinned \d{4}-\d\d-\d\d, \d\d:\d\d UTC$/ }),
      ).toBeVisible();
      assertNoErrors(errors);
    },
  );
});

test.describe("Dossiers rows", () => {
  test(
    "a row is sunken on hover; the revision link has the external-link title",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/t/");
      await expect(page.locator("table tbody tr")).toHaveCount(30);

      const row = page.locator("table tbody tr").first();
      await expect(row).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
      await row.hover();
      await expect(row).not.toHaveCSS("background-color", "rgba(0, 0, 0, 0)");

      const revisionLink = row.locator("a").nth(1);
      await expect(revisionLink).toHaveAttribute(
        "title",
        /Wikipedia revision \d+, opens en\.wikipedia\.org/,
      );
      assertNoErrors(errors);
    },
  );
});

test.describe("Truncation", () => {
  test(
    "graph labels are cut only where the free width asks, full title kept in <title>",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/", { viewport: DESKTOP, ready: graph(page) });

      const labels = page.locator("svg[role='group'] text:not([x^='+']):not([data-hull-label])");
      // The shown text sits in <tspan>s and the test reads the first.
      // A <title> child exists only on a cut label, so it is read apart from the text node's full textContent.
      const results = await labels.evaluateAll((nodes) =>
        nodes.map((node) => ({
          shown: node.querySelector("tspan")?.textContent ?? "",
          full: node.querySelector("title")?.textContent ?? null,
        })),
      );
      expect(results.length).toBeGreaterThan(10);
      for (const { shown, full } of results) {
        if (full == null) {
          // A label without a <title> is whole, so it must not end in an ellipsis.
          expect(shown.endsWith("...")).toBe(false);
        }
        if (full != null) {
          // A <title> exists only on a cut label.
          // Its full name is longer than the shown text and starts with it once the trailing ellipsis is removed.
          expect(full.length).toBeGreaterThan(shown.length);
          expect(full.startsWith(shown.replace(/\.\.\.$/, ""))).toBe(true);
        }
      }
      assertNoErrors(errors);
    },
  );
});

test.describe("Today's index", () => {
  test(
    "shows 20 entries; Show all 40 grows in place and moves focus to entry 21",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/", { viewport: DESKTOP, ready: graph(page) });

      const entries = page.locator("ol li");
      await expect(entries).toHaveCount(20);

      const showAll = page.getByRole("button", { name: "Show all 40" });
      await expect(showAll).toBeVisible();
      await showAll.click();
      await expect(entries).toHaveCount(40);
      await expect(showAll).toBeHidden();

      const entry21Link = entries.nth(20).locator("a").first();
      await expect(entry21Link).toBeFocused();
      assertNoErrors(errors);
    },
  );
});

test.describe("Keyboard and focus", () => {
  test(
    "/ focuses the Home search and the Dossiers filter",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/", { ready: graph(page) });
      await page.locator("h1").click();
      await page.keyboard.press("/");
      await expect(page.getByLabel("Build a dossier for a topic")).toBeFocused();

      await open("/t/");
      await page.locator("h1").click();
      await page.keyboard.press("/");
      await expect(page.getByLabel("Filter dossiers by title")).toBeFocused();
      assertNoErrors(errors);
    },
  );

  test("Esc clears the Dossiers filter", only("desktop-1440"), async ({ page, open }) => {
    const errors = trackErrors(page);
    await open("/t/");
    await expect(page.locator("table tbody tr")).toHaveCount(30);

    const filter = page.getByLabel("Filter dossiers by title");
    await filter.fill("jesus");
    await expect(page.locator("table tbody tr")).not.toHaveCount(30);
    await filter.press("Escape");
    await expect(filter).toHaveValue("");
    await expect(page.locator("table tbody tr")).toHaveCount(30);
    assertNoErrors(errors);
  });

  test(
    "focus-visible shows a 2px outline on a keyboard focus, not a mouse click",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/", { ready: graph(page) });

      await page.keyboard.press("Tab");
      await page.keyboard.press("Tab");
      const outlineWidth = await page.evaluate(() => {
        const el = document.activeElement;
        return el ? getComputedStyle(el).outlineWidth : null;
      });
      expect(outlineWidth).not.toBe("0px");

      // A pointer click suppresses the focus ring on a link or button.
      // The search field is covered by the test "Home search input shows a visible outline on keyboard focus (Tailwind v4 outline-style regression)".
      const dossiersLink = page.getByRole("link", { name: "Dossiers" });
      await dossiersLink.click();
      const mouseOutline = await dossiersLink.evaluate((el) => getComputedStyle(el).outlineStyle);
      expect(["none", "", undefined]).toContain(mouseOutline);
      assertNoErrors(errors);
    },
  );

  test(
    "Home search input shows a visible outline on keyboard focus (Tailwind v4 outline-style regression)",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/", { ready: graph(page) });

      const input = page.getByLabel("Build a dossier for a topic");
      for (let i = 0; i < 20; i++) {
        await page.keyboard.press("Tab");
        if (await input.evaluate((el) => el === document.activeElement)) {
          break;
        }
      }
      await expect(input).toBeFocused();
      const outlineStyle = await input.evaluate((el) => getComputedStyle(el).outlineStyle);
      expect(outlineStyle).not.toBe("none");
      assertNoErrors(errors);
    },
  );
});

test.describe("Theme and motion preferences", () => {
  test(
    "Dark toggle sets data-theme and persists in localStorage wke-theme",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/", { ready: graph(page) });

      const before = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
      await page.getByRole("button", { name: /theme/i }).click();
      const after = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
      expect(after).not.toBe(before);

      const stored = await page.evaluate(() => window.localStorage.getItem("wke-theme"));
      expect(stored).toBe(after);

      await page.reload();
      await expect(graph(page)).toBeVisible();
      const afterReload = await page.evaluate(() =>
        document.documentElement.getAttribute("data-theme"),
      );
      expect(afterReload).toBe(after);
      assertNoErrors(errors);
    },
  );
});

test.describe("Live edit rows and graph nodes", () => {
  lightOnly(() => {
    test("hovering or focusing a live edit row highlights its graph node", async ({
      page,
      open,
    }) => {
      await routeLizzie(page);
      await open("/", { ready: graph(page) });
      const node = page.locator("svg[role='group'] a[aria-label^='Lizzie Borden'] circle").first();
      const row = page.locator("table tbody tr", { hasText: "Lizzie Borden" }).first();
      await expect(row).toBeVisible();
      const width = () => node.evaluate((el) => el.getAttribute("stroke-width"));
      const before = await width();
      await row.hover();
      await expect.poll(width).not.toBe(before);
      await page.mouse.move(0, 0);
      await expect.poll(width).toBe(before);
      await row.locator("a").first().focus();
      await expect.poll(width).not.toBe(before);
    });
  });
});
