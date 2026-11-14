import { devices } from "@playwright/test";
import { contrastOf } from "./contrast";
import { eachTheme, expect, lightOnly, only, settleScroll, test } from "./support";

const DOSSIER_READY = 'section[id^="s"] [data-section-heading]';

// The iPhone profile without its default browser, which a describe cannot set.
const { defaultBrowserType: _browser, ...IPHONE } = devices["iPhone 12"];

test.describe("Dossier rail and data panel", () => {
  eachTheme(() => {
    test(
      "margin notes never overlap and the last one ends inside the article",
      // The margin column starts at 900px.
      only("tablet-1024", "desktop-1440", "desktop-1920"),
      async ({ page, open }) => {
        await open("/t/Jesus", { ready: page.locator(DOSSIER_READY).first() });
        const measure = () =>
          page.evaluate(() => {
            const notes = Array.from(
              document.querySelectorAll('aside [role="group"][aria-label^="Source for"]'),
            )
              .filter((el) => el.parentElement!.offsetParent !== null)
              .map((el) => {
                const r = el.parentElement!.getBoundingClientRect();
                return {
                  top: r.top + scrollY,
                  bottom: r.bottom + scrollY,
                  left: r.left,
                  right: r.right,
                };
              })
              .toSorted((a, b) => a.top - b.top);
            const article = document
              .querySelector('article[aria-label="Dossier text"]')!
              .getBoundingClientRect();
            return { notes, articleBottom: article.bottom + scrollY };
          });
        for (const y of [0, 1500, 3000, 100000]) {
          await page.evaluate((top) => window.scrollTo(0, top), y);
          await settleScroll(page);
          const { notes, articleBottom } = await measure();
          expect(notes.length).toBeGreaterThan(3);
          for (let i = 1; i < notes.length; i++) {
            const prev = notes[i - 1]!;
            const cur = notes[i]!;
            expect(cur.top, `note ${i} at scroll ${y}`).toBeGreaterThanOrEqual(prev.bottom - 0.5);
          }
          expect(notes[notes.length - 1]!.bottom).toBeLessThanOrEqual(articleBottom + 1);
        }
        expect(
          await contrastOf(page, 'aside [aria-label^="Source for"] span'),
        ).toBeGreaterThanOrEqual(4.5);
      },
    );

    test(
      "the token ruler has no crowded labels, one 0, and the rail ends at the article",
      // The ruler starts at 600px.
      only("tablet-768", "tablet-1024", "desktop-1440", "desktop-1920"),
      async ({ page, open }) => {
        await open("/t/Jesus", { ready: page.locator(DOSSIER_READY).first() });
        const width = page.viewportSize()?.width ?? 0;
        const labels = await page.evaluate(() =>
          Array.from(document.querySelectorAll("[data-ruler-label]")).map((el) => ({
            text: el.textContent ?? "",
            y: el.getBoundingClientRect().top + scrollY + el.getBoundingClientRect().height / 2,
          })),
        );
        expect(labels.length).toBeGreaterThan(2);
        expect(labels.filter((l) => l.text === "0")).toHaveLength(1);
        const ys = labels.map((l) => l.y).toSorted((a, b) => a - b);
        for (let i = 1; i < ys.length; i++) {
          expect(ys[i]! - ys[i - 1]!, `labels ${i - 1} and ${i}`).toBeGreaterThanOrEqual(14);
        }
        await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
        await settleScroll(page);
        const ends = await page.evaluate(() => {
          const articleBottom = document
            .querySelector('article[aria-label="Dossier text"]')!
            .getBoundingClientRect().bottom;
          const rail = [
            document.querySelector('nav[aria-label="Contents"]'),
            document.querySelector("[data-ruler-label]")?.closest(".relative.h-full, div.relative"),
          ].filter((el): el is Element => el instanceof HTMLElement && el.offsetParent !== null);
          const labelBottoms = Array.from(document.querySelectorAll("[data-ruler-label]")).map(
            (el) => el.getBoundingClientRect().bottom,
          );
          return {
            articleBottom,
            railBottoms: rail.map((el) => el.getBoundingClientRect().bottom),
            labelBottoms,
          };
        });
        for (const b of [...ends.railBottoms, ...ends.labelBottoms]) {
          expect(b).toBeLessThanOrEqual(ends.articleBottom + 1);
        }
        if (width >= 1340) {
          expect(ends.railBottoms.length).toBe(2);
        }
        expect(await contrastOf(page, "[data-ruler-label]")).toBeGreaterThanOrEqual(4.5);
      },
    );

    test(
      "the code block Copy is a quiet text control",
      only("desktop-1440"),
      async ({ page, open }) => {
        await open("/machines");
        const copy = page.locator("button[data-copy]").first();
        await copy.scrollIntoViewIfNeeded();
        const style = await copy.evaluate((el) => {
          const s = getComputedStyle(el);
          return {
            border: s.borderTopStyle,
            borderW: s.borderTopWidth,
            bg: s.backgroundColor,
            name: el.getAttribute("aria-label"),
          };
        });
        expect(style.border).toBe("none");
        expect(style.bg).toMatch(/rgba\(0, 0, 0, 0\)|transparent/);
        expect(style.name).toBeTruthy();
        expect(await contrastOf(page, "button[data-copy]")).toBeGreaterThanOrEqual(4.5);
        await copy.hover();
        expect(await copy.evaluate((el) => getComputedStyle(el).textDecorationLine)).toContain(
          "underline",
        );
        // A mouse click draws no focus ring. A keyboard focus draws a 2px ring.
        await copy.click();
        expect(await copy.evaluate((el) => getComputedStyle(el).outlineStyle)).toBe("none");
        // The click's own clipboard fallback moves focus once it settles.
        await expect(page.getByRole("status")).not.toBeEmpty();
        await page.mouse.move(0, 0);
        await page.keyboard.press("Shift");
        await copy.focus();
        const ring = await copy.evaluate((el) => {
          const s = getComputedStyle(el);
          return {
            width: s.outlineWidth,
            style: s.outlineStyle,
            focused: el === document.activeElement,
            visible: el.matches(":focus-visible"),
          };
        });
        expect(ring).toEqual({ width: "2px", style: "solid", focused: true, visible: true });
      },
    );
  });

  lightOnly(() => {
    test("This dossier as data: one row shape and one button column", async ({ page, open }) => {
      await open("/t/Jesus", { ready: page.locator(DOSSIER_READY).first() });
      const names = [
        "Copy URL: JSON",
        "Copy URL: Markdown",
        "Copy URL: llms.txt",
        "Copy MCP tool call",
      ];
      const boxes = [];
      for (const name of names) {
        const button = page.locator(`button[aria-label="${name}"]`).first();
        await button.scrollIntoViewIfNeeded();
        const box = await button.boundingBox();
        expect(box, name).not.toBeNull();
        boxes.push(box!);
      }
      const right = boxes[0]!.x + boxes[0]!.width;
      for (const box of boxes) {
        expect(Math.abs(box.x + box.width - right)).toBeLessThanOrEqual(1);
        expect(Math.abs(box.width - boxes[0]!.width)).toBeLessThanOrEqual(1);
      }
      // In the MCP row the label and the button share a line, and the tool call sits below them.
      const row = page
        .locator('button[aria-label="Copy MCP tool call"]')
        .first()
        .locator("xpath=ancestor::div[contains(@class,'flex-wrap')][1]");
      const label = await row.getByText("MCP", { exact: true }).boundingBox();
      const call = await row.locator("span.font-mono").boundingBox();
      const mcp = boxes[3]!;
      expect(label).not.toBeNull();
      expect(call).not.toBeNull();
      expect(Math.abs(label!.y + label!.height / 2 - (mcp.y + mcp.height / 2))).toBeLessThanOrEqual(
        8,
      );
      expect(call!.y).toBeGreaterThanOrEqual(mcp.y + mcp.height - 1);
      expect(await row.locator("span.font-mono").innerText()).toContain("get_dossier(");
    });
  });

  test.describe("on a phone", only("desktop-1440"), () => {
    test.use(IPHONE);

    test("the code block Copy keeps a 44px tap height on touch", async ({ page, open }) => {
      await open("/machines");
      const box = await page.locator("button[data-copy]").first().boundingBox();
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
    });
  });
});
