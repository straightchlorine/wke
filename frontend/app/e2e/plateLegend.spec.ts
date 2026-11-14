import { devices, type Locator, type Page } from "@playwright/test";
import { mockApi } from "./mockApi";
import { HOME_GRAPH } from "./plateLocators";
import { expect, lightOnly, only, settleBox, test } from "./support";

// The Home graph's legend: one swatch button per linked group. Its tooltip reads
// "Articles related to <most-read member>" with a link to that dossier, and
// while it is open the group's outline is drawn stronger on the graph.

type Open = (
  path: string,
  options?: { viewport?: { width: number; height: number }; ready?: Locator },
) => Promise<void>;

// The pause flag stops the replayed edit rows, so nothing below the graph moves mid-test.
test.use({ paused: true });

/** Opens Home and returns the figure that holds the graph and the legend's swatch buttons. */
async function openHome(page: Page, open: Open, size?: readonly [number, number]) {
  await open("/", {
    viewport: size ? { width: size[0], height: size[1] } : undefined,
    ready: page.locator(`${HOME_GRAPH} a`).first(),
  });
  const plate = page.locator("figure", { hasText: "Plate 1." });
  return {
    plate,
    buttons: plate.getByRole("group", { name: "Linked groups" }).getByRole("button"),
  };
}

/** Counts the dots, names and group-outline points that lie under the open swatch tooltip. */
async function obstaclesUnderTip(page: Page) {
  return page.evaluate((graph) => {
    const t = [...document.querySelectorAll('[role="tooltip"]')]
      .find(
        (e) =>
          e.textContent?.includes("Articles related to") && e.getBoundingClientRect().width > 0,
      )!
      .getBoundingClientRect();
    const hit = (r: DOMRect) =>
      Math.min(t.right, r.right) > Math.max(t.left, r.left) &&
      Math.min(t.bottom, r.bottom) > Math.max(t.top, r.top);
    const svg = document.querySelector(graph)!;
    let n = [
      ...svg.querySelectorAll(
        "a > circle:not([data-plate-hit]):not([data-plate-hover-ring]), text[data-plate-label]",
      ),
    ].filter((e) => hit(e.getBoundingClientRect())).length;
    for (const path of svg.querySelectorAll<SVGPathElement>("path[data-plate-hull]")) {
      const m = path.getScreenCTM()!;
      for (let at = 0; at < path.getTotalLength(); at += 3) {
        const q = path.getPointAtLength(at);
        const x = m.a * q.x + m.c * q.y + m.e;
        const y = m.b * q.x + m.d * q.y + m.f;
        if (x >= t.left && x <= t.right && y >= t.top && y <= t.bottom) n += 1;
      }
    }
    return n;
  }, HOME_GRAPH);
}

/** Scrolls so the legend chip's bottom edge is 4px above the bottom of the window. */
function scrollLegendIntoView(page: Page) {
  return page.evaluate(() => {
    const chip = document.querySelector("[data-plate-legend]")!.getBoundingClientRect();
    window.scrollBy(0, chip.bottom - (window.innerHeight - 4));
  });
}

const ACTIVE_HULL = `${HOME_GRAPH} path[data-plate-hull-active]`;

