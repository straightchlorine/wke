import type { Locator, Page } from "@playwright/test";
import { PLATE_BOARD_PX } from "../src/lib/plateSide";
import { BOARD, HOME_GRAPH, RELATED_GRAPH, reachableNodes } from "./plateLocators";
import { eachTheme, expect, only, test } from "./support";

type Open = (path: string, options?: { ready?: Locator }) => Promise<void>;

const PHONE_TABLET_DESKTOP = only("mobile-390", "tablet-1024", "desktop-1440");

// The pause flag stops the replayed edit rows, so nothing below the graph moves mid-test.
test.use({ paused: true });

/** Opens a page and waits for the graph to have faded in; the related graph is scrolled into view. */
async function openGraph(page: Page, open: Open, path: string, graph: string) {
  await open(path, { ready: page.locator(`${graph} a`).first() });
  await expect(page.locator(graph)).toHaveCSS("opacity", "1");
  if (graph === RELATED_GRAPH) {
    await page.locator(graph).scrollIntoViewIfNeeded();
  }
}

/** Returns the index of the reachable node with a label (want true) or without one (want false), after skipping the first `skip` matches, or -1 when there are none. */
async function labelled(page: Page, graph: string, want: boolean, skip = 0): Promise<number> {
  const ok = await reachableNodes(page, graph);
  const flags = await page.evaluate(
    ({ sel, ok: indexes }) => {
      const anchors = [...document.querySelectorAll(`${sel} a`)];
      return indexes.map((i) => anchors[i]!.querySelector("text[data-plate-label]") != null);
    },
    { sel: graph, ok },
  );
  const matches = ok.filter((_, k) => flags[k] === want);
  return matches[skip] ?? -1;
}

function hitOf(page: Page, graph: string, index: number) {
  return page.locator(`${graph} a`).nth(index).locator("[data-plate-hit]");
}

async function snapshot(page: Page, graph: string) {
  return page.evaluate((sel) => {
    const labels = [...document.querySelectorAll(`${sel} text[data-plate-label]`)].map(
      (t) => t.textContent ?? "",
    );
    const leaders = document.querySelectorAll(`${sel} line[data-plate-leader]`).length;
    const figure = document.querySelector("figure")!.getBoundingClientRect();
    return {
      labels: labels.toSorted(),
      leaders,
      pageHeight: document.documentElement.scrollHeight,
      figureHeight: figure.height,
      figureTop: figure.top + window.scrollY,
    };
  }, graph);
}

