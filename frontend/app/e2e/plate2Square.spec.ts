import type { Locator, Page } from "@playwright/test";
import { RELATED_GRAPH } from "./plateLocators";
import { eachTheme, expect, only, settle, test } from "./support";

// The related-articles graph on a dossier page is a square frame at every width, as large as its column allows.
// A long name breaks onto two lines before it is cut.
// Every label has an outline in the page's background colour (--wke-sheet), and none touches another dot.

async function openGraph(
  page: Page,
  open: (
    path: string,
    options: { viewport: { width: number; height: number }; ready: Locator },
  ) => Promise<void>,
  width: number,
  height: number,
) {
  await open("/t/Lizzie_Borden", {
    viewport: { width, height },
    ready: page.locator(`${RELATED_GRAPH} a`).first(),
  });
  await expect(page.locator(RELATED_GRAPH)).toHaveCSS("opacity", "1");
  await page.locator(RELATED_GRAPH).scrollIntoViewIfNeeded();
}

test.describe("related-articles graph", only("desktop-1440"), () => {
  eachTheme((theme) => {
    for (const [width, height, minSide] of [
      [1440, 900, 340],
      [1920, 1080, 340],
      [3840, 2160, 500],
      [1024, 768, 270],
      [390, 844, 300],
    ] as const) {
      test(`at ${width}: a square frame at least ${minSide}px wide, outlined labels clear of every other dot, whole names when they fit`, async ({
        page,
        open,
      }) => {
        await openGraph(page, open, width, height);
        const g = await page.evaluate((sel) => {
          const svg = document.querySelector(sel)!;
          const frame = svg
            .closest("figure")!
            .querySelector("[data-plate-frame]")!
            .getBoundingClientRect();
          const box = svg.getBoundingClientRect();
          const dots = [...svg.querySelectorAll("a")].map((a) => {
            const circle = a
              .querySelector("circle:not([data-plate-hit]):not([data-plate-hover-ring])")!
              .getBoundingClientRect();
            const label = a.querySelector("text[data-plate-label]");
            const tspans = label ? [...label.querySelectorAll("tspan")] : [];
            const cs = label ? getComputedStyle(label) : null;
            const r = label?.getBoundingClientRect();
            return {
              title: (a.getAttribute("aria-label") ?? "").split(",")[0]!,
              cx: circle.left + circle.width / 2,
              cy: circle.top + circle.height / 2,
              radius: circle.width / 2,
              // A two-line name is one tspan per line, both at one x.
              text: tspans.length > 0 ? tspans.map((t) => t.textContent).join(" ") : null,
              lines: tspans.map((t) => t.textContent ?? ""),
              lineX: tspans.map((t) => t.getAttribute("x")),
              lineDy: tspans.map((t) => t.getAttribute("dy")),
              box: r ? { l: r.left, t: r.top, r: r.right, b: r.bottom } : null,
              paintOrder: cs?.paintOrder ?? "",
              strokeWidth: cs?.strokeWidth ?? "",
              stroke: cs?.stroke ?? "",
              join: cs?.strokeLinejoin ?? "",
            };
          });
          const probe = document.createElement("span");
          probe.style.color = "var(--wke-sheet)";
          document.body.append(probe);
          const sheet = getComputedStyle(probe).color;
          probe.remove();
          return {
            sheet,
            frame: { w: frame.width, h: frame.height },
            svg: {
              w: box.width,
              h: box.height,
              l: box.left,
              t: box.top,
              r: box.right,
              b: box.bottom,
            },
            dots,
          };
        }, RELATED_GRAPH);
        expect(
          Math.abs(g.frame.w - g.frame.h),
          `frame ${g.frame.w} x ${g.frame.h}`,
        ).toBeLessThanOrEqual(1);
        expect(Math.abs(g.svg.w - g.svg.h), `graph ${g.svg.w} x ${g.svg.h}`).toBeLessThanOrEqual(1);
        expect(g.frame.w, "the frame is as large as its column allows").toBeGreaterThanOrEqual(
          minSide,
        );
        expect(g.dots.length).toBeGreaterThanOrEqual(6);

        for (const d of g.dots) {
          expect(d.text, `${d.title} is named`).not.toBeNull();
          const b = d.box!;
          // The outline is in the page background colour and drawn before the text, so a line behind the label does not cut through it.
          expect(d.paintOrder).toContain("stroke");
          expect(d.stroke, `${d.title} outline matches the ${theme} background`).toBe(g.sheet);
          expect(d.join).toBe("round");
          expect(Number.parseFloat(d.strokeWidth)).toBeGreaterThanOrEqual(3);
          expect(b.l, `${d.title} inside the left edge`).toBeGreaterThanOrEqual(g.svg.l - 0.5);
          expect(b.r, `${d.title} inside the right edge`).toBeLessThanOrEqual(g.svg.r + 0.5);
          expect(b.t).toBeGreaterThanOrEqual(g.svg.t - 0.5);
          expect(b.b).toBeLessThanOrEqual(g.svg.b + 0.5);
          for (const other of g.dots) {
            if (other === d) {
              continue;
            }
            if (other.box) {
              const o = other.box;
              expect(
                b.l < o.r && b.r > o.l && b.t < o.b && b.b > o.t,
                `"${d.text}" overlaps "${other.text}"`,
              ).toBe(false);
            }
            const nx = Math.max(b.l, Math.min(other.cx, b.r));
            const ny = Math.max(b.t, Math.min(other.cy, b.b));
            const gap = Math.hypot(other.cx - nx, other.cy - ny) - other.radius;
            expect(gap, `"${d.text}" label touches the dot of ${other.title}`).toBeGreaterThan(0);
          }
        }

        // A cut is a last resort, so a name of 22 characters or fewer is shown whole and a cut name keeps 18 characters.
        // Neither holds at 1024px, where the narrow frame makes the layout cut names short to fit.
        const cut = g.dots.filter((d) => d.text!.endsWith("..."));
        for (const d of g.dots.filter((x) => x.title.length <= 22 && width !== 1024)) {
          expect(d.text, `${d.title} fits and is shown whole`).toBe(d.title);
        }
        if (width >= 1440) {
          // At 1440px and wider every name fits whole, on one line or two, so none is cut.
          expect(cut.length, `cut names: ${cut.map((d) => d.text).join(", ")}`).toBe(0);
        }
        const twoLine = g.dots.filter((d) => d.lines.length === 2);
        if (width >= 1280) {
          expect(
            twoLine.length,
            "the 46-character Oak Grove Cemetery name is on two lines",
          ).toBeGreaterThanOrEqual(1);
        }
        for (const d of twoLine) {
          expect(
            d.lines.every((line) => line.length <= 26 && line.length > 0),
            `"${d.text}" lines are at most 26 characters`,
          ).toBe(true);
          expect(d.lineX[0], `"${d.text}" lines share one x`).toBe(d.lineX[1]);
          expect(d.lineDy[1], `"${d.text}" line height`).toBe("14");
          expect(d.box!.b - d.box!.t, `"${d.text}" is two lines tall`).toBeGreaterThan(24);
        }
        for (const d of cut.filter(() => width !== 1024)) {
          expect(
            d.text!.slice(0, -3).trimEnd().length,
            `"${d.text}" keeps 18 characters ahead of its ellipsis`,
          ).toBeGreaterThanOrEqual(18);
        }
        // A cut name must not be the start of another dot's name, because it would then read as that dot's name.
        for (const d of cut) {
          const kept = d.text!.slice(0, -3).trimEnd();
          expect(
            g.dots.some((o) => o !== d && o.title.startsWith(kept)),
            `"${d.text}" reads as the name of another dot`,
          ).toBe(false);
        }
      });
    }
  });

  // A label that a line crosses needs an outline of at least 4px, drawn before its text, and the label must come after every line in the SVG. Then the outline hides the line.
  eachTheme(() => {
    for (const [width, height] of [
      [1440, 900],
      [390, 844],
    ] as const) {
      test(`at ${width}: a line under a name is covered by its outline`, async ({ page, open }) => {
        await openGraph(page, open, width, height);
        const m = await page.evaluate((sel) => {
          const svg = document.querySelector(sel)!;
          const lines = [...svg.querySelectorAll("line:not([data-plate-leader])")];
          const segments = lines.map(
            (l) =>
              [
                Number(l.getAttribute("x1")),
                Number(l.getAttribute("y1")),
                Number(l.getAttribute("x2")),
                Number(l.getAttribute("y2")),
              ] as const,
          );
          // oxlint-disable-next-line unicorn/consistent-function-scoping -- the callback runs in the page, so its helpers cannot live outside it
          const hits = (
            s: readonly [number, number, number, number],
            r: { x: number; y: number; w: number; h: number },
          ) => {
            const [x1, y1, x2, y2] = s;
            let t0 = 0;
            let t1 = 1;
            const dx = x2 - x1;
            const dy = y2 - y1;
            for (const [p, q] of [
              [-dx, x1 - r.x],
              [dx, r.x + r.w - x1],
              [-dy, y1 - r.y],
              [dy, r.y + r.h - y1],
            ] as const) {
              if (p === 0) {
                if (q < 0) return false;
              } else {
                const t = q / p;
                if (p < 0) {
                  if (t > t1) return false;
                  t0 = Math.max(t0, t);
                } else {
                  if (t < t0) return false;
                  t1 = Math.min(t1, t);
                }
              }
            }
            return true;
          };
          return [...svg.querySelectorAll<SVGTextElement>("text[data-plate-label]")].map((t) => {
            const bb = t.getBBox();
            const box = { x: bb.x, y: bb.y + 2, w: bb.width, h: bb.height - 4 };
            const cs = getComputedStyle(t);
            return {
              text: t.querySelector("tspan")?.textContent ?? "",
              crossed: segments.filter((s) => hits(s, box)).length,
              strokeWidth: Number.parseFloat(cs.strokeWidth),
              paintOrder: cs.paintOrder,
              afterEveryLine: lines.every((l) =>
                Boolean(l.compareDocumentPosition(t) & Node.DOCUMENT_POSITION_FOLLOWING),
              ),
            };
          });
        }, RELATED_GRAPH);
        expect(m.length).toBeGreaterThan(5);
        for (const label of m) {
          if (label.crossed > 0) {
            expect(
              label.strokeWidth,
              `${label.text} crossed by ${label.crossed} lines`,
            ).toBeGreaterThanOrEqual(4);
            expect(label.paintOrder, label.text).toContain("stroke");
            expect(label.afterEveryLine, `${label.text} is drawn after the lines`).toBe(true);
          }
        }
      });
    }
  });

  for (const width of [1024, 1440]) {
    test(`at ${width}: labels render at 12px after the viewBox scaling`, async ({ page, open }) => {
      await openGraph(page, open, width, 900);
      const rendered = await settle(page, () =>
        page.evaluate((sel) => {
          const svg = document.querySelector(sel)!;
          const scale =
            svg.getBoundingClientRect().width / Number(svg.getAttribute("viewBox")!.split(" ")[2]);
          return [...svg.querySelectorAll("text")].map(
            (t) => parseFloat(getComputedStyle(t).fontSize) * scale,
          );
        }, RELATED_GRAPH),
      );
      expect(rendered.length).toBeGreaterThan(0);
      for (const px of rendered) {
        expect(px).toBeGreaterThanOrEqual(11.95);
      }
    });
  }

  eachTheme(() => {
    for (const [width, height] of [
      [1024, 768],
      [1440, 900],
      [1920, 1080],
    ] as const) {
      test(`at ${width}: every label keeps 6px from the frame rule`, async ({ page, open }) => {
        await openGraph(page, open, width, height);
        // The labels are placed after the fonts load, so read until two reads agree.
        const gaps = await settle(page, () =>
          page.evaluate((sel) => {
            const svg = document.querySelector(sel)!;
            const f = svg.getBoundingClientRect();
            return [...svg.querySelectorAll("text[data-plate-label]")].map((t) => {
              const b = t.getBoundingClientRect();
              return {
                text: t.textContent ?? "",
                gap: Math.min(
                  b.left - f.left,
                  b.top - f.top,
                  f.right - b.right,
                  f.bottom - b.bottom,
                ),
              };
            });
          }, RELATED_GRAPH),
        );
        expect(gaps.length).toBeGreaterThan(5);
        for (const l of gaps) {
          expect(l.gap, `${l.text} is ${l.gap.toFixed(1)}px from the frame`).toBeGreaterThanOrEqual(
            6,
          );
        }
      });
    }
  });
});
