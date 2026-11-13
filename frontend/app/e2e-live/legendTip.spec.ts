import type { Page } from "@playwright/test";
import { eachTheme, expect, only, settleBox, test } from "../e2e/support";

// The swatch tooltip of the Home graph's legend covers nothing on the real graph, at any width.
// When no spot inside the frame is clear, it opens under the frame, with a hover bridge up to the chip.

const SIZES = [
  [844, 390],
  [1024, 768],
  [1280, 800],
  [1440, 1000],
  [1920, 1080],
  [3840, 2160],
  [390, 844],
] as const;

async function underTip(page: Page) {
  return page.evaluate(() => {
    const t = [...document.querySelectorAll('[role="tooltip"]')]
      .find(
        (e) => e.textContent?.includes("Articles related") && e.getBoundingClientRect().width > 0,
      )!
      .getBoundingClientRect();
    const hit = (r: DOMRect) =>
      Math.min(t.right, r.right) > Math.max(t.left, r.left) &&
      Math.min(t.bottom, r.bottom) > Math.max(t.top, r.top);
    const svg = document.querySelector('svg[role="group"][aria-label^="The"]')!;
    let n = [
      ...svg.querySelectorAll(
        "a > circle:not([data-plate-hit]):not([data-plate-hover-ring]), text[data-plate-label]",
      ),
    ].filter((e) => hit(e.getBoundingClientRect())).length;
    for (const p of svg.querySelectorAll<SVGPathElement>("path[data-plate-hull]")) {
      const m = p.getScreenCTM()!;
      for (let a = 0; a < p.getTotalLength(); a += 3) {
        const q = p.getPointAtLength(a);
        const x = m.a * q.x + m.c * q.y + m.e;
        const y = m.b * q.x + m.d * q.y + m.f;
        if (x >= t.left && x <= t.right && y >= t.top && y <= t.bottom) n += 1;
      }
    }
    const figure = [...document.querySelectorAll("figure")].find((f) =>
      f.textContent?.includes("Plate 1."),
    )!;
    const col = figure.getBoundingClientRect();
    const frame = figure.querySelector("[data-plate-frame]")!;
    const bridge = document.querySelector<HTMLElement>("[data-tip-bridge]");
    return {
      n,
      below: t.top >= frame.getBoundingClientRect().bottom,
      bridged: bridge != null && getComputedStyle(bridge).display === "block",
      inColumn: t.left >= col.left - 0.5 && t.right <= col.right + 0.5,
      aboveBoard: t.bottom <= frame.nextElementSibling!.getBoundingClientRect().bottom + 0.5,
      inView: t.top >= 0 && t.bottom <= innerHeight,
    };
  });
}

const MODES = [
  ...SIZES.map(([width, height]) => ({ width, height, mode: "mouse" })),
  { width: 844, height: 390, mode: "tap" },
  { width: 844, height: 390, mode: "coarse-hover" },
  { width: 390, height: 844, mode: "tap" },
  { width: 390, height: 844, mode: "coarse-hover" },
] as const;

// The viewport is set per test, so each runs once, on the desktop-1440 project.
test.use({ mocked: false, paused: true });

eachTheme((theme) => {
  for (const { width, height, mode } of MODES) {
    const touch = mode !== "mouse";
    const tap = mode === "tap";
    test.describe(`${width}x${height}, ${mode}`, only("desktop-1440"), () => {
      test.use({ viewport: { width, height }, hasTouch: touch, isMobile: touch });

      test(`the swatch tooltips cover nothing, stay in the column and in view, and keep open along the hover path (${theme})`, async ({
        page,
        open,
      }) => {
        // The tooltip closes 700 ms after the pointer leaves, so the clock stands in for that wait.
        await page.clock.install();
        await open("/", { ready: page.locator('svg[role="group"][aria-label^="The"] a').first() });
        const plate = page.locator("figure", { hasText: "Plate 1." });
        const buttons = plate.getByRole("group", { name: "Linked groups" }).getByRole("button");
        const tip = plate.getByRole("tooltip").filter({ hasText: "Articles related to" });
        const swatches = await buttons.count();
        expect(swatches).toBeGreaterThan(0);
        for (let i = 0; i < swatches; i += 1) {
          if (tap) {
            await page.touchscreen.tap(2, 2);
            await buttons.nth(i).scrollIntoViewIfNeeded();
            await buttons.nth(i).tap();
          } else {
            await page.mouse.move(5, 5);
            await buttons.nth(i).hover();
          }
          await expect(tip).toBeVisible();
          await settleBox(tip);
          const r = await underTip(page);
          expect(r.n, `swatch ${i}: things under the tip`).toBe(0);
          expect(r.inColumn, `swatch ${i}: inside the column`).toBe(true);
          expect(r.aboveBoard, `swatch ${i}: above the board's bottom`).toBe(true);
          expect(r.inView, `swatch ${i}: in the viewport`).toBe(true);
          // The bridge is only drawn for a tip under the frame.
          expect(!r.bridged || r.below, `swatch ${i}: a bridged tip sits under the frame`).toBe(
            true,
          );
          if (!tap) {
            // Swatch to tip in 3 steps, then wait out the close delay: it stays.
            const from = (await buttons.nth(i).boundingBox())!;
            const to = (await tip.boundingBox())!;
            await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
            await page.mouse.move(to.x + 12, to.y + to.height / 2, { steps: 3 });
            await page.clock.runFor(900);
            await expect(tip).toBeVisible();
            await page.mouse.move(5, 5);
            await page.clock.runFor(900);
            await expect(tip).toBeHidden();
          }
        }
      });
    });
  }
});
