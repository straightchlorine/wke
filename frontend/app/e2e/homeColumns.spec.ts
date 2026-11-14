import type { Locator, Page } from "@playwright/test";
import { eachTheme, expect, only, settleLayout, test } from "./support";

/** The graph's frame, which Home renders once the most-read list has loaded. */
const graph = (page: Page) => page.locator("svg[role='group']").first();

type Open = (
  path: string,
  options?: { viewport?: { width: number; height: number }; ready?: Locator },
) => Promise<void>;

async function openHome(page: Page, open: Open, width: number, height: number) {
  await open("/", { viewport: { width, height }, ready: graph(page) });
  await expect(page.getByRole("heading", { level: 1 }).first()).toContainText("Cited context");
}

function geometry(page: Page) {
  return page.evaluate(() => {
    const frame = document.querySelector("[data-plate-frame]")!.getBoundingClientRect();
    const figure = document.querySelector("figure")!.getBoundingClientRect();
    const board = document.querySelector("[data-plate-board]")!.getBoundingClientRect();
    const caption = document.querySelector("figcaption")!.getBoundingClientRect();
    const panel = document.querySelector("[data-ledger-panel]")!.getBoundingClientRect();
    const hero = document.querySelector("h1")!.getBoundingClientRect();
    const rows = [...document.querySelectorAll("[data-ledger-panel] tbody tr")].map((r) => ({
      height: r.getBoundingClientRect().height,
      top: r.getBoundingClientRect().top,
      filled: /^\d\d:\d\d:\d\d/.test((r.textContent ?? "").trim()),
    }));
    return {
      frame: { w: frame.width, h: frame.height },
      figureBottom: figure.bottom,
      board: { top: board.top, bottom: board.bottom },
      captionBottom: caption.bottom,
      panel: { top: panel.top, bottom: panel.bottom, height: panel.height },
      heroLeft: hero.left,
      figureLeft: figure.left,
      rows,
      vh: window.innerHeight,
    };
  });
}

