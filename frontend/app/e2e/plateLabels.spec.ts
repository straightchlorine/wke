import type { Locator, Page } from "@playwright/test";
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

interface Dot {
  index: number;
  title: string;
  rank: number | null;
  labelled: boolean;
  leader: boolean;
  reachable: boolean;
  state: string;
}

/** Every dot of a graph: its rank figure (views or similarity), whether it carries a permanent label, and whether the pointer can reach it. */
async function dotStates(page: Page, graph: string): Promise<Dot[]> {
  const reachable = new Set(await reachableNodes(page, graph));
  const found = await page.evaluate((sel) => {
    return [...document.querySelectorAll(`${sel} a`)].map((a, index) => {
      const aria = a.getAttribute("aria-label") ?? "";
      const views = /, ([\d,]+) views/.exec(aria);
      const sim = /, similarity ([\d.]+)/.exec(aria);
      const text = a.querySelector("text[data-plate-label]");
      return {
        index,
        title: aria.split(/, (?:[\d,]+ views|similarity )/)[0] ?? "",
        rank: views ? Number(views[1]!.replaceAll(",", "")) : sim ? Number(sim[1]) : null,
        labelled: text != null,
        leader: text?.getAttribute("data-plate-label") === "leader",
        state:
          /dossier ready|dossier partial|dossier in progress|no dossier yet/.exec(aria)?.[0] ?? "",
      };
    });
  }, graph);
  return found.map((d) => ({ ...d, reachable: reachable.has(d.index) }));
}

/** The sentence in the graph's info tooltip that says which dots are named. */
async function statedRule(page: Page, graph: string): Promise<string> {
  const figure = page.locator("figure").filter({ has: page.locator(graph) });
  const text =
    (await figure
      .locator("[popover]")
      .filter({ hasText: /Point at any dot|Tap any dot/ })
      .textContent()) ?? "";
  const rule =
    /(A name is shown for [^.]*\.|Every dot is named[^.]*\.) (?:Point at|Tap) any dot for its name\./.exec(
      text,
    );
  expect(rule, text).not.toBeNull();
  return rule![1]!;
}

/** The graph's drawn geometry in graph units: dots, edges, hull outlines and every permanent name's box. */
async function geometry(page: Page, graph: string) {
  return page.evaluate((sel) => {
    const svg = document.querySelector<SVGSVGElement>(sel)!;
    const dots = [...svg.querySelectorAll("a")].map((a) => {
      const c = [...a.querySelectorAll("circle")].find(
        (x) => !x.hasAttribute("data-plate-hit") && x.getAttribute("fill") !== "none",
      )!;
      const aria = a.getAttribute("aria-label") ?? "";
      const views = /, ([\d,]+) views/.exec(aria);
      const sim = /, similarity ([\d.]+)/.exec(aria);
      const text = a.querySelector<SVGTextElement>("text[data-plate-label]");
      const box = text?.getBBox();
      const lead = a.querySelector("line[data-plate-leader]");
      const paint = text ? getComputedStyle(text) : null;
      return {
        leaderLine: lead
          ? [
              Number(lead.getAttribute("x1")),
              Number(lead.getAttribute("y1")),
              Number(lead.getAttribute("x2")),
              Number(lead.getAttribute("y2")),
            ]
          : null,
        halo: paint
          ? {
              order: paint.paintOrder,
              stroke: paint.stroke,
              width: paint.strokeWidth,
              join: paint.strokeLinejoin,
            }
          : null,
        title: aria.split(/, (?:[\d,]+ views|similarity )/)[0] ?? "",
        x: Number(c.getAttribute("cx")),
        y: Number(c.getAttribute("cy")),
        r: Number(c.getAttribute("r")),
        rank: views ? Number(views[1]!.replaceAll(",", "")) : sim ? Number(sim[1]) : null,
        named: text != null,
        relaxed: text?.hasAttribute("data-label-relaxed") ?? false,
        leader: text?.getAttribute("data-plate-label") === "leader",
        text: text?.textContent ?? "",
        box: box ? { x: box.x, y: box.y, w: box.width, h: box.height } : null,
      };
    });
    const edges = [...svg.querySelectorAll("line:not([data-plate-leader])")].map((l) => [
      Number(l.getAttribute("x1")),
      Number(l.getAttribute("y1")),
      Number(l.getAttribute("x2")),
      Number(l.getAttribute("y2")),
    ]);
    const hulls = [...svg.querySelectorAll("path")].map((p) =>
      (p.getAttribute("d") ?? "")
        .match(/-?[\d.]+ -?[\d.]+/g)!
        .map((pair) => pair.split(" ").map(Number)),
    );
    const names = [...svg.querySelectorAll("text[data-plate-label]")]
      .map((t) => {
        return `${t.textContent}@${t.getAttribute("x")},${t.getAttribute("y")}`;
      })
      .toSorted();
    return {
      dots,
      edges,
      hulls,
      names,
      width: svg.viewBox.baseVal.width,
      height: svg.viewBox.baseVal.height,
    };
  }, graph);
}

