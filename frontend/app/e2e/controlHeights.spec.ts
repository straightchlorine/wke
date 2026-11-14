import type { Locator } from "@playwright/test";
import { test, expect, lightOnly, only, VIEWPORTS } from "./support";

async function heights(locators: Locator[]): Promise<number[]> {
  return Promise.all(locators.map((l) => l.evaluate((el) => el.getBoundingClientRect().height)));
}

function expectOneHeight(label: string, values: number[], expected?: number) {
  const first = values[0]!;
  for (const v of values) {
    expect(Math.abs(v - first), `${label}: ${values.join(", ")}`).toBeLessThanOrEqual(0.5);
  }
  if (expected != null) {
    expect(first, label).toBe(expected);
  }
}

const DESKTOP = VIEWPORTS["desktop-1440"];
const PHONE = VIEWPORTS["mobile-390"];

// Every control in a row has the same visual height. The tests set their own
// viewport and pointer, so they run once, on the 1440 project.
test.describe("Control heights", only("desktop-1440"), () => {
  lightOnly(() => {
    test("Dossiers: the title filter equals the filter segments at 1440", async ({
      page,
      open,
    }) => {
      await open("/t", { viewport: DESKTOP });
      const input = page.getByRole("combobox", { name: "Filter dossiers by title" });
      const group = page.getByRole("radiogroup", { name: "Freshness" });
      await expect(group).toBeVisible();
      expectOneHeight("filter row", await heights([input, group]), 32);
    });

    test("Dossier toolbar: the budget selector equals its buttons at 1440", async ({
      page,
      open,
    }) => {
      await open("/t/Lizzie_Borden", { viewport: DESKTOP });
      const toolbar = page.locator("[data-dossier-toolbar]");
      await expect(toolbar).toBeVisible();
      const real = await toolbar.evaluate((el) =>
        [...el.querySelectorAll("button:not([aria-describedby]), [role=radiogroup]")].map(
          (c) => c.getBoundingClientRect().height,
        ),
      );
      expectOneHeight("toolbar row", real, 32);
      expect(real.length).toBeGreaterThanOrEqual(5);
    });

    test("Home: the search input and Build stay 44 px together at 1440", async ({ page, open }) => {
      await open("/", { viewport: DESKTOP });
      const form = page.locator("form").first();
      const input = form.getByRole("combobox");
      const build = form.getByRole("button", { name: /^(Build|Open)/ });
      expectOneHeight("home search row", await heights([input, build]), 44);
      expectOneHeight(
        "home budget row",
        await heights([page.getByRole("radiogroup", { name: "Token budget" })]),
        32,
      );
    });

    test.describe("on a touch screen", () => {
      test.use({ hasTouch: true, viewport: PHONE });

      test("390: one 44 px height per control row", async ({ page, open }) => {
        await open("/t/Lizzie_Borden");
        const hud = page.getByRole("toolbar", { name: "Token budget and copy" });
        await expect(hud).toBeVisible();
        expectOneHeight(
          "HUD row",
          await heights([
            hud.getByRole("radiogroup", { name: "Token budget" }),
            hud.getByRole("button", { name: /^Copy as context/ }),
          ]),
          44,
        );
        await open("/t");
        expectOneHeight(
          "dossiers 390 filter",
          await heights([
            page.getByRole("combobox", { name: "Filter dossiers by title" }),
            page.getByRole("radiogroup", { name: "Freshness" }),
          ]),
          44,
        );
        await open("/");
        const form = page.locator("form").first();
        expectOneHeight(
          "home search 390",
          await heights([
            form.getByRole("combobox"),
            form.getByRole("button", { name: /^(Build|Open)/ }),
          ]),
          44,
        );
      });
    });

    test("390 with a mouse: the HUD segments equal Copy as context", async ({ page, open }) => {
      await open("/t/Lizzie_Borden", { viewport: PHONE });
      const hud = page.getByRole("toolbar", { name: "Token budget and copy" });
      await expect(hud).toBeVisible();
      expectOneHeight(
        "HUD row",
        await heights([
          hud.getByRole("radiogroup", { name: "Token budget" }),
          hud.getByRole("button", { name: /^Copy as context/ }),
        ]),
      );
    });
  });
});
