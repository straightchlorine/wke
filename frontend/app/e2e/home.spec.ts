import type { Page } from "@playwright/test";
import { asObject, fixtureObject } from "./fixtureObject";
import { dossierEnvelope } from "./mockApi";
import { trackErrors, assertNoErrors, expectShellRendered } from "./errorTracking";
import { eachTheme, expect, only, test } from "./support";

/** The graph's frame, which Home renders once the most-read list has loaded. */
const graph = (page: Page) => page.locator("svg[role='group']").first();

/** The length of a JSON array, or 0 for anything else. */
function arrayLength(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}

/** A live-feed edit that happened `ageSeconds` ago. */
const liveEdit = (cursor: number, title: string, ageSeconds: number) => ({
  cursor,
  page_id: null,
  title,
  rev_new: 2000000 + cursor,
  rev_old: 1000000 + cursor,
  ts: new Date(Date.now() - ageSeconds * 1000).toISOString(),
  user_kind: "registered",
  byte_delta: 10 + cursor,
});

test("home has no console errors and no horizontal overflow", async ({ page, open }) => {
  const errors = trackErrors(page);

  await open("/", { ready: graph(page) });
  await expectShellRendered(page);

  const hasOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );

  assertNoErrors(errors);
  expect(hasOverflow).toBe(false);
});

test("the index's column headers, chip budgets and top dossier are real", async ({
  page,
  open,
}) => {
  const errors = trackErrors(page);

  await open("/", { ready: graph(page) });
  await expectShellRendered(page);

  // The columns are headed by the article with its edits line, Fits in, and Views.
  // The API has no day-over-day figure, so there is no column for it.
  await expect(
    page.getByText("Article, edits in the last hour", { exact: true }).first(),
  ).toBeVisible();
  // exact: true keeps "Views" from matching the node tooltips' "N views" text.
  await expect(page.getByText("Views", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Fits in").first()).toBeVisible();

  // At least one chip shows a built budget or "queued". A budget chip starts with words only a screen reader gets.
  const chipTexts = await page
    .locator("ol li >> text=/^(Fits in )?(2k|8k|32k|queued)$/")
    .allTextContents();
  expect(chipTexts.length).toBeGreaterThan(0);

  const pinned = page.getByRole("button", { name: /^pinned \d{4}-\d\d-\d\d, \d\d:\d\d UTC$/ });
  await expect(pinned).toBeVisible();

  // The token count comes from the dossier's own budget, not from the list item.
  await pinned.hover();
  await expect(
    page.getByRole("tooltip").getByText(/^Revision \d+, [\d,]+ of [\d,]+ tokens$/),
  ).toBeVisible();

  assertNoErrors(errors);
});

for (const width of [1024, 1440]) {
  eachTheme(() => {
    test(
      `the edits counter is a number with its own listening-since line before the first edit, and the marker row repeats it at ${width}`,
      only("desktop-1440"),
      async ({ page, open }) => {
        const errors = trackErrors(page);
        await open("/", { viewport: { width, height: 900 }, ready: graph(page) });
        await expectShellRendered(page);
        const ledger = page
          .locator("table")
          .filter({ has: page.locator("th", { hasText: "Time, UTC" }) });
        await expect(ledger.locator("tbody tr").first()).toBeVisible();
        const parts = await page.evaluate(() => {
          const label = [...document.querySelectorAll("span")].find((s) =>
            s.textContent?.startsWith("Edits seen since page load"),
          );
          const row = label?.closest("[data-record-row]");
          const kids = row ? [...row.children] : [];
          return {
            slot: kids[2]?.textContent ?? "",
            unit: row?.parentElement?.querySelector("[data-record-sub]")?.textContent ?? "",
            rowHeight: row?.getBoundingClientRect().height ?? 0,
          };
        });
        expect(parts.slot).toBe("0");
        expect(parts.unit).toMatch(/^since \d\d:\d\d UTC$/);
        expect(parts.rowHeight).toBeLessThan(40);
        // The marker row repeats the counter's start time, to the second.
        await expect(ledger.getByText(/^listening since \d\d:\d\d:\d\d UTC$/)).toBeVisible();
        assertNoErrors(errors);
      },
    );
  });
}

test(
  "the Home graph has no label collisions and labels at least its 10 most-read at 1440",
  only("desktop-1440"),
  async ({ page, open }) => {
    const errors = trackErrors(page);

    await open("/", { viewport: { width: 1440, height: 900 }, ready: graph(page) });
    await expectShellRendered(page);

    const labels = page.locator("svg[role=group] text:not([x^='+']):not([data-hull-label])");
    const labelCount = await labels.count();
    expect(labelCount).toBeGreaterThanOrEqual(10);

    // Labels are laid out again once the label font has loaded, so read every box in one pass after that.
    await page.evaluate(() => document.fonts.ready);
    await expect(graph(page)).toHaveCSS("opacity", "1");
    const boxes = await page.evaluate(() =>
      [...document.querySelectorAll("svg[role=group] text:not([x^='+'])")].map((el) => {
        const r = el.getBoundingClientRect();
        return { x: r.x, y: r.y, width: r.width, height: r.height };
      }),
    );
    let collisions = 0;
    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        const a = boxes[i];
        const b = boxes[j];
        if (!a || !b) {
          continue;
        }
        const overlap =
          a.x < b.x + b.width &&
          a.x + a.width > b.x &&
          a.y < b.y + b.height &&
          a.y + a.height > b.y;
        if (overlap) {
          collisions += 1;
        }
      }
    }
    expect(collisions).toBe(0);
    assertNoErrors(errors);
  },
);

