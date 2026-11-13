import type { Page } from "@playwright/test";
import { eachTheme, expect, only, settleLayout, test } from "./support";

// At 1024px and at 1440px the Home graph must keep group outlines whole inside the frame,
// show at least 10 names, and put a dot in every horizontal band.

const BANDS = 8;
const STROKE_PX = 1;
const DOTS = "svg[role='group'] a > circle:first-of-type";

/** Waits until the graph has been re-fitted to its column, which happens after it first renders at a default side. */
async function waitForFittedGraph(page: Page) {
  await page.waitForFunction(() => {
    const box = document.querySelector("svg[role='group']")?.getAttribute("viewBox");
    return box != null && Number(box.split(" ")[2]) <= window.innerWidth;
  });
  await settleLayout(page);
}

/** The most dots whose y values lie within 2px of one another. */
function widest(ys: number[]) {
  const sorted = ys.toSorted((a, b) => a - b);
  let best = 0;
  for (let i = 0; i < sorted.length; i++) {
    let j = i;
    while (j + 1 < sorted.length && (sorted[j + 1] ?? 0) - (sorted[i] ?? 0) <= 2) j++;
    best = Math.max(best, j - i + 1);
  }
  return best;
}

/** A cut name without its ellipsis. */
function stub(name: { text: string }) {
  return name.text.slice(0, -3).trimEnd();
}

