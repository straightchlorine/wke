import type { Locator, Page } from "@playwright/test";
import { test, expect, eachTheme, only, settleLayout } from "./support";

const PAGES = [
  { path: "/", ready: "Cited context" },
  { path: "/t", ready: "Dossiers" },
  { path: "/t/Lizzie_Borden", ready: "Lizzie Borden" },
] as const;

const DOTS = "button[aria-describedby]:not([data-info-text])";

/** Opens a path and waits for its first heading to contain the text, then for the page's info dots. */
async function openPage(
  page: Page,
  open: (path: string, options?: { ready?: Locator }) => Promise<void>,
  path: string,
  ready: string,
): Promise<void> {
  await open(path, {
    ready: page.getByRole("heading", { level: 1 }).filter({ hasText: ready }).first(),
  });
  if (path !== "/machines") {
    await expect(page.locator(DOTS).first()).toBeAttached();
  }
}

/**
 * Offset of each visible dot's centre from the x-height centre of the text before it, and the gap.
 * A dot inside a closed details element is skipped: its box is laid out but not shown.
 */
async function dotOffsets(page: Page) {
  return page.evaluate((dots) => {
    const canvas = document.createElement("canvas").getContext("2d")!;
    const zoom = Number.parseFloat(getComputedStyle(document.documentElement).zoom) || 1;
    const out: { label: string; dy: number; gap: number }[] = [];
    for (const btn of document.querySelectorAll<HTMLButtonElement>(dots)) {
      const box = btn.getBoundingClientRect();
      const wrapper = btn.parentElement;
      if (
        box.width === 0 ||
        !wrapper?.parentElement ||
        btn.closest("details:not([open]) > :not(summary)")
      ) {
        continue;
      }
      // Under 900px the toolbar keeps the dot and drops its "Token budget" text.
      // Its meter label may truncate when the column narrows, so the last glyph is not the visible edge.
      if (btn.closest("[data-dossier-toolbar]") && (window.innerWidth < 900 || zoom > 1)) {
        continue;
      }
      // The last visible text before the dot, in document order.
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      walker.currentNode = wrapper;
      let text: Text | null = null;
      for (let node = walker.previousNode(); node; node = walker.previousNode()) {
        if (
          node instanceof Text &&
          node.data.trim() !== "" &&
          node.parentElement?.checkVisibility() &&
          !wrapper.contains(node)
        ) {
          text = node;
          break;
        }
      }
      if (!text || !text.parentElement) {
        continue;
      }
      const range = document.createRange();
      const length = (text.textContent ?? "").replace(/\s+$/, "").length;
      range.setStart(text, length - 1);
      range.setEnd(text, length);
      const glyph = range.getBoundingClientRect();
      const host = getComputedStyle(text.parentElement);
      canvas.font = `${host.fontStyle} ${host.fontWeight} ${host.fontSize} ${host.fontFamily}`;
      const metrics = canvas.measureText("x");
      const baseline = glyph.top + metrics.fontBoundingBoxAscent * zoom;
      // A chip or other framed sibling ends at its own edge, not at its text.
      let top: HTMLElement = text.parentElement;
      while (top.parentElement && !top.parentElement.contains(wrapper)) {
        top = top.parentElement;
      }
      const edge =
        getComputedStyle(top).borderRightWidth !== "0px"
          ? top.getBoundingClientRect().right
          : glyph.right;
      out.push({
        label: btn.getAttribute("aria-label") ?? "",
        dy: box.top + box.height / 2 - (baseline - (metrics.actualBoundingBoxAscent * zoom) / 2),
        gap: (box.left - edge) / zoom,
      });
    }
    return out;
  }, DOTS);
}

