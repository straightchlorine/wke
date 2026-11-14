import type { Locator, Page } from "@playwright/test";
import { hitExtent, hitWidth } from "./hitAreas";
import { test, expect, lightOnly, only, VIEWPORTS, LANDSCAPE_PHONE as LANDSCAPE } from "./support";

const PHONE = VIEWPORTS["mobile-390"];

const MIN_HIT = 44;

test.describe("44 px hit height at 390", only("mobile-390"), () => {
  lightOnly(() => {
    test.describe("on a touch screen", () => {
      test.use({ hasTouch: true, viewport: PHONE });

      test("footer links on a dossier stay clear of the bottom bar and keep a 44 px strip", async ({
        page,
        open,
      }) => {
        await open("/t/Lizzie_Borden");
        await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
        const footerLinks = page.getByRole("contentinfo").locator("a");
        const count = await footerLinks.count();
        expect(count).toBeGreaterThanOrEqual(5);
        for (let i = 0; i < count; i++) {
          expect(await hitExtent(footerLinks.nth(i)), `footer link ${i}`).toBeGreaterThanOrEqual(
            MIN_HIT,
          );
        }
        // The strip is extra: the links keep their one-line visual height.
        const heights = await footerLinks.evaluateAll((els) =>
          els.map((el) => el.getBoundingClientRect().height),
        );
        for (const h of heights) expect(h).toBeLessThanOrEqual(20);
        await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
        const last = await footerLinks.last().evaluate((el) => el.getBoundingClientRect().bottom);
        const bar = await page
          .getByRole("toolbar", { name: "Token budget and copy" })
          .evaluate((el) => el.getBoundingClientRect().top);
        expect(last, "the last footer link ends above the bottom bar").toBeLessThanOrEqual(bar);
      });

      test("graph nodes have a 44 px hit area", async ({ page, open }) => {
        await open("/", { ready: page.locator('svg[role="group"] a').first() });
        const widths = await page
          .locator("[data-plate-hit]")
          .evaluateAll((els) => els.map((el) => el.getBoundingClientRect().width));
        expect(widths.length).toBeGreaterThan(20);
        for (const w of widths) {
          expect(w).toBeGreaterThanOrEqual(43);
        }
      });

      test("secondary links are 44 px in both directions", async ({ page, open }) => {
        const both = async (target: Locator, name: string) => {
          expect(await hitExtent(target), `${name} height`).toBeGreaterThanOrEqual(MIN_HIT);
          expect(await hitWidth(target), `${name} width`).toBeGreaterThanOrEqual(MIN_HIT);
        };
        await open("/t/Lizzie_Borden");
        await both(
          page.locator("header").getByRole("link", { name: "Source on GitHub" }),
          "GitHub link",
        );
        const toggle = page.locator("header").getByRole("button", { name: /Switch to/ });
        await both(toggle, "theme toggle");
        expect(
          (await toggle.boundingBox())?.height,
          "theme toggle box under a coarse pointer",
        ).toBeGreaterThanOrEqual(MIN_HIT);
        const record = page
          .getByRole("group", { name: "Source record" })
          .or(page.locator('[aria-labelledby="source-record-h"]'));
        await both(
          record
            .locator("a[href*='oldid'], a[href*='permalink'], a[href*='wikipedia.org/w/index.php']")
            .first(),
          "revision link",
        );
        await both(record.locator("a[href*='creativecommons']").first(), "CC BY-SA");
        await both(record.locator("summary").first(), "Full source record");
        expect(
          await hitExtent(page.locator("label:visible", { hasText: /^8k$/ }).first()),
          "budget option",
        ).toBeGreaterThanOrEqual(MIN_HIT);
        expect(
          await hitExtent(page.locator("ol a[href*='oldid'], ol a[href*='permalink']").first(), 20),
          "linked article row",
        ).toBeGreaterThanOrEqual(MIN_HIT);
        await open("/t/Apollo_11?budget=2000");
        await expect(page.getByRole("button", { name: /^Show at 8k/ }).first()).toBeVisible();
        expect(
          await hitExtent(page.getByRole("button", { name: /^Show at 8k/ }).first()),
          "Show at 8k",
        ).toBeGreaterThanOrEqual(MIN_HIT);
        expect(
          await hitExtent(
            page.getByRole("button", { name: "Read here without changing the export" }).first(),
          ),
          "Read here",
        ).toBeGreaterThanOrEqual(MIN_HIT);
        await open("/t/Nonexistent_Title");
        await both(
          page.getByRole("link", { name: "Back to today's index" }),
          "Back to today's index",
        );
        await open("/nope/nothing");
        await both(
          page.getByRole("main").getByRole("link", { name: "Today's index", exact: true }),
          "Today's index",
        );
        await open("/machines");
        await both(page.locator("a[href='#limits']").first(), "details");
      });
    });

    test("the not-built page: Did you mean links and the plain 404 links", async ({
      page,
      open,
    }) => {
      await open("/t/Nonexistent_Title", {
        ready: page.getByRole("heading", { level: 1, name: "No article by that title" }),
      });
      const links = page.locator("main a[href^='/t/']");
      const count = await links.count();
      expect(count).toBeGreaterThan(0);
      for (let i = 0; i < count; i++) {
        expect(await hitExtent(links.nth(i)), `suggestion ${i}`).toBeGreaterThanOrEqual(MIN_HIT);
      }
      await open("/nope/nothing", {
        ready: page.getByRole("heading", { level: 1, name: "Page not found" }),
      });
      for (const name of ["Dossiers", "Today's index"]) {
        expect(
          await hitExtent(page.getByRole("main").getByRole("link", { name, exact: true })),
          name,
        ).toBeGreaterThanOrEqual(MIN_HIT);
      }
    });
  });
});