/** The side of the line through p and q that r lies on: -1, 0 or 1. */
function turn(p: number[], q: number[], r: number[]) {
  return Math.sign((q[0]! - p[0]!) * (r[1]! - p[1]!) - (q[1]! - p[1]!) * (r[0]! - p[0]!));
}

function crosses(box: { x: number; y: number; w: number; h: number }, a: number[], b: number[]) {
  const inside = (x: number, y: number) =>
    x >= box.x && x <= box.x + box.w && y >= box.y && y <= box.y + box.h;
  if (inside(a[0]!, a[1]!) || inside(b[0]!, b[1]!)) return true;
  const sides = [
    [box.x, box.y, box.x + box.w, box.y],
    [box.x + box.w, box.y, box.x + box.w, box.y + box.h],
    [box.x + box.w, box.y + box.h, box.x, box.y + box.h],
    [box.x, box.y + box.h, box.x, box.y],
  ];
  return sides.some(([x1, y1, x2, y2]) => {
    const c = [x1!, y1!];
    const d = [x2!, y2!];
    return turn(a, b, c) !== turn(a, b, d) && turn(c, d, a) !== turn(c, d, b);
  });
}

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** The "A / B" titles of every pair of names whose boxes overlap. */
function overlappingNames(named: Array<{ title: string; box: Box | null }>): string[] {
  const pairs: string[] = [];
  for (const [i, a] of named.entries()) {
    for (const b of named.slice(i + 1)) {
      const overlap =
        a.box!.x < b.box!.x + b.box!.w &&
        a.box!.x + a.box!.w > b.box!.x &&
        a.box!.y < b.box!.y + b.box!.h &&
        a.box!.y + a.box!.h > b.box!.y;
      if (overlap) {
        pairs.push(`${a.title} / ${b.title}`);
      }
    }
  }
  return pairs;
}