test(
  "Home graph nodes stay clear of the frame wall",
  only("desktop-1440"),
  async ({ page, open }) => {
    const errors = trackErrors(page);

    await open("/", { viewport: { width: 1440, height: 900 } });
    await expectShellRendered(page);

    const circles = page.locator("svg[role='group'] a > circle:first-of-type");
    await expect(circles.first()).toBeVisible();

    // The frame and every circle are read in one evaluate, so all boxes come from the same layout.
    const measured = await page.evaluate(() => {
      const svgEl = document.querySelector<SVGSVGElement>("svg[role='group']");
      if (!svgEl) {
        return null;
      }
      const frameBox = svgEl.getBoundingClientRect();
      const viewBoxWidth = svgEl.viewBox.baseVal.width;
      const circleBoxes = Array.from(svgEl.querySelectorAll("a > circle:first-of-type")).map((c) =>
        c.getBoundingClientRect(),
      );
      return {
        frame: { x: frameBox.x, y: frameBox.y, width: frameBox.width, height: frameBox.height },
        viewBoxWidth,
        circles: circleBoxes.map((b) => ({ x: b.x, y: b.y, width: b.width, height: b.height })),
      };
    });
    expect(measured).not.toBeNull();
    if (!measured) {
      return;
    }
    const { frame, viewBoxWidth, circles: circleBoxes } = measured;
    expect(circleBoxes.length).toBeGreaterThan(0);

    // The layout keeps each node's edge at least INDEX_WALL_MARGIN_PX (src/lib/plateLayoutOptions.ts)
    // from the frame wall, in viewBox units. The scale converts that to rendered px.
    const scale = viewBoxWidth > 0 ? frame.width / viewBoxWidth : 1;
    // 2px slack for stroke width and subpixel rounding, scaled the same way.
    const MIN_WALL_GAP_PX = 12 * scale - 2 * scale;
    for (const box of circleBoxes) {
      const leftGap = box.x - frame.x;
      const rightGap = frame.x + frame.width - (box.x + box.width);
      const topGap = box.y - frame.y;
      const bottomGap = frame.y + frame.height - (box.y + box.height);
      const minGap = Math.min(leftGap, rightGap, topGap, bottomGap);
      expect(minGap).toBeGreaterThanOrEqual(MIN_WALL_GAP_PX);
    }
    assertNoErrors(errors);
  },
);

test(
  "every index column header says Fits in, and only the first carries the (i)",
  only("desktop-1440"),
  async ({ page, open }) => {
    const errors = trackErrors(page);

    await open("/", { viewport: { width: 1440, height: 900 }, ready: graph(page) });
    await expectShellRendered(page);

    // At xl and above all four headers say "Fits in", and only the first carries the (i), a focusable InfoDot.
    const headerGrid = page
      .locator("div.text-12.text-ink-3", { hasText: "Article, edits in the last hour" })
      .first();
    const headers = headerGrid.getByText("Fits in");
    expect(await headers.count()).toBe(4);
    const dots = headerGrid.locator(".rounded-full");
    expect(await dots.count()).toBe(1);
    const box = await dots.first().boundingBox();
    expect(box?.width).toBeGreaterThanOrEqual(14);
    assertNoErrors(errors);
  },
);

