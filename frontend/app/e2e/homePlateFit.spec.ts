import type { Locator, Page } from "@playwright/test";
import { eachTheme, expect, only, test } from "./support";

const HOME_SIZES = [
  [1024, 768],
  [1280, 800],
  [1366, 768],
  [1440, 900],
  [1920, 1080],
  [2560, 1440],
  [3840, 2160],
] as const;

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
    const figure = document.querySelector("figure")!;
    const slot = figure.parentElement!.getBoundingClientRect();
    const fig = figure.getBoundingClientRect();
    const board = document.querySelector("[data-plate-board]")!.getBoundingClientRect();
    const caption = figure.querySelector("figcaption")!.getBoundingClientRect();
    const row = figure
      .querySelector('[role="group"][aria-label="Linked groups"]')!
      .getBoundingClientRect();
    const outside = [
      ...figure.querySelectorAll('[role="group"][aria-label="Linked groups"]'),
    ].filter((el) => !el.closest("[data-plate-frame]")).length;
    const panel = document.querySelector("[data-ledger-panel]")!.getBoundingClientRect();
    const slots = document.querySelectorAll("[data-ledger-panel] tbody tr").length;
    return {
      frame: {
        w: frame.width,
        h: frame.height,
        top: frame.top,
        left: frame.left,
        right: frame.right,
      },
      slot: { left: slot.left, right: slot.right },
      figureBottom: fig.bottom,
      boardTop: board.top,
      boardBottom: board.bottom,
      row: { top: row.top, bottom: row.bottom, left: row.left, right: row.right },
      swatchRowsOutsideFrame: outside,
      captionTop: caption.top,
      captionBottom: caption.bottom,
      panelBottom: panel.bottom,
      slots,
      vh: window.innerHeight,
    };
  });
}

// Home's concept graph on a desktop window: a square frame whose side is capped so
// the frame and the selected-article panel under it (data-plate-board) are both on screen on load,
// centred in its column, with the two columns ending on one line. It sets its own viewport,
// so it runs only on the desktop-1440 project.
test.describe("Home graph fit", only("desktop-1440"), () => {
  eachTheme(() => {
    for (const [width, height] of HOME_SIZES) {
      test(`Home at ${width}x${height}: the square graph frame and its selected-article panel are on screen, the columns end together`, async ({
        page,
        open,
      }) => {
        await openHome(page, open, width, height);
        const g = await geometry(page);
        expect(
          Math.abs(g.frame.w - g.frame.h),
          `frame ${g.frame.w} x ${g.frame.h}`,
        ).toBeLessThanOrEqual(1);
        expect(g.frame.top, "frame top").toBeGreaterThanOrEqual(0);
        expect(
          g.boardBottom,
          `board bottom ${g.boardBottom} in a ${g.vh} px window`,
        ).toBeLessThanOrEqual(g.vh);
        // The linked-groups legend sits inside the frame, so no legend row stands outside it.
        expect(g.swatchRowsOutsideFrame, "no swatch row outside the frame").toBe(0);
        expect(g.row.top, "the chip starts inside the frame").toBeGreaterThanOrEqual(g.frame.top);
        expect(g.row.bottom, "the chip ends inside the frame").toBeLessThanOrEqual(
          g.frame.top + g.frame.h,
        );
        expect(g.row.left, "the chip is inside the frame's left edge").toBeGreaterThanOrEqual(
          g.frame.left,
        );
        expect(g.row.right, "the chip is inside the frame's right edge").toBeLessThanOrEqual(
          g.frame.right,
        );
        // The root zoom (set per window width in tokens.css) scales the gap between the frame and the selected-article panel, BOARD_GAP_PX in plateSide.ts.
        const zoom = width > 3400 ? 1.75 : width >= 2400 ? 1.25 : 1;
        expect(
          g.boardTop - (g.frame.top + g.frame.h),
          "the board follows the frame",
        ).toBeLessThanOrEqual(8 * zoom + 1);
        expect(g.boardBottom, "the board ends above the caption").toBeLessThanOrEqual(
          g.captionTop + 0.5,
        );
        expect(g.frame.w, "frame is no wider than its column").toBeLessThanOrEqual(
          g.slot.right - g.slot.left + 1,
        );
        const gapLeft = g.frame.left - g.slot.left;
        const gapRight = g.slot.right - g.frame.right;
        expect(Math.abs(gapLeft - gapRight), "frame centred in its column").toBeLessThanOrEqual(2);
        expect(Math.abs(g.panelBottom - g.figureBottom), "column bottoms").toBeLessThanOrEqual(1);
        expect(
          g.captionTop - g.boardBottom,
          "no gap between the board and its caption",
        ).toBeLessThanOrEqual(12);
        expect(g.captionBottom, "the caption ends inside the column").toBeLessThanOrEqual(
          g.figureBottom + 0.5,
        );
        expect(
          g.slots,
          "ledger slots: three edit rows and the two fixed ones",
        ).toBeGreaterThanOrEqual(5);
      });
    }

    // From 3400px up the root zoom is 1.75 and --container-page is widened (tokens.css), which puts the
    // column at 60 percent of the screen. The frame is held to MAX_SIDE_SCREEN_PX (plateSide.ts) on
    // screen, so it reads at the same scale as the related-articles graph on a dossier page.
    test("Home at 3840x2160: zoom 1.75, a column 60 percent of the screen, the frame held to 1000px and centred in its column", async ({
      page,
      open,
    }) => {
      await openHome(page, open, 3840, 2160);
      const m = await page.evaluate(() => {
        const main = document.querySelector("main")!;
        const style = getComputedStyle(main);
        const frame = document.querySelector("[data-plate-frame]")!.getBoundingClientRect();
        const slot = document.querySelector("figure")!.parentElement!.getBoundingClientRect();
        const zoom = parseFloat(getComputedStyle(document.documentElement).zoom);
        const gutters = (parseFloat(style.paddingLeft) + parseFloat(style.paddingRight)) * zoom;
        return {
          zoom,
          share: (main.getBoundingClientRect().width - gutters) / innerWidth,
          side: frame.width,
          offCentre: Math.abs(frame.left + frame.width / 2 - (slot.left + slot.width / 2)),
        };
      });
      expect(m.zoom).toBe(1.75);
      expect(m.share).toBeGreaterThan(0.59);
      expect(m.share).toBeLessThan(0.61);
      expect(m.side).toBeLessThanOrEqual(1001);
      expect(m.side).toBeGreaterThan(950);
      expect(m.offCentre).toBeLessThanOrEqual(2);
    });
  });
});