test.describe("coarse-pointer hit areas of the section list", only("mobile-390"), () => {
  test.use({ hasTouch: true });

  lightOnly(() => {
    test.describe("on a wide touch screen", () => {
      test.use({ viewport: { width: 1366, height: 900 } });

      test("the Contents list keeps a 44 px strip", async ({ page, open }) => {
        await open("/t/Apollo_11");
        const links = page.locator('nav[aria-label="Contents"] a');
        await expect(links.nth(2)).toBeVisible();
        for (let i = 0; i < 3; i++) {
          expect(await hitExtent(links.nth(i), 60), `Contents link ${i}`).toBeGreaterThanOrEqual(
            MIN_HIT,
          );
        }
      });
    });
  });
});

interface SmallTarget {
  name: string;
  hit: string;
}

/**
 * Every visible link and button whose touch target is under 44 px on either axis.
 * A target outside running text is judged by where a tap lands, so a neighbour that covers part of it counts against it.
 * An inline link in running text is judged by its declared box or hit strip, because the line height around it bounds it,
 * and graph nodes inside an svg are skipped.
 */
async function smallTargets(page: Page): Promise<SmallTarget[]> {
  return page.evaluate((min) => {
    document.documentElement.style.scrollBehavior = "auto";
    const found: SmallTarget[] = [];
    for (const el of document.querySelectorAll("a[href], button, [role=button], summary")) {
      const style = getComputedStyle(el);
      if (
        el.closest("svg") ||
        el.closest("[aria-hidden=true]") ||
        el.closest("details:not([open]) > :not(summary)")
      )
        continue;
      const first = el.getClientRects()[0];
      if (!first || first.width === 0 || first.height === 0 || style.visibility === "hidden")
        continue;
      el.scrollIntoView({ block: "center", inline: "center" });
      const box = el.getClientRects()[0] ?? first;
      const cx = box.left + box.width / 2;
      const cy = box.top + box.height / 2;
      const lands = (x: number, y: number) => {
        const hit = document.elementFromPoint(x, y);
        return hit != null && (hit === el || el.contains(hit));
      };
      if (cx < 0 || cy < 0 || cx > innerWidth || cy > innerHeight || !lands(cx, cy)) continue;
      let height: number;
      let width: number;
      if (style.display === "inline") {
        height = box.height;
        width = box.width;
        for (const pseudo of ["::before", "::after"]) {
          const strip = getComputedStyle(el, pseudo);
          if (strip.position === "absolute" && strip.content !== "none") {
            height = Math.max(height, parseFloat(strip.height) || 0);
            width = Math.max(width, parseFloat(strip.width) || 0);
          }
        }
      } else {
        const run = (dx: number, dy: number) => {
          let n = 0;
          // Stepping back starts one pixel from the centre and stepping forward starts at the centre, so the centre is counted once.
          const back = dx < 0 || dy < 0 ? 1 : 0;
          while (n < 70 && lands(cx + dx * (n + back), cy + dy * (n + back))) n += 1;
          return n;
        };
        height = run(0, -1) + run(0, 1);
        width = run(-1, 0) + run(1, 0);
      }
      if (height < min - 1 || width < min - 1) {
        found.push({
          name: (el.getAttribute("aria-label") ?? el.textContent ?? "").trim().slice(0, 30),
          hit: `${Math.round(width)}x${Math.round(height)}`,
        });
      }
    }
    return found;
  }, MIN_HIT);
}

