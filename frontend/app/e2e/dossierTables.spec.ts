import { AxeBuilder } from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { readFixtureJson } from "./buildFixture";
import { assertNoErrors, expectShellRendered, trackErrors } from "./errorTracking";
import { dossierBody } from "./mockApi";
import { eachTheme, expect, only, test } from "./support";

// The Apollo 11 dossier at 8000 holds three tables (3, 3 and 12 rows) and one list (8 items).
// They must reach the page as a real table and a real list, not as a run of words and pipes.

const FIXTURE = "dossier_662_8000.json";
const ROUTE = /\/api\/v1\/dossiers\/662(\?[^/]*)?$/;

interface FixtureChunk {
  id: string;
  kind?: string;
  text: string;
  links?: { start: number; end: number; title: string }[];
}

const chunks = readFixtureJson<{ chunks: FixtureChunk[] }>(FIXTURE).chunks;
const tableChunks = chunks.filter((c) => c.kind === "table");
const listChunk = chunks.find((c) => c.kind === "list")!;

/** Serves the fixture after an edit of its chunks. */
async function serveEdited(page: Page, edit: (chunks: FixtureChunk[]) => void): Promise<void> {
  const body = dossierBody(FIXTURE, (flat) => {
    const list: unknown = flat["chunks"];
    if (!Array.isArray(list)) {
      throw new Error("the fixture has no chunks");
    }
    edit(list);
  });
  await page.route(ROUTE, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body }),
  );
}

const WIDE_HEADER = ["Name", "Born", "Role", "Agency", "Site", "Years", "Notes"];

function wideRow(i: number): string {
  return `| Person ${i} | 19${30 + i} | Engineer for the guidance computer | NASA | Houston | 1961 to 1972 | A long remark about ${i} |`;
}

const passage = (page: Page, id: string) => page.locator(`[id="chunk-${id}"]`);

async function noSidewaysPage(page: Page): Promise<boolean> {
  return page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
}

