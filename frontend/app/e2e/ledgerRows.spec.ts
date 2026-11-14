import type { Page } from "@playwright/test";
import { liveEdit, liveFeedBody } from "./mockApi";
import { expect, lightOnly, only, test } from "./support";

// The edits panel: "last N" reads inline after the title, the rows start right
// under the marker row and fill the slots, and a slot is blank only when there
// are fewer edits than slots (always after the last row). Sets its own
// viewport, so it runs only on the desktop-1440 project.

/** A replayed edit, `cursor` seconds older than the 30 s base. */
const replay = (cursor: number) =>
  liveEdit({
    cursor,
    title: `Replay ${cursor}`,
    ageMs: 30_000 + cursor * 1000,
    rev: 3000000 + cursor,
    byteDelta: 12,
  });

/** Serves a live feed with `edits` replayed edits and clears the stored session state. */
async function serveFeed(page: Page, edits: number) {
  await page.addInitScript(() => window.sessionStorage.clear());
  await page.route("**/api/v1/live**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: liveFeedBody({
        cursor: edits,
        builtToday: 7,
        edits: Array.from({ length: edits }, (_, i) => replay(edits - i)),
      }),
    }),
  );
}

function panel(page: Page) {
  return page.evaluate(() => {
    const root = document.querySelector("[data-ledger-panel]")!;
    const heading = root.querySelector("h2")!.getBoundingClientRect();
    const status = root.querySelector("[data-ledger-status]")!.getBoundingClientRect();
    const rows = [...root.querySelectorAll("tbody tr")].map((tr) => ({
      blank: tr.getAttribute("aria-hidden") === "true",
      marker: /listening since/.test(tr.textContent ?? ""),
      top: tr.getBoundingClientRect().top,
      bottom: tr.getBoundingClientRect().bottom,
      text: (tr.textContent ?? "").trim(),
    }));
    const footer = root.querySelector("[data-ledger-footer]")!.getBoundingClientRect();
    return {
      headingRight: heading.right,
      headingBaseTop: heading.top,
      headingBottom: heading.bottom,
      statusLeft: status.left,
      statusTop: status.top,
      statusBottom: status.bottom,
      statusText: root.querySelector("[data-ledger-status]")!.textContent ?? "",
      rows,
      footerTop: footer.top,
    };
  });
}

test.describe("Edits panel rows", only("desktop-1440"), () => {
  lightOnly(() => {
    for (const [width, height] of [
      [1440, 900],
      [1920, 1080],
    ] as const) {
      test(`edits panel at ${width}: "last N" is inline after the title and a full feed fills every slot under the marker`, async ({
        page,
        open,
      }) => {
        await serveFeed(page, 14);
        await open("/", {
          viewport: { width, height },
          ready: page.locator("[data-ledger-panel]").getByText("Replay 1", { exact: true }),
        });
        const g = await panel(page);
        expect(g.statusText).toMatch(/^last \d+$/);
        expect(g.statusLeft, "the count follows the title on its line").toBeGreaterThanOrEqual(
          g.headingRight - 0.5,
        );
        expect(g.statusTop, "on the title's own line").toBeLessThan(g.headingBottom);
        const marker = g.rows.findIndex((r) => r.marker);
        expect(marker, "the marker row is the first slot").toBe(0);
        expect(
          g.rows.filter((r) => r.blank),
          "no blank slot while there are more edits than slots",
        ).toHaveLength(0);
        const last = g.rows[g.rows.length - 1]!;
        expect(last.text).toMatch(/^\d\d:\d\d:\d\d/);
        expect(g.footerTop - last.bottom, "no band under the last row").toBeLessThanOrEqual(26);
      });

      test(`edits panel at ${width}: with fewer edits than slots the blank slots come after the last row`, async ({
        page,
        open,
      }) => {
        await serveFeed(page, 2);
        await open("/", {
          viewport: { width, height },
          ready: page.locator("[data-ledger-panel]").getByText("Replay 1", { exact: true }),
        });
        const g = await panel(page);
        const edits = g.rows.filter((r) => /^\d\d:\d\d:\d\d/.test(r.text));
        expect(edits).toHaveLength(2);
        const marker = g.rows.findIndex((r) => r.marker);
        const firstEdit = g.rows.findIndex((r) => /^\d\d:\d\d:\d\d/.test(r.text));
        expect(firstEdit, "rows start right under the marker row").toBe(marker + 1);
        const lastEdit = g.rows
          .map((r, i) => (/^\d\d:\d\d:\d\d/.test(r.text) ? i : -1))
          .reduce((a, b) => Math.max(a, b));
        for (const [i, r] of g.rows.entries()) {
          if (r.blank) {
            expect(i, "a blank slot is after the last edit row").toBeGreaterThan(lastEdit);
          }
        }
        expect(g.rows.length, "three edit rows at least, plus the marker").toBeGreaterThanOrEqual(
          4,
        );
      });
    }
  });
});