eachTheme(() => {
  for (const [graph, path, name] of [
    [HOME_GRAPH, "/", "Home graph"],
    [RELATED_GRAPH, "/t/Lizzie_Borden", "Related graph"],
  ] as const) {
    test(
      `${name}: the names follow the naming rule, keep off lines and outlines, stay near their dot, and the rule is stated`,
      PHONE_TABLET_DESKTOP,
      async ({ page, open }, info) => {
        const phone = info.project.name === "mobile-390";
        await openGraph(page, open, path, graph);
        const rule = await statedRule(page, graph);
        const g = await geometry(page, graph);
        const named = g.dots.filter((d) => d.named);
        info.annotations.push({
          type: "names",
          description: `${name} ${info.project.name}: ${named.length} of ${g.dots.length} named, ${named.filter((d) => d.relaxed).length} relaxed, ${named.filter((d) => d.leader).length} with a leader`,
        });

        // A name stays within 30px of its dot's edge. The desktop project and the related graph allow 36px, because their layout uses longer leaders.
        const reach = info.project.name === "desktop-1440" || graph === RELATED_GRAPH ? 36 : 30;
        for (const d of named) {
          const b = d.box!;
          const gap =
            Math.hypot(
              d.x - Math.min(Math.max(d.x, b.x), b.x + b.w),
              d.y - Math.min(Math.max(d.y, b.y), b.y + b.h),
            ) - d.r;
          expect(gap, d.title).toBeLessThanOrEqual(reach);
          if (gap > 7) {
            expect(d.leader, `${d.title} is ${gap.toFixed(1)}px away`).toBe(true);
          }
        }
        expect(overlappingNames(named), "names that touch").toEqual([]);
        for (const d of named) {
          const b = d.box!;
          for (const o of g.dots) {
            if (o === d) continue;
            const dist = Math.hypot(
              Math.max(b.x - o.x, 0, o.x - (b.x + b.w)),
              Math.max(b.y - o.y, 0, o.y - (b.y + b.h)),
            );
            expect(dist, `${d.title} over ${o.title}`).toBeGreaterThanOrEqual(o.r);
          }
          if (!d.leaderLine) continue;
          const [x1, y1, x2, y2] = d.leaderLine;
          for (const o of named) {
            if (o !== d)
              expect(
                crosses(o.box!, [x1!, y1!], [x2!, y2!]),
                `${d.title} leader crosses ${o.title}`,
              ).toBe(false);
          }
          for (const o of g.dots) {
            if (o === d) continue;
            const len2 = (x2! - x1!) ** 2 + (y2! - y1!) ** 2 || 1;
            const t = Math.max(
              0,
              Math.min(1, ((o.x - x1!) * (x2! - x1!) + (o.y - y1!) * (y2! - y1!)) / len2),
            );
            expect(
              Math.hypot(x1! + t * (x2! - x1!) - o.x, y1! + t * (y2! - y1!) - o.y),
              `${d.title} leader through ${o.title}`,
            ).toBeGreaterThanOrEqual(o.r);
          }
        }
        // Each name has an outline in the graph's background colour, drawn before the text. It keeps lines behind the name from cutting through the letters.
        const sheet = await page.evaluate(() => {
          const probe = document.createElement("span");
          probe.style.color = "var(--wke-sheet)";
          document.body.append(probe);
          const colour = getComputedStyle(probe).color;
          probe.remove();
          return colour;
        });
        for (const d of named) {
          expect(d.halo!.order, d.title).toContain("stroke");
          expect(d.halo!.stroke, d.title).toBe(sheet);
          expect(Number.parseFloat(d.halo!.width), d.title).toBeGreaterThanOrEqual(2.5);
          expect(d.halo!.join, d.title).toBe("round");
        }

        if (graph === RELATED_GRAPH) {
          expect(rule).toBe(
            "Every dot is named, and a name crosses a line only where there is no clear space.",
          );
          expect(named.length, "every related-graph dot is named").toBe(g.dots.length);
          return;
        }

        expect(rule).toBe(
          "A name is shown for the 10 most-read dots, every dot with no other close by, the most-read dot of each group, and as many more as fit.",
        );
        // The ALWAYS_NAMED most-viewed dots are named first. A dot that finds no free spot stays unnamed instead of being printed over something.
        const top = g.dots.toSorted((a, b) => b.rank! - a.rank!).slice(0, 10);
        expect(
          top.filter((d) => d.named).length,
          top
            .filter((d) => !d.named)
            .map((d) => d.title)
            .join(", "),
        ).toBeGreaterThanOrEqual(phone ? 5 : 7);
        // An isolated dot has no other dot within the isolation radius (ISOLATED_RADIUS_*_PX in labelLayout.ts). It is named whenever a position fits.
        const radius = phone ? 56 : 90;
        const alone = g.dots.filter((d) =>
          g.dots.every((o) => o === d || Math.hypot(o.x - d.x, o.y - d.y) >= radius),
        );
        const aloneUnnamed = alone.filter((d) => !d.named);
        info.annotations.push({
          type: "isolated",
          description: `${name} ${info.project.name}: ${alone.length} isolated, ${alone.length - aloneUnnamed.length} named`,
        });
        // At 1024 the frame is narrow enough that every dot has a close neighbour.
        if (info.project.name !== "tablet-1024") expect(alone.length).toBeGreaterThan(0);
        expect(
          aloneUnnamed.length,
          aloneUnnamed.map((d) => d.title).join(", "),
        ).toBeLessThanOrEqual(phone ? 3 : 1);
        // No name over a line or a group outline, bar the few that had no clean spot left.
        const relaxed = named.filter((d) => d.relaxed);
        expect(relaxed.length, relaxed.map((d) => d.title).join(", ")).toBeLessThanOrEqual(
          phone ? 6 : 3,
        );
        for (const d of named.filter((x) => !x.relaxed)) {
          const b = d.box!;
          for (const [x1, y1, x2, y2] of g.edges) {
            expect(crosses(b, [x1!, y1!], [x2!, y2!]), `${d.title} crosses an edge`).toBe(false);
          }
          for (const hull of g.hulls) {
            for (const [i, p] of hull.entries()) {
              const q = hull[(i + 1) % hull.length]!;
              expect(crosses(b, p, q), `${d.title} crosses a group outline`).toBe(false);
            }
          }
        }
      },
    );

    if (graph === HOME_GRAPH) {
      // The desktop label rules add finer directions, an outer ring of spots with longer leaders, and a smaller grid cell. The collision rules stay.
      // The minimums are for the recorded Wikimedia day in mockApi, so a layout or frame-height change moves them.
      const DESKTOP_MINIMUM: Record<string, number> = { "desktop-1440": 23, "desktop-1920": 28 };
      test(
        `Home graph: the desktop label rules name at least ${JSON.stringify(DESKTOP_MINIMUM)} dots with no overlap and no leader across a name`,
        only("desktop-1440", "desktop-1920"),
        async ({ page, open }, info) => {
          const minimum = DESKTOP_MINIMUM[info.project.name];
          await openGraph(page, open, path, graph);
          const g = await geometry(page, graph);
          const named = g.dots.filter((d) => d.named);
          info.annotations.push({
            type: "names",
            description: `${info.project.name}: ${named.length} of ${g.dots.length} named, ${g.dots.length - named.length} dropped`,
          });
          expect(named.length).toBeGreaterThanOrEqual(minimum!);
          expect(overlappingNames(named), "names that touch").toEqual([]);
          for (const d of named) {
            if (!d.leaderLine) continue;
            const [x1, y1, x2, y2] = d.leaderLine;
            expect(Math.hypot(x2! - x1!, y2! - y1!), `${d.title} leader`).toBeLessThanOrEqual(36);
            for (const o of named) {
              if (o !== d)
                expect(
                  crosses(o.box!, [x1!, y1!], [x2!, y2!]),
                  `${d.title} leader crosses ${o.title}`,
                ).toBe(false);
            }
          }
        },
      );
    }

    test(
      `${name}: the set of names does not change on hover or selection`,
      PHONE_TABLET_DESKTOP,
      async ({ page, open }) => {
        await openGraph(page, open, path, graph);
        const idle = (await geometry(page, graph)).names;
        const all = await dotStates(page, graph);
        const reachable = all.filter((d) => d.reachable);
        expect(reachable.length).toBeGreaterThan(2);
        for (const dot of [reachable[0]!, reachable[reachable.length - 1]!]) {
          const hit = page.locator(`${graph} a`).nth(dot.index).locator("[data-plate-hit]");
          await hit.hover();
          await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "preview");
          expect((await geometry(page, graph)).names).toEqual(idle);
          await hit.click();
          await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "selected");
          expect((await geometry(page, graph)).names).toEqual(idle);
          await page.mouse.move(2, 2);
          expect((await geometry(page, graph)).names).toEqual(idle);
          await page.keyboard.press("Escape");
        }
      },
    );

    if (graph === HOME_GRAPH) {
      test(
        `Home graph: pointing at an unnamed dot names it in the label style and moves nothing`,
        PHONE_TABLET_DESKTOP,
        async ({ page, open }) => {
          await openGraph(page, open, path, graph);
          const all = await dotStates(page, graph);
          const unnamed = all.find((d) => !d.labelled && d.reachable);
          const named = all.filter((d) => d.labelled && d.reachable);
          expect(unnamed, "the Home graph leaves some reachable dot unnamed").toBeDefined();
          const set = () =>
            page.evaluate(
              (sel) => ({
                labels: [...document.querySelectorAll(`${sel} text[data-plate-label]`)]
                  .map((t) => t.textContent ?? "")
                  .toSorted(),
                positions: [...document.querySelectorAll(`${sel} text[data-plate-label]`)].map(
                  (t) => {
                    const b = t.getBoundingClientRect();
                    return `${b.left.toFixed(1)},${b.top.toFixed(1)}`;
                  },
                ),
              }),
              graph,
            );
          const idle = await set();
          const names = page.locator(`${graph} text[data-plate-name]`);
          await expect(names).toHaveCount(0);

          const hit = page.locator(`${graph} a`).nth(unnamed!.index).locator("[data-plate-hit]");
          await hit.hover();
          await expect(names).toHaveCount(1);
          expect(await set()).toEqual(idle);
          const style = await names.evaluate((el) => ({
            weight: getComputedStyle(el).fontWeight,
            size: getComputedStyle(el).fontSize,
            family: getComputedStyle(el).fontFamily,
          }));
          const restStyle = await page
            .locator(`${graph} text[data-plate-label]`)
            .first()
            .evaluate((el) => ({
              size: getComputedStyle(el).fontSize,
              family: getComputedStyle(el).fontFamily,
            }));
          expect(style.weight).toBe("500");
          expect({ size: style.size, family: style.family }).toEqual(restStyle);
          const near = await page.evaluate(
            ({ sel, index }) => {
              const a = document.querySelectorAll(`${sel} a`)[index]!;
              const c = [...a.querySelectorAll("circle")]
                .find(
                  (x) => !x.hasAttribute("data-plate-hit") && x.getAttribute("fill") !== "none",
                )!
                .getBoundingClientRect();
              const t = document
                .querySelector(`${sel} text[data-plate-name]`)!
                .getBoundingClientRect();
              const x = c.left + c.width / 2;
              const y = c.top + c.height / 2;
              return (
                Math.hypot(
                  x - Math.min(Math.max(x, t.left), t.right),
                  y - Math.min(Math.max(y, t.top), t.bottom),
                ) -
                c.width / 2
              );
            },
            { sel: graph, index: unnamed!.index },
          );
          expect(near).toBeLessThanOrEqual(9);

          // The name is removed with no hover-out delay, so it is gone within two frames.
          await page.mouse.move(2, 2);
          await page.evaluate(
            () =>
              new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
          );
          await expect(names).toHaveCount(0);

          // Selected: its name stays and is emphasised; a hovered named dot gets only its ring.
          await hit.click();
          await expect(names).toHaveCount(1);
          expect(await names.evaluate((el) => getComputedStyle(el).fontWeight)).toBe("500");
          const other = named.find((d) => d.index !== unnamed!.index);
          if (other) {
            await page.locator(`${graph} a`).nth(other.index).locator("[data-plate-hit]").hover();
            await expect(page.locator("[data-plate-hover-ring]")).toHaveCount(1);
            const otherWeight = await page
              .locator(`${graph} a`)
              .nth(other.index)
              .locator("text[data-plate-label]")
              .evaluate((el) => getComputedStyle(el).fontWeight);
            expect(otherWeight).toBe("400");
            expect(await set()).toEqual(idle);
          }
        },
      );
    }

    test(
      `${name}: the board's badge and title keep one place across five different names`,
      PHONE_TABLET_DESKTOP,
      async ({ page, open }) => {
        await openGraph(page, open, path, graph);
        const all = (await dotStates(page, graph)).filter((d) => d.reachable);
        const byLength = all.toSorted((a, b) => a.title.length - b.title.length);
        const picks = new Map<number, Dot>();
        const unbuilt = all.find((d) => d.state === "no dossier yet");
        if (unbuilt) {
          picks.set(unbuilt.index, unbuilt);
        }
        for (const at of [0, 0.25, 0.5, 0.75, 1]) {
          const dot =
            byLength[Math.min(byLength.length - 1, Math.round(at * (byLength.length - 1)))]!;
          if (picks.size < 5) {
            picks.set(dot.index, dot);
          }
        }
        expect(picks.size).toBeGreaterThanOrEqual(Math.min(5, all.length));
        const boardGeometry = () =>
          page.locator(BOARD).evaluate((board) => {
            const box = board.getBoundingClientRect();
            const badge = board.querySelector("[data-plate-badge]")?.getBoundingClientRect();
            const title = board.querySelector("p")!.getBoundingClientRect();
            return {
              height: box.height,
              badgeX: badge ? Math.round((badge.left - box.left) * 10) / 10 : null,
              badgeRight: badge ? Math.round((box.right - badge.right) * 10) / 10 : null,
              badgeWidth: badge?.width ?? null,
              badgeCentre: badge
                ? Math.round((badge.top + badge.height / 2 - box.top) * 10) / 10
                : null,
              titleX: Math.round((title.left - box.left) * 10) / 10,
              titleY: Math.round((title.top - box.top) * 10) / 10,
            };
          });
        const seen: Array<Awaited<ReturnType<typeof boardGeometry>>> = [];
        for (const dot of picks.values()) {
          const hit = page.locator(`${graph} a`).nth(dot.index).locator("[data-plate-hit]");
          await hit.hover();
          await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "preview");
          seen.push(await boardGeometry());
          await hit.click();
          await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "selected");
          seen.push(await boardGeometry());
          await page.keyboard.press("Escape");
          await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "preview");
        }
        const first = seen[0]!;
        for (const g of seen) {
          expect(g.height).toBe(first.height);
          expect(g.badgeX).toBe(first.badgeX);
          expect(g.badgeWidth).toBe(first.badgeWidth);
          expect(g.badgeCentre).toBe(first.badgeCentre);
          expect(g.titleX).toBe(first.titleX);
          expect(g.titleY).toBe(first.titleY);
        }
        if (graph === HOME_GRAPH) {
          expect(first.badgeX).not.toBeNull();
        }
      },
    );
  }
});

