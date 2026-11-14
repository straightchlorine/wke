import { AxeBuilder } from "@axe-core/playwright";
import type { Locator, Page } from "@playwright/test";
import { test, expect, eachTheme, lightOnly, only } from "./support";
import { fixtureObject } from "./fixtureObject";
import { trackErrors, assertNoErrors, expectShellRendered } from "./errorTracking";

type Box = NonNullable<Awaited<ReturnType<Locator["boundingBox"]>>>;

/** The boxes of the Freshness (i), the Freshness segments and the title filter on the Dossiers page. */
async function filterBoxes(page: Page): Promise<[Box, Box, Box]> {
  const [dotBox, groupBox, inputBox] = await Promise.all([
    page.getByRole("button", { name: "About the Freshness filter" }).boundingBox(),
    page.getByRole("radiogroup", { name: "Freshness" }).boundingBox(),
    page.getByLabel("Filter dossiers by title").boundingBox(),
  ]);
  if (!dotBox || !groupBox || !inputBox) throw new Error("missing box");
  return [dotBox, groupBox, inputBox];
}

const firstRow = (page: Page) => page.locator("table tbody tr").first();

/** The colours and border width of the first element the locator matches. */
function chipStyle(loc: Locator) {
  return loc.first().evaluate((el) => {
    const cs = getComputedStyle(el);
    return { bg: cs.backgroundColor, color: cs.color, border: cs.borderTopWidth };
  });
}

