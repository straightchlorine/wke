import { chromium, type Page } from "@playwright/test";
import { test, expect, only, settleBox, settleLayout, THEMES, type Theme } from "./support";
import { mockApi } from "./mockApi";

/**
 * Screen sizes, each with the device pixel ratio the browser is launched with
 * and the root zoom the page applies at that width. Each runs in a browser
 * launched with a real device scale factor, because context-level emulation
 * lays out in CSS pixels and cannot show the rounding a real screen applies.
 */
const SCREENS: Array<{ width: number; height: number; dppx: number; zoom: number }> = [
  { width: 2560, height: 1440, dppx: 1.5, zoom: 1.25 },
  { width: 3840, height: 2160, dppx: 1, zoom: 1.75 },
  { width: 1920, height: 1080, dppx: 2, zoom: 1 },
];

type Rows = { run: number; before: "flat" | "blend"; after: "flat" | "blend" };

/**
 * Counts the device-pixel rows an element's border paints on one side, from a screenshot strip across the edge.
 * The run is the first unbroken stretch of rows whose channels are each within 1 of the border colour.
 * The two rows just outside the run are reported as flat when they match each other, and as blend otherwise.
 */
async function ruleRows(page: Page, selector: string, side: "top" | "bottom"): Promise<Rows> {
  const box = (await page.locator(selector).first().boundingBox())!;
  const edge = side === "top" ? box.y : box.y + box.height;
  const x = box.x + Math.min(box.width / 2, 400);
  const above = 6;
  const below = 4;
  const shot = await page.screenshot({
    clip: { x, y: Math.max(edge - above, 0), width: 2, height: above + below },
    scale: "device",
  });
  const color = await page
    .locator(selector)
    .first()
    .evaluate(
      (el, which) => getComputedStyle(el)[which === "top" ? "borderTopColor" : "borderBottomColor"],
      side,
    );
  return page.evaluate(
    async ([b64, wanted]) => {
      const img = new Image();
      img.src = `data:image/png;base64,${b64}`;
      await img.decode();
      const canvas = document.createElement("canvas");
      canvas.width = img.width;
      canvas.height = img.height;
      const ctx = canvas.getContext("2d")!;
      ctx.drawImage(img, 0, 0);
      const px = (y: number) => Array.from(ctx.getImageData(0, y, 1, 1).data.slice(0, 3));
      const tolerance = 1;
      const same = (a: number[], c: number[]) =>
        a.every((v, i) => Math.abs(v - c[i]!) <= tolerance);
      ctx.fillStyle = wanted!;
      ctx.clearRect(0, 0, 1, 1);
      ctx.fillRect(0, 0, 1, 1);
      const rule = Array.from(ctx.getImageData(0, 0, 1, 1).data.slice(0, 3));
      ctx.clearRect(0, 0, 1, 1);
      ctx.drawImage(img, 0, 0);
      const rows = Array.from({ length: img.height }, (_unused, y) => px(y));
      const first = rows.findIndex((c) => same(c, rule));
      if (first < 0) return { run: 0, before: "blend", after: "blend" };
      let end = first;
      while (end + 1 < rows.length && same(rows[end + 1]!, rule)) end += 1;
      const flat = (i: number, j: number) =>
        rows[i] && rows[j] && same(rows[i], rows[j]) ? "flat" : "blend";
      return {
        run: end - first + 1,
        before: flat(first - 1, first - 2),
        after: flat(end + 1, end + 2),
      } as const;
    },
    [shot.toString("base64"), color] as const,
  );
}

type Screen = (typeof SCREENS)[number];