// The 9 named dots and 4 leaders are the layout's output for the recorded Lizzie Borden fixture, so a layout change can move them.
test.describe("Related graph at 1440", only("desktop-1440"), () => {
  test.use({ theme: "light" });

  test("every name more than 7px off its dot carries a leader, and 4 of the 9 do", async ({
    page,
    open,
  }) => {
    await openGraph(page, open, "/t/Lizzie_Borden", RELATED_GRAPH);
    const m = await page.locator(`${RELATED_GRAPH} a`).evaluateAll((anchors) =>
      anchors.map((a) => {
        const c = a
          .querySelector("circle:not([data-plate-hit]):not([data-plate-hover-ring])")!
          .getBoundingClientRect();
        const t = a.querySelector("text[data-plate-label]");
        const b = t?.getBoundingClientRect();
        const cx = c.left + c.width / 2;
        const cy = c.top + c.height / 2;
        const gap = b
          ? Math.hypot(
              Math.max(b.left - cx, 0, cx - b.right),
              Math.max(b.top - cy, 0, cy - b.bottom),
            ) -
            c.width / 2
          : 0;
        return {
          named: t != null,
          gap,
          leader: a.querySelector("line[data-plate-leader]") != null,
        };
      }),
    );
    expect(m.filter((d) => d.named).length).toBe(9);
    for (const d of m.filter((x) => x.named && x.gap > 7)) {
      expect(d.leader, `a name ${d.gap.toFixed(1)}px off its dot`).toBe(true);
    }
    expect(m.filter((d) => d.leader).length).toBe(4);
  });
});
