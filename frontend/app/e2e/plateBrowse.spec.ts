import type { Locator, Page } from "@playwright/test";
import { AxeBuilder } from "@axe-core/playwright";
import { PLATE_BOARD_PX } from "../src/lib/plateSide";
import { BOARD, HOME_GRAPH, RELATED_GRAPH, reachableNodes } from "./plateLocators";
import { eachTheme, expect, lightOnly, only, test } from "./support";

// The board is the panel under the graph that describes the node the pointer is on or that is selected.

type Open = (path: string, options?: { ready?: Locator }) => Promise<void>;

/** Opens a page and waits for the graph to have faded in. */
async function openGraph(page: Page, open: Open, path: string, graph: string) {
  await open(path, { ready: page.locator(`${graph} a`).first() });
  await expect(page.locator(graph)).toHaveCSS("opacity", "1");
}

/** Returns the index of the `skip`-th reachable node, or -1 when there are fewer. */
async function pickNode(page: Page, graph: string, skip = 0): Promise<number> {
  return (await reachableNodes(page, graph))[skip] ?? -1;
}

function nodeCircle(page: Page, graph: string, index: number): Locator {
  return page.locator(`${graph} a`).nth(index).locator("[data-plate-hit]");
}

/** Measures the page, figure and board heights, the frame's top and bottom and the board's top in document coordinates, and the scroll offset. */
async function metrics(page: Page, graph: string) {
  return page.evaluate((sel) => {
    const frame = document.querySelector(sel)!.getBoundingClientRect();
    const board = document.querySelector("[data-plate-board]")!.getBoundingClientRect();
    const figure = document.querySelector("figure")!.getBoundingClientRect();
    return {
      pageHeight: document.documentElement.scrollHeight,
      figureHeight: figure.height,
      frameTop: frame.top + window.scrollY,
      frameBottom: frame.bottom + window.scrollY,
      boardHeight: board.height,
      boardTop: board.top + window.scrollY,
      scrollY: window.scrollY,
    };
  }, graph);
}

async function boardTitle(page: Page): Promise<string> {
  return (await page.locator(`${BOARD} p`).first().textContent()) ?? "";
}