// Home's two columns end on one line from 1024px up, and the concept graph
// frame is a square at every width. It sets its own viewport, so it runs only
// on the desktop-1440 project.
test.describe("Home columns", only("desktop-1440"), () => {
  eachTheme(() => {
    for (const [width, height] of [
      [1440, 900],
      [1920, 1080],
      [3840, 2160],
    ] as const) {
      test(`Home at ${width}x${height}: the hero starts left of the graph and every edit slot is 26px`, async ({
        page,
        open,
      }) => {
        await openHome(page, open, width, height);
        const g = await geometry(page);
        expect(g.heroLeft).toBeLessThan(g.figureLeft);
        for (const r of g.rows) {
          expect(Math.round(r.height / (width > 3400 ? 1.75 : 1))).toBe(26);
        }
      });
    }

    test("Home from 1024 up: the columns end together and the frame stays square", async ({
      page,
      open,
    }) => {
      for (const [width, height] of [
        [1024, 768],
        [1280, 800],
        [1399, 800],
        [1600, 900],
      ] as const) {
        await openHome(page, open, width, height);
        const g = await geometry(page);
        expect(Math.abs(g.frame.w - g.frame.h), `${width}: frame`).toBeLessThanOrEqual(1);
        expect(
          Math.abs(g.panel.bottom - g.figureBottom),
          `${width}: column bottoms`,
        ).toBeLessThanOrEqual(1);
        expect(g.rows.length, `${width}: slots`).toBeGreaterThanOrEqual(5);
      }
    });

    test("Home below 1024 stacks the columns and keeps a fixed-height panel", async ({
      page,
      open,
    }) => {
      for (const [width, height] of [
        [768, 1024],
        [390, 844],
      ] as const) {
        await openHome(page, open, width, height);
        const g = await geometry(page);
        expect(Math.abs(g.frame.w - g.frame.h), `${width}: frame`).toBeLessThanOrEqual(1);
        expect(g.panel.top, `${width}: panel under the graph`).toBeGreaterThan(g.figureBottom);
        expect(g.panel.height, `${width}: fixed panel`).toBe(328);
        expect(g.rows, "a 328px panel holds ten 26px slots under its title row").toHaveLength(10);
      }
    });

    test("Home at 1920x1080: graph frame, selected-article panel, caption and three edit rows are on screen on load", async ({
      page,
      open,
    }) => {
      await page.route("**/api/v1/live**", (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            stream: "connected",
            server_time: new Date().toISOString(),
            cursor: 8,
            last_event_at: new Date().toISOString(),
            counters: {
              enwiki_edits_last_hour: 14,
              tracked_edits_last_hour: 0,
              window_complete: true,
              dossiers_built_today: 7,
              topics_tracked: 40,
            },
            edits: Array.from({ length: 8 }, (_, i) => ({
              cursor: i + 1,
              page_id: null,
              title: `Replayed ${i}`,
              rev_new: 4000000 + i,
              rev_old: 3000000 + i,
              ts: new Date(Date.now() - 20_000 - i * 1000).toISOString(),
              user_kind: "registered",
              byte_delta: 21,
            })),
          }),
        }),
      );
      await open("/", { viewport: { width: 1920, height: 1080 }, ready: graph(page) });
      await expect(page.locator("[data-ledger-panel]").getByText("Replayed 0")).toBeVisible({
        timeout: 15_000,
      });
      await settleLayout(page);
      const g = await geometry(page);
      expect(g.frame.h).toBeGreaterThan(600);
      expect(g.board.bottom, "board").toBeLessThanOrEqual(g.vh);
      expect(g.captionBottom, "caption").toBeLessThanOrEqual(g.vh);
      const visible = g.rows.filter((r) => r.filled && r.top + r.height <= g.vh);
      expect(visible.length, "edit rows on screen").toBeGreaterThanOrEqual(3);
    });

    test("Home at 1440x900: what sits below the fold (reported)", async ({ page, open }) => {
      await openHome(page, open, 1440, 900);
      const g = await geometry(page);
      // The frame is at most the window height minus 88px, and the selected-article panel (data-plate-board) starts above the fold.
      expect(g.frame.h + 88).toBeLessThanOrEqual(g.vh);
      expect(g.board.top).toBeLessThan(g.vh);
      test.info().annotations.push({
        type: "below the fold",
        description: `board bottom ${Math.round(g.board.bottom)}, caption bottom ${Math.round(g.captionBottom)}, figure bottom ${Math.round(g.figureBottom)} of ${g.vh}`,
      });
    });

    test("Home: the panel never changes height and keeps its slot count while edits arrive", async ({
      page,
      open,
    }) => {
      test.setTimeout(90_000);
      await page.clock.install();
      let polls = 0;
      await page.route("**/api/v1/live**", async (route) => {
        polls += 1;
        const count = polls === 1 ? 4 : (polls % 4) + 1;
        const edits = Array.from({ length: count }, (_, i) => ({
          cursor: polls * 10 + i,
          page_id: null,
          title: `Arrival ${polls}.${i}`,
          rev_new: 4000000 + polls * 10 + i,
          rev_old: 3000000 + polls * 10 + i,
          ts: new Date(Date.now() - 5_000).toISOString(),
          user_kind: "registered",
          byte_delta: 21,
        }));
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            stream: "connected",
            server_time: new Date().toISOString(),
            cursor: polls * 10 + count,
            last_event_at: new Date().toISOString(),
            counters: {
              enwiki_edits_last_hour: 14,
              tracked_edits_last_hour: 0,
              window_complete: true,
              dossiers_built_today: 7,
              topics_tracked: 40,
            },
            edits,
          }),
        });
      });
      await open("/", { viewport: { width: 1440, height: 900 }, ready: graph(page) });
      await expect(page.locator("[data-ledger-panel]").getByText("Arrival 1.0")).toBeVisible();
      const first = await geometry(page);
      for (let step = 0; step < 8; step += 1) {
        const before = polls;
        await page.clock.fastForward(21_000);
        await expect.poll(() => polls).toBeGreaterThan(before);
        await settleLayout(page);
        const g = await geometry(page);
        expect(Math.abs(g.panel.height - first.panel.height)).toBeLessThanOrEqual(0.5);
        expect(g.rows).toHaveLength(first.rows.length);
        expect(Math.abs(g.panel.bottom - g.figureBottom)).toBeLessThanOrEqual(1);
      }
      expect(polls).toBeGreaterThanOrEqual(5);
    });
  });
});
