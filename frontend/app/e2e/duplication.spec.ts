import { eachTheme, expect, only, test } from "./support";

eachTheme(() => {
  test.describe("one statement per fact", only("mobile-390", "desktop-1440"), () => {
    test("Dossiers: the per-row Not checked chip is quieter than the Up to date and Out of date chips", async ({
      page,
      open,
    }) => {
      await open("/t/");
      const quiet = page.locator("tbody").getByText("Not checked", { exact: true }).first();
      await expect(quiet).toBeVisible();
      const inkThree = await page.evaluate(() => {
        const probe = document.createElement("span");
        probe.className = "text-ink-3";
        document.body.append(probe);
        const color = getComputedStyle(probe).color;
        probe.remove();
        return color;
      });
      const style = await quiet.evaluate((el) => {
        const cs = getComputedStyle(el);
        return {
          color: cs.color,
          bg: cs.backgroundColor,
          height: el.getBoundingClientRect().height,
        };
      });
      expect(style.color).toBe(inkThree);
      expect(style.bg).toBe("rgba(0, 0, 0, 0)");
      const fits = await page
        .locator("tbody tr")
        .first()
        .locator("td")
        .nth(3)
        .locator("span")
        .first()
        .evaluate((el) => el.getBoundingClientRect().height);
      expect(Math.abs(style.height - fits)).toBeLessThanOrEqual(1);
    });
  });
});
