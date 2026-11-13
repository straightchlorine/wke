import type { Locator, Page } from "@playwright/test";
import { mockApi, readFixture } from "./mockApi";
import { eachTheme, expect, only, test } from "./support";

// Each state routes the API itself, so the shared routes are not installed.
test.use({ mocked: false });

type State = "counts" | "disconnected" | "rate limited" | "no top dossier";
const STATES: State[] = ["counts", "disconnected", "rate limited", "no top dossier"];

function limited() {
  return {
    status: 429,
    contentType: "application/problem+json",
    headers: { "retry-after": "30" },
    body: JSON.stringify({
      type: "about:blank",
      title: "Too many requests",
      status: 429,
      code: "rate_limited",
      request_id: "r1",
      detail: "12 per 1 minute",
    }),
  };
}

async function openIn(
  page: Page,
  open: (path: string, options?: { ready?: Locator }) => Promise<void>,
  state: State,
) {
  await page.unrouteAll();
  await mockApi(page);
  if (state === "disconnected") {
    await page.route("**/api/v1/live**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          stream: "down",
          server_time: new Date().toISOString(),
          cursor: 5,
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
      }),
    );
  } else if (state === "rate limited") {
    await page.route("**/api/v1/live**", (route) => route.fulfill(limited()));
  } else if (state === "no top dossier") {
    // Every topic's dossier_state becomes "none", so no dossier is built yet.
    const trending: unknown = JSON.parse(readFixture("trending.json"), (key, value: unknown) =>
      key === "dossier_state" ? "none" : value,
    );
    await page.route("**/api/v1/trending", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(trending),
      }),
    );
  }
  await open("/", {
    ready:
      state === "no top dossier" ? undefined : page.locator("[data-top-dossier] button").first(),
  });
  await expect(page.getByRole("heading", { level: 1 }).first()).toContainText("Cited context");
}

function measure(page: Page) {
  return page.getByRole("group", { name: "Today's counters" }).evaluate((root) => {
    // The y of an element's text baseline, read off a zero-size inline probe placed first in it.
    const baseline = (el: Element) => {
      const probe = root.ownerDocument.createElement("span");
      probe.style.cssText = "display:inline-block;width:0;height:0;";
      el.prepend(probe);
      const y = probe.getBoundingClientRect().bottom;
      probe.remove();
      return y;
    };
    const rows = [...root.querySelectorAll("[data-record-row]")].map((row) => {
      const [label, , value] = [...row.children];
      const sub = row.parentElement!.querySelector("[data-record-sub]")!;
      const subCopy = sub.cloneNode(true);
      if (subCopy instanceof Element) {
        subCopy.querySelectorAll("[role=tooltip]").forEach((t) => t.remove());
      }
      const link = value!.querySelector("a");
      return {
        label: label!.textContent ?? "",
        valueRight: value!.getBoundingClientRect().right,
        valueText: value!.textContent ?? "",
        valueSize: getComputedStyle(value!).fontSize,
        valueFamily: getComputedStyle(value!).fontFamily,
        linkTitle: link?.getAttribute("title") ?? null,
        baselines: [baseline(label!.firstElementChild ?? label!), baseline(value!)],
        sub: {
          text: subCopy.textContent ?? "",
          size: getComputedStyle(sub).fontSize,
          align: getComputedStyle(sub).textAlign,
          height: sub.getBoundingClientRect().height,
        },
      };
    });
    const actions = root.querySelector("[data-top-dossier]");
    const items = actions
      ? [...actions.children].map((el) => ({
          text: el.textContent ?? "",
          top: el.getBoundingClientRect().top,
          left: el.getBoundingClientRect().left,
          height: el.getBoundingClientRect().height,
          baseline: baseline(el.tagName === "BUTTON" ? (el.firstElementChild ?? el) : el),
        }))
      : [];
    return {
      recordRight: root.getBoundingClientRect().right,
      recordLeft: root.getBoundingClientRect().left,
      rows,
      items,
      hairlines: [...root.querySelectorAll("div:not([popover])")].filter(
        (el) => getComputedStyle(el).borderTopWidth !== "0px",
      ).length,
      scrollOk: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    };
  });
}