test.describe("Dossiers index", () => {
  test("renders all 30 cached dossiers", async ({ page, open }) => {
    const errors = trackErrors(page);
    await open("/t/");
    await expect(page.locator("table tbody tr")).toHaveCount(30);
    await expectShellRendered(page);
    assertNoErrors(errors);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth),
    ).toBe(false);
  });

  test("an all-digit ?q fills the title filter", only("desktop-1440"), async ({ page, open }) => {
    await open("/t/?q=1984");
    await expect(page.getByLabel("Filter dossiers by title")).toHaveValue("1984");
  });

  test(
    "a list with more entries than it shows says so",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await page.route(/\/api\/v1\/dossiers(\?[^/]*)?$/, async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ ...fixtureObject("dossiers.json"), next_cursor: "c" }),
        });
      });
      await open("/t/");
      await expect(page.getByRole("radio", { name: /^All 100\+/ })).toBeVisible();
      await expect(
        page.getByText("Newest 100 shown, newest build first, times UTC."),
      ).toBeVisible();
      await expectShellRendered(page);
      assertNoErrors(errors);
    },
  );

  test("title filter narrows the rows", only("desktop-1440"), async ({ page, open }) => {
    const errors = trackErrors(page);
    await open("/t/");
    await expect(page.locator("table tbody tr")).toHaveCount(30);

    await page.getByLabel("Filter dossiers by title").fill("asian games");
    await expect(page.locator("table tbody tr")).toHaveCount(3);
    await expectShellRendered(page);
    assertNoErrors(errors);
  });

  for (const width of [768, 1440]) {
    test(
      `an out-of-date chip reads "N edit(s) since built" with its space at ${width}`,
      only("desktop-1440"),
      async ({ page, open }) => {
        await open("/t/", { viewport: { width, height: 900 } });
        await expect(page.locator("table tbody tr")).toHaveCount(30);
        const chips = await page
          .locator("table tbody tr span:has(> span.max-md\\:hidden)")
          .evaluateAll((els) =>
            els
              .map((el) =>
                (el instanceof HTMLElement ? el.innerText : "").replace(/\s+/g, " ").trim(),
              )
              .filter((text) => text.startsWith("Out of date:")),
          );
        expect(chips.length).toBeGreaterThan(0);
        for (const text of chips) {
          expect(text).toMatch(/^Out of date: [\d,]+ edits? since built$/);
        }
        expect(chips.some((text) => /^Out of date: 1 edit since built$/.test(text))).toBe(true);
      },
    );
  }

  test(
    "Stale filter shows only rows with edits since pin",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/t/");

      await page.getByText(/^Out of date \d+$/).click();
      const rows = page.locator("table tbody tr");
      await expect(rows).toHaveCount(18);
      for (const chip of await rows.locator("text=/^Out of date:/").all()) {
        await expect(chip).toBeVisible();
      }
      await expect(rows.locator("text=/^Up to date/")).toHaveCount(0);
      await expect(rows.locator("text=Not checked")).toHaveCount(0);
      await expectShellRendered(page);
      assertNoErrors(errors);
    },
  );

  test("Current filter excludes Not checked rows", only("desktop-1440"), async ({ page, open }) => {
    const errors = trackErrors(page);
    await open("/t/");

    await page.getByText(/^Up to date \d+$/).click();
    const rows = page.locator("table tbody tr");
    await expect(rows).toHaveCount(6);
    await expect(rows.locator("text=/^Out of date:/")).toHaveCount(0);
    await expect(rows.locator("text=Not checked")).toHaveCount(0);
    await expectShellRendered(page);
    assertNoErrors(errors);
  });

  test(
    "an empty filter uses the API did_you_mean when present",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await page.route(/\/api\/v1\/search(\?[^/]*)?$/, async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ query: "Jesuss", results: [], did_you_mean: "Jesus" }),
        });
      });
      await open("/t/");
      await expect(page.locator("table tbody tr")).toHaveCount(30);
      await page.getByLabel("Filter dossiers by title").fill("Jesuss");
      const hint = page.getByText("Did you mean", { exact: false });
      await expect(hint).toBeVisible();
      await expect(hint.getByRole("link", { name: "Jesus" })).toHaveAttribute("href", /\/t\/Jesus/);
      await expectShellRendered(page);
      assertNoErrors(errors);
    },
  );

  test(
    "an empty filter falls back to the local guess when the API has no suggestion",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await page.route(/\/api\/v1\/search(\?[^/]*)?$/, async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ query: "x", results: [], did_you_mean: null }),
        });
      });
      await open("/t/");
      await expect(page.locator("table tbody tr")).toHaveCount(30);
      const first = (await page.locator("table tbody tr td a").first().textContent())?.trim() ?? "";
      await page.getByLabel("Filter dossiers by title").fill(`${first.slice(0, 3)}zzqq`);
      await expect(page.getByText(/^No built dossier matches/)).toBeVisible();
      await expect(page.getByText("Did you mean")).toHaveCount(0);
      await expect(
        page.getByRole("group", { name: "Closest built titles" }).getByRole("link").first(),
      ).toBeVisible();
      assertNoErrors(errors);
    },
  );

  test(
    "clear button empties the filter and returns focus",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/t/");

      const input = page.getByLabel("Filter dossiers by title");
      await input.fill("asian games");
      await page.getByLabel("Clear search").click();
      await expect(input).toHaveValue("");
      await expect(input).toBeFocused();
      await expect(page.locator("table tbody tr")).toHaveCount(30);
      await expectShellRendered(page);
      assertNoErrors(errors);
    },
  );

  test(
    "Back from a dossier restores the Dossiers scroll position",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/t/");
      await expect(page.locator("table tbody tr")).toHaveCount(30);

      // The last row is already in view after scrolling to the bottom, so the click does not scroll again.
      // The position measured here is then the one the back navigation should restore.
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      await page.waitForFunction(() => window.scrollY > 0);
      const before = await page.evaluate(() => window.scrollY);

      await page.locator("table tbody tr").last().locator("td").first().locator("a").click();
      await page.waitForURL(/\/t\/[^/]+/);
      await page.goBack();
      await expect(page.locator("table tbody tr")).toHaveCount(30);

      await expect
        .poll(async () => Math.abs((await page.evaluate(() => window.scrollY)) - before))
        .toBeLessThanOrEqual(50);
      await expectShellRendered(page);
      assertNoErrors(errors);
    },
  );

  test(
    "the whole row is the link: a click away from the title opens the dossier, the revision link stays its own",
    only("desktop-1440"),
    async ({ page, open }) => {
      await open("/t/");
      const row = page.locator("table tbody tr").first();
      await expect(row).toBeVisible();
      const href = await row.locator("td").first().locator("a").getAttribute("href");
      expect(href).toMatch(/^\/t\/[^/?]+\?budget=/);
      // The "Built on" cell holds no link of its own: a click there is a click on the row.
      const box = (await row.locator("td").last().boundingBox())!;
      const cursor = await page.evaluate(
        ([x, y]) => getComputedStyle(document.elementFromPoint(x!, y!)!).cursor,
        [box.x + box.width / 2, box.y + box.height / 2],
      );
      expect(cursor).toBe("pointer");
      // The revision link sits above the title link's full-row overlay.
      const rev = row.locator("a[href*='oldid']");
      const revBox = (await rev.boundingBox())!;
      const topmost = await page.evaluate(
        ([x, y]) => document.elementFromPoint(x!, y!)?.closest("a")?.getAttribute("href") ?? "",
        [revBox.x + revBox.width / 2, revBox.y + revBox.height / 2],
      );
      expect(topmost).toContain("oldid");
      await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
      await expect
        .poll(() => decodeURI(new URL(page.url()).pathname + new URL(page.url()).search))
        .toBe(decodeURI(href!));
      await expect(page.locator("h1").first()).toBeVisible();
    },
  );

  // Each width sets its own viewport and a touch screen, so these run once, on the phone project.
  test.describe("phone rows", only("mobile-390"), () => {
    for (const width of [360, 390, 430]) {
      test.describe(`at ${width}`, () => {
        test.use({ hasTouch: true, viewport: { width, height: 800 } });

        test("are three lines: title, one chip-and-date line, revision and build date", async ({
          page,
          open,
        }) => {
          await open("/t/");
          await expect(page.locator("table tbody tr")).toHaveCount(30);
          const rows = await page.locator("table tbody tr").evaluateAll((trs) =>
            trs.map((tr) => {
              const cells = [...tr.querySelectorAll("td")];
              const [title, , fresh, fits, , built] = cells.map((cell) =>
                cell.getBoundingClientRect(),
              );
              const date = cells[1]!.querySelector("span.inline-block")!.getBoundingClientRect();
              const revisionLink = cells[1]!.querySelector("a")!.getBoundingClientRect();
              return {
                height: tr.getBoundingClientRect().height,
                freshTop: Math.round(fresh!.top),
                fitsTop: Math.round(fits!.top),
                freshLeft: fresh!.left,
                freshRight: fresh!.right,
                fitsRight: fits!.right,
                dateTop: Math.round(date.top),
                dateLeft: date.left,
                dateRight: date.right,
                cellRight: title!.right,
                revTop: Math.round(revisionLink.top),
                builtTop: Math.round(built!.top),
              };
            }),
          );
          for (const row of rows) {
            // Every row is three lines tall, so its height must fall between 80 and 100 px.
            expect(row.height, `row height at ${width}`).toBeLessThanOrEqual(100);
            expect(row.height).toBeGreaterThanOrEqual(80);
            // On the second line the Fits in chip comes first, then the Freshness chip, then the pinned date at the right end.
            expect(Math.abs(row.freshTop - row.fitsTop)).toBeLessThanOrEqual(4);
            expect(Math.abs(row.freshTop - row.dateTop)).toBeLessThanOrEqual(6);
            expect(row.fitsRight).toBeLessThanOrEqual(row.freshLeft + 0.5);
            expect(row.freshRight).toBeLessThanOrEqual(row.dateLeft);
            expect(Math.abs(row.dateRight - row.cellRight)).toBeLessThanOrEqual(1);
            expect(row.revTop).toBeGreaterThan(row.freshTop + 10);
            expect(Math.abs(row.revTop - row.builtTop)).toBeLessThanOrEqual(6);
          }

          expect(
            await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth),
            `overflow at ${width}`,
          ).toBe(false);
        });
      });
    }
  });

  test("has zero axe violations", async ({ page, open }) => {
    const errors = trackErrors(page);
    await open("/t/");
    await expect(page.locator("table tbody tr")).toHaveCount(30);
    await expectShellRendered(page);

    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
    assertNoErrors(errors);
  });
});