eachTheme(() => {
  test(`Home graph: hover fills the board, click selects, a second click opens`, async ({
    page,
    open,
  }) => {
    await openGraph(page, open, "/", HOME_GRAPH);
    const index = await pickNode(page, HOME_GRAPH);
    expect(index).toBeGreaterThanOrEqual(0);
    const circle = nodeCircle(page, HOME_GRAPH, index);
    const title = (await page
      .locator(`${HOME_GRAPH} a`)
      .nth(index)
      .getAttribute("aria-label"))!.split(/, [\d,]+ views/)[0]!;
    const url = page.url();
    const vw = page.viewportSize()!.width;

    await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "idle");
    await expect(page.locator(BOARD)).toContainText(
      "Point at a dot to see it here. Click it to select, then open its dossier.",
    );
    await expect(page.getByRole("region", { name: "Selected article" })).toHaveCount(1);
    const idle = await metrics(page, HOME_GRAPH);

    await circle.hover();
    await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "preview");
    expect(await boardTitle(page)).toBe(title);
    await expect(page.locator(BOARD)).not.toContainText(/click to select/i);
    await expect(page.locator("[data-plate-hover-ring]")).toHaveCount(1);
    const hover = await metrics(page, HOME_GRAPH);
    expect(hover.figureHeight).toBe(idle.figureHeight);
    expect(hover.frameTop).toBe(idle.frameTop);
    expect(hover.frameBottom).toBe(idle.frameBottom);
    expect(hover.boardHeight).toBe(idle.boardHeight);
    expect(page.url()).toBe(url);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(vw);

    await page.mouse.move(2, 2);
    await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "idle");

    await circle.click();
    expect(page.url()).toBe(url);
    await expect(page.locator("[data-plate-ring]")).toHaveCount(1);
    await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "selected");
    expect(await boardTitle(page)).toBe(title);
    await expect(
      page.locator(BOARD).getByRole("link", { name: /Open dossier|Build dossier/ }),
    ).toBeVisible();
    await expect(page.locator(BOARD)).not.toContainText(/pinned/i);
    const selected = await metrics(page, HOME_GRAPH);
    expect(selected.boardHeight).toBe(idle.boardHeight);
    expect(selected.figureHeight).toBe(idle.figureHeight);
    expect(selected.frameTop).toBe(idle.frameTop);
    expect(selected.frameBottom).toBe(idle.frameBottom);
    expect(selected.scrollY).toBe(idle.scrollY);
    // axe 4.14 drops parentheses from the name but not from a cut label like "Film (2026 Indian...", so that rule is replaced by a direct check below.
    const axe = await new AxeBuilder({ page })
      .include("figure")
      .disableRules(["label-content-name-mismatch"])
      .analyze();
    expect(axe.violations).toEqual([]);
    const names = await page.locator(`${HOME_GRAPH} a`).evaluateAll((nodes) =>
      nodes.map((a) => ({
        name: a.getAttribute("aria-label") ?? "",
        shown: (a.querySelector("text tspan")?.textContent ?? "").replace(/\.{3}$/, ""),
      })),
    );
    for (const { name, shown } of names) {
      expect(name.startsWith(shown), `"${name}" starts with its shown text "${shown}"`).toBe(true);
    }

    const other = await pickNode(page, HOME_GRAPH, 3);
    expect(other).toBeGreaterThanOrEqual(0);
    expect(other).not.toBe(index);
    await nodeCircle(page, HOME_GRAPH, other).hover();
    await expect(page.locator("[data-plate-hover-ring]")).toHaveCount(1);
    expect(await boardTitle(page)).toBe(title);
    await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "selected");
    const both = await metrics(page, HOME_GRAPH);
    expect(both.boardHeight).toBe(idle.boardHeight);
    expect(both.figureHeight).toBe(idle.figureHeight);

    await circle.click();
    await expect(page).toHaveURL(/\/t\/[^/?]+\?budget=8000$/);
  });

  test(
    "the board is one fixed slot under the frame and never overflows, whichever node is selected",
    only("mobile-390", "desktop-1440"),
    async ({ page, open }) => {
      await openGraph(page, open, "/", HOME_GRAPH);
      const idle = await metrics(page, HOME_GRAPH);
      expect(idle.boardHeight).toBe(PLATE_BOARD_PX);
      const gap = await page.evaluate((sel) => {
        const frame = document
          .querySelector(sel)!
          .closest("figure")!
          .firstElementChild!.getBoundingClientRect();
        const board = document.querySelector("[data-plate-board]")!.getBoundingClientRect();
        // The legend chip is inside the frame, so the board follows the frame directly.
        return board.top - frame.bottom;
      }, HOME_GRAPH);
      expect(gap).toBeCloseTo(8, 0);
      const style = await page.locator(BOARD).evaluate((el) => {
        const cs = getComputedStyle(el);
        return { border: cs.borderTopWidth, shadow: cs.boxShadow, radius: cs.borderTopLeftRadius };
      });
      expect(style).toEqual({ border: "1px", shadow: "none", radius: "0px" });
      for (let pick = 0; pick < 5; pick += 1) {
        const index = await pickNode(page, HOME_GRAPH, pick * 4);
        if (index < 0) {
          break;
        }
        const title = (await page
          .locator(`${HOME_GRAPH} a`)
          .nth(index)
          .getAttribute("aria-label"))!.split(/, [\d,]+ views/)[0]!;
        await nodeCircle(page, HOME_GRAPH, index).click();
        await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "selected");
        expect(await boardTitle(page)).toBe(title);
        await expect(
          page.locator(BOARD).getByRole("link", { name: /Open dossier|Build dossier/ }),
        ).toBeVisible();
        const now = await metrics(page, HOME_GRAPH);
        expect(now.boardHeight).toBe(idle.boardHeight);
        expect(now.frameBottom).toBe(idle.frameBottom);
        const overflow = await page
          .locator(BOARD)
          .evaluate((el) => el.scrollHeight > el.clientHeight + 1);
        expect(overflow).toBe(false);
      }
    },
  );
});