eachTheme(() => {
  test(
    "home counters are three one-line rows on one right edge in every state",
    only("mobile-390", "tablet-1024", "desktop-1440"),
    async ({ page, open }) => {
      const edges: number[] = [];
      for (const state of STATES) {
        await openIn(page, open, state);
        const g = await measure(page);
        expect(g.rows, state).toHaveLength(3);
        expect(g.scrollOk, state).toBe(true);
        expect(g.hairlines, `${state}: no hairline or stacked block`).toBe(0);
        edges.push(g.recordRight);
        for (const row of g.rows) {
          expect(
            Math.abs(row.valueRight - g.recordRight),
            `${state} ${row.label} value edge`,
          ).toBeLessThanOrEqual(0.5);
          expect(
            Math.abs(row.baselines[0]! - row.baselines[1]!),
            `${state} ${row.label} baseline`,
          ).toBeLessThanOrEqual(0.5);
          expect(row.sub.size, `${state} ${row.label} sub size`).toBe("12px");
          expect(row.sub.align).toBe("right");
          expect(row.sub.height, `${state} ${row.label} sub is one line`).toBeLessThanOrEqual(16.5);
        }
        const [stored, edits, top] = g.rows;
        if (!stored || !edits || !top) {
          throw new Error(`${state}: expected three rows`);
        }
        expect(stored.label).toMatch(/^Dossiers stored/);
        expect(edits.label).toMatch(/^Edits seen since page load/);
        expect(top.label).toMatch(/^Top dossier today/);
        expect(stored.valueSize).toBe("18px");
        if (state === "disconnected") {
          expect(edits.valueText).toBe("no edit data");
          expect(edits.valueSize).toBe("13px");
        } else {
          expect(edits.valueSize).toBe("18px");
          expect(edits.sub.text).toMatch(/^(since \d\d:\d\d UTC|in \d+ min)$/);
        }
        if (state === "counts" || state === "disconnected") {
          expect(stored.sub.text).toMatch(/^\d+ built today$/);
        } else if (state === "rate limited") {
          // A refused first poll shows the figure from this tab's last good poll, or nothing; never a stand-in.
          expect(stored.sub.text).toMatch(/^(\d+ built today)?$/);
        }
        if (state === "no top dossier") {
          expect(top.valueText).toBe("None built yet");
          expect(top.sub.text).toBe("");
          expect(g.items).toHaveLength(0);
          continue;
        }
        // The Top dossier name is a 15px serif link. It ends in an ellipsis when too long and never wraps.
        expect(top.valueSize).toBe("15px");
        expect(top.valueFamily).toContain("Newsreader");
        expect(top.linkTitle).toBeTruthy();
        expect(top.sub.text).toMatch(/^pinned \d{4}-\d\d-\d\d, \d\d:\d\d UTC$/);
        // Chips and buttons are 32px tall and start at the record's left edge. When a row wraps, as it can at 390, each line still starts at that edge.
        expect(g.items.map((i) => i.text.replace(/\s+/g, " ").trim().split(" ")[0])).toEqual([
          "Fits",
          expect.any(String),
          "Open",
          "Copy",
        ]);
        for (const item of g.items) {
          expect(item.height, `${state} ${item.text}`).toBe(32);
        }
        const lineTops = [...new Set(g.items.map((i) => Math.round(i.top)))];
        for (const lineTop of lineTops) {
          const line = g.items.filter((i) => Math.round(i.top) === lineTop);
          for (const item of line) {
            expect(
              Math.abs(item.baseline - line[0]!.baseline),
              `${state} action baseline`,
            ).toBeLessThanOrEqual(0.5);
          }
          expect(
            Math.abs(Math.min(...line.map((i) => i.left)) - g.recordLeft),
            `${state} line at ${lineTop} flush left`,
          ).toBeLessThanOrEqual(0.5);
        }
      }
      for (const edge of edges) {
        expect(Math.abs(edge - edges[0]!)).toBeLessThanOrEqual(0.5);
      }
    },
  );
});
