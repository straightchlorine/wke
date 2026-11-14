import type { Page } from "@playwright/test";
import { AxeBuilder } from "@axe-core/playwright";
import { hitsControl } from "./hitAreas";
import { nearestHeading, waitForBudget } from "./readingSection";
import { eachTheme, expect, lightOnly, only, settleLayout, settleScroll, test } from "./support";

/** Waits for every finite animation and transition on the page, so a colour check does not read a half-faded one. */
async function settleAnimations(page: Page) {
  await page.evaluate(() =>
    Promise.allSettled(
      document
        .getAnimations()
        .filter((a) => Number.isFinite(a.effect?.getComputedTiming().endTime ?? 0))
        .map((a) => a.finished),
    ),
  );
}

async function activeInfo(page: Page) {
  return page.evaluate(() => {
    const el = document.activeElement;
    return {
      tag: el?.tagName ?? "",
      type: el instanceof HTMLInputElement ? el.type : "",
      value: el instanceof HTMLInputElement ? el.value : "",
      label: el instanceof HTMLInputElement ? (el.labels?.[0]?.textContent ?? "") : "",
    };
  });
}

test.describe("search-param changes keep focus and scroll", () => {
  lightOnly(() => {
    test(
      "typing in the Dossiers filter keeps every letter and the focus",
      only("desktop-1440"),
      async ({ page, open }) => {
        await open("/t/");
        await expect(page.locator("table tbody tr")).toHaveCount(30);
        const input = page.getByLabel("Filter dossiers by title");
        await input.click();
        await page.keyboard.type("lizz", { delay: 60 });
        await expect(input).toHaveValue("lizz");
        await expect(page).toHaveURL(/[?&]q=lizz(&|$)/);
        await expect(input).toBeFocused();
      },
    );

    test(
      "arrow keys walk the freshness radios with focus on the radio",
      only("desktop-1440"),
      async ({ page, open }) => {
        await open("/t/");
        await expect(page.locator("table tbody tr")).toHaveCount(30);
        await page.getByText(/^Up to date \d+$/).click();
        await page.keyboard.press("ArrowRight");
        await expect(page.getByRole("radio", { name: /^Out of date \d+$/ })).toBeChecked();
        expect(await activeInfo(page)).toMatchObject({
          tag: "INPUT",
          type: "radio",
          label: expect.stringMatching(/^Out of date/),
        });
        await page.keyboard.press("ArrowRight");
        await expect(page.getByRole("radio", { name: /^Not checked \d+$/ })).toBeChecked();
        expect(await activeInfo(page)).toMatchObject({
          tag: "INPUT",
          type: "radio",
          label: expect.stringMatching(/^Not checked/),
        });
      },
    );

    test(
      "key 3 mid-dossier keeps the scroll position and focus",
      only("mobile-390", "tablet-768", "desktop-1440"),
      async ({ page, open }) => {
        await open("/t/Apollo_11");
        await expect(page.locator('section[id^="s"] [data-section-heading]')).toHaveCount(38);
        await page.evaluate(() => window.scrollTo(0, 3000));
        const before = await settleScroll(page);
        await page.keyboard.press("3");
        await expect(page).toHaveURL(/budget=32000/);
        await waitForBudget(page, 32000);
        const after = await page.evaluate(() => window.scrollY);
        expect(Math.abs(after - before)).toBeLessThanOrEqual(50);
        expect(after).toBeGreaterThan(2900);
        expect((await activeInfo(page)).tag).not.toBe("BODY");
      },
    );

    test(
      "clicking 2k mid-dossier keeps the section being read and focus",
      only("mobile-390", "tablet-768", "desktop-1440"),
      async ({ page, open }) => {
        await open("/t/Jesus");
        await expect(page.locator('section[id^="s"] [data-section-heading]')).toHaveCount(46);
        await page.evaluate(() => window.scrollTo(0, 2000));
        await settleScroll(page);
        const before = await nearestHeading(page);
        await page.locator("label:visible", { hasText: /^2k$/ }).first().click();
        await expect(page).toHaveURL(/budget=2000/);
        await waitForBudget(page, 2000);
        const after = await nearestHeading(page);
        // Deep inside a long section, a shorter section may no longer reach the reader's depth, so its heading ends up lower than before.
        // The same section must still be the one at the top.
        expect(after.n).toBe(before.n);
        expect(after.top).toBeGreaterThanOrEqual(before.top);
        const active = await activeInfo(page);
        expect(active.tag).not.toBe("BODY");
      },
    );
  });
});

test.describe("not-built panel contrast", () => {
  eachTheme(() => {
    test(
      "the not-built panel passes axe color-contrast",
      only("mobile-390", "desktop-1440"),
      async ({ page, open }) => {
        await page.route(/\/api\/v1\/dossiers(\?[^/]*)?$/, async (route) => {
          if (route.request().method() !== "POST") {
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
              detail: 'No Wikipedia article titled "No Such Article Xyz".',
              code: "not_found",
              request_id: "spec-contrast-1",
            }),
          });
        });
        await open("/t/No_Such_Article_Xyz", { ready: page.getByText("Request ID:") });
        await settleAnimations(page);
        const results = await new AxeBuilder({ page }).withRules(["color-contrast"]).analyze();
        expect(results.violations.flatMap((v) => v.nodes.map((n) => n.html.slice(0, 120)))).toEqual(
          [],
        );
      },
    );
  });
});

