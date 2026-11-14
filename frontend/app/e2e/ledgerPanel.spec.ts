import type { Page } from "@playwright/test";
import { liveEdit, liveFeedBody, rateLimitedResponse } from "./mockApi";
import { eachTheme, expect, lightOnly, only, settle, settleLayout, test } from "./support";

/** Panel, figure and left-column geometry in page coordinates. */
function geometry(page: Page) {
  return page.evaluate(() => {
    const panel = document.querySelector("[data-ledger-panel]")!.getBoundingClientRect();
    const figure = document.querySelector("figure")!.getBoundingClientRect();
    const h1 = document.querySelector("h1")!.getBoundingClientRect();
    const rows = [...document.querySelectorAll("[data-ledger-panel] tbody tr")].map(
      (r) => r.getBoundingClientRect().height,
    );
    const pause = [...document.querySelectorAll("[data-ledger-panel] button")]
      .find((b) => /^(Pause|Resume)$/.test(b.textContent ?? ""))!
      .getBoundingClientRect();
    return {
      panelHeight: panel.height,
      panelBottom: panel.bottom + window.scrollY,
      figureBottom: figure.bottom + window.scrollY,
      figureHeight: figure.height,
      columnHeight: panel.bottom + window.scrollY - (h1.top + window.scrollY),
      rows,
      pause: {
        x: Math.round(pause.right + window.scrollX),
        y: Math.round(pause.top + window.scrollY),
        w: Math.round(pause.width),
      },
      status: document.querySelector("[data-ledger-status]")!.textContent ?? "",
      scrollOk: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    };
  });
}

/** Geometry once the panel and figure heights have stopped changing, so a slow layout is not measured while it settles. */
async function settledGeometry(page: Page) {
  await page.locator("figure").first().waitFor();
  await settle(page, async () => {
    const g = await geometry(page);
    return [Math.round(g.panelHeight), Math.round(g.figureHeight)];
  });
  return geometry(page);
}

/** A live-feed edit that happened five seconds ago. */
const arrival = (cursor: number, title: string) =>
  liveEdit({ cursor, title, ageMs: 5_000, rev: 4000000 + cursor, byteDelta: 21 });

eachTheme(() => {
  test.describe("with the pause stored", () => {
    test.use({ paused: true });

    test(
      "a stored pause reads as paused in the status row and the marker, Resume brings back listening since",
      only("desktop-1440", "mobile-390"),
      async ({ page, open }) => {
        await open("/");
        const panel = page.locator("[data-ledger-panel]");
        const button = panel.getByRole("button", { name: /^(Pause|Resume)$/ });
        await expect(button).toHaveText("Resume");
        await expect(panel.locator("[data-ledger-status]")).toHaveText(/paused/);
        await expect(panel).toContainText(/live edits paused/i);
        await expect(panel).not.toContainText("listening since");
        await button.click();
        await expect(button).toHaveText("Pause");
        await expect(panel).toContainText(/listening since/);
        await expect(panel.locator("[data-ledger-status]")).not.toHaveText(/paused/);
      },
    );
  });
});

