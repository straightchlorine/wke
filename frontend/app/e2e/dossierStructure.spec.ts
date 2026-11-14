import type { Page } from "@playwright/test";
import { eachTheme, expect, only, test } from "./support";

const NO_PROSE_LINE = "No prose passages kept: lists and tables are not extracted.";
const NOT_INCLUDED = "Lists and tables in this section are not included.";
const COMPLETE = "The source text below is complete.";

async function openDossier(
  open: (path: string) => Promise<void>,
  page: Page,
  budget = 8000,
  slug = "Lizzie_Borden",
) {
  await open(`/t/${slug}?budget=${budget}`);
  await expect(page.locator("[data-section-heading]").first()).toBeVisible();
}

interface ServedGodel {
  dossier: { sections: { label: string; dropped_non_prose: boolean; chunk_ids: string[] }[] };
  metadata: { budget: { included_chunk_ids: string[] } };
}

/** Fetches the 8k dossier of the Godel page, as the API serves it. */
function servedGodel(page: Page): Promise<ServedGodel> {
  return page.evaluate(async (): Promise<ServedGodel> =>
    (await fetch("/api/v1/dossiers/58863?budget=8000")).json(),
  );
}

/** Opens every visible fold of the source record and returns the record. */
async function openRecord(page: Page) {
  const record = page.locator('[aria-labelledby="source-record-h"]');
  for (const summary of await record.locator("summary").all()) {
    if (await summary.isVisible()) {
      await summary.click();
    }
  }
  return record;
}

