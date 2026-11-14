import type { Page } from "@playwright/test";
import { test, expect, eachTheme } from "./support";

const filter = (page: Page) => page.getByRole("combobox", { name: "Filter dossiers by title" });

eachTheme(() => {
  test(`the filter narrows the table and lists suggestions underneath`, async ({ page, open }) => {
    await open("/t", { ready: page.locator("table tbody tr").first() });
    const rowsBefore = await page.locator("table tbody tr").count();
    await filter(page).fill("Liz");
    await expect(page).toHaveURL(/q=Liz/);
    const rows = page.locator("table tbody tr");
    await expect(rows).not.toHaveCount(rowsBefore);
    for (const text of await rows.allTextContents()) {
      expect(text.toLowerCase()).toContain("liz");
    }
    const list = page.getByRole("listbox", { name: "Suggested titles" });
    await expect(list).toBeVisible();
    const count = await list.getByRole("option").count();
    expect(count).toBeGreaterThan(0);
    expect(count).toBeLessThanOrEqual(5);
    // In flow, under the narrowed table and a small heading, never over it.
    const table = (await page.locator("table").boundingBox())!;
    const box = (await list.boundingBox())!;
    expect(box.y).toBeGreaterThanOrEqual(table.y + table.height - 1);
    const heading = page.getByRole("heading", { name: "On Wikipedia" });
    await expect(heading).toBeVisible();
    const headingBox = (await heading.boundingBox())!;
    expect(headingBox.y).toBeGreaterThanOrEqual(table.y + table.height - 1);
    expect(headingBox.y).toBeLessThan(box.y);
    await expect(filter(page)).toHaveAttribute("aria-controls", (await list.getAttribute("id"))!);
    // Both counts reach the live region as one message.
    await expect(page.locator("#live-region")).toHaveText(
      new RegExp(`dossiers match, ${count} suggestions?$`),
    );
  });

  test(`the first table row's title stays visible while suggestions show`, async ({
    page,
    open,
  }) => {
    await open("/t", { ready: page.locator("table tbody tr").first() });
    await filter(page).fill("Liz");
    await expect(page.getByRole("listbox", { name: "Suggested titles" })).toBeVisible();
    const title = page.locator("table tbody tr").first().getByRole("link").first();
    await expect(title).toBeVisible();
    const covered = await title.evaluate((el) => {
      const r = el.getBoundingClientRect();
      const list = document.querySelector('[role="listbox"]')!.getBoundingClientRect();
      const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      const overlaps =
        r.left < list.right && r.right > list.left && r.top < list.bottom && r.bottom > list.top;
      return overlaps || top?.closest('[role="listbox"]') != null;
    });
    expect(covered).toBe(false);
    const list = (await page.getByRole("listbox", { name: "Suggested titles" }).boundingBox())!;
    const row = (await page.locator("table tbody tr").first().boundingBox())!;
    expect(list.y).toBeGreaterThanOrEqual(row.y + row.height - 1);
  });

  test(`arrows move through the rows, Enter opens the highlighted one`, async ({ page, open }) => {
    await open("/t", { ready: page.locator("table tbody tr").first() });
    await filter(page).fill("Liz");
    const options = page.getByRole("option");
    await expect(options.first()).toBeVisible();
    await filter(page).press("ArrowDown");
    await expect(options.first()).toHaveAttribute("aria-selected", "true");
    await filter(page).press("ArrowDown");
    await expect(options.nth(1)).toHaveAttribute("aria-selected", "true");
    await filter(page).press("ArrowUp");
    await expect(options.first()).toHaveAttribute("aria-selected", "true");
    const title = (await options.first().locator("span.truncate").first().textContent()) ?? "";
    await filter(page).press("Enter");
    await expect(page).toHaveURL(/\/t\/[^/?]+\?budget=\d+$/);
    expect(decodeURIComponent(page.url())).toContain(title.replace(/ /g, "_"));
  });

  test(`Enter with nothing highlighted keeps the filter`, async ({ page, open }) => {
    await open("/t", { ready: page.locator("table tbody tr").first() });
    await filter(page).fill("Liz");
    await expect(page.getByRole("option").first()).toBeVisible();
    await filter(page).press("Enter");
    await expect(page).toHaveURL(/\/t\?q=Liz/);
    await expect(filter(page)).toHaveValue("Liz");
  });

  test(`with no built match the rows replace the Build button and Clear filter stays`, async ({
    page,
    open,
  }) => {
    await open("/t", { ready: page.locator("table tbody tr").first() });
    await filter(page).fill("Zzyzx");
    const heading = page.getByRole("heading", { name: /No built dossier matches "Zzyzx"/ });
    await expect(heading).toBeVisible();
    const list = page.getByRole("listbox", { name: "Suggested titles" });
    await expect(list).toBeVisible();
    // The list sits in the panel, below its heading, not floating over the table.
    const panel = (await heading.boundingBox())!;
    const listBox = (await list.boundingBox())!;
    expect(listBox.y).toBeGreaterThan(panel.y);
    await expect(page.getByRole("link", { name: /Build a dossier for/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Clear filter" })).toBeVisible();
    await expect(page.locator("#live-region")).toHaveText(
      /0 of \d+ dossiers match, \d+ suggestions?$/,
    );
    await filter(page).press("ArrowDown");
    await expect(page.getByRole("option").first()).toHaveAttribute("aria-selected", "true");
    await page.getByRole("button", { name: "Clear filter" }).click();
    await expect(page).toHaveURL(/\/t\/?$/);
  });
});
