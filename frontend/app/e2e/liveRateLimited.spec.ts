import type { Page } from "@playwright/test";
import { eachTheme, expect, only, test } from "./support";

/** The 429 the live feed answers with when it asks the client to wait 30 s. */
const rateLimited = {
  status: 429,
  contentType: "application/problem+json",
  headers: { "retry-after": "30" },
  body: JSON.stringify({
    type: "about:blank",
    title: "Too many requests",
    status: 429,
    code: "rate_limited",
    request_id: "spec-live-429",
    detail: "12 per 1 minute",
  }),
};

/** The live-feed counters, with the given count of dossiers built today. */
const counters = (builtToday: number) => ({
  enwiki_edits_last_hour: 14,
  tracked_edits_last_hour: 0,
  window_complete: true,
  dossiers_built_today: builtToday,
  topics_tracked: 40,
});

/** A live-feed edit 30 s old. */
const edit = (cursor: number, title: string) => ({
  cursor,
  page_id: null,
  title,
  rev_new: 3000000 + cursor,
  rev_old: 2000000 + cursor,
  ts: new Date(Date.now() - 30_000).toISOString(),
  user_kind: "registered",
  byte_delta: 12,
});

/** The body of a connected live feed with these edits. */
const feed = (cursor: number, builtToday: number, edits: object[]) =>
  JSON.stringify({
    stream: "connected",
    server_time: new Date().toISOString(),
    cursor,
    last_event_at: new Date().toISOString(),
    counters: counters(builtToday),
    edits,
  });

/** Answers every live-feed request with a 429. */
function refuseLive(page: Page) {
  return page.route("**/api/v1/live**", (route) => route.fulfill(rateLimited));
}