eachTheme(() => {
  for (const [graph, path, name] of [
    [HOME_GRAPH, "/", "Home graph"],
    [RELATED_GRAPH, "/t/Lizzie_Borden", "Related graph"],
  ] as const) {
    test(
      `${name}: page, figure and label set hold across idle, hover, selected, selected plus hover`,
      PHONE_TABLET_DESKTOP,
      async ({ page, open }) => {
        await openGraph(page, open, path, graph);
        const first = await labelled(page, graph, true, 0);
        const second = await labelled(page, graph, true, 1);
        expect(first).toBeGreaterThanOrEqual(0);
        expect(second).toBeGreaterThanOrEqual(0);
        expect(second).not.toBe(first);

        const idle = await snapshot(page, graph);
        expect(idle.labels.length).toBeGreaterThan(3);

        await hitOf(page, graph, first).hover();
        await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "preview");
        const hover = await snapshot(page, graph);
        expect(hover).toEqual(idle);
        // The hovered dot's label turns ink and medium; nothing else changes.
        const hoveredStyle = await page
          .locator(`${graph} a`)
          .nth(first)
          .locator("text[data-plate-label]")
          .evaluate((el) => {
            const cs = getComputedStyle(el);
            return { weight: cs.fontWeight, fill: cs.fill };
          });
        expect(hoveredStyle.weight).toBe("500");
        const restFill = await page
          .locator(`${graph} a`)
          .nth(second)
          .locator("text[data-plate-label]")
          .evaluate((el) => getComputedStyle(el).fill);
        expect(hoveredStyle.fill).not.toBe(restFill);

        await hitOf(page, graph, first).click();
        await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "selected");
        await expect(page.locator("[data-plate-ring]")).toHaveCount(1);
        expect(await snapshot(page, graph)).toEqual(idle);

        await hitOf(page, graph, second).hover();
        await expect(page.locator("[data-plate-hover-ring]")).toHaveCount(1);
        await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "selected");
        await expect(page.locator("[data-plate-ring]")).toHaveCount(1);
        expect(await snapshot(page, graph)).toEqual(idle);

        const url = page.url();
        await hitOf(page, graph, second).click();
        expect(page.url()).toBe(url);
        await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "selected");
        const moved = await page.locator(`${BOARD} p`).first().textContent();
        const label = await page.locator(`${graph} a`).nth(second).getAttribute("aria-label");
        expect(label!.startsWith(moved!)).toBe(true);
        expect(await snapshot(page, graph)).toEqual(idle);
      },
    );

    test(
      `${name}: every label's nearest dot is its own unless a leader joins them`,
      PHONE_TABLET_DESKTOP,
      async ({ page, open }) => {
        await openGraph(page, open, path, graph);
        const result = await page.evaluate((sel) => {
          const dots = [...document.querySelectorAll(`${sel} a`)].map((a) => {
            const c = [...a.querySelectorAll("circle")].find(
              (x) => !x.hasAttribute("data-plate-hit") && x.getAttribute("fill") !== "none",
            )!;
            const b = c.getBoundingClientRect();
            return { a, x: b.left + b.width / 2, y: b.top + b.height / 2, r: b.width / 2 };
          });
          const bad: string[] = [];
          let checked = 0;
          let leaders = 0;
          for (const dot of dots) {
            const text = dot.a.querySelector("text[data-plate-label]");
            if (!text) {
              continue;
            }
            if (text.getAttribute("data-plate-label") === "leader") {
              leaders += 1;
              continue;
            }
            // A name set where no clean spot was left carries data-label-relaxed and may stand nearer a neighbour.
            if (text.hasAttribute("data-label-relaxed")) {
              continue;
            }
            checked += 1;
            const t = text.getBoundingClientRect();
            const gap = (d: (typeof dots)[number]) => {
              const nx = Math.min(Math.max(d.x, t.left), t.right);
              const ny = Math.min(Math.max(d.y, t.top), t.bottom);
              return Math.hypot(d.x - nx, d.y - ny) - d.r;
            };
            const nearest = dots.toSorted((p, q) => gap(p) - gap(q))[0]!;
            if (nearest !== dot) {
              bad.push(
                `${text.textContent}: own ${gap(dot).toFixed(1)}, nearest ${gap(nearest).toFixed(1)} ${nearest.a.getAttribute("aria-label")}`,
              );
            }
          }
          return { bad, checked, leaders };
        }, graph);
        // On the related graph a name beside its dot also gets a leader when another dot is less than NEIGHBOUR_DOT_MARGIN_PX (labelLayout.ts) farther from it than its own.
        // Every name there can end up on a leader, so the guard counts leaders as well as checked names.
        expect(result.checked + result.leaders).toBeGreaterThan(0);
        expect(result.bad).toEqual([]);
      },
    );
  }
});

test.describe("leader lines", only("mobile-390"), () => {
  test.use({ theme: "light" });

  test("a leader line is one rule-strong pixel from its label to its own dot", async ({
    page,
    open,
  }) => {
    await openGraph(page, open, "/", HOME_GRAPH);
    const leaders = await page.locator(`${HOME_GRAPH} line[data-plate-leader]`).evaluateAll((els) =>
      els.map((el) => {
        const cs = getComputedStyle(el);
        const a = el.closest("a")!;
        const circle = [...a.querySelectorAll("circle")].find(
          (c) => !c.hasAttribute("data-plate-hit") && c.getAttribute("fill") !== "none",
        )!;
        const b = circle.getBoundingClientRect();
        const root = el.closest("svg")!;
        const svg = root.getBoundingClientRect();
        const scale = svg.width / root.viewBox.baseVal.width;
        const x1 = svg.left + Number(el.getAttribute("x1")) * scale;
        const y1 = svg.top + Number(el.getAttribute("y1")) * scale;
        return {
          width: cs.strokeWidth,
          startsOnDot:
            Math.hypot(x1 - (b.left + b.width / 2), y1 - (b.top + b.height / 2)) <= b.width / 2 + 1,
          hasLabel: a.querySelector("text[data-plate-label]") != null,
        };
      }),
    );
    for (const leader of leaders) {
      expect(leader).toEqual({ width: "1px", startsOnDot: true, hasLabel: true });
    }
  });
});