const APP_URL = /https?:\/\/[a-zA-Z0-9.-]+(?::\d+)?(?=\/(?:api|mcp|llms\.txt)|['"\s]|$)/g;

test.describe("For machines base URL", () => {
  lightOnly(() => {
    test(
      "the Base URL row and every code block quote one origin before any scroll",
      only("desktop-1440"),
      async ({ page, open }) => {
        await open("/machines");
        const baseRow = page.locator("code", { hasText: /^https?:\/\// }).first();
        await expect(baseRow).toHaveText("http://localhost:8010");
        await expect.poll(() => page.locator("pre").count()).toBeGreaterThan(3);
        await settleLayout(page);
        const texts = await page.locator("pre").allInnerTexts();
        const origins = new Set<string>([(await baseRow.innerText()).trim()]);
        for (const text of texts) {
          for (const m of text.matchAll(APP_URL)) {
            origins.add(new URL(m[0]).origin);
          }
        }
        expect([...origins]).toEqual(["http://localhost:8010"]);
      },
    );
  });
});

test.describe("Dossiers freshness control at 390", only("mobile-390"), () => {
  lightOnly(() => {
    test("the segments end at the search input's right edge", async ({ page, open }) => {
      await open("/t/");
      await expect(page.locator("table tbody tr")).toHaveCount(30);
      const edges = await page.evaluate(() => {
        const input = document.querySelector("#dossier-filter")?.getBoundingClientRect();
        const group = document.querySelector("[role=radiogroup][aria-label=Freshness]");
        const groupBox = group?.getBoundingClientRect();
        const labels = [...(group?.querySelectorAll("label") ?? [])].map(
          (l) => l.getBoundingClientRect().right,
        );
        return {
          input: input?.right ?? 0,
          group: groupBox?.right ?? 0,
          lastLabel: Math.max(...labels),
        };
      });
      expect(Math.abs(edges.group - edges.input)).toBeLessThanOrEqual(1);
      expect(edges.lastLabel).toBeLessThanOrEqual(edges.group);
    });
  });
});

test.describe("plain 404", () => {
  eachTheme(() => {
    test(
      "reuses the not-built panel: one sentence, the search box, Dossiers and Today's index",
      only("mobile-390", "desktop-1440"),
      async ({ page, open }) => {
        await open("/nope/nothing");
        await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
        await expect(
          page.getByText("This address has no page. Search for a topic instead."),
        ).toBeVisible();
        await expect(page.getByRole("combobox", { name: "Search for a topic" })).toBeVisible();
        await expect(
          page.getByRole("main").getByRole("link", { name: "Dossiers" }),
        ).toHaveAttribute("href", "/t");
        await expect(
          page.getByRole("main").getByRole("link", { name: "Today's index" }),
        ).toHaveAttribute("href", "/");
        await settleAnimations(page);
        const results = await new AxeBuilder({ page }).withRules(["color-contrast"]).analyze();
        expect(results.violations.flatMap((v) => v.nodes.map((n) => n.html.slice(0, 120)))).toEqual(
          [],
        );
      },
    );
  });

  lightOnly(() => {
    test(
      "a title typed into the 404 search opens its dossier",
      only("desktop-1440"),
      async ({ page, open }) => {
        await open("/nope/nothing");
        const box = page.getByRole("combobox", { name: "Search for a topic" });
        await box.fill("Jesus");
        await box.press("Enter");
        await expect(page).toHaveURL(/\/t\/Jesus/);
      },
    );
  });
});

test.describe("44 px tap areas at 390", only("mobile-390"), () => {
  lightOnly(() => {
    test("Dossiers rows: the whole row opens the dossier, the revision link keeps 24 px", async ({
      page,
      open,
    }) => {
      await open("/t/");
      await expect(page.locator("table tbody tr")).toHaveCount(30);
      for (let i = 0; i < 4; i++) {
        const rowHit = await page.evaluate((index) => {
          const tr = document.querySelectorAll("table tbody tr")[index];
          tr?.scrollIntoView({ block: "center" });
          const box = tr?.getBoundingClientRect();
          const link = tr?.querySelector("td:first-child a");
          if (!box || !link) {
            return { height: 0, allLink: false };
          }
          // Probe at an x position away from the revision link, which sits on top of the row link.
          const x = box.left + 250;
          let allLink = true;
          for (let y = box.top + 2; y < box.bottom - 2; y += 4) {
            const hit = document.elementFromPoint(x, y);
            allLink = allLink && (hit === link || link.contains(hit));
          }
          return { height: box.height, allLink };
        }, i);
        expect(rowHit.height, `row ${i}`).toBeGreaterThanOrEqual(44);
        expect(rowHit.allLink, `row ${i} is one link`).toBe(true);
        expect(
          await hitsControl(page, "table tbody tr a[href*='oldid']", i, 11),
          `revision link ${i}`,
        ).toBe(true);
      }
    });

    test("section chips", async ({ page, open }) => {
      await open("/t/Jesus");
      await expect(page.locator('section[id^="s"] [data-section-heading]')).toHaveCount(46);
      for (let i = 0; i < 3; i++) {
        expect(await hitsControl(page, 'nav[aria-label="Sections"] a', i, 21), `chip ${i}`).toBe(
          true,
        );
      }
    });
  });
});
