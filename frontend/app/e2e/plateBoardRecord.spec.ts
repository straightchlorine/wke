import type { Locator, Page } from "@playwright/test";
import { BOARD, HOME_GRAPH, RELATED_GRAPH, reachableNodes } from "./plateLocators";
import { eachTheme, expect, lightOnly, only, test } from "./support";

type Open = (
  path: string,
  options?: { viewport?: { width: number; height: number }; ready?: Locator },
) => Promise<void>;

// The board is the panel under a graph that describes the dot the pointer is on or that is selected.
// This file checks the board and the square box that marks the selected dot.
// The file sets its own viewport, so it runs only on the desktop-1440 project.

// The pause flag stops the replayed edit rows, so nothing below the graph moves mid-test.
test.use({ paused: true });

/** Opens a page at a size and waits for the graph to have faded in, then scrolls it into view. */
async function openGraph(
  page: Page,
  open: Open,
  path: string,
  graph: string,
  width: number,
  height: number,
) {
  await open(path, { viewport: { width, height }, ready: page.locator(`${graph} a`).first() });
  await expect(page.locator(graph)).toHaveCSS("opacity", "1");
  await page.locator(graph).scrollIntoViewIfNeeded();
}

/** Returns the index of the first dot in rank order that the pointer can reach. */
async function reachableDot(page: Page, graph: string): Promise<number> {
  return (await reachableNodes(page, graph))[0] ?? -1;
}

async function boardBox(page: Page) {
  return page.locator(BOARD).evaluate((el) => {
    const r = el.getBoundingClientRect();
    return { w: r.width, h: r.height, top: r.top, bottom: r.bottom, right: r.right };
  });
}