// Every test here sets its own viewport, so it runs only on the desktop-1440 project.
test.describe("Home graph at several widths", only("desktop-1440"), () => {
  eachTheme(() => {
    for (const width of [1024, 1440, 1920]) {
      test(`Home graph at ${width}: hulls inside the frame, at least the 10 most-read named, all ${BANDS} bands`, async ({
        page,
        open,
      }) => {
        await open("/", {
          viewport: { width, height: width === 1024 ? 768 : 1000 },
          ready: page.locator(DOTS).first(),
        });
        const m = await page.evaluate(() => {
          const svg = document.querySelector("svg[role='group']")!;
          const f = svg.getBoundingClientRect();
          const scale = f.width / Number(svg.getAttribute("viewBox")!.split(" ")[2]);
          return {
            frame: { x: f.left, y: f.top, r: f.right, b: f.bottom, h: f.height },
            scale,
            hulls: [...svg.querySelectorAll("path")]
              .map((p) => p.getBoundingClientRect())
              .filter((b) => b.width > 20)
              .map((b) => ({ x: b.left, y: b.top, r: b.right, b: b.bottom })),
            labels: svg.querySelectorAll("a > text").length,
            centres: [...svg.querySelectorAll("a > circle:first-of-type")].map((c) => {
              const b = c.getBoundingClientRect();
              return b.top + b.height / 2 - f.top;
            }),
          };
        });

        const stroke = (STROKE_PX / 2) * m.scale;
        for (const h of m.hulls) {
          expect(h.x - stroke, "hull left edge").toBeGreaterThanOrEqual(m.frame.x - 0.5);
          expect(h.y - stroke, "hull top edge").toBeGreaterThanOrEqual(m.frame.y - 0.5);
          expect(h.r + stroke, "hull right edge").toBeLessThanOrEqual(m.frame.r + 0.5);
          expect(h.b + stroke, "hull bottom edge").toBeLessThanOrEqual(m.frame.b + 0.5);
        }
        expect(m.labels).toBeGreaterThanOrEqual(10);
        const counts = Array.from({ length: BANDS }, () => 0);
        for (const y of m.centres) {
          const band = Math.min(BANDS - 1, Math.max(0, Math.floor((y / m.frame.h) * BANDS)));
          counts[band] = (counts[band] ?? 0) + 1;
        }
        expect(m.centres.length).toBe(40);
        expect(
          counts.every((n) => n > 0),
          `bands ${counts.join(",")}`,
        ).toBe(true);
      });
    }

    for (const [width, height] of [
      [390, 844],
      [1024, 768],
      [1440, 1000],
      [1920, 1080],
    ] as const) {
      test(`Home graph at ${width}: every dot keeps 12px from the frame`, async ({
        page,
        open,
      }) => {
        await open("/", { viewport: { width, height }, ready: page.locator(DOTS).first() });
        const inset = await page.evaluate(() => {
          const svg = document.querySelector("svg[role='group']")!;
          const f = svg.getBoundingClientRect();
          return Math.min(
            ...[...svg.querySelectorAll("a > circle:first-of-type")].map((c) => {
              const b = c.getBoundingClientRect();
              return Math.min(
                b.left - f.left,
                b.top - f.top,
                f.right - b.right,
                f.bottom - b.bottom,
              );
            }),
          );
        });
        expect(inset).toBeGreaterThanOrEqual(12);
      });
    }

    // No row of three dots may sit along the top or bottom edge. Below 1280px the layout skips any cut that leaves
    // fewer than 18 characters before the ellipsis, because a very short cut name tells the reader nothing. A cut name must not be the prefix
    // of another shown name.
    for (const [width, height] of [
      [390, 844],
      [1024, 768],
      [1440, 1000],
      [1920, 1080],
    ] as const) {
      test(`Home graph at ${width}: no row of 3 dots along an edge, no cut name shorter than ${width < 1280 ? 18 : 8} characters, no name that is the prefix of another`, async ({
        page,
        open,
      }) => {
        await open("/", { viewport: { width, height }, ready: page.locator(DOTS).first() });
        await waitForFittedGraph(page);
        const m = await page.evaluate(() => {
          const svg = document.querySelector("svg[role='group']")!;
          const vb = svg.getAttribute("viewBox")!.split(" ").map(Number);
          const dots = [...svg.querySelectorAll("a > circle:first-of-type")].map((c) => ({
            cy: Number(c.getAttribute("cy")),
            r: Number(c.getAttribute("r")),
          }));
          const names = [...svg.querySelectorAll("a")].flatMap((a) => {
            const text = a.querySelector("text[data-plate-label] > tspan")?.textContent;
            return text == null
              ? []
              : [
                  {
                    text,
                    title:
                      (a.getAttribute("aria-label") ?? "").split(
                        /, (?:[\d,]+ views|similarity )/,
                      )[0] ?? "",
                  },
                ];
          });
          return { height: vb[3] ?? 0, dots, names };
        });
        // Dots whose centre, top edge or bottom edge sit within 2px of one y, in the 40px band along an edge.
        const top = m.dots.filter((d) => d.cy - d.r < 40);
        const bottom = m.dots.filter((d) => m.height - d.cy - d.r < 40);
        expect(widest(top.map((d) => d.cy)), "centres along the top edge").toBeLessThan(3);
        expect(widest(top.map((d) => d.cy - d.r)), "top edges along the top edge").toBeLessThan(3);
        expect(widest(bottom.map((d) => d.cy)), "centres along the bottom edge").toBeLessThan(3);
        expect(
          widest(bottom.map((d) => d.cy + d.r)),
          "bottom edges along the bottom edge",
        ).toBeLessThan(3);
        const cut = m.names.filter((n) => n.text.endsWith("..."));
        for (const n of cut) {
          expect(stub(n).length, `"${n.text}"`).toBeGreaterThanOrEqual(width < 1280 ? 18 : 8);
          const twin = m.names.find((o) => o.title !== n.title && o.title.startsWith(stub(n)));
          expect(twin, `"${n.text}" is the prefix of "${twin?.title}"`).toBeUndefined();
        }
      });
    }

    for (const [width, height] of [
      [390, 844],
      [1024, 768],
      [1440, 1000],
      [1920, 1080],
      [3840, 2160],
    ] as const) {
      test(`Home graph at ${width}: every label keeps 6px from the frame rule`, async ({
        page,
        open,
      }) => {
        await open("/", { viewport: { width, height }, ready: page.locator(DOTS).first() });
        const m = await page.evaluate(() => {
          const svg = document.querySelector("svg[role='group']")!;
          const f = svg.getBoundingClientRect();
          const gaps = [...svg.querySelectorAll("text[data-plate-label]")].map((t) => {
            const b = t.getBoundingClientRect();
            return {
              text: t.textContent ?? "",
              gap: Math.min(b.left - f.left, b.top - f.top, f.right - b.right, f.bottom - b.bottom),
            };
          });
          return gaps;
        });
        expect(m.length).toBeGreaterThanOrEqual(10);
        for (const l of m) {
          expect(l.gap, `${l.text} is ${l.gap.toFixed(1)}px from the frame`).toBeGreaterThanOrEqual(
            6,
          );
        }
      });
    }

    for (const coarse of [false, true]) {
      test.describe(coarse ? "coarse pointer" : "fine pointer", () => {
        test.use(coarse ? { hasTouch: true, isMobile: true } : {});
        for (const [width, height] of [
          [360, 780],
          [390, 844],
          [430, 932],
          [844, 390],
        ] as const) {
          test(`Home graph at ${width}x${height}: dots keep radii plus 2px apart and no label lies on a dot`, async ({
            page,
            open,
          }) => {
            await open("/", { viewport: { width, height }, ready: page.locator(DOTS).first() });
            await waitForFittedGraph(page);
            const m = await page.evaluate(() => {
              const svg = document.querySelector("svg[role='group']")!;
              const anchors = [...svg.querySelectorAll("a")];
              const dots = anchors.map((a) => {
                const c = a.querySelector("circle:first-of-type")!.getBoundingClientRect();
                return {
                  x: c.left + c.width / 2,
                  y: c.top + c.height / 2,
                  r: c.width / 2,
                  name: a.getAttribute("aria-label") ?? "",
                };
              });
              const scale =
                svg.getBoundingClientRect().width /
                Number(svg.getAttribute("viewBox")!.split(" ")[2]);
              const labels = anchors.flatMap((a, own) => {
                const t = a.querySelector("text[data-plate-label]");
                if (!t) return [];
                const b = t.getBoundingClientRect();
                return [
                  { own, text: t.textContent ?? "", l: b.left, t: b.top, r: b.right, b: b.bottom },
                ];
              });
              return { dots, labels, scale };
            });
            const close: string[] = [];
            for (let i = 0; i < m.dots.length; i++) {
              for (let j = i + 1; j < m.dots.length; j++) {
                const a = m.dots[i]!;
                const b = m.dots[j]!;
                const gap = Math.hypot(a.x - b.x, a.y - b.y) - (a.r + b.r) - 2 * m.scale;
                if (gap < -0.25)
                  close.push(`${a.name.slice(0, 20)} / ${b.name.slice(0, 20)} ${gap.toFixed(1)}`);
              }
            }
            const onDot: string[] = [];
            for (const l of m.labels) {
              m.dots.forEach((d, k) => {
                if (k === l.own) return;
                const nx = Math.min(Math.max(d.x, l.l), l.r);
                const ny = Math.min(Math.max(d.y, l.t), l.b);
                if (Math.hypot(d.x - nx, d.y - ny) < d.r)
                  onDot.push(`${l.text} on ${d.name.slice(0, 20)}`);
              });
            }
            expect(close, "dot pairs closer than radii plus 2px").toEqual([]);
            expect(onDot, "labels on a dot").toEqual([]);
          });
        }
      });
    }
  });
});