test.describe(
  "no link or button under 44 px on a touch screen, and a tap 20 px off centre lands",
  only("mobile-390"),
  () => {
    const PAGES: Array<[string, string, string]> = [
      ["Home", "/", "[data-entry-views]"],
      ["a dossier", "/t/Lizzie_Borden", 'section[id^="s"] h2'],
      ["Dossiers", "/t/", "table tbody tr"],
      ["For machines", "/machines", "h1"],
    ];
    lightOnly(() => {
      for (const [name, viewport] of [
        ["390x844", PHONE],
        ["844x390", LANDSCAPE],
      ] as const) {
        test.describe(name, () => {
          test.use({ hasTouch: true, isMobile: true, viewport });

          for (const [label, path, ready] of PAGES) {
            test(label, async ({ page, open }) => {
              await open(path, { ready: page.locator(ready).first() });
              expect(
                await page.evaluate(() => window.matchMedia("(pointer: coarse)").matches),
              ).toBe(true);
              expect.soft(await smallTargets(page)).toEqual([]);
              // Opening every details comes after the sweep, which skips closed ones.
              await page.evaluate(() =>
                document.querySelectorAll("details").forEach((d) => (d.open = true)),
              );
              expect.soft(await threePointMisses(page, false)).toEqual([]);
              if (path === "/") {
                const swatch = page
                  .locator('[role="group"] button[aria-label^="Articles related to"]')
                  .first();
                await swatch.tap();
                await expect(page.locator("[popover]:popover-open a[href]").first()).toBeVisible();
                expect.soft(await threePointMisses(page, true)).toEqual([]);
              }
            });
          }
        });
      }
    });

    for (const [touch, expected] of [
      [true, 44],
      [false, 36],
    ] as const) {
      test.describe(touch ? "with a touch screen" : "with a mouse", () => {
        test.use({ hasTouch: touch, isMobile: touch, viewport: PHONE });

        test(`the header nav links are ${expected} px tall boxes`, async ({ page, open }) => {
          await open("/");
          await expect(page.locator('header nav[aria-label="Primary"] a')).toHaveCount(3);
          const heights = await page
            .locator('header nav[aria-label="Primary"] a')
            .evaluateAll((els) => els.map((el) => Math.round(el.getBoundingClientRect().height)));
          expect(heights).toEqual([expected, expected, expected]);
        });
      });
    }
  },
);

/**
 * Taps the way a thumb does: at an element's centre and 20 px above and below
 * it (and 20 px left and right for a glyph of 20 px or less). Each point must
 * resolve to the element or something inside it, so a hit strip that is
 * lopsided, or that a neighbour's strip covers, shows up as a miss.
 * With `tip` set it checks the links in open popovers instead of the page's links.
 */
async function threePointMisses(page: Page, tip: boolean): Promise<string[]> {
  return page.evaluate(
    async ({ selector }) => {
      const misses: string[] = [];
      for (const el of document.querySelectorAll(selector)) {
        if (el.closest("svg, [aria-hidden='true'], [hidden], details:not([open])")) continue;
        if (el.matches("[class*='sr-only']") || (el.getAttribute("href") ?? "").startsWith("#main"))
          continue;
        const style = getComputedStyle(el);
        if (style.visibility === "hidden" || style.display === "none") continue;
        if (el.getBoundingClientRect().width === 0) continue;
        el.scrollIntoView({ block: "center", inline: "center" });
        await new Promise((resolve) => requestAnimationFrame(() => resolve(null)));
        const box = el.getBoundingClientRect();
        const cx = box.left + box.width / 2;
        const cy = box.top + box.height / 2;
        const glyph = box.width <= 20 && box.height <= 20;
        const offsets: Array<[number, number]> = [
          [0, 0],
          [0, -20],
          [0, 20],
        ];
        if (glyph) offsets.push([-20, 0], [20, 0]);
        for (const [dx, dy] of offsets) {
          const x = cx + dx;
          const y = cy + dy;
          if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) continue;
          const hit = document.elementFromPoint(x, y);
          if (!(hit && (hit === el || el.contains(hit)))) {
            const name = (el.getAttribute("aria-label") ?? el.textContent ?? "")
              .trim()
              .slice(0, 30);
            misses.push(`${name} (${dx},${dy}) landed on ${hit?.tagName ?? "nothing"}`);
          }
        }
      }
      return misses;
    },
    { selector: tip ? "[popover]:popover-open a[href]" : "a[href], button, [role='button']" },
  );
}