lightOnly(() => {
  test(
    `Home graph: the board link opens the dossier`,
    only("mobile-390", "desktop-1440"),
    async ({ page, open }) => {
      await openGraph(page, open, "/", HOME_GRAPH);
      const index = await pickNode(page, HOME_GRAPH);
      await nodeCircle(page, HOME_GRAPH, index).click();
      await page
        .locator(BOARD)
        .getByRole("link", { name: /Open dossier|Build dossier/ })
        .click();
      await expect(page).toHaveURL(/\/t\/[^/?]+\?budget=8000$/);
    },
  );

  test(
    `Home graph: Tab, arrows, Enter selects, Enter opens, Esc clears and keeps focus`,
    only("desktop-1440"),
    async ({ page, open }) => {
      await openGraph(page, open, "/", HOME_GRAPH);
      await expect(page.locator(`${HOME_GRAPH} a[tabindex="0"]`)).toHaveCount(1);
      const anchor = page.locator(`${HOME_GRAPH} a[tabindex="0"]`);
      const url = page.url();
      await anchor.focus();
      // Keyboard focus previews a node as hover does: the ring and the board follow.
      await page.keyboard.press("ArrowRight");
      await expect(page.locator(`${HOME_GRAPH} a[tabindex="0"]`)).toHaveCount(1);
      await expect(page.locator("[data-plate-hover-ring]")).toHaveCount(1);
      await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "preview");
      await page.keyboard.press("ArrowLeft");
      await page.keyboard.press("Enter");
      expect(page.url()).toBe(url);
      await expect(page.locator("[data-plate-ring]")).toHaveCount(1);
      await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "selected");
      // Tab leaves the node for the legend chip, then continues on to the dossier link in the board.
      const boardLink = page.locator(BOARD).getByRole("link");
      await page.keyboard.press("Tab");
      await expect(page.locator("[data-plate-legend] button").first()).toBeFocused();
      for (let stop = 0; stop < 20; stop += 1) {
        if (await boardLink.evaluate((el) => el === document.activeElement)) {
          break;
        }
        await page.keyboard.press("Tab");
      }
      await expect(boardLink).toBeFocused();
      await page.keyboard.press("Escape");
      await expect(page.locator("[data-plate-ring]")).toHaveCount(0);
      // Focus stays on the node, so the board previews it instead of showing it as selected.
      await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "preview");
      await expect(anchor).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(page.locator("[data-plate-ring]")).toHaveCount(1);
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(/\/t\/[^/?]+\?budget=8000$/);
    },
  );

  test(
    `Home graph: a modified click is left to the browser`,
    only("desktop-1440"),
    async ({ page, open }) => {
      await openGraph(page, open, "/", HOME_GRAPH);
      const result = await page.evaluate((plate) => {
        const anchor = document.querySelector(`${plate} a`)!;
        let prevented: boolean | null = null;
        document.addEventListener(
          "click",
          (event) => {
            prevented = event.defaultPrevented;
            event.preventDefault();
          },
          { once: true },
        );
        anchor.dispatchEvent(
          new MouseEvent("click", { bubbles: true, cancelable: true, ctrlKey: true }),
        );
        return prevented;
      }, HOME_GRAPH);
      expect(result).toBe(false);
      await expect(page.locator("[data-plate-ring]")).toHaveCount(0);
    },
  );

  test(`Home graph: a click on an empty spot clears the selection, every node has a 24px hit area`, async ({
    page,
    open,
  }) => {
    await openGraph(page, open, "/", HOME_GRAPH);
    const hits = await page.locator(`${HOME_GRAPH} [data-plate-hit]`).evaluateAll((els) =>
      els.map((el) => {
        const box = el.getBoundingClientRect();
        return Math.min(box.width, box.height);
      }),
    );
    expect(hits.length).toBeGreaterThan(0);
    for (const size of hits) {
      expect(size).toBeGreaterThanOrEqual(23.5);
    }
    const index = await pickNode(page, HOME_GRAPH);
    await nodeCircle(page, HOME_GRAPH, index).click();
    await expect(page.locator("[data-plate-ring]")).toHaveCount(1);
    const empty = await page.evaluate((plate) => {
      const svg = document.querySelector(plate)!;
      const box = svg.getBoundingClientRect();
      for (let y = box.top + 6; y < box.bottom - 6; y += 8) {
        for (let x = box.left + 6; x < box.right - 6; x += 8) {
          const hit = document.elementFromPoint(x, y);
          if (hit && svg.contains(hit) && !hit.closest("a")) {
            return { x, y };
          }
        }
      }
      return null;
    }, HOME_GRAPH);
    expect(empty).not.toBeNull();
    await page.mouse.click(empty!.x, empty!.y);
    await expect(page.locator("[data-plate-ring]")).toHaveCount(0);
    await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "idle");
  });

  test(`Related graph: the board sits under the frame and speaks of similarity`, async ({
    page,
    open,
  }) => {
    await openGraph(page, open, "/t/Lizzie_Borden", RELATED_GRAPH);
    const labels = await page
      .locator(`${RELATED_GRAPH} a`)
      .evaluateAll((els) => els.map((el) => el.getAttribute("aria-label") ?? ""));
    expect(labels.length).toBeGreaterThan(0);
    for (const label of labels) {
      expect(label).not.toMatch(/views/i);
    }
    const hits = await page
      .locator(`${RELATED_GRAPH} [data-plate-hit]`)
      .evaluateAll((els) =>
        els.map((el) =>
          Math.min(el.getBoundingClientRect().width, el.getBoundingClientRect().height),
        ),
      );
    for (const size of hits) {
      expect(size).toBeGreaterThanOrEqual(23.5);
    }
    await page.locator(RELATED_GRAPH).scrollIntoViewIfNeeded();
    const index = await pickNode(page, RELATED_GRAPH);
    expect(index).toBeGreaterThanOrEqual(0);
    const circle = nodeCircle(page, RELATED_GRAPH, index);
    await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "idle");
    const idle = await metrics(page, RELATED_GRAPH);
    expect(idle.boardHeight).toBe(PLATE_BOARD_PX);
    const frame = (await page.locator(RELATED_GRAPH).boundingBox())!;
    const board = (await page.locator(BOARD).boundingBox())!;
    expect(board.y).toBeGreaterThanOrEqual(frame.y + frame.height);

    // Hovering a dot puts the board into its preview state.
    await circle.hover();
    await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "preview");
    await expect(page.locator(BOARD)).not.toContainText(/click to select/i);
    const url = page.url();
    await circle.click();
    expect(page.url()).toBe(url);
    await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "selected");
    const text = (await page.locator(BOARD).textContent()) ?? "";
    expect(text).not.toMatch(/views/i);
    expect(text).toMatch(/Similarity\s*\d\.\d\d|Linked to/);
    const selected = await metrics(page, RELATED_GRAPH);
    expect(selected.boardHeight).toBe(idle.boardHeight);
    expect(selected.frameBottom).toBe(idle.frameBottom);
    await circle.click();
    await expect(page).toHaveURL(/\/t\/[^/?]+\?budget=8000$/);
  });
});

