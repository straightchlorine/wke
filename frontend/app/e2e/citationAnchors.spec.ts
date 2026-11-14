import type { Page } from "@playwright/test";
import type { DossierView } from "../src/api/dossier";
import { readFixtureJson } from "./buildFixture";
import { dossierEnvelope } from "./mockApi";
import { eachTheme, expect, only, test } from "./support";

const WIDTHS = [1440, 390] as const;

const anchored = readFixtureJson<DossierView>("dossier_214796_8000.json");

async function openAnchored(page: Page, open: (path: string) => Promise<void>) {
  await page.route(/\/api\/v1\/dossiers\/214796(\?[^/]*)?$/, async (route) => {
    const budget = new URL(route.request().url()).searchParams.get("budget");
    if (budget !== "8000" && budget !== null) {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(dossierEnvelope(anchored)),
    });
  });
  await open("/t/Lizzie_Borden?budget=8000");
  await expect(page.locator("[data-section-heading]").first()).toBeVisible();
}

eachTheme(() => {
  for (const width of WIDTHS) {
    test.describe(`Section-anchored citations, ${width}`, only("desktop-1440"), () => {
      test.use({ viewport: { width, height: 900 } });

      test("every in-text [n] link carries the section anchor of its citation", async ({
        page,
        open,
      }) => {
        await openAnchored(page, open);
        const markers = page.locator("article sup a");
        const count = await markers.count();
        expect(count).toBeGreaterThan(5);
        const urlOf = new Map(anchored.citations.map((c) => [c.id, c.url ?? c.pin.permalink]));
        const hrefs = await markers.evaluateAll((els) =>
          els.map((el) => (el instanceof HTMLAnchorElement ? el.href : "")),
        );
        const anchoredHrefs = hrefs.filter((href) => href.includes("#"));
        expect(anchoredHrefs.length).toBeGreaterThan(5);
        for (const href of hrefs) expect([...urlOf.values()]).toContain(href);
      });

      test("notes run in number order, seed first then related, and name their section", async ({
        page,
        open,
      }) => {
        await openAnchored(page, open);
        const items = page.locator("#cites li");
        const texts = await items.allInnerTexts();
        const numbers = texts.map((t) => Number(/^\[(\d+)\]/.exec(t.trim())?.[1]));
        expect(numbers).toEqual(numbers.map((_, i) => i + 1));
        const cited = anchored.citations.filter(
          (c) => c.role === "seed" && anchored.chunks.some((k) => k.citation_id === c.id),
        );
        const related = anchored.citations.filter((c) => c.role === "related");
        expect(texts).toHaveLength(cited.length + related.length);
        expect(texts[0]).toContain("Lizzie Borden, revision 1384380651");
        expect(texts[0]).not.toContain(", Early");
        expect(texts.some((t) => t.includes("Lizzie Borden, Inquest, revision 1384380651"))).toBe(
          true,
        );
        expect(texts.some((t) => t.includes("Lizzie Borden, Trial and acquittal, revision"))).toBe(
          true,
        );
        expect(texts[cited.length]).toContain(related[0]?.pin.title ?? "");
        const links = await items
          .locator("a")
          .evaluateAll((els) => els.map((el) => (el instanceof HTMLAnchorElement ? el.href : "")));
        expect(links[2]).toContain("#");
        // Each in-text number links to the note that has the same href.
        const markerPairs = await page.locator("article sup a").evaluateAll((els) =>
          els.map((el) => ({
            label: el.textContent ?? "",
            href: el instanceof HTMLAnchorElement ? el.href : "",
          })),
        );
        for (const { label, href } of markerPairs) {
          const n = Number(/\d+/.exec(label)?.[0]);
          expect(links[n - 1]).toBe(href);
        }
      });
    });
  }
});