test(
  "a live edit on a tracked topic rings that node's circle",
  only("desktop-1440"),
  async ({ page, open }) => {
    const errors = trackErrors(page);

    // Overrides mockApi's live route with an edit titled after the first trending topic
    // (Lizzie Borden, page 214796), so resolveTopic finds a match and the initial replay rings its node.
    await page.route("**/api/v1/live**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          stream: "connected",
          server_time: "2026-09-28T11:38:39Z",
          cursor: 1,
          last_event_at: "2026-09-28T11:38:37Z",
          counters: { edits_last_hour: 1 },
          edits: [
            {
              cursor: 1,
              page_id: null,
              title: "Lizzie Borden",
              rev_new: 1377229293,
              rev_old: 1376900021,
              ts: "2026-09-28T11:38:37Z",
              user_kind: "registered",
              byte_delta: -91,
              diff_url: "https://en.wikipedia.org/w/index.php?diff=1377229293&oldid=1376900021",
            },
          ],
        }),
      });
    });
    await open("/", { viewport: { width: 1440, height: 900 }, ready: graph(page) });
    const ring = page.locator("svg[role=group] circle[stroke='var(--wke-stamp)']").first();
    await expect(ring).toBeVisible();
    const nodeCircle = page
      .locator('svg[role=group] a[aria-label^="Lizzie Borden"]')
      .locator("circle")
      .first();
    await expect(nodeCircle).toHaveAttribute("stroke", "var(--wke-stamp)");
    const [ringBox, nodeBox] = await Promise.all([ring.boundingBox(), nodeCircle.boundingBox()]);
    expect(ringBox).not.toBeNull();
    expect(nodeBox).not.toBeNull();
    if (ringBox && nodeBox) {
      expect(
        Math.abs(ringBox.x + ringBox.width / 2 - (nodeBox.x + nodeBox.width / 2)),
      ).toBeLessThan(1);
      expect(
        Math.abs(ringBox.y + ringBox.height / 2 - (nodeBox.y + nodeBox.height / 2)),
      ).toBeLessThan(1);
    }
    assertNoErrors(errors);
  },
);

test("the built-today figure is the API's own count, not the stored total", async ({
  page,
  open,
}) => {
  const errors = trackErrors(page);
  const live = fixtureObject("live.json");
  const storedCount = arrayLength(fixtureObject("dossiers.json").items);
  // Fewer dossiers are built today than stored, so the two figures must differ.
  const builtToday = 8;
  expect(storedCount).toBeGreaterThan(builtToday);
  await page.route("**/api/v1/live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...live,
        server_time: new Date().toISOString(),
        counters: { ...asObject(live.counters), dossiers_built_today: builtToday },
      }),
    });
  });
  await open("/", { ready: graph(page) });
  const record = page
    .locator("main")
    .getByText("Dossiers stored")
    .first()
    .locator("xpath=ancestor::*[self::li or self::div][2]");
  await expect(record).toContainText(`${builtToday} built today`);
  await expect(record).toContainText(String(storedCount));
  assertNoErrors(errors);
});

test("the live region announces the feed as Live edits, never the edit stream", async ({
  page,
  open,
}) => {
  const errors = trackErrors(page);
  await open("/", { ready: graph(page) });
  await expect(page.locator("#live-region")).toHaveText("Live edits connected");
  assertNoErrors(errors);
});

eachTheme(() => {
  test("a disconnected edit feed shows no edit data, never 0 edits", async ({ page, open }) => {
    const errors = trackErrors(page);
    await page.route("**/api/v1/live**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          stream: "down",
          server_time: new Date().toISOString(),
          cursor: 55242,
          last_event_at: "2026-09-29T13:54:12Z",
          edits: [],
          counters: {
            enwiki_edits_last_hour: 0,
            tracked_edits_last_hour: 0,
            window_complete: false,
            dossiers_built_today: 16,
            topics_tracked: 40,
          },
        }),
      });
    });
    await open("/", { ready: graph(page) });

    const main = page.locator("main");
    await expect(
      main.locator("ol li").getByText("no edit data", { exact: true }).first(),
    ).toBeVisible();
    await expect(main.getByText("no edit data", { exact: true }).last()).toBeVisible();
    await expect(main.getByText("Live edits disconnected since 13:54 UTC")).toBeVisible();
    await expect(main).not.toContainText(/\b0 edits?\b/);
    await expect(main).toContainText("16 built today");
    await expect(page.locator("#live-region")).toHaveText(
      "Live edits disconnected since 13:54 UTC",
    );

    // The selected-article panel (data-plate-board) says "no edit data" on its edits row while the feed is down, never 0.
    await page.locator("svg[role='group'] a").first().focus();
    await page.keyboard.press("Enter");
    const card = page.locator("[data-plate-board]");
    await expect(card).toBeVisible();
    await expect(card).toContainText(/Edits in the last hour\s*no edit data/);
    await expect(card).not.toContainText(/Edits in the last hour\s*\d/);
    assertNoErrors(errors);
  });
});