test.describe("Dossier tables and lists", () => {
  eachTheme(() => {
    test(
      "shows each table and the list as a real table and a real list",
      only("desktop-1440"),
      async ({ page, open }) => {
        const errors = trackErrors(page);
        await open("/t/Apollo_11");

        const tables = page.locator('[data-role="source-text"] table');
        await expect(tables).toHaveCount(3);
        await expect(tables.locator("caption")).toHaveText([
          /^Prime crew/,
          /^Backup crew/,
          /^Other personnel/,
        ]);
        const bodyRows = tables.locator("tbody tr");
        expect(
          await tables.evaluateAll((els) => els.map((t) => t.querySelectorAll("tbody tr").length)),
        ).toEqual([3, 3, 12]);
        await expect(bodyRows.first().locator("td")).toHaveText(["Commander", /^Neil Armstrong/]);
        await expect(tables.nth(2).locator("thead th")).toHaveText(["Name", "Activities"]);

        const list = page.locator('[data-role="source-text"] ul');
        await expect(list).toHaveCount(1);
        await expect(list.locator("li")).toHaveCount(8);
        await expect(list.locator("li").first()).toContainText("Footprints on the Moon");

        await expect(page.locator("article")).not.toContainText("| --- |");
        await expect(page.locator("article")).not.toContainText(/^- /m);
        await expectShellRendered(page);
        assertNoErrors(errors);
      },
    );

    test(
      "keeps the citation marker: the first passage of a section carries it, a table or list after it does not",
      only("desktop-1440"),
      async ({ page, open }) => {
        await open("/t/Apollo_11");
        // The films section holds only the list, so the list is its first passage and ends with the marker.
        const films = page.locator(`[id="chunk-${listChunk.id}"]`);
        const marker = films
          .locator("li")
          .last()
          .getByRole("link", { name: /^\[\d+\]$/ });
        await expect(marker).toHaveCount(1);
        await expect(marker).toHaveAttribute("href", /^https:\/\/en\.wikipedia\.org\//);
        // Each table follows prose of its section, which already carries the marker.
        for (const table of tableChunks) {
          await expect(passage(page, table.id).locator("a")).toHaveCount(0);
        }
      },
    );

    test("a link inside a table cell and inside a list item opens its article", async ({
      page,
      open,
    }) => {
      const errors = trackErrors(page);
      const table = tableChunks[2]!;
      const cellStart = table.text.indexOf("Margaret Hamilton");
      const itemStart = listChunk.text.indexOf("Moonwalk One");
      await serveEdited(page, (all) => {
        all.find((c) => c.id === table.id)!.links = [
          {
            start: cellStart,
            end: cellStart + "Margaret Hamilton".length,
            title: "Margaret Hamilton",
          },
        ];
        all.find((c) => c.id === listChunk.id)!.links = [
          { start: itemStart, end: itemStart + "Moonwalk One".length, title: "Moonwalk One" },
        ];
      });
      await page.route("https://en.wikipedia.org/**", (route) =>
        route.fulfill({ status: 200, contentType: "text/html", body: "<title>Stub</title>" }),
      );
      await open("/t/Apollo_11");

      const cellLink = passage(page, table.id).getByRole("link", { name: "Margaret Hamilton" });
      await expect(cellLink).toHaveAttribute(
        "href",
        "https://en.wikipedia.org/wiki/Margaret_Hamilton",
      );
      await expect(cellLink.locator("xpath=ancestor::td")).toContainText("Margaret Hamilton");
      const itemLink = passage(page, listChunk.id).getByRole("link", { name: "Moonwalk One" });
      await expect(itemLink).toHaveAttribute("href", "https://en.wikipedia.org/wiki/Moonwalk_One");
      await expect(itemLink.locator("xpath=ancestor::li")).toContainText("a 1971 documentary film");

      await cellLink.click();
      await expect(page).toHaveURL("https://en.wikipedia.org/wiki/Margaret_Hamilton");
      assertNoErrors(errors);
    });

    test("has no axe violations and no sideways page scroll", async ({ page, open }) => {
      await open("/t/Apollo_11");
      await expect(page.locator('[data-role="source-text"] table')).toHaveCount(3);
      expect(await noSidewaysPage(page)).toBe(true);
      const results = await new AxeBuilder({ page }).analyze();
      expect(results.violations).toEqual([]);
    });

    test(
      "a table wider than a phone scrolls inside its own named, focusable block",
      only("mobile-390"),
      async ({ page, open }) => {
        const wide = tableChunks[2]!;
        await serveEdited(page, (all) => {
          all.find((c) => c.id === wide.id)!.text = [
            "Wide table",
            `| ${WIDE_HEADER.join(" | ")} |`,
            `| ${WIDE_HEADER.map(() => "---").join(" | ")} |`,
            wideRow(1),
            wideRow(2),
            wideRow(3),
          ].join("\n");
        });
        await open("/t/Apollo_11");

        const block = page.getByRole("group", { name: "Wide table", exact: true });
        await expect(block).toHaveCount(1);
        await expect(block).toHaveAttribute("tabindex", "0");
        const sizes = await block.evaluate((el) => ({
          inner: el.scrollWidth,
          outer: el.clientWidth,
        }));
        expect(sizes.inner).toBeGreaterThan(sizes.outer);
        expect(await noSidewaysPage(page)).toBe(true);

        await block.focus();
        await page.keyboard.press("ArrowRight");
        await expect.poll(() => block.evaluate((el) => el.scrollLeft)).toBeGreaterThan(0);
        expect(await noSidewaysPage(page)).toBe(true);

        // A table that fits is no tab stop and no named group.
        await expect(page.getByRole("group", { name: "Prime crew", exact: true })).toHaveCount(0);
        const results = await new AxeBuilder({ page }).analyze();
        expect(results.violations).toEqual([]);
      },
    );

    test(
      "two wide tables with the same caption are no axe violation",
      only("mobile-390"),
      async ({ page, open }) => {
        await serveEdited(page, (all) => {
          for (const chunk of [tableChunks[0]!, tableChunks[2]!]) {
            all.find((c) => c.id === chunk.id)!.text = [
              "Results",
              `| ${WIDE_HEADER.join(" | ")} |`,
              `| ${WIDE_HEADER.map(() => "---").join(" | ")} |`,
              wideRow(1),
              wideRow(2),
            ].join("\n");
          }
        });
        await open("/t/Apollo_11");

        await expect(page.locator('[data-role="source-text"] [aria-label="Results"]')).toHaveCount(
          2,
        );
        const results = await new AxeBuilder({ page }).analyze();
        expect(results.violations).toEqual([]);
      },
    );

    test(
      "fits a phone without a sideways page scroll",
      only("mobile-390"),
      async ({ page, open }) => {
        await open("/t/Apollo_11");
        await expect(page.locator('[data-role="source-text"] table')).toHaveCount(3);
        expect(await noSidewaysPage(page)).toBe(true);
      },
    );
  });
});