test.describe("Dossier structure", () => {
  eachTheme(() => {
    test("a section with no prose is left out of the page, and the source record says so", async ({
      page,
      open,
    }) => {
      await openDossier(open, page);
      // Lizzie Borden has 20 sections; "Works cited" (the last) has no prose and no subsections.
      expect(
        await page
          .locator("article section[id]")
          .evaluateAll((els) => els.filter((el) => /^s\d+$/.test(el.id)).length),
      ).toBe(19);
      await expect(page.locator("section#s20")).toHaveCount(0);
      await expect(page.locator("article")).not.toContainText("Works cited");
      await expect(page.locator("article")).not.toContainText(NO_PROSE_LINE);
      const sections = page.locator('nav[aria-label="Contents"], nav[aria-label="Sections"]');
      for (const nav of await sections.all()) {
        await expect(nav).not.toContainText("Works cited");
        await expect(nav).not.toContainText("no prose passages kept");
      }
      // A heading-only parent whose subsections have prose stays.
      await expect(page.locator("section#s4 [data-section-heading]")).toContainText(
        "Murders of Andrew and Abby",
      );
      await expect(page.locator("section#s9 [data-section-heading]")).toContainText("Theories");
      const record = await openRecord(page);
      const line = record.locator("[data-record-row]:visible").filter({ hasText: /^Left out/ });
      await expect(line).toHaveCount(1);
      await expect(line).toContainText(/1 section$/);
      await expect(line).not.toContainText("without prose");
      const info = record
        .getByRole("button", { name: "About the sections left out" })
        .locator("visible=true");
      await info.focus();
      await expect(page.getByRole("tooltip")).toContainText(
        "No prose, so left out (lists and tables are not extracted): Works cited.",
      );
    });

    test(
      "the Left out row is one line with the count as its value, and the (i) holds the why and the titles",
      only("mobile-390", "desktop-1440"),
      async ({ page, open }) => {
        await openDossier(open, page, 2000);
        const record = await openRecord(page);
        const row = record.locator("[data-record-row]:visible").filter({ hasText: /^Left out/ });
        await expect(row).toHaveCount(1);
        const geometry = await row.evaluate((el) => {
          const [label, , value] = Array.from(el.children);
          // oxlint-disable-next-line unicorn/consistent-function-scoping -- the callback runs in the page, so its helpers cannot live outside it
          const probe = (node: Element) => {
            const span = document.createElement("span");
            span.style.cssText = "display:inline-block;width:0;height:0;";
            node.prepend(span);
            const y = span.getBoundingClientRect().bottom;
            span.remove();
            return y;
          };
          return {
            height: el.getBoundingClientRect().height,
            value: value!.textContent,
            sameBaseline:
              Math.abs(probe(label!.firstElementChild ?? label!) - probe(value!)) <= 0.5,
            valueRight: Math.abs(
              value!.getBoundingClientRect().right - el.getBoundingClientRect().right,
            ),
          };
        });
        expect(geometry.value).toMatch(/^\d+ sections?$/);
        expect(geometry.height).toBeLessThanOrEqual(36);
        expect(geometry.sameBaseline).toBe(true);
        expect(geometry.valueRight).toBeLessThanOrEqual(0.5);
        await record
          .getByRole("button", { name: "About the sections left out" })
          .locator("visible=true")
          .focus();
        const tip = page.getByRole("tooltip");
        await expect(tip).toContainText(
          "No prose, so left out (lists and tables are not extracted): Works cited.",
        );
        await expect(tip).toContainText("Left out at 2k: ");
      },
    );

    test("the section counts name one total that the left-out count adds up to, and titles are split by semicolons", async ({
      page,
      open,
    }) => {
      await openDossier(open, page, 2000);
      const record = await openRecord(page);
      const total = Number(
        ((
          await record
            .locator("[data-record-row]:visible")
            .filter({ hasText: /^Sections/ })
            .innerText()
        ).match(/(\d+)\s*$/) ?? [])[1],
      );
      expect(total).toBe(20);
      const left = Number(
        ((
          await record
            .locator("[data-record-row]:visible")
            .filter({ hasText: /^Left out/ })
            .innerText()
        ).match(/(\d+) sections?\s*$/) ?? [])[1],
      );
      const contents = page.getByText(new RegExp(`\\d+ of ${total} sections`));
      await expect(contents.first()).toContainText(`${total - left} of ${total} sections`);
      await record
        .getByRole("button", { name: "About the sections left out" })
        .locator("visible=true")
        .focus();
      const tip = (await page.getByRole("tooltip").innerText()).replace(/\s+/g, " ");
      const folded = tip.split("Left out at 2k: ")[1]?.replace(/\.$/, "") ?? "";
      expect(folded.split("; ")).toHaveLength(left - 1);
    });

    test("the completeness line follows dropped_non_prose in both states", async ({
      page,
      open,
    }) => {
      await openDossier(open, page, 8000, "G%C3%B6del's_incompleteness_theorems");
      const dossier = await servedGodel(page);
      const sections = dossier.dossier.sections;
      const dropped = sections.findIndex((s) => s.dropped_non_prose && s.chunk_ids.length > 0);
      const included = new Set<string>(dossier.metadata.budget.included_chunk_ids);
      const kept = sections.findIndex(
        (s, i) =>
          !s.dropped_non_prose &&
          s.chunk_ids.length > 0 &&
          i > 0 &&
          s.chunk_ids.every((id) => included.has(id)),
      );
      expect(dropped).toBeGreaterThan(-1);
      expect(kept).toBeGreaterThan(-1);
      const droppedMeta = page.locator(`section#s${dropped + 1} p`).first();
      await expect(droppedMeta).toContainText(NOT_INCLUDED);
      await expect(droppedMeta).not.toContainText(COMPLETE);
      const keptSection = page.locator(`section#s${kept + 1}`);
      await expect(keptSection.locator('[data-role="completeness"]')).toHaveText(`. ${COMPLETE}`);
      await expect(keptSection).not.toContainText(NOT_INCLUDED);
    });

    test("every section whose lists were left out says so, and no other section does", async ({
      page,
      open,
    }) => {
      await openDossier(open, page, 8000, "G%C3%B6del's_incompleteness_theorems");
      const labels = (await servedGodel(page)).dossier.sections
        .filter((s) => s.dropped_non_prose)
        .map((s) => s.label);
      expect(labels).toHaveLength(4);
      const notes = page.locator("article section[id]", { hasText: NOT_INCLUDED });
      await expect(notes).toHaveCount(labels.length);
      const headings = await notes.locator("[data-section-heading]").allTextContents();
      labels.forEach((label, i) => expect(headings[i]).toContain(label));
    });

    test("subsections render as h3 under their h2 and the rail or strip marks the depth", async ({
      page,
      open,
    }) => {
      await openDossier(open, page);
      await expect(page.locator("section#s4 h2")).toContainText("4 Murders of Andrew and Abby");
      await expect(page.locator("section#s5 h3")).toContainText("5 Thursday, August 4, 1892");
      await expect(page.locator("section#s5 h2")).toHaveCount(0);
      await expect(page.locator("section#s4 h2")).toHaveCount(1);
      // A heading-only parent says where its text is instead of claiming a gap.
      await expect(page.locator("section#s4 p").first()).toContainText(
        "heading only, its text is in the subsections that follow",
      );
      await expect(page.locator("section#s4").getByRole("note")).toHaveCount(0);
      const wide = (page.viewportSize()?.width ?? 0) >= 1340;
      const nav = page.locator(wide ? 'nav[aria-label="Contents"]' : 'nav[aria-label="Sections"]');
      if (wide) {
        const parent = await nav.locator('a[href$="#s4"] span').first().boundingBox();
        const child = await nav.locator('a[href$="#s5"] span').first().boundingBox();
        expect(child!.x - parent!.x).toBeGreaterThanOrEqual(11);
        await expect(nav.locator("li[data-depth='2']").first()).toContainText(
          "5 Thursday, August 4, 1892",
        );
        await expect(nav.locator("li[data-depth='1']").nth(3)).toContainText(
          "4 Murders of Andrew and Abby",
        );
        await expect(nav.locator('a[href$="#s20"]')).toHaveCount(0);
      } else {
        await expect(nav.locator('a[href$="#s5"]')).toHaveAttribute("data-depth", "2");
        await expect(nav.locator('a[href$="#s4"]')).toHaveAttribute("data-depth", "1");
        await expect(nav.locator('a[href$="#s5"]')).toHaveAttribute(
          "title",
          "Murders of Andrew and Abby > Thursday, August 4, 1892",
        );
      }
    });
  });
});