test.describe("pointer sweep", only("desktop-1440"), () => {
  test.use({ theme: "light" });

  test("a pointer sweep: the board names only the node under the pointer", async ({
    page,
    open,
  }) => {
    test.setTimeout(120_000);
    await openGraph(page, open, "/", HOME_GRAPH);
    const frame = (await page.locator(HOME_GRAPH).boundingBox())!;
    const bad: string[] = [];
    let steps = 0;
    for (let y = frame.y + 12; y < frame.y + frame.height - 6; y += 24) {
      for (let x = frame.x + 12; x < frame.x + frame.width - 6; x += 24) {
        await page.mouse.move(x, y);
        steps += 1;
        // The board may keep the last dot for at most one animation frame.
        await page.evaluate(
          () => new Promise((resolve) => requestAnimationFrame(() => resolve(null))),
        );
        const seen = await page.evaluate(
          ({ x: px, y: py }) => {
            const under = document.elementFromPoint(px, py)?.closest("a");
            const underTitle =
              under?.getAttribute("aria-label")?.split(/, [\d,]+ views/)[0] ?? null;
            const board = document.querySelector("[data-plate-board]")!;
            const kind = board.getAttribute("data-plate-board");
            const named = kind === "idle" ? null : (board.querySelector("p")?.textContent ?? null);
            return {
              underTitle,
              named,
              kind,
            };
          },
          { x, y },
        );
        if (seen.named !== seen.underTitle) {
          bad.push(`${Math.round(x)},${Math.round(y)} ${JSON.stringify(seen)}`);
        }
      }
    }
    expect(steps).toBeGreaterThan(300);
    expect(bad.slice(0, 5)).toEqual([]);
  });
});