/** Runs the callback on a page of a browser launched at the screen's device pixel ratio, with the API mocked. */
async function withScreen(
  screen: Screen,
  theme: Theme,
  baseURL: string | undefined,
  run: (page: Page) => Promise<void>,
): Promise<void> {
  const browser = await chromium.launch({
    args: [
      `--force-device-scale-factor=${screen.dppx}`,
      `--window-size=${screen.width},${screen.height}`,
    ],
  });
  try {
    const context = await browser.newContext({
      viewport: null,
      deviceScaleFactor: undefined,
      baseURL,
    });
    const page = await context.newPage();
    await page.addInitScript((t) => window.localStorage.setItem("wke-theme", t), theme);
    await mockApi(page);
    await run(page);
  } finally {
    await browser.close();
  }
}

// These tests launch their own browsers, so one run is enough.
test.describe(
  "hairlines land on whole device pixels at the scaled screens",
  only("desktop-1440"),
  () => {
    for (const screen of SCREENS) {
      const { width, height, dppx, zoom } = screen;
      for (const theme of THEMES) {
        test(`${width}x${height} at ${dppx} dppx (${theme})`, async ({ baseURL }) => {
          await withScreen(screen, theme, baseURL, async (page) => {
            const rules: Record<string, number> = {};
            for (const path of ["/", "/t/"]) {
              await page.goto(path);
              await expect(page.locator("header")).toBeVisible();
              expect(await page.evaluate(() => window.devicePixelRatio)).toBe(dppx);
              const found = await page.evaluate(() => {
                const rootZoom = parseFloat(getComputedStyle(document.documentElement).zoom) || 1;
                const frame = document.querySelector("[data-plate-frame]");
                const targets: Array<[string, Element | null, "Top" | "Bottom"]> = [
                  ["header", document.querySelector("header"), "Bottom"],
                  ["graph frame", frame, "Top"],
                  ["graph inner frame", frame?.firstElementChild ?? null, "Top"],
                  ["record", document.querySelector("[data-record]"), "Top"],
                  ["table", document.querySelector("table"), "Top"],
                  ["table row", document.querySelector("tbody tr"), "Bottom"],
                ];
                const out: Array<{ name: string; product: number }> = [];
                for (const [name, el, side] of targets) {
                  if (!el) continue;
                  const borderWidth = parseFloat(getComputedStyle(el)[`border${side}Width`]);
                  if (borderWidth === 0) continue;
                  out.push({ name, product: borderWidth * rootZoom * window.devicePixelRatio });
                }
                return { rootZoom, out };
              });
              expect(found.rootZoom).toBe(zoom);
              for (const { name, product } of found.out) {
                rules[`${path} ${name}`] = product;
                expect(
                  Math.abs(product - Math.round(product)),
                  `${path} ${name}: ${product} device px`,
                ).toBeLessThan(0.01);
                expect(
                  Math.round(product),
                  `${path} ${name} is at least one device pixel`,
                ).toBeGreaterThanOrEqual(1);
              }
            }
            expect(Object.keys(rules).length).toBeGreaterThanOrEqual(5);
          });
        });
      }
    }

    for (const screen of SCREENS) {
      const { width, height, dppx, zoom } = screen;
      for (const theme of THEMES) {
        test(`painted rule rows: header and graph frame at ${width}x${height} at ${dppx} dppx (${theme})`, async ({
          baseURL,
        }) => {
          await withScreen(screen, theme, baseURL, async (page) => {
            await page.goto("/");
            const frame = page.locator("[data-plate-frame]");
            await expect(frame).toBeVisible();
            await settleLayout(page);
            await settleBox(frame);
            expect(await page.evaluate(() => window.devicePixelRatio)).toBe(dppx);
            expect(
              parseFloat(
                await page.evaluate(() => getComputedStyle(document.documentElement).zoom),
              ),
            ).toBe(zoom);
            for (const [name, selector, side] of [
              ["header bottom", "header", "bottom"],
              ["graph frame top", "[data-plate-frame]", "top"],
            ] as const) {
              const rows = await ruleRows(page, selector, side);
              expect(rows, `${name} at ${width}x${height} @${dppx}`).toEqual({
                run: 2,
                before: "flat",
                after: "flat",
              });
            }
          });
        });
      }
    }
  },
);
