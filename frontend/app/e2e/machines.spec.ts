import { AxeBuilder } from "@axe-core/playwright";
import { test, expect, eachTheme, only } from "./support";
import { trackErrors, assertNoErrors, expectShellRendered } from "./errorTracking";
import { readFixtureJson } from "./buildFixture";

const SECTION_IDS = ["llms", "json", "markdown", "build", "mcp", "limits"];

test.describe("For machines", () => {
  test("the page content", only("desktop-1440"), async ({ page, open }) => {
    const errors = trackErrors(page);
    // The llms.txt excerpt takes its date from GET /api/v1/trending, the same date Home shows, so this page needs the API mock.
    await open("/machines");
    for (const id of SECTION_IDS) {
      await expect(page.locator(`section#${id}`)).toBeVisible();
    }

    for (const id of ["llms", "json", "markdown"]) {
      await page.locator(`section#${id}`).scrollIntoViewIfNeeded();
    }
    const main = page.locator("main");
    const date = readFixtureJson<{ date: string }>("trending.json").date;
    const dossier = readFixtureJson<{ id: string; build: { built_at: string } }>(
      "dossier_1095706_8000.json",
    );
    const id = dossier.id;
    const builtAt = dossier.build.built_at;
    await expect(main).toContainText(`snapshot ${date}`);
    await expect(main).toContainText(`"id": "${id}"`);
    await expect(main).toContainText(`"built_at": "${builtAt}"`);
    await expect(main).toContainText(
      new RegExp(`Most read on Wikipedia (yesterday \\(|on )${date}`),
    );
    await expect(main).not.toContainText("captured");
    await expect(main).not.toContainText("Waiting for the API");

    await expect(page.locator("[data-copy]").first()).toBeVisible();
    const labels = await page
      .locator("[data-copy]")
      .evaluateAll((els) => [
        ...new Set(els.map((el) => (el instanceof HTMLElement ? el.innerText.trim() : ""))),
      ]);
    expect(labels.toSorted()).toEqual(["Copy", "Copy config"]);

    const table = page
      .locator("section#limits")
      .getByRole("group", { name: "Rate limits per route class" });
    await expect(table).toContainText("Job polling (GET /api/v1/jobs/{id})");
    await expect(table).toContainText("600 a minute");
    await expect(table).toContainText("2 an hour");

    await expect(
      main.getByText("30 a minute per client IP on search and MCP, 12 a minute on live edits"),
    ).toBeVisible();
    await expectShellRendered(page);
    assertNoErrors(errors);
  });

  test(
    "every data-copy button copies its text and shows one Toast",
    only("mobile-390", "desktop-1440"),
    async ({ page, context, open }) => {
      await context.grantPermissions(["clipboard-read", "clipboard-write"]);
      const errors = trackErrors(page);

      await open("/machines");

      const buttons = page.locator("[data-copy]");
      // Waiting for the first button to be visible retries until the page has rendered. A bare count() could run before that and return zero.
      await expect(buttons.first()).toBeVisible();
      const count = await buttons.count();
      expect(count).toBeGreaterThan(0);

      for (let i = 0; i < count; i++) {
        const button = buttons.nth(i);
        await button.scrollIntoViewIfNeeded();
        await button.click();

        // The handler shows the toast only after navigator.clipboard.writeText resolves.
        // Waiting for the toast also waits for the write, so the clipboard read below cannot run early.
        const toasts = page.getByTestId("toast");
        await expect(toasts).toHaveCount(1);
        await expect(toasts.first()).toBeVisible();

        const clipboardText = await page.evaluate(() => navigator.clipboard.readText());
        expect(clipboardText.length).toBeGreaterThan(0);
      }

      await expectShellRendered(page);
      assertNoErrors(errors);
    },
  );

  test("no horizontal overflow", async ({ page, open }) => {
    const errors = trackErrors(page);
    await open("/machines");
    await expect(page.locator("section#limits")).toBeVisible();

    const hasOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    );
    expect(hasOverflow).toBe(false);
    await expectShellRendered(page);
    assertNoErrors(errors);
  });

  test("zero axe violations", async ({ page, open }) => {
    const errors = trackErrors(page);
    await open("/machines");
    await page.locator("h1").waitFor();
    await page.waitForLoadState("networkidle");
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
    await expectShellRendered(page);
    assertNoErrors(errors);
  });

  test("the markdown example is fetched when its section nears the viewport; the JSON one on arrival", async ({
    page,
    open,
  }) => {
    await page.clock.install();
    const seen: string[] = [];
    page.on("request", (request) => {
      const { pathname } = new URL(request.url());
      if (/^\/api\/v1\/dossiers\/1095706(\.md)?$/.test(pathname)) {
        seen.push(pathname.endsWith(".md") ? "markdown" : "json");
      }
    });
    await open("/machines");
    await expect(page.locator("section#llms")).toBeVisible();
    await page.clock.runFor(500);
    // The JSON example is fetched on arrival, because its links.self gives the base URL every block on the page quotes.
    // The Markdown example is fetched only when its section nears the viewport.
    await expect.poll(() => seen).toContain("json");
    const tops = await page.evaluate(() => ({
      viewport: window.innerHeight,
      markdown: document.getElementById("markdown")!.getBoundingClientRect().top,
    }));
    expect(tops.markdown - tops.viewport).toBeGreaterThan(250);
    expect(seen).not.toContain("markdown");

    await page.locator("section#json").scrollIntoViewIfNeeded();
    await expect(page.locator("section#json pre").last()).toContainText("HTTP/1.1 200 OK");

    await page.locator("section#markdown").scrollIntoViewIfNeeded();
    await expect.poll(() => seen).toContain("markdown");
    await expect(page.locator("section#markdown pre").last()).not.toContainText(
      "Waiting for the API",
    );
  });

  test(
    "a failed JSON example says the API did not return it",
    only("desktop-1440"),
    async ({ page, open }) => {
      await page.route(/\/api\/v1\/dossiers\/1095706(\?[^/]*)?$/, async (route) => {
        await route.fulfill({
          status: 500,
          contentType: "application/problem+json",
          body: JSON.stringify({
            type: "about:blank",
            title: "Internal Server Error",
            status: 500,
            code: "internal",
            request_id: "spec-machines-example",
          }),
        });
      });
      await open("/machines");
      const section = page.locator("section#json");
      await section.scrollIntoViewIfNeeded();
      await expect(section).toContainText("The API did not return this example.");
    },
  );

  test("a loaded example does not change its block height", async ({ page, open }) => {
    await open("/machines");
    // The pre sits in a fade wrapper, which sits in the block's frame. Two levels up is the frame.
    const block = page.locator("section#json pre").last().locator("../..");
    const before = (await block.boundingBox())?.height ?? 0;
    await page.locator("section#json").scrollIntoViewIfNeeded();
    await expect(page.locator("section#json pre").last()).toContainText("HTTP/1.1 200 OK");
    const after = (await block.boundingBox())?.height ?? 0;
    expect(before).toBeGreaterThanOrEqual(1930);
    expect(after).toBeGreaterThanOrEqual(before - 1);
    expect(after - before).toBeLessThan(400);
  });

  test(
    "a code pane that runs past its frame keeps a visible scrollbar, never a hidden one",
    only("desktop-1440"),
    async ({ page, open }) => {
      await open("/machines");
      await expect(page.locator("pre").first()).toBeVisible();
      const panes = await page.locator("pre").evaluateAll((els) =>
        els.map((el) => ({
          overflowX: getComputedStyle(el).overflowX,
          thumbHidden: /^(transparent|rgba\(0, 0, 0, 0\))/.test(
            getComputedStyle(el).scrollbarColor,
          ),
          quietClass: el.classList.contains("thin-scroll"),
        })),
      );
      expect(panes.length).toBeGreaterThan(3);
      for (const pane of panes) {
        expect(pane.overflowX).toBe("auto");
        expect(pane.thumbHidden).toBe(false);
        expect(pane.quietClass).toBe(false);
      }
    },
  );

  test("a clipped code pane shows a right-edge fade until it is scrolled to its end", async ({
    page,
    open,
  }) => {
    await open("/machines");
    await expect(page.locator("[data-code-more]").first()).toBeVisible();
    // The fade eases in, so read the opacity once every flagged pane has settled.
    await expect
      .poll(() =>
        page
          .locator("[data-code-more='true']")
          .evaluateAll((wraps) =>
            wraps.every((wrap) => getComputedStyle(wrap, "::after").opacity === "1"),
          ),
      )
      .toBe(true);
    const panes = await page.locator("[data-code-more]").evaluateAll((wraps) =>
      wraps.map((wrap) => {
        const pre = wrap.querySelector("pre")!;
        const fade = getComputedStyle(wrap, "::after");
        return {
          clipped: pre.scrollWidth > pre.clientWidth + 1,
          more: wrap.getAttribute("data-code-more"),
          opacity: fade.opacity,
          width: fade.width,
          pointerEvents: fade.pointerEvents,
        };
      }),
    );
    expect(
      panes.some((pane) => pane.clipped),
      "at least one pane is clipped",
    ).toBe(true);
    for (const pane of panes) {
      expect(pane.more === "true", "the flag follows the overflow").toBe(pane.clipped);
      expect(pane.opacity).toBe(pane.clipped ? "1" : "0");
      expect(pane.width).toBe("24px");
      expect(pane.pointerEvents).toBe("none");
    }
    const clipped = page.locator("[data-code-more]").nth(panes.findIndex((pane) => pane.clipped));
    await clipped.scrollIntoViewIfNeeded();
    await clipped.locator("pre").evaluate((pre) => (pre.scrollLeft = pre.scrollWidth));
    await expect(clipped).toHaveAttribute("data-code-more", "false");
    await clipped.locator("pre").evaluate((pre) => (pre.scrollLeft = 0));
    await expect(clipped).toHaveAttribute("data-code-more", "true");
  });

  // The test sets its own viewport, so it runs once, on the 1440 project.
  test.describe("at 390", only("desktop-1440"), () => {
    eachTheme(() => {
      test("every overflowing code pane shows a 24px token-coloured fade at its right edge", async ({
        page,
        open,
      }) => {
        await open("/machines", {
          viewport: { width: 390, height: 844 },
          ready: page.locator("[data-code-more='true']").first(),
        });
        // The fade eases in, so wait until every flagged pane's fade is fully shown.
        await expect
          .poll(() =>
            page
              .locator("[data-code-more='true']")
              .evaluateAll((wraps) =>
                wraps.every((wrap) => getComputedStyle(wrap, "::after").opacity === "1"),
              ),
          )
          .toBe(true);
        const m = await page.evaluate(() => {
          const probe = document.createElement("span");
          probe.style.color = "var(--color-sunken)";
          document.body.append(probe);
          const sunken = getComputedStyle(probe).color;
          probe.remove();
          const panes = [...document.querySelectorAll("[data-code-more]")].map((wrap) => {
            const pre = wrap.querySelector("pre")!;
            const fade = getComputedStyle(wrap, "::after");
            return {
              clipped: pre.scrollWidth > pre.clientWidth + 1,
              flagged: wrap.getAttribute("data-code-more") === "true",
              opacity: fade.opacity,
              width: fade.width,
              image: fade.backgroundImage,
            };
          });
          return { sunken, panes };
        });
        const clipped = m.panes.filter((p) => p.clipped);
        expect(clipped.length, "overflowing panes at 390").toBeGreaterThan(5);
        for (const pane of clipped) {
          expect(pane.flagged).toBe(true);
          expect(pane.opacity).toBe("1");
          expect(pane.width).toBe("24px");
          expect(pane.image).toContain(m.sunken);
        }
      });
    });
  });
});