test("the dossier does not call itself up to date while the edit feed is disconnected", async ({
  page,
  open,
}) => {
  const errors = trackErrors(page);
  const body = fixtureObject("dossier_1095706_8000.json");
  body.freshness = {
    ...asObject(body.freshness),
    state: "fresh",
    source: "watcher",
    edits_since: 0,
  };
  await page.route(/\/api\/v1\/dossiers\/1095706(\?[^/]*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(dossierEnvelope(body)),
    });
  });
  await page.route(/\/api\/v1\/status$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        version: "0.1.0",
        redis: true,
        ml_ready: true,
        watcher_connected: false,
        queue_depth: 0,
      }),
    });
  });
  await open("/t/Jesus");
  await expect(page.getByText("Not checked").filter({ visible: true }).first()).toBeVisible();
  await expect(page.locator("main")).not.toContainText("Up to date");
  assertNoErrors(errors);
});

test("the index heading names the snapshot date and says yesterday only when it is", async ({
  page,
  open,
}) => {
  const errors = trackErrors(page);
  // trending.json is dated 2026-09-26.
  await page.clock.setFixedTime(new Date("2026-09-27T09:00:00Z"));
  await open("/", { ready: graph(page) });
  await expect(
    page.getByRole("heading", { level: 2, name: "Most read yesterday (26 September 2026 UTC)" }),
  ).toBeVisible();
  await expect(page.locator("main")).not.toContainText("has not refreshed");

  await page.clock.setFixedTime(new Date("2026-09-28T09:00:00Z"));
  await page.reload();
  await expect(graph(page)).toBeVisible();
  await expect(
    page.getByRole("heading", { level: 2, name: "Most read on 26 September 2026 (UTC)" }),
  ).toBeVisible();
  await expect(page.locator("main")).not.toContainText("has not refreshed");

  await page.clock.setFixedTime(new Date("2026-09-29T09:00:00Z"));
  await page.reload();
  await expect(graph(page)).toBeVisible();
  await expect(page.locator("main")).toContainText(
    "the nightly index has not refreshed since 26 September 2026",
  );
  assertNoErrors(errors);
});

eachTheme(() => {
  test(
    "the edits panel keeps the newest live edits, folds the oldest, and lists replayed rows last",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await page.clock.install();
      let polls = 0;
      await page.route("**/api/v1/live**", async (route) => {
        polls += 1;
        const edits =
          polls === 1
            ? [
                liveEdit(4, "Replay D", 40),
                liveEdit(3, "Replay C", 45),
                liveEdit(2, "Replay B", 50),
                liveEdit(1, "Replay A", 55),
              ]
            : Array.from({ length: 10 }, (_, i) => liveEdit(10 + i, `Live ${i + 1}`, 10 - i));
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            stream: "connected",
            server_time: new Date().toISOString(),
            cursor: polls === 1 ? 4 : 19,
            last_event_at: new Date().toISOString(),
            counters: { edits_last_hour: 14 },
            edits,
          }),
        });
      });
      await open("/", { ready: graph(page) });
      const ledger = page
        .locator("table")
        .filter({ has: page.locator("th", { hasText: "Time, UTC" }) });
      await expect(ledger.getByText("Replay A")).toBeVisible();
      await page.clock.fastForward(21_000);
      await page.clock.runFor(3_000);
      await expect(ledger.getByText("Live 10")).toBeVisible();
      const rows = await ledger
        .locator("tbody tr")
        .evaluateAll((trs) =>
          trs.map((tr) =>
            tr.querySelector("td:nth-child(2)") && !tr.querySelector("td[colspan]")
              ? (tr.children[1]?.textContent ?? "")
              : (tr.textContent ?? ""),
          ),
        );
      // The slot count comes from the panel's height: the fixed rows are the "+N more" row and the marker.
      const editRows = rows.length - 2;
      expect(editRows).toBeGreaterThanOrEqual(3);
      // A burst of 10 shows its newest 3 and folds the other 7 into "+7 more".
      const live = Math.min(3, editRows);
      const replayed = ["Replay D", "Replay C", "Replay B", "Replay A"].slice(0, editRows - live);
      const trimmed = rows.map((r) => r.trim());
      expect(trimmed.slice(0, live)).toEqual(
        Array.from({ length: live }, (_, i) => `Live ${10 - i}`),
      );
      expect(trimmed[live]).toBe("+7 more edits not shown");
      expect(trimmed[live + 1]).toMatch(
        /^listening since \d\d:\d\d:\d\d UTC(\s*earlier edits below)?$/,
      );
      expect(trimmed.slice(live + 2, live + 2 + replayed.length)).toEqual(replayed);
      assertNoErrors(errors);
    },
  );
});