test.describe("Board record", only("desktop-1440"), () => {
  eachTheme(() => {
    for (const [label, path, graph] of [
      ["Home graph", "/", HOME_GRAPH],
      ["Related graph", "/t/Lizzie_Borden", RELATED_GRAPH],
    ] as const) {
      for (const [width, height] of [
        [1440, 900],
        [390, 844],
      ] as const) {
        test(`${label} at ${width}: one board height across idle, hover and selected, and a square selection box centred on the dot`, async ({
          page,
          open,
        }) => {
          await openGraph(page, open, path, graph, width, height);
          const idle = await boardBox(page);
          await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "idle");
          const hint = await page.locator(`${BOARD} p`).evaluate((p) => {
            const b = p.getBoundingClientRect();
            const parent = p.parentElement!.getBoundingClientRect();
            return {
              dx: b.left + b.width / 2 - (parent.left + parent.width / 2),
              dy: b.top + b.height / 2 - (parent.top + parent.height / 2),
            };
          });
          expect(Math.abs(hint.dx)).toBeLessThanOrEqual(1);
          expect(Math.abs(hint.dy)).toBeLessThanOrEqual(1);

          const index = await reachableDot(page, graph);
          expect(index).toBeGreaterThanOrEqual(0);
          const dot = page.locator(`${graph} a`).nth(index);
          const hit = (await dot.locator("[data-plate-hit]").boundingBox())!;
          const cx = hit.x + hit.width / 2;
          const cy = hit.y + hit.height / 2;
          await page.mouse.move(cx, cy);
          await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "preview");
          const hover = await boardBox(page);
          const skin = (sel: string) =>
            page.locator(sel).evaluate((el) => {
              const cs = getComputedStyle(el);
              return {
                bg: cs.backgroundColor,
                border: cs.borderTopColor,
                badge: el.querySelector("[data-plate-badge]")!.getBoundingClientRect().width,
              };
            });
          const ink = await page.evaluate(() => {
            const probe = document.createElement("i");
            probe.style.color = "var(--wke-ink)";
            document.body.append(probe);
            const c = getComputedStyle(probe).color;
            probe.remove();
            return c;
          });
          const hoverSkin = await skin(BOARD);
          expect(hoverSkin.border, "hover border is not ink").not.toBe(ink);
          const plain = await page.locator(BOARD).evaluate((board) => ({
            icons: board.querySelectorAll("[data-plate-badge] svg").length,
            links: board.querySelectorAll("a, [role=link]").length,
            events: getComputedStyle(board.querySelector("[data-plate-badge] > span")!)
              .pointerEvents,
            underline: getComputedStyle(
              [...board.querySelectorAll("[data-plate-badge] span")].find(
                (x) => x.children.length === 0,
              )!,
            ).textDecorationLine,
            text: board.textContent ?? "",
          }));
          expect(plain.icons, "no link icon in any state").toBe(0);
          expect(plain.underline, "the badge text is plain while the pointer only previews").toBe(
            "none",
          );
          expect(plain.links, "the badge is not a link while previewing").toBe(0);
          expect(plain.events).toBe("none");
          expect(plain.text).not.toMatch(/click to select|tap to select/i);
          await expect(page.locator("[data-plate-hover-ring]")).toHaveCount(1);
          expect(await page.locator("[data-plate-hover-ring]").evaluate((el) => el.tagName)).toBe(
            "circle",
          );

          await page.mouse.click(cx, cy);
          await page.mouse.move(2, 2);
          await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "selected");
          const selected = await boardBox(page);
          for (const [name, b] of [
            ["hover", hover],
            ["selected", selected],
          ] as const) {
            expect(Math.abs(b.h - idle.h), `${name} height`).toBeLessThanOrEqual(0.5);
            expect(Math.abs(b.w - idle.w), `${name} width`).toBeLessThanOrEqual(0.5);
            expect(Math.abs(b.top - idle.top), `${name} top`).toBeLessThanOrEqual(0.5);
          }

          // The selection mark is a square box, 1 px ink, a few px larger than the dot, centred on it.
          const mark = await dot.evaluate((a) => {
            const rect = a.querySelector("[data-plate-ring]")!;
            const circle = a.querySelector(
              "circle:not([data-plate-hit]):not([data-plate-hover-ring])",
            )!;
            const r = rect.getBoundingClientRect();
            const c = circle.getBoundingClientRect();
            const cs = getComputedStyle(rect);
            return {
              tag: rect.tagName,
              w: r.width,
              h: r.height,
              dx: r.left + r.width / 2 - (c.left + c.width / 2),
              dy: r.top + r.height / 2 - (c.top + c.height / 2),
              larger: r.width - c.width,
              stroke: cs.strokeWidth,
              rx: rect.getAttribute("rx"),
            };
          });
          expect(mark.tag).toBe("rect");
          expect(Math.abs(mark.w - mark.h)).toBeLessThanOrEqual(0.5);
          expect(Math.abs(mark.dx)).toBeLessThanOrEqual(0.5);
          expect(Math.abs(mark.dy)).toBeLessThanOrEqual(0.5);
          expect(mark.larger).toBeGreaterThanOrEqual(4);
          expect(mark.larger).toBeLessThanOrEqual(14);
          expect(mark.stroke).toBe("1px");
          expect(mark.rx).toBe("0");

          // The selected board has an ink border, and its badge is the dossier link: underlined, with no icon.
          const selectedSkin = await skin(BOARD);
          expect(selectedSkin.border, "selected border is ink").toBe(ink);

          const parts = await page.locator(BOARD).evaluate((board) => {
            const b = board.getBoundingClientRect();
            const cs = getComputedStyle(board);
            const baseline = (el: Element) => {
              const probe = board.ownerDocument.createElement("span");
              probe.style.cssText = "display:inline-block;width:0;height:0;vertical-align:baseline";
              el.append(probe);
              const y = probe.getBoundingClientRect().bottom;
              probe.remove();
              return y;
            };
            const title = board.querySelector("p[title]")!;
            const rows = [...board.querySelectorAll("[data-record-row]")].map((r) => {
              const rowLabel = r.firstElementChild!;
              const leader = r.querySelector("span[aria-hidden]")!;
              return {
                label: rowLabel.textContent ?? "",
                leaders: r.querySelectorAll(":scope > span[aria-hidden]").length,
                labelBaseline: baseline(rowLabel),
                leaderBottom: leader.getBoundingClientRect().bottom,
                bottom: r.getBoundingClientRect().bottom,
              };
            });
            const linked = [...board.querySelectorAll("[data-record-row]")].find(
              (r) => r.firstElementChild?.textContent === "Linked to",
            )!;
            const linkedValue = linked.lastElementChild!;
            const trigger = linkedValue.querySelector("button");
            const badge = board.querySelector("[data-plate-badge]")!;
            return {
              family: getComputedStyle(title).fontFamily,
              text: board.textContent ?? "",
              rows,
              badgeText: badge.textContent ?? "",
              badgeIcons: badge.querySelectorAll("svg").length,
              badgeUnderline: getComputedStyle(badge.querySelector("a span span")!)
                .textDecorationLine,
              badgeLinks: board.querySelectorAll("a[href]").length,
              badgeHref: board.querySelector("a[href]")?.getAttribute("href") ?? "",
              padBottom:
                Number.parseFloat(cs.paddingBottom) + Number.parseFloat(cs.borderBottomWidth),
              gap: b.bottom - Math.max(...rows.map((r) => r.bottom)),
              linkedHeight: (trigger ?? linkedValue).getBoundingClientRect().height,
              linkedEllipsis: getComputedStyle(trigger ?? linkedValue).textOverflow,
              linkedNowrap: getComputedStyle(trigger ?? linkedValue).whiteSpace,
              linkedFocusable: trigger != null,
            };
          });
          expect(parts.family).toContain("Newsreader");
          expect(parts.text).not.toMatch(/click to select|tap to select/i);
          expect(parts.badgeText).toMatch(/^(Ready|Partial|Building|Not built|Open)$/);
          expect(parts.badgeIcons, "no link icon in any state").toBe(0);
          expect(parts.badgeUnderline, "the selected badge text is underlined").toContain(
            "underline",
          );
          expect(parts.badgeLinks, "the badge is the one link").toBe(1);
          expect(parts.badgeHref).toMatch(/^\/t\//);
          expect(parts.gap, "no empty band under the last row").toBeLessThanOrEqual(
            parts.padBottom + 0.5,
          );
          expect(parts.linkedHeight, "Linked to is one line").toBeLessThanOrEqual(20);
          expect(parts.linkedEllipsis).toBe("ellipsis");
          expect(parts.linkedNowrap).toBe("nowrap");
          for (const row of parts.rows) {
            expect(row.leaders, row.label).toBe(1);
            expect(
              Math.abs(row.leaderBottom - row.labelBaseline),
              `${row.label} leader sits on the baseline`,
            ).toBeLessThanOrEqual(1);
          }
          const labels = parts.rows.map((r) => r.label);
          expect(labels).toEqual([
            label === "Home graph" ? "Views" : expect.stringMatching(/^(Similarity|Views)$/),
            "Edits in the last hour",
            "Linked to",
            "Dossier",
          ]);

          expect(hoverSkin.bg, "selected wash differs from hover").not.toBe(selectedSkin.bg);
          expect(hoverSkin.badge, "the badge keeps one width").toBe(selectedSkin.badge);
          expect(
            selectedSkin.badge,
            "wide enough for the widest state text, not wider than a chip needs",
          ).toBeLessThanOrEqual(72);
        });
      }
    }
  });

  lightOnly(() => {
    for (const [label, path, graph] of [
      ["Home graph", "/", HOME_GRAPH],
      ["Related graph", "/t/Lizzie_Borden", RELATED_GRAPH],
    ] as const) {
      for (const [width, height] of [
        [1440, 900],
        [390, 844],
      ] as const) {
        test(`${label} at ${width}: Linked to shows the full list in the tooltip on hover and focus, the screen reader is told`, async ({
          page,
          open,
        }) => {
          await openGraph(page, open, path, graph, width, height);
          const index = await reachableDot(page, graph);
          const dot = page.locator(`${graph} a`).nth(index);
          const hit = (await dot.locator("[data-plate-hit]").boundingBox())!;
          await page.mouse.click(hit.x + hit.width / 2, hit.y + hit.height / 2);
          await page.mouse.move(2, 2);
          await expect(page.locator(BOARD)).toHaveAttribute("data-plate-board", "selected");
          await expect(dot).toHaveAttribute("aria-pressed", "true");
          await expect(page.locator("#live-region")).toContainText(/^Selected /);
          const trigger = page
            .locator(`${BOARD} [data-record-row]`)
            .filter({ hasText: "Linked to" })
            .locator("button");
          await expect(trigger, "the first reachable dot has links").toHaveCount(1);
          const full = await trigger.evaluate(
            (el) => el.parentElement!.querySelector("[role=tooltip]")!.textContent ?? "",
          );
          expect(full.length).toBeGreaterThan(0);
          await trigger.focus();
          await expect(page.getByRole("tooltip").filter({ hasText: full })).toBeVisible();
          await page.keyboard.press("Escape");
          await expect(page.getByRole("tooltip").filter({ hasText: full })).toBeHidden();
          await trigger.hover();
          await expect(page.getByRole("tooltip").filter({ hasText: full })).toBeVisible();
        });
      }
    }
  });
});