eachTheme(() => {
  test(
    "Up to date is one chip on Dossiers and on Home",
    only("desktop-1440"),
    async ({ page, open }) => {
      await open("/t/", { ready: page.locator("table tbody tr").first() });
      const row = page.locator("table tbody tr").getByText(/^Up to date$/);
      await expect(row.first()).toBeVisible();
      const list = await chipStyle(row);
      const home = page.locator("[data-top-dossier]").getByText(/^Up to date$/);
      await open("/", { ready: home });
      expect(await chipStyle(home)).toEqual(list);
    },
  );
});

lightOnly(() => {
  test.describe("the Freshness (i) placement", () => {
    test("is one visible dot", only("tablet-768"), async ({ page, open }) => {
      await open("/t/", { ready: firstRow(page) });
      const dot = page.getByRole("button", { name: "About the Freshness filter" });
      await expect(dot).toHaveCount(1);
      await expect(dot).toBeVisible();
    });

    test(
      "sits above the segments on a phone, which still span the search box",
      only("mobile-390"),
      async ({ page, open }) => {
        await open("/t/", { ready: firstRow(page) });
        const [dotBox, groupBox, inputBox] = await filterBoxes(page);
        expect(dotBox.y + dotBox.height).toBeLessThanOrEqual(groupBox.y + 1);
        expect(Math.abs(groupBox.x - inputBox.x)).toBeLessThanOrEqual(1);
        expect(
          Math.abs(groupBox.x + groupBox.width - (inputBox.x + inputBox.width)),
        ).toBeLessThanOrEqual(1);
      },
    );

    test(
      "sits after the segments, on the same line, at 1440",
      only("desktop-1440"),
      async ({ page, open }) => {
        await open("/t/", { ready: firstRow(page) });
        const [dotBox, groupBox] = await filterBoxes(page);
        expect(
          Math.abs(dotBox.y + dotBox.height / 2 - (groupBox.y + groupBox.height / 2)),
        ).toBeLessThanOrEqual(groupBox.height / 2);
        expect(dotBox.x).toBeGreaterThanOrEqual(groupBox.x + groupBox.width - 1);
      },
    );
  });

  test(
    "rows print dates in the record format",
    only("mobile-390", "tablet-768", "desktop-1440"),
    async ({ page, open }) => {
      await open("/t/", { ready: page.locator("tbody tr a[href*='oldid']").first() });
      const text = await page.locator("tbody tr").first().innerText();
      // Below the md breakpoint the pinned date on the chip line drops its " UTC"; the build date keeps it.
      const phone = (page.viewportSize()?.width ?? 0) < 768;
      expect(text.match(/\d{4}-\d\d-\d\d, \d\d:\d\d/g)?.length).toBe(2);
      expect(text.match(/\d{4}-\d\d-\d\d, \d\d:\d\d UTC/g)?.length).toBe(phone ? 1 : 2);
    },
  );
});