eachTheme(() => {
  test("a 429 on the most-read list shows the retry state with a countdown, not an empty graph", async ({
    page,
    open,
  }) => {
    const errors = trackErrors(page);
    await page.route("**/api/v1/trending", async (route) => {
      await route.fulfill({
        status: 429,
        contentType: "application/problem+json",
        headers: { "retry-after": "3" },
        body: JSON.stringify({
          type: "about:blank",
          title: "Too Many Requests",
          status: 429,
          detail: "Rate limit exceeded: 30 per 1 minute",
          code: "rate_limited",
          request_id: "spec-429",
          retry_after: 3,
        }),
      });
    });
    await open("/", { ready: page.getByText("Today's index is unavailable") });
    await expect(page.locator("[data-plate-error]").getByText("Too many requests")).toBeVisible();
    const waiting = page
      .locator("[data-plate-error]")
      .getByRole("button", { name: /^Retry in [1-3] s$/ });
    await expect(waiting).toBeVisible();
    await expect(waiting).toHaveAttribute("aria-disabled", "true");
    await expect(page.locator("table, ol").filter({ hasText: "Lizzie Borden" })).toHaveCount(0);
    // The error frame (data-plate-error) holds the message and the countdown, and nothing overflows.
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth),
    ).toBe(false);
    // When the countdown ends the button reads Retry. It does not retry on its own.
    await expect(page.getByRole("button", { name: "Retry", exact: true })).toBeVisible({
      timeout: 6000,
    });
    expect(errors.page).toEqual([]);
  });
});

eachTheme(() => {
  test(
    "at 1024 no node centre sits under the stats chip and the top groups clear the frame",
    only("desktop-1440"),
    async ({ page, open }) => {
      await open("/", {
        viewport: { width: 1024, height: 768 },
        ready: page.locator("svg[role='group'] a > circle:first-of-type").first(),
      });
      const m = await page.evaluate(() => {
        const svg = document.querySelector("svg[role='group']")!;
        const f = svg.getBoundingClientRect();
        const chip = [...document.querySelectorAll("figure > span")].find((s) =>
          /nodes, .* edges/.test(s.textContent ?? ""),
        )!;
        const c = chip.getBoundingClientRect();
        const circleBoxes = [...svg.querySelectorAll("a > circle:first-of-type")].map((el) =>
          el.getBoundingClientRect(),
        );
        const hulls = [...svg.querySelectorAll("path")]
          .map((p) => p.getBoundingClientRect())
          .filter((b) => b.width > 20);
        return {
          chip: { x: c.left, y: c.top, r: c.right, b: c.bottom },
          frameTop: f.top,
          centres: circleBoxes.map((b) => ({
            x: b.left + b.width / 2,
            y: b.top + b.height / 2,
            rad: b.width / 2,
          })),
          hullTop: Math.min(...hulls.map((b) => b.top)),
        };
      });
      expect(m.centres.length).toBe(40);
      const touching = m.centres.filter(
        (p) =>
          p.x + p.rad > m.chip.x &&
          p.x - p.rad < m.chip.r &&
          p.y + p.rad > m.chip.y &&
          p.y - p.rad < m.chip.b,
      );
      expect(touching).toEqual([]);
      expect(m.hullTop - m.frameTop).toBeGreaterThanOrEqual(4);
    },
  );
});

test(
  "the search hint never breaks between Press / and to search.",
  only("tablet-768", "tablet-1024", "desktop-1440", "desktop-1920"),
  async ({ page, open }) => {
    await open("/");
    const hint = page.getByText("to search.").first();
    await expect(hint).toBeVisible();
    expect(await hint.evaluate((el) => Array.from(el.getClientRects()).length)).toBe(1);
  },
);
