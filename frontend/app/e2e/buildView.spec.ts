import type { Page } from "@playwright/test";
import { AxeBuilder } from "@axe-core/playwright";
import { freeze, readFixtureJson } from "./buildFixture";
import { mockApi } from "./mockApi";
import { eachTheme, expect, lightOnly, settleLayout, test } from "./support";

async function h1Box(page: Page) {
  const box = await page.getByRole("heading", { level: 1 }).boundingBox();
  const size = await page
    .getByRole("heading", { level: 1 })
    .evaluate((el) => getComputedStyle(el).fontSize);
  return { y: box!.y, size };
}

eachTheme(() => {
  test("the building page is the finished page's head over one list of steps", async ({ page }) => {
    await freeze(page, { done: 7, total: 12 }, 700);
    await page.goto("/t/Jesus");
    await expect(page.getByText("Opening this dossier...")).toBeVisible();
    const opening = await h1Box(page);
    await expect(page.getByText("Building this dossier now.")).toBeVisible();
    await expect(page.getByText("7 of 12 steps")).toBeVisible();
    await settleLayout(page);
    const width = page.viewportSize()!.width;
    const building = await h1Box(page);
    expect(building).toEqual(opening);
    expect(building.size).toBe(width >= 1024 ? "44px" : "36px");

    const report = await page.evaluate(() => {
      const ol = document.querySelector("ol")!;
      const olRight = ol.getBoundingClientRect().right;
      const rows = [...ol.querySelectorAll("li")].map((li) => {
        const [, , leader, value] = Array.from(li.children);
        const l = leader!.getBoundingClientRect();
        const v = value!.getBoundingClientRect();
        return {
          leaderRight: l.right,
          leaderWidth: l.width,
          valueRight: v.right,
          valueLeft: v.left,
          height: li.getBoundingClientRect().height,
          overflow: li.scrollWidth > li.clientWidth,
        };
      });
      const lede = document.querySelector("h1 ~ p")!;
      const ledeStyle = getComputedStyle(lede);
      const footer = document.querySelector("footer")?.getBoundingClientRect();
      return {
        olRight,
        rows,
        ledeFont: ledeStyle.fontFamily,
        ledeWidth: lede.getBoundingClientRect().width,
        ledeSize: ledeStyle.fontSize,
        bars: document.querySelectorAll(".animate-pulse").length,
        scrollWidth: document.documentElement.scrollWidth,
        docHeight: document.documentElement.scrollHeight,
        footerTop: footer?.top ?? null,
        inner: { w: window.innerWidth, h: window.innerHeight },
        pageWidthOk: document.documentElement.scrollWidth === window.innerWidth,
      };
    });
    expect(report.rows).toHaveLength(8);
    await expect(page.locator("ol")).not.toContainText(/\d\d:\d\d/);
    for (const row of report.rows) {
      expect(Math.abs(row.leaderRight - report.rows[0]!.leaderRight)).toBeLessThanOrEqual(0.5);
      expect(row.leaderWidth).toBeGreaterThanOrEqual(120);
      expect(Math.abs(row.valueRight - report.olRight)).toBeLessThanOrEqual(0.5);
      expect(row.valueLeft).toBeGreaterThanOrEqual(row.leaderRight - 0.5);
      expect(row.overflow).toBe(false);
      expect(Math.abs(row.height - 26)).toBeLessThanOrEqual(1);
    }
    expect(report.pageWidthOk).toBe(true);
    expect(report.ledeFont).toContain("Newsreader");
    expect(report.ledeSize).toBe(width >= 1024 ? "18px" : "16px");
    expect(report.ledeWidth).toBeLessThanOrEqual(660.5);
    expect(report.bars).toBeGreaterThanOrEqual(3);
    expect(report.docHeight).toBeGreaterThanOrEqual(report.inner.h);
    if (report.footerTop !== null) {
      expect(report.footerTop).toBeGreaterThanOrEqual(report.inner.h);
    }

    // The status is a line, not a button; Cancel is the only button in the page body.
    const status = page.getByRole("status").filter({ hasText: /Building/ });
    await expect(status).toHaveText("Building, sections streaming in");
    // The status is a plain line, not a ninth step: it has no bullet and sits clear of the list of steps.
    await expect(status.locator("span")).toHaveCount(0);
    const gap = await status.evaluate((el) => {
      const ol = document.querySelector("ol")!.getBoundingClientRect();
      return el.getBoundingClientRect().top - ol.bottom;
    });
    expect(gap).toBeGreaterThanOrEqual(16);
    await expect(page.getByRole("main").getByRole("button")).toHaveCount(1);
    await expect(page.getByRole("button", { name: "Cancel" })).toBeVisible();

    const axe = await new AxeBuilder({ page }).analyze();
    expect(axe.violations).toEqual([]);
  });
});

lightOnly(() => {
  test("the building head sits where the finished head sits", async ({ page, open }) => {
    await freeze(page);
    await open("/t/Jesus", { ready: page.getByText("Building this dossier now.") });
    const crumb = await page.getByRole("navigation", { name: "Breadcrumb" }).boundingBox();
    const building = await h1Box(page);
    // The same page once the dossier exists.
    await page.unrouteAll();
    await mockApi(page);
    await open("/t/Jesus", { ready: page.locator('section[id^="s"] h2').first() });
    const finishedCrumb = await page.getByRole("navigation", { name: "Breadcrumb" }).boundingBox();
    const finished = await h1Box(page);
    expect(finished.size).toBe(building.size);
    expect(Math.abs(finished.y - building.y)).toBeLessThanOrEqual(1);
    expect(Math.abs(finishedCrumb!.y - crumb!.y)).toBeLessThanOrEqual(1);
  });
});

test("a build polled while running shows its step count and the streaming status", async ({
  page,
  open,
}) => {
  const running = readFixtureJson<{ id: string; progress: { done: number; total: number } }>(
    "job_running_partial.json",
  );
  await page.route(/\/api\/v1\/dossiers\/(\d+)(\?[^/]*)?$/, async (route) => {
    if (route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 404,
      contentType: "application/problem+json",
      body: JSON.stringify({
        type: "about:blank",
        title: "Not Found",
        status: 404,
        detail: "No dossier has been built for page 662.",
        code: "not_built",
        request_id: "spec-build-view-apollo",
      }),
    });
  });
  await page.route(/\/api\/v1\/dossiers(\?[^/]*)?$/, async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      headers: { location: `/api/v1/jobs/${running.id}` },
      body: JSON.stringify({ ...running, status: "queued", stage: "resolve" }),
    });
  });
  await open("/");
  await page.getByLabel("Build a dossier for a topic").fill("Apollo 11");
  await page.getByRole("button", { name: "Build" }).click();
  await expect(page).toHaveURL(/\/t\/Apollo_11/);
  await expect(page.getByRole("status").filter({ hasText: /Building/ })).toHaveText(
    "Building, sections streaming in",
  );
  await expect(
    page.getByText(`${running.progress.done} of ${running.progress.total} steps`),
  ).toBeVisible();
  await expect(page.getByText(`Job ${running.id}`)).toBeVisible();
});