lightOnly(() => {
  test.describe("Home graph legend tooltip", () => {
    test(
      "hover opens it with the dossier link, it stays open under the pointer, and the group's outline answers",
      only("desktop-1440"),
      async ({ page, open }) => {
        // The clock runs on, and runFor passes the tooltip's close delay without waiting for it.
        await page.clock.install();
        const { plate, buttons } = await openHome(page, open);
        const button = buttons.first();
        const name = ((await button.getAttribute("aria-label")) ?? "").replace(
          "Articles related to ",
          "",
        );
        const tip = plate.getByRole("tooltip").filter({ hasText: "Articles related to" });
        await expect(tip).toHaveCount(0);
        await expect(page.locator(ACTIVE_HULL)).toHaveCount(0);
        const idle = await page
          .locator(`${HOME_GRAPH} path[data-plate-hull]`)
          .first()
          .getAttribute("fill-opacity");
        await button.hover();
        await expect(tip).toBeVisible();
        await expect(tip).toContainText(`Articles related to ${name}`);
        const link = tip.getByRole("link", { name: /^(Open|Build) dossier$/ });
        expect(await link.getAttribute("href")).toMatch(/^\/t\/[^/?]+\?budget=\d+$/);
        await expect(page.locator(ACTIVE_HULL)).toHaveCount(1);
        expect(await page.locator(ACTIVE_HULL).getAttribute("fill-opacity")).not.toBe(idle);
        expect(Number(await page.locator(ACTIVE_HULL).getAttribute("stroke-opacity"))).toBe(1);
        // The pointer crosses into the tooltip: it stays open.
        await link.hover();
        await page.clock.runFor(1_000);
        await expect(tip).toBeVisible();
        await expect(page.locator(ACTIVE_HULL)).toHaveCount(1);
        await page.mouse.move(5, 5);
        await expect(tip).toHaveCount(0);
        await expect(page.locator(ACTIVE_HULL)).toHaveCount(0);
      },
    );

    // The tooltip tries a fixed list of spots and takes the first one clear of every dot, outline point and name.
    // When none is clear, it opens just under the frame if that fits, otherwise on the spot that covers least.
    for (const [width, height] of [
      [844, 390],
      [1024, 768],
      [1280, 800],
      [1440, 1000],
      [1920, 1080],
      [3840, 2160],
    ] as const) {
      test(
        `the tooltip of each swatch covers no dot, outline point or name, and stays in the graph column above the board's bottom, at ${width}x${height}`,
        only("desktop-1440"),
        async ({ page, open }) => {
          // The clock runs on, and runFor passes the tooltip's close delay without waiting for it.
          await page.clock.install();
          const { plate, buttons } = await openHome(page, open, [width, height]);
          const tip = plate.getByRole("tooltip").filter({ hasText: "Articles related to" });
          const own: number[] = [];
          const other: number[] = [];
          for (let i = 0; i < (await buttons.count()); i += 1) {
            await page.mouse.move(5, 5);
            await buttons.nth(i).hover();
            await expect(tip).toBeVisible();
            await settleBox(tip);
            const under = await page.evaluate((graph) => {
              const tipEl = [...document.querySelectorAll('[role="tooltip"]')].find(
                (el) =>
                  el.textContent?.includes("Articles related to") &&
                  el.getBoundingClientRect().width > 0,
              )!;
              const t = tipEl.getBoundingClientRect();
              const svg = document.querySelector(graph)!;
              const hits = (r: DOMRect) =>
                Math.min(t.right, r.right) > Math.max(t.left, r.left) &&
                Math.min(t.bottom, r.bottom) > Math.max(t.top, r.top);
              const active =
                svg
                  .querySelector("path[data-plate-hull-active]")
                  ?.getAttribute("data-plate-hull") ?? "none";
              let ownCount = 0;
              let otherCount = 0;
              for (const el of svg.querySelectorAll(
                "a > circle:not([data-plate-hit]):not([data-plate-hover-ring]), text[data-plate-label]",
              )) {
                if (hits(el.getBoundingClientRect())) {
                  if (
                    (el.getAttribute("data-plate-cluster") ??
                      el
                        .closest("a")
                        ?.querySelector("circle[data-plate-cluster]")
                        ?.getAttribute("data-plate-cluster")) === active
                  )
                    ownCount += 1;
                  else otherCount += 1;
                }
              }
              for (const path of svg.querySelectorAll<SVGPathElement>("path[data-plate-hull]")) {
                const m = path.getScreenCTM()!;
                const length = path.getTotalLength();
                for (let at = 0; at < length; at += 3) {
                  const q = path.getPointAtLength(at);
                  const x = m.a * q.x + m.c * q.y + m.e;
                  const y = m.b * q.x + m.d * q.y + m.f;
                  if (x >= t.left && x <= t.right && y >= t.top && y <= t.bottom) {
                    if (path.getAttribute("data-plate-hull") === active) ownCount += 1;
                    else otherCount += 1;
                  }
                }
              }
              const column = tipEl.closest("figure")!.getBoundingClientRect();
              const frame = document.querySelector("[data-plate-frame]")!;
              const board = frame.nextElementSibling!.getBoundingClientRect();
              const hullBox = svg
                .querySelector("path[data-plate-hull-active]")
                ?.getBoundingClientRect();
              return {
                ownCount,
                otherCount,
                tipInView:
                  t.top >= 0 &&
                  t.left >= 0 &&
                  t.bottom <= window.innerHeight &&
                  t.right <= window.innerWidth,
                hullInView:
                  hullBox != null &&
                  hullBox.top >= 0 &&
                  hullBox.left >= 0 &&
                  hullBox.bottom <= window.innerHeight &&
                  hullBox.right <= window.innerWidth,
                inColumn: t.left >= column.left - 0.5 && t.right <= column.right + 0.5,
                aboveBoardBottom: t.bottom <= board.bottom + 0.5,
              };
            }, HOME_GRAPH);
            own.push(under.ownCount);
            other.push(under.otherCount);
            // The pointer goes from the swatch to the tip in 3 steps; the tip stays open past the close delay.
            const from = (await buttons.nth(i).boundingBox())!;
            const to = (await tip.boundingBox())!;
            await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
            await page.mouse.move(to.x + 12, to.y + to.height / 2, { steps: 3 });
            await page.clock.runFor(1_000);
            await expect(tip, `tip ${i} stays open along the hover path`).toBeVisible();
            await page.mouse.move(5, 5);
            await expect(tip, `tip ${i} closes after the pointer leaves`).toBeHidden({
              timeout: 3000,
            });
            // Only these sizes show the whole frame without scrolling.
            if (width === 1280 || width === 1920) {
              expect(under.tipInView, `tip ${i} inside the viewport`).toBe(true);
              expect(under.hullInView, `hull ${i} inside the viewport`).toBe(true);
            }
            expect(under.inColumn, `tip ${i} inside the graph column`).toBe(true);
            expect(under.aboveBoardBottom, `tip ${i} above the board's bottom`).toBe(true);
          }
          expect(Math.max(...own), `own-group things under each tip: ${own.join(",")}`).toBe(0);
          expect(
            other.reduce((a, b) => a + b, 0),
            `other groups' things under each tip: ${other.join(",")}`,
          ).toBe(0);
        },
      );
    }

    test(
      "the keyboard opens it on focus, Enter and Tab reach the link, Esc closes it and returns focus",
      only("desktop-1440"),
      async ({ page, open }) => {
        const { plate, buttons } = await openHome(page, open);
        const button = buttons.nth(1);
        const tip = plate.getByRole("tooltip").filter({ hasText: "Articles related to" });
        await button.focus();
        await expect(tip).toBeVisible();
        const link = tip.getByRole("link");
        await page.keyboard.press("Enter");
        await expect(link).toBeFocused();
        await expect(tip).toBeVisible();
        await page.keyboard.press("Escape");
        await expect(tip).toHaveCount(0);
        await expect(button).toBeFocused();
        await expect(page.locator(ACTIVE_HULL)).toHaveCount(0);
        // With the tooltip open, Tab from the swatch lands in it; Tab out of it moves on to the next swatch and closes this tooltip.
        const tipId = await button.getAttribute("aria-describedby");
        await button.blur();
        await button.focus();
        await expect(tip).toBeVisible();
        await page.keyboard.press("Tab");
        await expect(link).toBeFocused();
        await page.keyboard.press("Tab");
        await expect(buttons.nth(2)).toBeFocused();
        await expect(page.locator(`[id="${tipId}"]`)).toBeHidden();
      },
    );

    test(
      "Esc closes the tooltip and Enter or Space reopens it while the swatch keeps focus",
      only("desktop-1440"),
      async ({ page, open }) => {
        const { plate, buttons } = await openHome(page, open);
        const button = buttons.nth(1);
        const tip = plate.getByRole("tooltip").filter({ hasText: "Articles related to" });
        await button.focus();
        await expect(tip).toBeVisible();
        for (const key of ["Enter", "Space"]) {
          await page.keyboard.press("Escape");
          await expect(tip).toHaveCount(0);
          await expect(button).toBeFocused();
          await page.keyboard.press(key);
          await expect(tip).toBeVisible();
          await expect(page.locator(ACTIVE_HULL)).toHaveCount(1);
          await expect(button).toBeFocused();
        }
      },
    );

    test(
      "only linked groups carry a colour: grey dots are the unlinked, and every swatch has a hull to highlight",
      only("desktop-1440"),
      async ({ page, open }) => {
        const { buttons } = await openHome(page, open);
        const m = await page.evaluate((graph) => {
          const svg = document.querySelector(graph)!;
          const dots = [
            ...svg.querySelectorAll<SVGCircleElement>("a > circle:first-of-type"),
          ].filter(
            (c) =>
              c.getAttribute("fill") !== "var(--wke-stamp-wash)" &&
              c.getAttribute("fill") !== "var(--wke-ink)",
          );
          const neutral = dots.filter((c) => c.hasAttribute("data-plate-neutral"));
          const coloured = dots.filter((c) => !c.hasAttribute("data-plate-neutral"));
          return {
            neutralPaint: [
              ...new Set(
                neutral.map((c) => `${c.getAttribute("fill")}|${c.getAttribute("stroke")}`),
              ),
            ],
            colouredStrokes: [...new Set(coloured.map((c) => c.getAttribute("stroke")))],
            neutral: neutral.length,
            coloured: coloured.length,
            hulls: svg.querySelectorAll("path[data-plate-hull]").length,
          };
        }, HOME_GRAPH);
        expect(m.neutral).toBeGreaterThan(0);
        expect(m.neutralPaint).toEqual(["var(--wke-paper)|var(--wke-ink-3)"]);
        expect(m.colouredStrokes.every((s) => /^var\(--wke-c[1-6]\)$/.test(s ?? ""))).toBe(true);
        expect(m.colouredStrokes.length).toBe(await buttons.count());
        expect(m.hulls).toBe(await buttons.count());
      },
    );

    test("the link opens the group's dossier", only("desktop-1440"), async ({ page, open }) => {
      const { plate, buttons } = await openHome(page, open);
      await buttons.first().focus();
      const link = plate.getByRole("tooltip").getByRole("link");
      const href = await link.getAttribute("href");
      await page.keyboard.press("Enter");
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(
        new RegExp(href!.split("?")[0]!.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
      );
    });
  });

  test.describe("Home graph legend tooltip, touch", () => {
    test.use({ hasTouch: true });

    test(
      "a tap leaves the tooltip and the highlighted hull on screen together, the tooltip inside the graph column, the chip inside the frame",
      only("mobile-390"),
      async ({ page, open }) => {
        const { plate, buttons } = await openHome(page, open);
        const chip = plate.locator("[data-plate-legend]");
        const frame = await plate.locator("[data-plate-frame]").boundingBox();
        const box = await chip.boundingBox();
        expect(box!.y).toBeGreaterThanOrEqual(frame!.y);
        expect(box!.y + box!.height).toBeLessThanOrEqual(frame!.y + frame!.height);
        // The chip is 28px tall; each swatch's 44px hit area overhangs it by 8px
        // at top and bottom, and the bottom reaches no further than the frame.
        expect(
          frame!.y + frame!.height - (box!.y + box!.height + 8),
          "hit area ends inside the frame",
        ).toBeGreaterThanOrEqual(-0.5);
        await buttons.first().scrollIntoViewIfNeeded();
        const reach = await buttons.first().evaluate((el) => {
          const r = el.getBoundingClientRect();
          const x = r.left + r.width / 2;
          const cy = r.top + r.height / 2;
          return [cy - 21, cy + 21].map((y) => document.elementFromPoint(x, y) === el);
        });
        expect(reach, "44px tall hit area on the first swatch").toEqual([true, true]);
        const pitch = await buttons.evaluateAll((els) =>
          els.map((el) => el.getBoundingClientRect().left),
        );
        expect(pitch[1]! - pitch[0]!, "44px pitch between swatches").toBeCloseTo(44, 0);
        await buttons.last().tap();
        const tip = plate.getByRole("tooltip").filter({ hasText: "Articles related to" });
        await expect(tip).toBeVisible();
        const view = page.viewportSize()!;
        const inside = (b: { x: number; y: number; width: number; height: number } | null) =>
          b != null &&
          b.x >= 0 &&
          b.y >= 0 &&
          b.x + b.width <= view.width &&
          b.y + b.height <= view.height;
        expect(inside(await tip.boundingBox()), "tooltip in the viewport").toBe(true);
        expect(await obstaclesUnderTip(page), "things under the tip at 390").toBe(0);
        expect(inside(await page.locator(ACTIVE_HULL).boundingBox()), "hull in the viewport").toBe(
          true,
        );
        const column = await plate.boundingBox();
        const tipBox = (await tip.boundingBox())!;
        expect(tipBox.x, "tooltip inside the column on the left").toBeGreaterThanOrEqual(
          column!.x - 0.5,
        );
        expect(
          tipBox.x + tipBox.width,
          "tooltip inside the column on the right",
        ).toBeLessThanOrEqual(column!.x + column!.width + 0.5);
        const link = await tip.getByRole("link").boundingBox();
        expect(link!.height, "Open dossier hit area").toBeLessThan(44);
        const hit = await tip.getByRole("link").evaluate((el) => {
          const r = el.getBoundingClientRect();
          const x = r.left + r.width / 2;
          return [r.top - 12 + 1, r.bottom + 12 - 1].map(
            (y) => document.elementFromPoint(x, y) === el,
          );
        });
        expect(hit).toEqual([true, true]);
      },
    );

    test(
      "on a landscape phone (844x390) a tap on any swatch brings the frame into view (at most 24px of its top cut) and shows the tooltip and the outlined group together",
      only("mobile-390"),
      async ({ page, open }) => {
        const { plate, buttons } = await openHome(page, open, [844, 390]);
        const tip = plate.getByRole("tooltip").filter({ hasText: "Articles related to" });
        const view = page.viewportSize()!;
        const inside = (b: { x: number; y: number; width: number; height: number } | null) =>
          b != null &&
          b.x >= 0 &&
          b.y >= 0 &&
          b.x + b.width <= view.width &&
          b.y + b.height <= view.height;
        for (let i = 0; i < (await buttons.count()); i += 1) {
          await page.touchscreen.tap(4, 4);
          await expect(tip).toHaveCount(0);
          await scrollLegendIntoView(page);
          await buttons.nth(i).tap();
          await expect(tip).toBeVisible();
          expect(inside(await tip.boundingBox()), `tooltip ${i} in the viewport`).toBe(true);
          expect(await obstaclesUnderTip(page), `things under tip ${i} at 844x390`).toBe(0);
          expect(
            inside(await page.locator(ACTIVE_HULL).boundingBox()),
            `hull ${i} in the viewport`,
          ).toBe(true);
          // A tip that falls back under the frame may scroll away at most 24px of the frame's top.
          const frame = (await plate.locator("[data-plate-frame]").boundingBox())!;
          expect(frame.y, `frame ${i} loses at most 24px of its top`).toBeGreaterThanOrEqual(-24);
          expect(frame.y + frame.height, `frame ${i} bottom on screen`).toBeLessThanOrEqual(
            view.height,
          );
          const column = (await plate.boundingBox())!;
          const box = (await tip.boundingBox())!;
          expect(box.x).toBeGreaterThanOrEqual(column.x - 0.5);
          expect(box.x + box.width).toBeLessThanOrEqual(column.x + column.width + 0.5);
        }
      },
    );

    // Each floor is the label count with no chip, minus the 2 labels the chip's reserved corner may cost.
    // The counts come from the mock data and move with the layout.
    for (const [width, height, floor] of [
      [360, 780, 7],
      [390, 844, 10],
      [430, 932, 15],
      [844, 390, 2],
    ] as const) {
      test(
        `touch swatches have 44px hit areas centred on each dot: a tap 20px either side lands on its own swatch at ${width}x${height}, and the labels stay within budget`,
        only("mobile-390"),
        async ({ page, open }) => {
          const { plate, buttons } = await openHome(page, open, [width, height]);
          await plate.locator("[data-plate-frame]").scrollIntoViewIfNeeded();
          await scrollLegendIntoView(page);
          const count = await buttons.count();
          expect(count).toBe(6);
          const hits = await buttons.evaluateAll((els) =>
            els.map((el, i) => {
              const r = el.getBoundingClientRect();
              const cx = r.left + r.width / 2;
              const cy = r.top + r.height / 2;
              return [0, -20, 20].map((dx) => {
                const hit = document.elementFromPoint(cx + dx, cy)?.closest("button");
                return hit === el ? i : `${i} -> ${hit?.getAttribute("aria-label") ?? "none"}`;
              });
            }),
          );
          expect(hits, "6 of 6 swatches answer at the centre and 20px either side").toEqual(
            Array.from({ length: count }, (_, i) => [i, i, i]),
          );
          const geo = await buttons.evaluateAll((els) =>
            els.map((el) => {
              const r = el.getBoundingClientRect();
              return { cx: r.left + r.width / 2, cy: r.top + r.height / 2 };
            }),
          );
          const chip = (await plate.locator("[data-plate-legend]").boundingBox())!;
          const frame = (await plate.locator("[data-plate-frame]").boundingBox())!;
          for (const [i, g] of geo.entries()) {
            if (i > 0) {
              expect(
                g.cx - geo[i - 1]!.cx,
                "44px pitch, so the hit areas do not overlap",
              ).toBeGreaterThanOrEqual(43.9);
            }
            expect(g.cx - 22, "hit area inside the frame on the left").toBeGreaterThanOrEqual(
              frame.x - 0.5,
            );
            expect(g.cy + 22, "hit area inside the frame at the bottom").toBeLessThanOrEqual(
              frame.y + frame.height + 0.5,
            );
          }
          expect(chip.x + chip.width, "chip inside the frame").toBeLessThanOrEqual(
            frame.x + frame.width,
          );
          const tip = plate.getByRole("tooltip").filter({ hasText: "Articles related to" });
          for (let i = 0; i < count; i += 1) {
            await page.touchscreen.tap(4, 4);
            await expect(tip).toHaveCount(0);
            await scrollLegendIntoView(page);
            const g = await buttons.nth(i).evaluate((el) => {
              const r = el.getBoundingClientRect();
              return { cx: r.left + r.width / 2, cy: r.top + r.height / 2 };
            });
            await page.touchscreen.tap(g.cx + 20, g.cy);
            await expect(tip).toBeVisible();
            const name = ((await buttons.nth(i).getAttribute("aria-label")) ?? "").replace(
              "Articles related to ",
              "",
            );
            await expect(tip).toContainText(`Articles related to ${name}`);
          }
          const labels = await page.locator(`${HOME_GRAPH} text[data-plate-label]`).count();
          expect(labels, "Home graph labels shown").toBeGreaterThanOrEqual(floor);
        },
      );
    }

    test(
      "a tap opens it with its link, a tap outside closes it",
      only("mobile-390"),
      async ({ page, open }) => {
        const { plate, buttons } = await openHome(page, open);
        const button = buttons.first();
        const tip = plate.getByRole("tooltip").filter({ hasText: "Articles related to" });
        await button.tap();
        await expect(tip).toBeVisible();
        await expect(tip.getByRole("link", { name: /^(Open|Build) dossier$/ })).toBeVisible();
        await expect(page.locator(ACTIVE_HULL)).toHaveCount(1);
        await page.locator("h1").first().tap();
        await expect(tip).toHaveCount(0);
        await expect(page.locator(ACTIVE_HULL)).toHaveCount(0);
      },
    );
  });

  test.describe("Home graph legend placement", () => {
    for (const [width, height] of [
      [390, 844],
      [1024, 768],
      [1440, 900],
      [1920, 1080],
    ] as const) {
      test(
        `the legend is a chip inside the frame's bottom-left corner at ${width}, 12px swatches, nothing of the plate under it`,
        only("desktop-1440"),
        async ({ page, open }) => {
          const { buttons } = await openHome(page, open, [width, height]);
          await page.locator("[data-plate-legend]").scrollIntoViewIfNeeded();
          const m = await page.evaluate(() => {
            const figure = document.querySelector("figure")!;
            const frame = figure.querySelector("[data-plate-frame]")!.getBoundingClientRect();
            const chipEl = figure.querySelector("[data-plate-legend]")!;
            const chip = chipEl.getBoundingClientRect();
            const svg = figure.querySelector('svg[role="group"]')!;
            const dots = [
              ...svg.querySelectorAll<SVGCircleElement>("a > circle:first-of-type"),
            ].map((c) => {
              const r = c.getBoundingClientRect();
              return { x: r.left + r.width / 2, y: r.top + r.height / 2, r: r.width / 2 };
            });
            const labels = [...svg.querySelectorAll("text[data-plate-label]")].map((t) =>
              t.getBoundingClientRect(),
            );
            const hits = (l: number, t: number, r: number, b: number) =>
              l < chip.right && r > chip.left && t < chip.bottom && b > chip.top;
            const hulls = [...svg.querySelectorAll<SVGPathElement>("path[data-plate-hull]")].filter(
              (h) => {
                const m2 = h.getScreenCTM()!;
                const length = h.getTotalLength();
                for (let at = 0; at < length; at += 1.5) {
                  const pt = h.getPointAtLength(at);
                  const x = m2.a * pt.x + m2.c * pt.y + m2.e;
                  const y = m2.b * pt.x + m2.d * pt.y + m2.f;
                  if (x >= chip.left && x <= chip.right && y >= chip.top && y <= chip.bottom) {
                    return true;
                  }
                }
                return false;
              },
            ).length;
            const leaders = [
              ...svg.querySelectorAll<SVGLineElement>("line[data-plate-leader]"),
            ].filter((l) => {
              const m2 = l.getScreenCTM()!;
              const [x1, y1, x2, y2] = ["x1", "y1", "x2", "y2"].map((k) =>
                Number(l.getAttribute(k)),
              );
              for (let t = 0; t <= 1; t += 0.02) {
                const x = m2.a * (x1! + (x2! - x1!) * t) + m2.e;
                const y = m2.d * (y1! + (y2! - y1!) * t) + m2.f;
                if (x >= chip.left && x <= chip.right && y >= chip.top && y <= chip.bottom) {
                  return true;
                }
              }
              return false;
            }).length;
            return {
              frame,
              chip,
              insideFrame:
                chip.left >= frame.left &&
                chip.right <= frame.right &&
                chip.top >= frame.top &&
                chip.bottom <= frame.bottom,
              dotsUnder: dots.filter((d) => hits(d.x - d.r, d.y - d.r, d.x + d.r, d.y + d.r))
                .length,
              labelsUnder: labels.filter((l) => hits(l.left, l.top, l.right, l.bottom)).length,
              hulls,
              leaders,
              above:
                document
                  .elementFromPoint(chip.left + chip.width / 2, chip.top + chip.height / 2)
                  ?.closest("[data-plate-legend]") != null,
            };
          });
          expect(m.insideFrame, "the chip lies inside the frame").toBe(true);
          expect(
            m.chip.left - m.frame.left,
            "the chip's inset from the frame's left edge is 8px",
          ).toBeCloseTo(8, 0);
          expect(m.frame.bottom - m.chip.bottom, "and from its bottom edge").toBeCloseTo(8, 0);
          expect(m.above, "the chip is above the drawing").toBe(true);
          expect(m.dotsUnder, "no dot under the chip").toBe(0);
          expect(m.labelsUnder, "no name under the chip").toBe(0);
          expect(m.hulls, "no group outline under the chip").toBe(0);
          expect(m.leaders, "no leader under the chip").toBe(0);
          const swatch = await buttons.first().locator('span[aria-hidden="true"]').boundingBox();
          expect(Math.round(swatch!.width)).toBe(12);
          expect(await buttons.count()).toBe(6);
        },
      );
    }
  });
});

// An iPhone (touch, coarse pointer) draws the chip at its 44px pitch: layout and hit areas flip together on (pointer: coarse).
lightOnly(() => {
  test(
    `on an iPhone the legend chip keeps a 44px swatch pitch and a 28px row`,
    only("desktop-1440"),
    async ({ browser, baseURL, theme }) => {
      const context = await browser.newContext({ ...devices["iPhone 14"], baseURL });
      const page = await context.newPage();
      await page.addInitScript(
        (t) => window.localStorage.setItem("wke-theme", t),
        theme ?? "light",
      );
      await page.addInitScript(() => window.localStorage.setItem("wke-paused", "1"));
      await mockApi(page);
      await page.goto("/");
      await page.waitForSelector("[data-plate-legend]");
      await page.evaluate(() => document.fonts.ready);
      const m = await page.evaluate(() => {
        const chip = document.querySelector("[data-plate-legend]")!.getBoundingClientRect();
        const xs = [...document.querySelectorAll("[data-plate-legend] button")].map((b) => {
          const r = b.getBoundingClientRect();
          return r.left + r.width / 2;
        });
        return {
          coarse: matchMedia("(pointer: coarse)").matches,
          h: chip.height,
          pitches: xs.slice(1).map((x, i) => x - xs[i]!),
        };
      });
      await context.close();
      expect(m.coarse).toBe(true);
      expect(m.h).toBeCloseTo(28, 0);
      for (const pitch of m.pitches) {
        expect(pitch).toBeCloseTo(44, 0);
      }
    },
  );
});