// Every test here runs only on the desktop-1440 project.
test.describe("Live feed rate limits", only("desktop-1440"), () => {
  eachTheme(() => {
    test("a 429 from the live feed reads as paused, keeps the counts and rows, and retries after Retry-After", async ({
      page,
      open,
    }) => {
      await page.clock.install();
      let polls = 0;
      await page.route("**/api/v1/live**", async (route) => {
        polls += 1;
        if (polls === 2) {
          await route.fulfill(rateLimited);
          return;
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: feed(
            polls === 1 ? 2 : 3,
            7,
            polls === 1 ? [edit(2, "Replay B"), edit(1, "Replay A")] : [edit(3, "Live C")],
          ),
        });
      });
      await open("/");
      const main = page.locator("main");
      await expect(main.getByText("Replay A")).toBeVisible();
      await expect(main).toContainText("7 built today");
      await page.clock.fastForward(21_000);
      await expect.poll(() => polls).toBe(2);
      await expect(main).toContainText("Live edits paused, retrying shortly");
      await expect(page.locator("body")).not.toContainText("12 per 1 minute");
      await expect(page.locator("body")).not.toContainText("no edit data");
      // The feed is paused by the server: Pause is not offered as a working control.
      await expect(page.getByRole("button", { name: "Pause" })).toHaveAttribute(
        "aria-disabled",
        "true",
      );
      await expect(main.getByText("Replay A")).toBeVisible();
      await expect(main).toContainText("7 built today");
      // Retry-After is 30 s: nothing is asked before it passes.
      await page.clock.fastForward(20_000);
      expect(polls).toBe(2);
      await page.clock.fastForward(11_000);
      await expect.poll(() => polls).toBe(3);
      await expect(main).not.toContainText("Live edits paused");
      await expect(page.getByRole("button", { name: "Pause" })).not.toHaveAttribute(
        "aria-disabled",
        "true",
      );
      await expect(main).toContainText("7 built today");
    });
  });

  test("a reload whose first poll is refused still shows the built-today figure from this tab's last good poll", async ({
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
          cursor: 1,
          last_event_at: null,
          counters: counters(9),
          edits: [],
        }),
      }),
    );
    await open("/");
    await expect(page.locator("main")).toContainText("9 built today");
    await refuseLive(page);
    await page.reload();
    await expect(page.locator("[data-ledger-status]")).toHaveText(
      "Live edits paused, retrying shortly",
    );
    await expect(page.locator("main")).toContainText("9 built today");
  });

  eachTheme(() => {
    test("Home keeps its counts and edit rows through a 429 after leaving and returning, and after a reload", async ({
      page,
      open,
    }) => {
      await page.route("**/api/v1/live**", (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: feed(2, 34, [edit(2, "Replay B"), edit(1, "Replay A")]),
        }),
      );
      await open("/");
      const main = page.locator("main");
      await expect(main.getByText("Replay A")).toBeVisible();
      await expect(main.getByText("Replay B")).toBeVisible();
      await expect(main).toContainText("34 built today");

      await refuseLive(page);
      for (const way of ["leaving and returning", "reloading"]) {
        if (way === "reloading") {
          await page.reload();
        } else {
          await page.getByRole("link", { name: "Dossiers", exact: true }).first().click();
          await expect(page).toHaveURL(/\/t$/);
          await page.getByRole("link", { name: "Today's index", exact: true }).first().click();
        }
        await expect(page.locator("[data-ledger-status]")).toHaveText(
          "Live edits paused, retrying shortly",
        );
        await expect(main, way).toContainText("34 built today");
        await expect(main.getByText("Replay A"), way).toBeVisible();
        await expect(main.getByText("Replay B"), way).toBeVisible();
        await expect(page.locator("body")).not.toContainText("no edits yet");
        await expect(page.getByRole("button", { name: "Pause" })).toHaveAttribute(
          "aria-disabled",
          "true",
        );
      }
    });

    test("a first poll refused with an empty session shows one paused line instead of blank row slots, and no bare unit", async ({
      page,
      open,
    }) => {
      await page.addInitScript(() => window.sessionStorage.clear());
      await refuseLive(page);
      await open("/");
      const panel = page.locator("[data-ledger-panel]");
      await expect(panel.locator("[data-ledger-status]")).toHaveText(
        "Live edits paused, retrying shortly",
      );
      await expect(panel.getByText("Live edits paused, retrying shortly")).toHaveCount(1);
      await expect(panel.locator("tbody tr"), "no row slots, blank or not").toHaveCount(0);
      await expect(panel.locator("table")).toHaveCount(0);
      await expect(page.locator("body")).not.toContainText("12 per 1 minute");
      const main = page.locator("main");
      // With no counters yet, the line under the value says so instead of staying empty.
      expect((await page.locator("[data-record-sub]").allTextContents()).join(" | ")).toContain(
        "built today: unknown",
      );
      await expect(main).toContainText("Dossiers stored");
      // Every line under a value is empty or a whole phrase, never a unit on its own.
      for (const text of await page.locator("[data-record-sub]").allTextContents()) {
        expect(text.trim(), "a line under a value is empty or a whole phrase").toMatch(
          /^$|^\S+(?: \S+)+$/,
        );
        expect(text.trim()).not.toMatch(/^(built today|edits|min)$/);
      }
      const geometry = await page.evaluate(() => {
        const panelBox = document.querySelector("[data-ledger-panel]")!.getBoundingClientRect();
        const figure = document.querySelector("figure")!.getBoundingClientRect();
        return { panelBottom: panelBox.bottom, figureBottom: figure.bottom };
      });
      expect(
        Math.abs(geometry.panelBottom - geometry.figureBottom),
        "the columns still end together",
      ).toBeLessThanOrEqual(1);
    });

    test("a 429 after rows were shown keeps the last rows under the one status line, with the same number of slots and none blank", async ({
      page,
      open,
    }) => {
      await page.addInitScript(() => window.sessionStorage.clear());
      await page.clock.install();
      let polls = 0;
      await page.route("**/api/v1/live**", async (route) => {
        polls += 1;
        if (polls >= 2) {
          await route.fulfill(rateLimited);
          return;
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: feed(
            12,
            7,
            Array.from({ length: 12 }, (_, i) => edit(12 - i, `Replay ${12 - i}`)),
          ),
        });
      });
      await open("/", { viewport: { width: 1440, height: 1000 } });
      const panel = page.locator("[data-ledger-panel]");
      await expect(panel.getByText("Replay 1", { exact: true })).toBeVisible();
      // The replay spreads over 2 s of the page clock.
      await page.clock.fastForward(3000);
      const read = () =>
        panel.locator("tbody tr").evaluateAll((trs) => {
          const edits = trs.filter((tr) => /^\d\d:\d\d:\d\d/.test(tr.textContent ?? ""));
          return {
            slots: trs.length,
            edits: edits.map((tr) => tr.children[1]?.textContent ?? ""),
            blank: trs.filter((tr) => (tr.textContent ?? "").trim() === "").length,
            firstEditTop: edits[0]?.getBoundingClientRect().top ?? 0,
          };
        });
      const before = await read();
      expect(before.edits.length).toBeGreaterThan(4);
      expect(before.blank, "a full feed has no blank slot").toBe(0);

      await page.clock.fastForward(21_000);
      await expect.poll(() => polls).toBeGreaterThanOrEqual(2);
      const status = panel.locator("[data-ledger-status]");
      await expect(status).toHaveText("Live edits paused, retrying shortly");
      const after = await read();
      expect(after.slots, "the fixed slot count stays").toBe(before.slots);
      expect(after.blank, "no blank slot appears").toBe(0);
      // The status line takes one slot: the newest rows stay, the oldest one makes room.
      expect(after.edits).toEqual(before.edits.slice(0, after.edits.length));
      expect(after.edits.length).toBeGreaterThanOrEqual(before.edits.length - 1);
      expect((await status.boundingBox())!.y, "the status line is above the rows").toBeLessThan(
        after.firstEditTop,
      );
    });
  });
});
