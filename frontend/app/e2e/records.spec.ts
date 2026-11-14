import type { Page } from "@playwright/test";
import { expect, lightOnly, test } from "./support";

/** The first h1 containing `text`. */
function titled(page: Page, text: string) {
  return page.getByRole("heading", { level: 1 }).filter({ hasText: text }).first();
}

lightOnly(() => {
  test("Dossiers has no freshness key beside the title; the chips carry the counts", async ({
    page,
    open,
  }) => {
    await open("/t", { ready: titled(page, "Dossiers") });
    await expect(page.getByRole("group", { name: "Dossier counts" })).toHaveCount(0);
    await expect(
      page.getByText("same revision as Wikipedia now").filter({ visible: true }),
    ).toHaveCount(0);
    await expect(page.getByRole("radio", { name: /^All \d+$/ })).toBeVisible();
  });

  test("Home counters use a 13px label and a 12px second line", async ({ page, open }) => {
    await open("/", { ready: titled(page, "Cited context") });
    const report = await page.getByRole("group", { name: "Today's counters" }).evaluate((root) =>
      [...root.querySelectorAll("[data-record-row]")].map((row) => {
        const [label, , value] = Array.from(row.children);
        const sub = row.parentElement!.querySelector("[data-record-sub]")!;
        return {
          labelSize: getComputedStyle(label!.firstElementChild!).fontSize,
          valueSize: getComputedStyle(value!).fontSize,
          subSize: getComputedStyle(sub).fontSize,
          overflow: row.scrollWidth > row.clientWidth,
        };
      }),
    );
    expect(report).toHaveLength(3);
    for (const row of report) {
      expect(row.labelSize).toBe("13px");
      expect(["18px", "15px"]).toContain(row.valueSize);
      expect(row.subSize).toBe("12px");
      expect(row.overflow).toBe(false);
    }
  });

  test.describe("normal records", () => {
    for (const { path, ready } of [
      { path: "/t/Jesus", ready: "Jesus" },
      { path: "/machines", ready: "For machines" },
    ]) {
      test(`stay 13px, ${path}`, async ({ page, open }) => {
        await open(path, { ready: titled(page, ready) });
        await expect(page.locator('[class~="@container"]:visible').first()).toBeVisible();
        const sizes = await page.evaluate(() => {
          const out: { value: string; height: number }[] = [];
          for (const root of document.querySelectorAll('[class~="@container"]')) {
            if (root.getBoundingClientRect().width === 0) {
              continue;
            }
            for (const row of root.children) {
              const cells = Array.from(row.children);
              const value = cells[2];
              if (value) {
                out.push({
                  value: getComputedStyle(value).fontSize,
                  height: row.getBoundingClientRect().height,
                });
              }
            }
          }
          return out;
        });
        expect(sizes.length).toBeGreaterThan(0);
        // Between 1024px and 1199px the source record beside the head uses 24px rows.
        const width = page.viewportSize()!.width;
        const minHeight = path.startsWith("/t/") && width >= 1024 && width < 1200 ? 24 : 32;
        for (const { value, height } of sizes) {
          expect(value).toBe("13px");
          expect(height).toBeGreaterThanOrEqual(minHeight);
        }
      });
    }
  });

  test("the graph badge is 12px", async ({ page, open }) => {
    await open("/", { ready: page.locator("svg[role='group']").first() });
    const badge = page.getByText(/\d+ nodes, \d+ edges/).first();
    expect(await badge.evaluate((el) => getComputedStyle(el).fontSize)).toBe("12px");
  });
});