lightOnly(() => {
  test(
    "the edits panel keeps one height and ends where the graph figure ends, over 60 s of arrivals, a 429 and a pause",
    only("mobile-390", "tablet-1024", "desktop-1440"),
    async ({ page, open }) => {
      test.setTimeout(90_000);
      const width = page.viewportSize()!.width;
      await page.clock.install();
      let polls = 0;
      await page.route("**/api/v1/live**", async (route) => {
        polls += 1;
        if (polls === 4) {
          await route.fulfill(rateLimitedResponse("r"));
          return;
        }
        // Poll 1 is the replay and poll 2 is a burst above ringBurstLimit. Every other poll returns 1 to 3 edits, except poll 4, which is the 429.
        const count = polls === 1 ? 4 : polls === 2 ? 6 : (polls % 3) + 1;
        const edits = Array.from({ length: count }, (_, i) =>
          arrival(polls * 10 + i, `Arrival ${polls}.${i}`),
        );
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: liveFeedBody({ cursor: polls * 10 + count, builtToday: 7, edits }),
        });
      });
      await open("/");
      await expect(page.locator("[data-ledger-panel]").getByText("Arrival 1.0")).toBeVisible();
      const first = await geometry(page);
      const seen = [first];
      for (let step = 0; step < 6; step += 1) {
        await page.clock.fastForward(11_000);
        // The poll the clock just fired has reached the route once the count holds for two frames.
        await settle(page, async () => polls);
        if (polls === 4) {
          await expect(page.locator("[data-ledger-status]")).toHaveText(
            "Live edits paused, retrying shortly",
          );
        }
        await settleLayout(page);
        seen.push(await geometry(page));
        if (step === 2) {
          await page.getByRole("button", { name: "Pause" }).click();
        }
        if (step === 4) {
          await page.getByRole("button", { name: "Resume" }).click();
        }
      }
      expect(polls).toBeGreaterThanOrEqual(3);
      for (const g of seen) {
        expect(g.scrollOk).toBe(true);
        // Each slot is LEDGER_ROW_PX tall, whether it holds an edit, the "+N more" row, the marker, a status line or a blank.
        // The slot count follows the panel height, not the number of edits that arrive.
        expect(g.rows.length).toBeGreaterThanOrEqual(5);
        expect(g.rows).toHaveLength(first.rows.length);
        for (const h of g.rows) {
          expect(h).toBe(26);
        }
        expect(Math.abs(g.panelHeight - first.panelHeight)).toBeLessThanOrEqual(0.5);
        expect(
          Math.abs(g.pause.x - first.pause.x) +
            Math.abs(g.pause.y - first.pause.y) +
            Math.abs(g.pause.w - first.pause.w),
        ).toBeLessThanOrEqual(1);
        if (width >= 1024) {
          expect(
            Math.abs(g.panelBottom - g.figureBottom),
            "panel bottom meets figure bottom",
          ).toBeLessThanOrEqual(1);
        }
      }
      expect(
        seen.some((g) => g.status === "Live edits paused, retrying shortly"),
        seen.map((g) => g.status).join(" | "),
      ).toBe(true);
    },
  );

  test(
    "the edits panel stays one height with no edits and with a 429 first",
    only("mobile-390", "tablet-1024", "desktop-1440"),
    async ({ page, open }) => {
      const width = page.viewportSize()!.width;
      const heights: Array<Awaited<ReturnType<typeof geometry>>> = [];
      for (const state of ["empty", "limited"] as const) {
        await page.route("**/api/v1/live**", (route) =>
          state === "limited"
            ? route.fulfill(rateLimitedResponse("r"))
            : route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({
                  stream: "connected",
                  server_time: new Date().toISOString(),
                  cursor: 1,
                  last_event_at: null,
                  counters: {
                    enwiki_edits_last_hour: 0,
                    tracked_edits_last_hour: 0,
                    window_complete: true,
                    dossiers_built_today: 3,
                    topics_tracked: 40,
                  },
                  edits: [],
                }),
              }),
        );
        await open("/");
        if (state === "limited") {
          // The feed is empty and the server asked for a pause, so the panel shows one status line and no row slots.
          await expect(page.locator("[data-ledger-panel] [data-ledger-status]")).toHaveText(
            "Live edits paused, retrying shortly",
          );
        } else {
          await expect(page.locator("[data-ledger-panel] tbody tr").first()).toBeAttached();
        }
        heights.push(await settledGeometry(page));
      }
      const [empty, limited] = heights;
      if (!empty || !limited) {
        throw new Error("expected one geometry per state");
      }
      expect(empty.rows.length).toBeGreaterThanOrEqual(5);
      expect(limited.rows, "a refused first poll shows one line, not blank slots").toHaveLength(0);
      for (const g of heights) {
        expect(Math.abs(g.panelHeight - heights[0]!.panelHeight)).toBeLessThanOrEqual(0.5);
        if (width >= 1024) {
          expect(Math.abs(g.panelBottom - g.figureBottom)).toBeLessThanOrEqual(1);
        }
      }
    },
  );
});
