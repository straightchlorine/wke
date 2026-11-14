import type { Locator, Page } from "@playwright/test";
import { test, expect, eachTheme, only, settleScroll } from "./support";
import { trackErrors, assertNoErrors } from "./errorTracking";

type Item = { x: number; y: number; w: number; h: number };

const centre = (b: Item) => b.y + b.h / 2;

const DESKTOP = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };
const UHD = { width: 3840, height: 2160 };

function sectionHeading(page: Page): Locator {
  return page.locator('section[id^="s"] [data-section-heading]').first();
}

// These checks set their own viewport, so they run once, on the 1440 project.
test.describe("Layout", only("desktop-1440"), () => {
  test.describe("Dossier grid", () => {
    for (const width of [1200, 1280, 1340, 1440]) {
      test(`no horizontal overflow and nothing in the gutter at ${width}`, async ({
        page,
        open,
      }) => {
        const errors = trackErrors(page);
        await open("/t/Jesus", { viewport: { width, height: 800 }, ready: sectionHeading(page) });
        const m = await page.evaluate(() => {
          const main = document.querySelector("main")!;
          const style = getComputedStyle(main);
          const inner = main.getBoundingClientRect().right - Number.parseFloat(style.paddingRight);
          const grid = document.querySelector('article[aria-label="Dossier text"]')?.parentElement;
          const rights = Array.from(grid!.children).map((el) => el.getBoundingClientRect().right);
          return { scrollWidth: document.documentElement.scrollWidth, innerWidth, inner, rights };
        });
        expect(m.scrollWidth).toBe(m.innerWidth);
        for (const right of m.rights) {
          expect(right).toBeLessThanOrEqual(m.inner + 1);
        }
        assertNoErrors(errors);
      });
    }

    test("the contents rail takes over from the chip strip at 1340", async ({ page, open }) => {
      await open("/t/Jesus", { viewport: { width: 1339, height: 800 } });
      await expect(page.locator('nav[aria-label="Sections"]')).toBeVisible();
      await expect(page.locator('nav[aria-label="Contents"]')).toBeHidden();
      await page.setViewportSize({ width: 1340, height: 800 });
      await expect(page.locator('nav[aria-label="Sections"]')).toBeHidden();
      await expect(page.locator('nav[aria-label="Contents"]')).toBeVisible();
    });
  });

  test.describe("Header", () => {
    const phones: Array<[number, number, number]> = [
      [390, 844, 80],
      [844, 390, 56],
    ];
    for (const [width, height, headerHeight] of phones) {
      test(`the active mark sits inside the ${headerHeight}px header at ${width}x${height}`, async ({
        page,
        open,
      }) => {
        await open("/", { viewport: { width, height } });
        const box = await page.evaluate(() => {
          const header = document.querySelector("header")!.getBoundingClientRect();
          const link = document
            .querySelector('nav[aria-label="Primary"] a[aria-current="page"]')!
            .getBoundingClientRect();
          return {
            header: { top: header.top, bottom: header.bottom, height: header.height },
            link: { top: link.top, bottom: link.bottom, height: link.height },
          };
        });
        expect(box.header.height).toBe(headerHeight);
        if (headerHeight === 80) {
          expect(box.link.height).toBe(36);
        }
        expect(box.link.top).toBeGreaterThanOrEqual(box.header.top);
        expect(box.link.bottom).toBeLessThanOrEqual(box.header.bottom);
      });
    }

    test("a landscape phone has one 56px header row: wordmark, three links and the icon on one line", async ({
      page,
      open,
    }) => {
      await open("/", { viewport: { width: 844, height: 390 } });
      const rows = await page.evaluate(() => {
        const header = document.querySelector("header")!;
        return {
          height: header.getBoundingClientRect().height,
          centres: [
            header.querySelector('a[aria-label^="WKE"]')!,
            ...header.querySelectorAll('nav[aria-label="Primary"] a'),
            ...header.querySelectorAll("button, a[aria-label$='GitHub']"),
          ].map((el) => {
            const r = el.getBoundingClientRect();
            return Math.round(r.top + r.height / 2);
          }),
        };
      });
      expect(rows.height).toBe(56);
      expect(rows.centres.length).toBeGreaterThanOrEqual(6);
      expect(Math.max(...rows.centres) - Math.min(...rows.centres)).toBeLessThanOrEqual(2);
    });

    test("a nav link keeps a 44px hit area on a phone", async ({ open, page }) => {
      await open("/", { viewport: PHONE });
      const hit = await page.evaluate(() => {
        const link = document.querySelector('nav[aria-label="Primary"] a[aria-current="page"]')!;
        const rect = link.getBoundingClientRect();
        const x = rect.left + rect.width / 2;
        // The link is shorter than 44px, and its ::after reaches below it to make up the difference.
        // The wordmark's own 44px row ends at the link's top, so the two do not overlap.
        return (
          document.elementFromPoint(x, rect.bottom + 6)?.closest("a") === link &&
          document.elementFromPoint(x, rect.top + 18)?.closest("a") === link
        );
      });
      expect(hit).toBe(true);
    });

    eachTheme(() => {
      test("the header has an icon link to GitHub and no Source nav item", async ({
        page,
        open,
      }) => {
        await open("/");
        await expect(
          page.locator('header nav[aria-label="Primary"] a', { hasText: "Source" }),
        ).toHaveCount(0);
        const gh = page.locator("header").getByRole("link", { name: "Source on GitHub" });
        const ghHref = (await gh.getAttribute("href")) ?? "";
        expect(ghHref).toMatch(/^https:\/\/github\.com\//);
        expect(await gh.evaluate((el) => getComputedStyle(el.querySelector("svg")!).fill)).toBe(
          await gh.evaluate((el) => getComputedStyle(el).color),
        );
        const toggle = page.locator("header").getByRole("button", { name: /Switch to/ });
        // From the right edge inwards the order is GitHub, then the theme toggle.
        const [toggleBox, ghBox] = await Promise.all(
          [toggle, gh].map((link) => link.boundingBox()),
        );
        expect(toggleBox!.x + toggleBox!.width).toBeLessThanOrEqual(ghBox!.x + 0.5);
      });

      test("the theme toggle carries its state in its label only", async ({ page, open }) => {
        await open("/");
        const toggle = page.getByRole("button", { name: /^Switch to (light|dark) theme$/ });
        await expect(toggle).not.toHaveAttribute("aria-pressed", /.*/);
      });

      for (const [width, height] of [
        [390, 844],
        [844, 390],
      ] as const) {
        test.describe(`on a touch screen at ${width}x${height}`, () => {
          test.use({ hasTouch: true, viewport: { width, height } });

          test("the wordmark, icon link and theme toggle share a row and never overlap", async ({
            page,
            open,
          }) => {
            await open("/");
            const boxes = await page.evaluate(() => {
              const header = document.querySelector("header")!;
              const items = [
                "a[href='/']",
                "a[aria-label='Source on GitHub']",
                "button[aria-label^='Switch to']",
              ].map((selector) => {
                const r = header.querySelector(selector)!.getBoundingClientRect();
                return { x: r.x, y: r.y, w: r.width, h: r.height };
              });
              return {
                items,
                overflow: header.scrollWidth > header.clientWidth + 1,
                docOverflow:
                  document.documentElement.scrollWidth > document.documentElement.clientWidth,
              };
            });
            expect(boxes.overflow).toBe(false);
            expect(boxes.docOverflow).toBe(false);
            const wordmark = boxes.items[0]!;
            const gh = boxes.items[1]!;
            const toggle = boxes.items[2]!;
            for (const item of boxes.items) {
              expect(Math.abs(centre(item) - centre(wordmark)), "one row").toBeLessThanOrEqual(1);
            }
            for (const [i, a] of boxes.items.entries()) {
              for (const b of boxes.items.slice(i + 1)) {
                expect(a.x + a.w <= b.x + 0.5 || b.x + b.w <= a.x + 0.5, "no overlap").toBe(true);
              }
              // Touch: every target is 44 px tall and the icon link is 44 px wide.
              expect(a.h).toBeGreaterThanOrEqual(43.5);
            }
            expect(gh.w).toBeGreaterThanOrEqual(43.5);
            expect(gh.x, "GitHub is right of the theme toggle").toBeGreaterThan(
              toggle.x + toggle.w - 0.5,
            );
          });
        });
      }

      test("Dossiers is marked current on /t and under it", async ({ page, open }) => {
        await open("/t", { viewport: DESKTOP });
        const dossiers = page
          .locator('nav[aria-label="Primary"]')
          .getByRole("link", { name: "Dossiers" });
        await expect(dossiers).toHaveAttribute("aria-current", "page");
        await open("/t/Jesus", { ready: sectionHeading(page) });
        await expect(dossiers).toHaveAttribute("aria-current", "true");
        await expect(
          page.locator('nav[aria-label="Primary"]').getByRole("link", { name: "Today's index" }),
        ).not.toHaveAttribute("aria-current", /.+/);
      });
    });
  });

  test.describe("4K", () => {
    test("3840x2160 lays out at zoom 1.75 and a graph node is still clickable", async ({
      page,
      open,
    }) => {
      const errors = trackErrors(page);
      await open("/", { viewport: UHD, ready: page.locator("svg[role='group']").first() });
      const m = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        innerWidth,
        zoom: Number.parseFloat(getComputedStyle(document.documentElement).zoom),
      }));
      expect(m.scrollWidth).toBe(m.innerWidth);
      expect(m.zoom).toBe(1.75);
      const node = page.locator("svg[role='group'] a").nth(3);
      const href = await node.getAttribute("href");
      const box = await node.locator("circle").first().boundingBox();
      expect(box).not.toBeNull();
      // The first click selects, the second opens.
      await page.mouse.click(box!.x + box!.width / 2, box!.y + box!.height / 2);
      await expect(page.locator("[data-plate-ring]")).toHaveCount(1);
      await page.mouse.click(box!.x + box!.width / 2, box!.y + box!.height / 2);
      await expect(page).toHaveURL(new RegExp(`${href!.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`));
      assertNoErrors(errors);
    });

    test("an info tooltip opens next to its button at 3840", async ({ page, open }) => {
      await open("/t/Jesus", { viewport: UHD, ready: sectionHeading(page) });
      const button = page.locator('button[aria-label^="About"]:visible').first();
      await button.focus();
      const tip = page.locator('[role="tooltip"]:visible').first();
      await expect(tip).toBeVisible();
      const [b, t] = await Promise.all([button.boundingBox(), tip.boundingBox()]);
      expect(Math.abs(t!.x - b!.x)).toBeLessThan(40);
      expect(Math.abs(t!.y + t!.height - b!.y)).toBeLessThan(40);
    });

    test("at 3840 the content column reaches 55 percent of the viewport and the graph frame stays square", async ({
      page,
      open,
    }) => {
      await open("/", { viewport: UHD, ready: page.locator("[data-plate-frame]") });
      const m = await page.evaluate(() => {
        const first = document.querySelector("header a")!.getBoundingClientRect();
        const last = [...document.querySelectorAll("header a")].at(-1)!.getBoundingClientRect();
        const frame = document.querySelector("[data-plate-frame]")!.getBoundingClientRect();
        return {
          share: (last.right - first.left) / window.innerWidth,
          frame: [frame.width, frame.height],
        };
      });
      expect(m.share).toBeGreaterThan(0.55);
      expect(Math.abs(m.frame[0]! - m.frame[1]!)).toBeLessThan(2);
    });

    test("the contents rail fits the viewport at 3840", async ({ page, open }) => {
      await open("/t/Jesus", { viewport: UHD, ready: sectionHeading(page) });
      await page.evaluate(() => window.scrollTo(0, 900));
      await settleScroll(page);
      const bottom = await page
        .locator('nav[aria-label="Contents"]')
        .evaluate((el) => el.getBoundingClientRect().bottom);
      expect(bottom).toBeLessThanOrEqual(2160);
    });
  });

  test.describe("For machines at 1920", () => {
    test("the excerpt pads its right edge and the left column stays beside it", async ({
      page,
      open,
    }) => {
      await open("/machines", { viewport: { width: 1920, height: 1080 } });
      const pre = page.locator("#llms pre").last();
      await expect(pre).toBeVisible();
      const padRight = await pre.evaluate((el) =>
        Number.parseFloat(getComputedStyle(el).paddingRight),
      );
      expect(padRight).toBeGreaterThanOrEqual(20);
      const overflowX = await pre.evaluate((el) => getComputedStyle(el).overflowX);
      expect(overflowX).toBe("auto");
      const position = await page
        .locator("#llms > div")
        .first()
        .evaluate((el) => getComputedStyle(el).position);
      expect(position).toBe("sticky");
    });
  });

  test.describe("Home on a phone", () => {
    test("the node-count chip is not on the graph frame", async ({ page, open }) => {
      await open("/", { viewport: PHONE, ready: page.locator("svg[role='group']").first() });
      const m = await page.evaluate(() => {
        const chip = Array.from(document.querySelectorAll("figure span"))
          .find((el) => /\d+ nodes, \d+ edges/.test(el.textContent ?? ""))!
          .getBoundingClientRect();
        const frame = document.querySelector("figure > div")!.getBoundingClientRect();
        const caption = document.querySelector("figure figcaption")!.getBoundingClientRect();
        return {
          chipTop: chip.top,
          chipBottom: chip.bottom,
          frameBottom: frame.bottom,
          captionTop: caption.top,
        };
      });
      expect(m.chipTop).toBeGreaterThanOrEqual(m.frameBottom);
      expect(m.chipBottom).toBeLessThanOrEqual(m.captionTop + 1);
    });
  });

  test.describe("Dossier on a phone", () => {
    test("the bottom bar's copy button names the token count", async ({ page, open }) => {
      await open("/t/Jesus", { viewport: PHONE, ready: sectionHeading(page) });
      const button = page.getByLabel("Token budget and copy").getByRole("button");
      await expect(button).toHaveAccessibleName(/^Copy as context, [\d,]+ dossier tokens$/);
      await expect(button).toHaveText("Copy as context");
      const count = await button
        .locator("span[data-count]")
        .evaluate((el) => getComputedStyle(el, "::after").content);
      expect(count).toMatch(/^"[\d,]+ dossier tokens"$/);
    });
  });
});
