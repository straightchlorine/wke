import { RELATED_GRAPH } from "./plateLocators";
import { expect, lightOnly, only, test } from "./support";

// On a landscape phone (the `short` height variant) the window height, not the column width, caps the size of
// the Home concept graph and of the related-articles graph on a dossier page. The header fits on one row.

// The pause flag stops the replayed edit rows, so nothing below the graph moves mid-test.
test.use({ paused: true });

const SIZES = [
  [844, 390],
  [932, 430],
] as const;

// Every test here sets its own viewport, so it runs only on the desktop-1440 project.
test.describe("Landscape phone", only("desktop-1440"), () => {
  lightOnly(() => {
    for (const [width, height] of SIZES) {
      test(`Home at ${width}x${height}: graph side is the window height less 96px (under 320 at 844x390), centred in its column, header one 56px row`, async ({
        page,
        open,
      }) => {
        await open("/", {
          viewport: { width, height },
          ready: page.locator('svg[role="group"] a').first(),
        });
        const m = await page.evaluate(() => {
          const frame = document.querySelector("[data-plate-frame]")!.getBoundingClientRect();
          const figure = document.querySelector("figure")!.getBoundingClientRect();
          const slot = document.querySelector("figure")!.parentElement!.getBoundingClientRect();
          const header = document.querySelector("header")!.getBoundingClientRect();
          return {
            side: frame.width,
            square: Math.abs(frame.width - frame.height) < 1,
            offCentre: Math.abs(figure.left + figure.width / 2 - (slot.left + slot.width / 2)),
            header: header.height,
            noOverflow: document.documentElement.scrollWidth <= window.innerWidth,
          };
        });
        expect(Math.abs(m.side - (height - 96))).toBeLessThanOrEqual(1);
        if (height === 390) {
          expect(m.side).toBeLessThan(320);
        }
        expect(m.square).toBe(true);
        expect(m.offCentre).toBeLessThanOrEqual(1);
        expect(m.header).toBe(56);
        expect(m.noOverflow).toBe(true);
      });
    }

    for (const [width, height] of SIZES) {
      test(`Dossier at ${width}x${height}: the related-articles graph is no taller than the window less 96px, centred in its rail, with the board under it and no swatch row`, async ({
        page,
        open,
      }) => {
        await open("/t/Lizzie_Borden", { viewport: { width, height } });
        const plate = page.locator("figure", { hasText: "Plate 1." });
        await plate.locator("[data-plate-frame]").scrollIntoViewIfNeeded();
        const m = await plate.evaluate((figure) => {
          const frame = figure.querySelector("[data-plate-frame]")!.getBoundingClientRect();
          const rail = figure.closest("aside")!.getBoundingClientRect();
          const board = figure.querySelector("[data-plate-board]")!.getBoundingClientRect();
          return {
            side: frame.width,
            square: Math.abs(frame.width - frame.height) < 1,
            offCentre: Math.abs(frame.left + frame.width / 2 - (rail.left + rail.width / 2)),
            railWidth: rail.width,
            top: frame.top,
            bottom: frame.bottom,
            boardGap: board.top - frame.bottom,
            swatchRows: figure.querySelectorAll('[role="group"]:not(svg)').length,
            noOverflow: document.documentElement.scrollWidth <= window.innerWidth,
          };
        });
        expect(m.side, "never taller than the window less the header and gaps").toBeLessThanOrEqual(
          height - 96 + 1,
        );
        if (m.railWidth >= height - 96) {
          expect(
            Math.abs(m.side - (height - 96)),
            "the cap is the window height less 96px",
          ).toBeLessThanOrEqual(1);
        }
        if (height === 390) {
          expect(m.side).toBeLessThan(320);
        }
        expect(m.square).toBe(true);
        expect(m.offCentre).toBeLessThanOrEqual(1);
        expect(m.top, "the whole frame is on screen").toBeGreaterThanOrEqual(0);
        expect(m.bottom).toBeLessThanOrEqual(height);
        expect(m.boardGap, "the board sits under the frame").toBeCloseTo(8, 0);
        expect(m.swatchRows, "the related-articles graph has one hull, so no swatch row").toBe(0);
        expect(m.noOverflow).toBe(true);
      });
    }

    // Even the narrow landscape-phone frame lets a related-articles name stand off its dot on a leader.
    // The name "Oak Grove Cemetery (Fall River, Massachusetts)" has no room for two lines there, so it is cut after a whole word, not mid-word.
    test("Related-articles graph at 844x390: the Oak Grove name is whole or cut after a whole word, and joined by a leader", async ({
      page,
      open,
    }) => {
      const graph = page.locator(RELATED_GRAPH);
      await open("/t/Lizzie_Borden", {
        viewport: { width: 844, height: 390 },
        ready: graph.locator("a").first(),
      });
      const oak = await graph.evaluate((svg) => {
        const label = [...svg.querySelectorAll("a")].find((a) =>
          /Oak Grove/.test(a.getAttribute("aria-label") ?? ""),
        )!;
        const text = label.querySelector("text[data-plate-label]")!;
        const shown = [...text.childNodes]
          .filter((n) => n.nodeName !== "title")
          .map((n) => n.textContent ?? "")
          .join("");
        return { shown, leader: label.querySelector("line[data-plate-leader]") != null };
      });
      const title = "Oak Grove Cemetery (Fall River, Massachusetts)";
      const cut = oak.shown.endsWith("...");
      const stub = cut ? oak.shown.slice(0, -3) : oak.shown;
      expect(title.startsWith(stub), "the shown text is the name's own start").toBe(true);
      if (cut) {
        expect(title.charAt(stub.length), "cut after a whole word").toBe(" ");
      } else {
        expect(stub, "an uncut name is whole").toBe(title);
      }
      expect(oak.leader, "a name standing off its dot carries a leader").toBe(true);
    });
  });
});