test.describe("the board strip", () => {
  eachTheme(() => {
    test(
      "serif title, one description line and four record rows, the badge the dossier link, one height and never overflowing",
      PHONE_TABLET_DESKTOP,
      async ({ page, open }) => {
        await openGraph(page, open, "/", HOME_GRAPH);
        const idle = await page.locator(BOARD).evaluate((el) => el.getBoundingClientRect().height);
        expect(idle).toBe(PLATE_BOARD_PX);
        const hint = await page.locator(`${BOARD} p`).evaluate((el) => {
          const board = el.closest("section")!.getBoundingClientRect();
          const r = el.getBoundingClientRect();
          return {
            size: getComputedStyle(el).fontSize,
            centred: Math.abs(r.top + r.height / 2 - (board.top + board.height / 2)) <= 1,
          };
        });
        expect(hint).toEqual({ size: "13px", centred: true });
        const index = await labelled(page, HOME_GRAPH, true, 1);
        await hitOf(page, HOME_GRAPH, index).click();
        await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "selected");
        const rows = await page.locator(BOARD).evaluate((board) => {
          const box = board.getBoundingClientRect();
          const title = board.querySelector("p")!;
          const description = board.querySelector("[data-plate-description]")!;
          const link = board.querySelector("a")!.getBoundingClientRect();
          const records = [...board.querySelectorAll("[data-record-row]")].map((r) =>
            r.getBoundingClientRect(),
          );
          const left = Math.min(...records.map((r) => r.left));
          return {
            height: box.height,
            overflow: board.scrollHeight > board.clientHeight + 1,
            titleSize: getComputedStyle(title).fontSize,
            titleFamily: getComputedStyle(title).fontFamily,
            titleClipped: getComputedStyle(title).textOverflow,
            descriptionSize: getComputedStyle(description).fontSize,
            descriptionHeight: description.getBoundingClientRect().height,
            descriptionBelowTitle:
              description.getBoundingClientRect().top >= title.getBoundingClientRect().bottom - 0.5,
            rows: records.length,
            columns: new Set(records.map((r) => Math.round(r.left))).size,
            rowsInside: records.every(
              (r) => r.bottom <= box.bottom && r.top >= box.top && r.left >= box.left,
            ),
            rowsLeftAligned: left - box.left <= 14,
            linkRight: Math.round(box.right - link.right),
            linkInsideBoard: link.bottom <= box.bottom && link.top >= box.top,
          };
        });
        expect(rows.height).toBe(idle);
        expect(rows.overflow).toBe(false);
        expect(rows.titleSize).toBe("16px");
        expect(rows.titleFamily).toContain("Newsreader");
        expect(rows.titleClipped).toBe("ellipsis");
        expect(rows.descriptionSize).toBe("12px");
        expect(
          rows.descriptionHeight,
          "the description line keeps its height even when empty",
        ).toBe(16);
        expect(rows.descriptionBelowTitle).toBe(true);
        expect(rows.rows).toBe(4);
        expect(rows.columns).toBe(1);
        expect(rows.rowsInside).toBe(true);
        expect(rows.rowsLeftAligned).toBe(true);
        expect(rows.linkInsideBoard).toBe(true);
        expect(rows.linkRight).toBeLessThanOrEqual(14);
        const text = ((await page.locator(BOARD).textContent()) ?? "").replace(/\s+/g, " ");
        expect(text).toMatch(
          /Views\s*[\d,]+\s*Edits in the last hour\s*[\d,]+\s*Linked to.+Dossier\s*(Ready|Partial|Building|Not built)/,
        );
      },
    );
  });
});