eachTheme(() => {
  for (const { path, ready } of PAGES) {
    test(`tooltips wrap inside the viewport and the column, ${path}`, async ({ page, open }) => {
      await openPage(page, open, path, ready);
      const labels = await page.evaluate((dots) => {
        // A per-section dot ends its label with ": <section label>"; one dot per kind is enough.
        const seen = new Map<string, string>();
        for (const btn of document.querySelectorAll<HTMLButtonElement>(dots)) {
          if (
            btn.getBoundingClientRect().width > 0 &&
            !btn.closest("details:not([open]) > :not(summary)")
          ) {
            const label = btn.getAttribute("aria-label") ?? "";
            const kind = label.split(": ", 1)[0] ?? label;
            if (!seen.has(kind)) {
              seen.set(kind, label);
            }
          }
        }
        return [...seen.values()];
      }, DOTS);
      expect(labels.length).toBeGreaterThan(0);
      const viewport = page.viewportSize()!;
      for (const label of labels) {
        const dot = page
          .locator(`button[aria-label="${label.replace(/"/g, '\\"')}"]:visible`)
          .first();
        await dot.evaluate((el) => el.scrollIntoView({ block: "center" }));
        const at = (await dot.boundingBox())!;
        await page.mouse.move(0, 0);
        await page.mouse.move(at.x + at.width / 2, at.y + at.height / 2);
        const tip = page.locator("[role=tooltip]").filter({ visible: true });
        await expect(tip).toHaveCount(1);
        const report = await tip.evaluate((el, btnLabel) => {
          const box = el.getBoundingClientRect();
          const main = el.closest("main")?.getBoundingClientRect() ?? {
            left: 0,
            right: window.innerWidth,
          };
          const dotBox = [
            ...document.querySelectorAll(`button[aria-label="${btnLabel.replace(/"/g, '\\"')}"]`),
          ]
            .find((b) => b.getBoundingClientRect().width > 0)!
            .getBoundingClientRect();
          const style = getComputedStyle(el);
          const probe = document.createElement("i");
          const resolve = (prop: "color" | "backgroundColor" | "borderTopColor", token: string) => {
            probe.style.cssText = `color:var(${token});background:var(${token});border:1px solid var(${token})`;
            document.body.append(probe);
            const value = getComputedStyle(probe)[prop];
            probe.remove();
            return value;
          };
          const gapAbove = dotBox.top - box.bottom;
          const gapBelow = box.top - dotBox.bottom;
          return {
            whiteSpace: style.whiteSpace,
            fontStyle: style.fontStyle,
            fontSize: style.fontSize,
            scrollWidth: el.scrollWidth,
            clientWidth: el.clientWidth,
            left: box.left,
            right: box.right,
            top: box.top,
            bottom: box.bottom,
            width: box.width,
            mainLeft: main.left,
            mainRight: main.right,
            gap: Math.min(Math.abs(gapAbove), Math.abs(gapBelow)),
            bg: [style.backgroundColor, resolve("backgroundColor", "--wke-sheet")],
            color: [style.color, resolve("color", "--wke-ink-2")],
            border: [style.borderTopColor, resolve("borderTopColor", "--wke-rule-strong")],
            borderWidth: style.borderTopWidth,
            shadow: style.boxShadow !== "none",
          };
        }, label);
        expect(report.whiteSpace, label).toBe("normal");
        expect(report.fontStyle, label).toBe("normal");
        expect(report.fontSize, label).toBe("13px");
        expect(report.scrollWidth, label).toBeLessThanOrEqual(report.clientWidth);
        expect(report.width, label).toBeLessThanOrEqual(320.5);
        expect(report.left, label).toBeGreaterThanOrEqual(16 - 1);
        expect(report.right, label).toBeLessThanOrEqual(viewport.width - 16 + 1);
        expect(report.left, label).toBeGreaterThanOrEqual(report.mainLeft - 1);
        expect(report.right, label).toBeLessThanOrEqual(report.mainRight + 1);
        expect(report.top, label).toBeGreaterThanOrEqual(16 - 1);
        expect(report.bottom, label).toBeLessThanOrEqual(viewport.height - 16 + 1);
        expect(Math.abs(report.gap - 6), label).toBeLessThanOrEqual(1);
        expect(report.bg[0], label).toBe(report.bg[1]);
        expect(report.color[0], label).toBe(report.color[1]);
        expect(report.border[0], label).toBe(report.border[1]);
        expect(report.borderWidth, label).toBe("1px");
        expect(report.shadow, label).toBe(true);
        await page.keyboard.press("Escape");
        await expect(tip).toHaveCount(0);
      }
    });

    test(`every (i) sits on the x-height centre of its text, ${path}`, async ({ page, open }) => {
      await openPage(page, open, path, ready);
      const offsets = await dotOffsets(page);
      expect(offsets.length).toBeGreaterThan(0);
      for (const { label, dy, gap } of offsets) {
        expect(Math.abs(dy), `${label} dy ${dy}`).toBeLessThanOrEqual(1);
        expect(Math.abs(gap - 4), `${label} gap ${gap}`).toBeLessThanOrEqual(0.5);
      }
    });
  }

  test("the info glyph is 12 px", async ({ page, open }) => {
    await open("/");
    const size = await page
      .locator("button[aria-label^='About Dossiers']")
      .first()
      .evaluate((el) => getComputedStyle(el).fontSize);
    expect(size).toBe("12px");
  });
});

// The test sets its own viewport widths, so it runs once, on the 1440 project.
test.describe("info glyph size on Home", only("desktop-1440"), () => {
  eachTheme(() => {
    for (const width of [1024, 1280, 1440, 1920]) {
      test(`every (i) glyph is at least 14 by 14, the Fits in header included, at ${width}`, async ({
        page,
        open,
      }) => {
        await open("/", { viewport: { width, height: 1000 } });
        await expect(page.getByRole("heading", { name: /^Most read/ })).toBeVisible();
        const sizes = await page.evaluate(() =>
          [...document.querySelectorAll("button[aria-label], span[aria-hidden='true']")]
            .filter(
              (el) =>
                el.classList.contains("font-serif") &&
                el.classList.contains("italic") &&
                (el.textContent ?? "").trim() === "i",
            )
            .map((el) => {
              const b = el.getBoundingClientRect();
              return [b.width, b.height];
            })
            .filter(([w]) => (w ?? 0) > 0),
        );
        expect(sizes.length).toBeGreaterThan(3);
        for (const [w, h] of sizes) {
          expect(w, "glyph width").toBeGreaterThanOrEqual(13.5);
          expect(h, "glyph height").toBeGreaterThanOrEqual(13.5);
        }
        // One real (i) in the most-read header: the repeated column headers carry the words alone.
        await expect(page.getByRole("button", { name: "About Fits in" })).toHaveCount(1);
      });
    }
  });
});

test("the (i) alignment holds at 150 percent zoom", async ({ page, open }) => {
  await openPage(page, open, "/t/Lizzie_Borden", "Lizzie Borden");
  await page.evaluate(() => {
    document.documentElement.style.zoom = "1.5";
  });
  await settleLayout(page);
  const offsets = await dotOffsets(page);
  expect(offsets.length).toBeGreaterThan(0);
  for (const { label, dy, gap } of offsets) {
    expect(Math.abs(dy), `${label} dy ${dy}`).toBeLessThanOrEqual(1);
    expect(Math.abs(gap - 4), `${label} gap ${gap}`).toBeLessThanOrEqual(0.5);
  }
});

test("the machines page has no InfoDot", async ({ page, open }) => {
  await openPage(page, open, "/machines", "For machines");
  await expect(page.locator(DOTS)).toHaveCount(0);
});
