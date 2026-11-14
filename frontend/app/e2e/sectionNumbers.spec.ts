import { readFixtureJson } from "./buildFixture";
import { dossierBody } from "./mockApi";
import { expect, only, test } from "./support";

// Jesus with its Manichaeism section emptied of prose: a hidden section
// in the middle of the list must leave no gap in the numbers a reader sees.

test(
  "visible sections, chips and Contents are numbered 1..N with a hidden section in the middle",
  only("mobile-390", "desktop-1440"),
  async ({ page, open }) => {
    const dossier = readFixtureJson<{
      sections: Array<{
        label: string;
        summary_state: string;
        chunk_ids: string[];
        summary?: unknown;
      }>;
    }>("dossier_1095706_8000.json");
    const hidden = dossier.sections.find((s) => s.label === "Manichaeism")!;
    hidden.summary_state = "no_prose";
    hidden.chunk_ids = [];
    hidden.summary = null;
    const body = dossierBody("dossier_1095706_8000.json", (flat) => {
      flat["sections"] = dossier.sections;
    });
    await page.route(/\/api\/v1\/dossiers\/1095706(\?[^/]*)?$/, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body }),
    );
    await open("/t/Jesus?budget=8000", {
      ready: page.locator("article section[id] [data-section-heading]").first(),
    });

    const headings = await page
      .locator("article section[id] [data-section-heading]")
      .evaluateAll((els) =>
        els
          .map((el) => ({ id: el.closest("section")!.id, text: (el.textContent ?? "").trim() }))
          .filter((h) => /^s\d+$/.test(h.id)),
      );
    const total = headings.length;
    expect(total).toBe(45);
    await expect(page.locator("article")).not.toContainText("Manichaeism");
    headings.forEach((h, i) => {
      expect(h.text.startsWith(`${i + 1} `)).toBe(true);
      expect(h.id).toBe(`s${i + 1}`);
    });
    for (const label of ["Contents", "Sections"]) {
      const nav = page.locator(`nav[aria-label="${label}"]`);
      if (!(await nav.isVisible())) {
        continue;
      }
      const links = await nav.locator("a[href*='#s']").evaluateAll((els) =>
        els.map((el) => ({
          href: el.getAttribute("href") ?? "",
          text: (el.textContent ?? "").trim(),
        })),
      );
      expect(links).toHaveLength(total);
      links.forEach((link, i) => {
        expect(link.text.startsWith(`${i + 1} `)).toBe(true);
        expect(link.href.endsWith(`#s${i + 1}`)).toBe(true);
      });
      await expect(nav).not.toContainText("Manichaeism");
    }
  },
);
