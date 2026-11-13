import { eachTheme, expect, only, test } from "./support";

eachTheme(() => {
  test.describe("one statement per fact", only("mobile-390", "desktop-1440"), () => {
    test("dossier page: the build time lives in the source record only, the contents carry no budget caption", async ({
      page,
      open,
    }) => {
      await open("/t/Lizzie_Borden");
      await expect(page.getByRole("heading", { level: 1 }).first()).toContainText("Lizzie Borden");
      const body = page.locator("body");
      await expect(body.getByText(/^built \d/)).toHaveCount(0);
      await expect(body.getByText(/\d+ of \d+ sections at \d+k/)).toHaveCount(0);
      await expect(page.getByText("About build log times")).toHaveCount(0);
    });

    test("Home: the graph caption names the day, not the date; the heading keeps the date", async ({
      page,
      open,
    }) => {
      await open("/");
      const caption = page.locator("figcaption").first();
      await expect(caption).toContainText("Plate 1.");
      await expect(caption).not.toContainText(/\d{4}/);
      await expect(
        page.getByRole("heading", { level: 2 }).filter({ hasText: /^Most read/ }),
      ).toContainText(/\d{4}/);
    });

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
