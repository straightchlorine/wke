import type { Page } from "@playwright/test";
import { test, expect, only } from "./support";
import { freshnessRow, mockFreshness } from "./readingSection";
import { trackErrors, assertNoErrors } from "./errorTracking";

// Words that must not appear in the page's text, tooltips or aria-labels.
// Class names and data attributes are not checked.
const RETIRED = [
  /\bwatcher\b/i,
  /\bheld back\b/i,
  /\bcosine\b/i,
  /\bClustered\b/,
  /\bclustering\b/i,
  /\bcached\b/i,
  /\bBuilt to\b/,
];

/** Opens the info tooltips, then returns the page text with every tooltip and aria-label. */
async function readerText(page: Page): Promise<string> {
  for (const dot of await page
    .locator("main button[aria-label^='About'], main button[aria-label^='How to']")
    .all()) {
    await dot.focus();
  }
  return page.evaluate(
    () =>
      document.body.innerText +
      "\n" +
      Array.from(document.querySelectorAll("[role=tooltip]"))
        .map((el) => el.textContent)
        .join("\n") +
      "\n" +
      Array.from(document.querySelectorAll("[aria-label]"))
        .map((el) => el.getAttribute("aria-label"))
        .join("\n"),
  );
}

// The copy does not vary with width, so these run once, on the 1440 project.
test.describe("Reader-facing copy", only("desktop-1440"), () => {
  test("Home shows none of the banned words and dates its caption by day", async ({
    page,
    open,
  }) => {
    const errors = trackErrors(page);
    await open("/", { ready: page.locator("svg[role='group']").first() });
    const text = await readerText(page);
    for (const word of RETIRED) {
      expect(text, String(word)).not.toMatch(word);
    }
    await expect(page.locator("main")).toContainText("Dossiers stored");
    await expect(page.locator("main")).not.toContainText("packed chunks");
    await expect(page.locator("main")).toContainText("sections, citations and passages");
    await expect(page.locator("main")).toContainText("sections grouped by topic");
    const caption = page.locator("figcaption").first();
    await expect(caption).toContainText("Plate 1.");
    await expect(caption).not.toContainText(/\d{4}/);
    await expect(
      page.getByRole("heading", { level: 2 }).filter({ hasText: /^Most read/ }),
    ).toContainText(/\d{4}/);
    assertNoErrors(errors);
  });

  test("dossier: no leaked words, one contentinfo landmark outside main, in both states", async ({
    page,
    open,
  }) => {
    const errors = trackErrors(page);
    await open("/t/Jesus", {
      ready: page.locator('section[id^="s"] [data-section-heading]').first(),
    });
    const navs = page.locator('nav[aria-label="Contents"], nav[aria-label="Sections"]');
    await expect(navs).toHaveCount(2);
    await expect(page.locator('nav[aria-label="Contents"] a').first()).toBeVisible();
    const body = page.locator("main");
    await expect(body).not.toContainText("seed article");
    await expect(body).not.toContainText("the lead is its own");
    await expect(body).not.toContainText(
      "Wikipedia Knowledge Explorer turns one Wikipedia article",
    );
    await expect(navs.getByText("heading", { exact: true })).toHaveCount(0);
    await expect(page.locator("section#s1")).toContainText("the lead has no model summary");
    await expect(
      page.locator('figure:has-text("Plate 1.") [role="tooltip"]').filter({ hasText: "Method" }),
    ).toContainText("similarity to this article");
    const footer = page.getByRole("contentinfo");
    await expect(footer).toHaveCount(1);
    await expect(footer).toContainText("Jesus");
    expect(await footer.evaluate((el) => el.closest("main") === null)).toBe(true);
    await page.getByRole("link", { name: "Dossiers", exact: true }).first().click();
    await expect(page.getByRole("contentinfo")).toHaveCount(1);
    assertNoErrors(errors);
  });

  test("the dossier shows none of the banned words and says Up to date", async ({ page, open }) => {
    const errors = trackErrors(page);
    await mockFreshness(page, "dossier_1095706_2000.json", {
      state: "fresh",
      source: "poll",
      edits_since: 0,
      checked_at: "2026-09-29T12:00:00Z",
    });
    await open("/t/Jesus?budget=2000", {
      ready: page.locator('section[id^="s"] [data-section-heading]').first(),
    });
    await expect(freshnessRow(page).getByRole("button", { name: "Up to date" })).toBeVisible();
    const text = await readerText(page);
    for (const word of RETIRED) {
      expect(text, String(word)).not.toMatch(word);
    }
    expect(text).not.toContain("Current: built from the live revision");
    assertNoErrors(errors);
  });

  test("the dossier says no packer, no 0-of-0, no range of one value and no build time in the contents", async ({
    page,
    open,
  }) => {
    await open("/t/Lizzie_Borden", { ready: page.locator("article section[id]").first() });
    await expect(page.getByRole("heading", { level: 1 }).first()).toContainText("Lizzie Borden");
    const text = (await page.locator("main").textContent()) ?? "";
    expect(text).not.toMatch(/packer/i);
    expect(text).not.toMatch(/Passages\s*0 of 0/);
    expect(text).not.toMatch(/(\d\.\d\d) to \1\b/);
    expect(text).not.toMatch(/this 1 link/);
    await expect(page.getByText(/^built \d/)).toHaveCount(0);
    await expect(page.getByText(/\d+ of \d+ sections at \d+k/)).toHaveCount(0);
    await expect(page.getByText("About build log times")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "About the token count" })).toHaveCount(1);
  });

  test("the Dossiers table says Article, About Freshness and the 32k help", async ({
    page,
    open,
  }) => {
    await open("/t/");
    await expect(page.getByRole("columnheader", { name: "Article" })).toBeVisible();
    await page.getByLabel("About Fits in").first().focus();
    await expect(
      page.getByRole("tooltip").filter({ hasText: "do not fit even at 32k" }),
    ).toBeVisible();
  });

  test("a search suggestion badge reflects the real state", async ({ page, open }) => {
    await page.route(/\/api\/v1\/search(\?[^/]*)?$/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          query: "jesus",
          results: [
            { page_id: 1, title: "Jesus", description: null, dossier_state: "ready" },
            { page_id: 2, title: "Jesus in Islam", description: null, dossier_state: "partial" },
            { page_id: 3, title: "Christianity", description: null, dossier_state: "building" },
            {
              page_id: 4,
              title: "Apostles in the New Testament",
              description: null,
              dossier_state: "none",
            },
          ],
        }),
      });
    });
    await open("/");
    const box = page.getByRole("combobox", { name: "Build a dossier for a topic" });
    await box.click();
    await box.pressSequentially("jesus", { delay: 40 });
    const options = page.getByRole("option");
    await expect(options).toHaveCount(4);
    await expect(options.nth(0)).toContainText("Ready");
    await expect(options.nth(1)).toContainText("Partial");
    await expect(options.nth(2)).toContainText("Building");
    await expect(options.nth(3)).toContainText("Not built");
    await expect(options.nth(1)).not.toContainText(/\bready\b/);
  });
});