test.describe("dwelling on nodes", only("desktop-1440"), () => {
  test.use({ theme: "dark" });

  test("dwelling on every reachable node: the board names it", async ({ page, open }) => {
    test.setTimeout(120_000);
    await openGraph(page, open, "/", HOME_GRAPH);
    const reachable = await reachableNodes(page, HOME_GRAPH);
    expect(reachable.length).toBeGreaterThan(10);
    for (const i of reachable) {
      const anchor = page.locator(`${HOME_GRAPH} a`).nth(i);
      const title = (await anchor.getAttribute("aria-label"))!.split(/, [\d,]+ views/)[0]!;
      await anchor.locator("[data-plate-hit]").hover();
      await expect.soft(page.locator(`${BOARD} p`).first(), `node ${i}`).toHaveText(title);
    }
  });
});

test.describe("on touch", only("mobile-390"), () => {
  test.use({ hasTouch: true });

  lightOnly(() => {
    test("Home graph: the first tap selects and the second tap opens", async ({ page, open }) => {
      await openGraph(page, open, "/", HOME_GRAPH);
      const index = await pickNode(page, HOME_GRAPH);
      const hit = (await nodeCircle(page, HOME_GRAPH, index).boundingBox())!;
      const url = page.url();
      const idle = await metrics(page, HOME_GRAPH);
      await page.touchscreen.tap(hit.x + hit.width / 2, hit.y + hit.height / 2);
      await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "selected");
      expect(page.url()).toBe(url);
      const selected = await metrics(page, HOME_GRAPH);
      expect(selected.boardHeight).toBe(PLATE_BOARD_PX);
      expect(selected.boardHeight).toBe(idle.boardHeight);
      expect(selected.frameBottom).toBe(idle.frameBottom);
      const figure = (await page.locator("figure").first().boundingBox())!;
      const board = (await page.locator(BOARD).boundingBox())!;
      expect(Math.abs(board.width - figure.width)).toBeLessThanOrEqual(1);
      const again = (await nodeCircle(page, HOME_GRAPH, index).boundingBox())!;
      await page.touchscreen.tap(again.x + again.width / 2, again.y + again.height / 2);
      await expect(page).toHaveURL(/\/t\/[^/?]+\?budget=8000$/);
    });

    test("Home graph: a tap on an empty spot clears the selection", async ({ page, open }) => {
      await openGraph(page, open, "/", HOME_GRAPH);
      const index = await pickNode(page, HOME_GRAPH);
      const hit = (await nodeCircle(page, HOME_GRAPH, index).boundingBox())!;
      await page.touchscreen.tap(hit.x + hit.width / 2, hit.y + hit.height / 2);
      await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "selected");
      const empty = await page.evaluate((plate) => {
        const svg = document.querySelector(plate)!;
        const box = svg.getBoundingClientRect();
        for (
          let y = Math.max(box.top, 80) + 6;
          y < Math.min(box.bottom, window.innerHeight) - 6;
          y += 8
        ) {
          for (let x = box.left + 6; x < box.right - 6; x += 8) {
            const under = document.elementFromPoint(x, y);
            if (under && svg.contains(under) && !under.closest("a")) {
              return { x, y };
            }
          }
        }
        return null;
      }, HOME_GRAPH);
      expect(empty).not.toBeNull();
      await page.touchscreen.tap(empty!.x, empty!.y);
      await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "idle");
    });
  });
});
