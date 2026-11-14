import type { Page } from "@playwright/test";
import { AxeBuilder } from "@axe-core/playwright";
import { readFixtureJson } from "./buildFixture";
import { dossierBody } from "./mockApi";
import { trackErrors, assertNoErrors, expectShellRendered } from "./errorTracking";
import { freshnessChip, mockFreshness, openJesus } from "./readingSection";
import { expect, lightOnly, only, settleScroll, test } from "./support";

const dossier = readFixtureJson<{
  sections: {
    id: string;
    label: string;
    label_source: string;
    summary_state: string;
    summary: unknown;
    chunk_ids: string[];
  }[];
  chunks: unknown[];
  build: { summaries_done: number; summaries_total: number };
}>("dossier_1095706_8000.json");
const dossierMarkdown = readFixtureJson<{ markdown: string }>("dossier_1095706_md.json").markdown;

const modelPanelCount = dossier.sections.filter(
  (s) => s.summary_state === "done" && s.summary != null,
).length;
// A section gets a summary line, in place of a model summary, unless it is the lead (the first section, or one labelled with the article title), already has a finished summary, or has no passages.
const summaryLineCount = dossier.sections.filter(
  (s, i) =>
    i !== 0 &&
    s.label_source !== "article_title" &&
    !(s.summary_state === "done" && s.summary != null) &&
    s.chunk_ids.length > 0,
).length;

const HEADINGS = 'section[id^="s"] [data-section-heading]';

/** Opens the Jesus dossier and waits until every section is on the page. */
const openAll = (page: Page, open: (path: string) => Promise<void>) =>
  openJesus(page, open, dossier.sections.length);

test.describe("Dossier page", () => {
  test("a stored dossier opens on a skeleton, never the Building panel, and the footer stays put", async ({
    page,
  }) => {
    const errors = trackErrors(page);
    // The server answers slowly, so the opening state stays on screen.
    await page.route(/\/api\/v1\/dossiers\/\d+(\?[^/]*)?$/, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 900));
      await route.fallback();
    });
    await page.goto("/t/Jesus");
    await expect(page.getByText("Opening this dossier...")).toBeVisible();
    await expect(page.getByText("Building", { exact: false })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Cancel" })).toHaveCount(0);
    // The footer must not enter the viewport on either side of the swap:
    // a skeleton shorter than the screen would put it in view and then
    // push it off, which is the layout shift this guards against.
    const footerTop = () => page.locator("footer").evaluate((el) => el.getBoundingClientRect().top);
    const viewportHeight = page.viewportSize()?.height ?? 0;
    expect(await footerTop()).toBeGreaterThanOrEqual(viewportHeight - 8);
    await expect(page.locator(HEADINGS)).toHaveCount(dossier.sections.length);
    expect(await footerTop()).toBeGreaterThanOrEqual(viewportHeight - 8);
    assertNoErrors(errors);
  });

  test(
    "a typed title that differs from the article title builds and ends on that article's dossier",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      const posted = page.waitForRequest(
        (request) => request.method() === "POST" && /\/api\/v1\/dossiers(\?|$)/.test(request.url()),
      );
      await open("/t/Kamchatka", {
        ready: page.getByRole("heading", { level: 1, name: "Kamchatka Peninsula" }),
      });
      expect((await posted).postDataJSON()).toMatchObject({ title: "Kamchatka" });
      await expect(page.locator(HEADINGS).first()).toBeVisible();
      assertNoErrors(errors);
    },
  );

  test(
    "the build record scopes the model summaries to the dossier's sections and says Ready",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await openAll(page, open);
      const main = page.locator("main");
      await expect(main.getByText("Model summaries", { exact: true })).toHaveCount(1);
      await expect(
        main.getByText(
          `${dossier.build.summaries_done} of ${dossier.sections.length} sections (${dossier.build.summaries_total} selected)`,
          { exact: true },
        ),
      ).toBeVisible();
      await expect(main.getByText("Summaries", { exact: true })).toHaveCount(0);
      await expect(main.getByText("Complete", { exact: true })).toHaveCount(0);
      assertNoErrors(errors);
    },
  );

  test(
    "renders all section labels in order, model panels and summary lines",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await openAll(page, open);

      const headings = await page.locator(HEADINGS).allTextContents();
      dossier.sections.forEach((section, index) => {
        expect(headings[index]).toContain(section.label);
      });

      await expect(page.locator("[data-model-panel]")).toHaveCount(modelPanelCount);
      await expect(page.locator('p[role="note"]')).toHaveCount(summaryLineCount);

      await expectShellRendered(page);
      assertNoErrors(errors);
    },
  );

  test(
    "one citation marker per revision per section, not per passage",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await openAll(page, open);

      const sections = page.locator('article section[id^="s"]');
      const sectionCount = await sections.count();
      let sectionsWithPassages = 0;
      for (let i = 0; i < sectionCount; i++) {
        const paragraphs = sections.nth(i).locator('[data-role="source-text"] p');
        const count = await paragraphs.count();
        if (count === 0) {
          continue;
        }
        sectionsWithPassages += 1;
        const markerCounts = await paragraphs.evaluateAll((els) =>
          els.map((el) => el.querySelectorAll("sup a").length),
        );
        // Every passage in the fixture cites the same pinned revision, so only the first passage of each section carries a citation marker.
        expect(markerCounts.filter((n) => n > 0)).toHaveLength(1);
        expect(markerCounts[0]).toBe(1);
      }
      expect(sectionsWithPassages).toBeGreaterThan(0);

      await expectShellRendered(page);
      assertNoErrors(errors);
    },
  );

  test(
    "budget keys switch the URL and re-fetch; 2k shows cut rows",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await openAll(page, open);

      await page.keyboard.press("1");
      await expect(page).toHaveURL(/budget=2000/);
      await expect(page.getByText(/passages left out at this budget/).first()).toBeVisible();
      await expect(page.getByText(/^.*: not shown\./).first()).toBeVisible();

      await page.keyboard.press("2");
      await expect(page).toHaveURL(/budget=8000/);

      await page.keyboard.press("3");
      await expect(page).toHaveURL(/budget=32000/);

      await expectShellRendered(page);
      assertNoErrors(errors);
    },
  );

  test("Copy as context copies the API's markdown and shows a toast", async ({
    page,
    context,
    open,
  }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    const errors = trackErrors(page);
    await openAll(page, open);

    // Below 600px the toolbar is hidden and the HUD stands in for it, so only one of the two buttons is visible.
    await page.getByRole("button", { name: /^Copy as context/ }).click();
    // The shared live region is always mounted, so waiting on its role
    // alone would resolve before the async clipboard write finishes; the
    // toast's own visibility is the real completion signal.
    await expect(page.getByTestId("toast")).toBeVisible();
    const clipboardText = await page.evaluate(() => navigator.clipboard.readText());
    expect(clipboardText).toBe(dossierMarkdown);

    await expectShellRendered(page);
    assertNoErrors(errors);
  });

  test("an unbuilt title shows the 404 panel with Did you mean entries", async ({ page, open }) => {
    const errors = trackErrors(page);

    await open("/t/Nonexistent_Title");
    await expect(page.getByText("No article by that title")).toBeVisible();
    await expect(page.getByText("Did you mean")).toBeVisible();
    await expect(page.getByText("Request ID: mock-not-found")).toBeVisible();
    await expect(page.getByRole("link", { name: "Jesus" })).toBeVisible();

    await expectShellRendered(page);
    // Chromium logs "Failed to load resource" independently for any 404; this mock 404 is expected
    expect(errors.console.filter((m) => !m.includes("Failed to load resource"))).toEqual([]);
    expect(errors.page).toEqual([]);
  });

  test("a not_found title shows the API did_you_mean as the lead link", async ({ page, open }) => {
    const errors = trackErrors(page);
    await page.route(/\/api\/v1\/search(\?[^/]*)?$/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ query: "Jesu", results: [], did_you_mean: "Jesus" }),
      });
    });
    await page.route(/\/api\/v1\/dossiers(\?[^/]*)?$/, async (route) => {
      if (route.request().method() !== "POST") {
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
          detail: 'No article titled "Jesu" on en.wikipedia.',
          code: "not_found",
          request_id: "test-request",
        }),
      });
    });
    await open("/t/Jesu");
    const hint = page.getByText("Did you mean");
    await expect(hint).toBeVisible();
    await expect(hint.getByRole("link", { name: "Jesus" })).toHaveAttribute("href", /\/t\/Jesus/);
    expect(errors.page).toEqual([]);
  });

  test(
    "a null checked_at reads not checked, never Invalid Date",
    only("mobile-390", "desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      // The recorded build is already unchecked, so the page first serves a checked one, which the edit must produce.
      let patch: Record<string, unknown> = {
        state: "fresh",
        source: "poll",
        edits_since: 0,
        checked_at: "2026-09-28T16:18:40Z",
      };
      await mockFreshness(page, "dossier_1095706_2000.json", () => patch);
      await open("/t/Jesus?budget=2000", { ready: page.locator(HEADINGS).first() });
      const chip = freshnessChip(page);
      const tip = page.getByRole("tooltip").filter({ visible: true });
      await expect(chip).toHaveText(/^Up to date/);
      patch = { state: "unknown", source: "poll", checked_at: null };
      await page.reload();
      await expect(page.locator(HEADINGS).first()).toBeVisible();
      await expect(chip).toHaveText(/^Not checked/);
      await chip.focus();
      await expect(tip).toContainText(/^Not checked yet\./);
      const text = (await page.locator("main").innerText()) + (await tip.innerText());
      expect(text).not.toMatch(/Invalid Date|\bNaN\b/);
      // A check from an earlier UTC day names its date; one from today names only the time.
      patch = {
        state: "fresh",
        source: "poll",
        edits_since: 0,
        checked_at: new Date(Date.now() - 31 * 3_600_000).toISOString(),
      };
      await page.reload();
      await expect(page.locator(HEADINGS).first()).toBeVisible();
      await chip.focus();
      await expect(tip).toContainText(/^Checked \d{4}-\d\d-\d\d, \d\d:\d\d UTC\./);
      patch = { ...patch, checked_at: new Date().toISOString() };
      await page.reload();
      await expect(page.locator(HEADINGS).first()).toBeVisible();
      await chip.focus();
      await expect(tip).toContainText(/^Checked \d\d:\d\d UTC\./);
      expect(errors.page).toEqual([]);
    },
  );

  test("has zero axe violations and no horizontal overflow", async ({ page, open }) => {
    const errors = trackErrors(page);
    await openAll(page, open);

    const hasOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    );
    expect(hasOverflow).toBe(false);

    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
    await expectShellRendered(page);
    assertNoErrors(errors);
  });

  test("header measures 56px at 1200 and up, 80px below", async ({ page, open }) => {
    const errors = trackErrors(page);
    await openAll(page, open);

    const width = page.viewportSize()?.width ?? 0;
    const header = await page.locator("header").boundingBox();
    expect(header?.height).toBe(width >= 1200 ? 56 : 80);

    await expectShellRendered(page);
    assertNoErrors(errors);
  });

  test("margin notes sit in the margin column at 900px and up, inline under their section below that", async ({
    page,
    open,
  }) => {
    const errors = trackErrors(page);
    await openAll(page, open);

    const width = page.viewportSize()?.width ?? 0;
    const inline = page.locator('section[id^="s"] [aria-label^="Source for"]');
    const columnList = page.locator('aside [aria-label^="Source for"]');
    if (width >= 900) {
      await expect(inline.first()).toBeHidden();
      await expect(columnList).toHaveCount(dossier.sections.length);
    } else {
      await expect(inline).toHaveCount(dossier.sections.length);
      await expect(inline.first()).toBeVisible();
    }

    await expectShellRendered(page);
    assertNoErrors(errors);
  });

  test(
    "token ruler ticks are level with their section headings at 1440",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await openAll(page, open);

      // Each section-start tick has the title "<index> <label> starts at token <n>".
      // The label part equals its heading's text, so ticks are matched to headings by text.
      // A heading-only section has no tick, so matching by array position would drift.
      const ticks = page.locator('span[title*=" starts at token "]');
      const tickCount = await ticks.count();
      expect(tickCount).toBeGreaterThan(0);

      const headingTexts = await page.locator(HEADINGS).allTextContents();
      let matched = 0;
      for (let i = 0; i < tickCount; i += 1) {
        const title = await ticks.nth(i).getAttribute("title");
        const label = title?.replace(/ starts at token [\d,]+$/, "");
        const headingIndex = label ? headingTexts.indexOf(label) : -1;
        if (headingIndex === -1) {
          continue; // The tick for the header, headings and summaries has no heading.
        }
        matched += 1;
        const heading = page.locator(HEADINGS).nth(headingIndex);
        const [headingBox, tickBox] = await Promise.all([
          heading.boundingBox(),
          ticks.nth(i).boundingBox(),
        ]);
        expect(headingBox).not.toBeNull();
        expect(tickBox).not.toBeNull();
        if (headingBox && tickBox) {
          // The label is centred on its tick by a -50% translate. Its box is 16px tall (12px text, 16px line height), so a centred label sits at most 8px from the tick.
          // One more pixel allows for rounding.
          expect(Math.abs(tickBox.y - headingBox.y)).toBeLessThanOrEqual(9);
        }
      }
      expect(matched).toBeGreaterThan(0);
      assertNoErrors(errors);
    },
  );

  test(
    "the section-chip strip marks the last section current once scrolled to the bottom",
    // The chip strip is replaced by the contents rail at 1340px and up.
    only("mobile-390", "tablet-768", "tablet-1024"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await openAll(page, open);

      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      await settleScroll(page);

      const lastSectionId = `s${dossier.sections.length}`;
      const lastChip = page.locator(`nav[aria-label="Sections"] a[href$="#${lastSectionId}"]`);
      await expect(lastChip).toHaveAttribute("aria-current", "location");

      assertNoErrors(errors);
    },
  );

  test.describe("a jump to a section", () => {
    lightOnly(() => {
      test(
        "a Contents click moves focus to the section heading and draws no ring",
        only("desktop-1440", "desktop-1920"),
        async ({ page, open }) => {
          await openAll(page, open);
          const link = page.locator('nav[aria-label="Contents"] a').nth(5);
          const id = (await link.getAttribute("href"))?.split("#")[1];
          await link.click();
          const heading = page.locator(`section#${id} [data-section-heading]`);
          await expect(heading).toBeFocused();
          expect(await heading.evaluate((el) => getComputedStyle(el).outlineStyle)).toBe("none");
          expect(await heading.getAttribute("tabindex")).toBe("-1");
          await settleScroll(page);
          const top = await heading.evaluate((el) => el.getBoundingClientRect().top);
          expect(top).toBeGreaterThanOrEqual(64);
          expect(top).toBeLessThanOrEqual(200);
        },
      );
    });

    test(
      "a section chip tap moves focus to the section heading",
      only("mobile-390"),
      async ({ page, open }) => {
        await openAll(page, open);
        const chip = page.locator('nav[aria-label="Sections"] a').nth(5);
        const id = (await chip.getAttribute("href"))?.split("#")[1];
        await chip.click();
        await expect(page.locator(`section#${id} [data-section-heading]`)).toBeFocused();
      },
    );
  });

  test(
    "the copy toast never sits under the bottom HUD at 390",
    // The HUD only renders below 600px; wider viewports have no bar to clip the toast.
    only("mobile-390"),
    async ({ page, context, open }) => {
      await context.grantPermissions(["clipboard-read", "clipboard-write"]);
      const errors = trackErrors(page);
      await openAll(page, open);

      await page.getByLabel("Token budget and copy").getByRole("button").click();
      const toast = page.getByTestId("toast");
      await expect(toast).toBeVisible();
      const [toastBox, hudBox] = await Promise.all([
        toast.boundingBox(),
        page.getByRole("toolbar", { name: "Token budget and copy" }).boundingBox(),
      ]);
      expect(toastBox).not.toBeNull();
      expect(hudBox).not.toBeNull();
      if (toastBox && hudBox) {
        expect(toastBox.y + toastBox.height).toBeLessThanOrEqual(hudBox.y);
      }
      assertNoErrors(errors);
    },
  );

  test(
    "one GET per page and budget, no duplicate fetch on mount",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      await page.clock.install();
      let getCount = 0;
      await page.route(/\/api\/v1\/dossiers\/\d+(\?[^/]*)?$/, async (route) => {
        if (route.request().method() === "GET") {
          getCount += 1;
        }
        await route.fallback();
      });
      await openAll(page, open);
      // A refetch that a timer would start has to start within this time.
      await page.clock.runFor(1_000);

      expect(getCount).toBe(1);
      assertNoErrors(errors);
    },
  );

  test(
    "a lead with a model summary shows it, and one without says so",
    only("desktop-1440"),
    async ({ page, open }) => {
      const errors = trackErrors(page);
      // No recorded lead carries a model summary, so the lead of a Jesus build
      // gets the summary the build recorded for its "Comparative structure
      // and content" section.
      const withLeadSummary = readFixtureJson<{
        sections: { summary: { text: string } | null; summary_state: string }[];
      }>("dossier_1095706_32000.json");
      const donor = withLeadSummary.sections.find((s) => s.summary != null);
      withLeadSummary.sections[0]!.summary = donor?.summary ?? null;
      withLeadSummary.sections[0]!.summary_state = "done";
      const leadSummary = withLeadSummary.sections[0]?.summary;
      expect(leadSummary?.text).toBeTruthy();
      await page.route(/\/api\/v1\/dossiers\/1095706(\?[^/]*)?$/, async (route) => {
        if (new URL(route.request().url()).searchParams.get("budget") === "32000") {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: dossierBody("dossier_1095706_32000.json", (flat) => {
              flat["sections"] = withLeadSummary.sections;
            }),
          });
          return;
        }
        await route.fallback();
      });

      await open("/t/Jesus?budget=32000");
      const lead = page.locator('article section[id="s1"]');
      await expect(lead.getByText(leadSummary?.text ?? "", { exact: false })).toBeVisible();
      await expect(lead.locator("[data-model-panel]")).toHaveCount(1);
      await expect(lead).not.toContainText("no model summary");

      await open("/t/Jesus?budget=8000");
      const plainLead = page.locator('article section[id="s1"]');
      await expect(plainLead).toContainText("the lead has no model summary");
      await expect(plainLead.locator("[data-model-panel]")).toHaveCount(0);
      assertNoErrors(errors);
    },
  );
});

lightOnly(() => {
  test("section meta names the group as N of M", async ({ page, open }) => {
    await open("/t/Jesus");
    const meta = page.locator("section[id^='s'] p", { hasText: "Wikipedia section:" });
    await expect(meta.first()).toBeVisible();
    const texts = await meta.allInnerTexts();
    const grouped = texts.filter((t) => /passages (in group|split across groups)/.test(t));
    expect(grouped.length).toBeGreaterThan(0);
    for (const t of grouped) {
      expect(t).toMatch(
        /passages (in group \d+|split across groups \d+(, \d+)*( and \d+)?) of \d+/,
      );
    }
  });

  test(
    "section meta hides a zero token offset on a phone",
    only("mobile-390"),
    async ({ page, open }) => {
      await open("/t/Jesus");
      const meta = page.locator("section[id^='s'] p", { hasText: "Wikipedia section:" });
      await expect(meta.first()).toBeVisible();
      const texts = await meta.allInnerTexts();
      // The first section starts at token 0, so a phone does not say so.
      await expect(meta.first()).not.toContainText("at 0 tokens");
      expect(texts.slice(1).some((t) => /, at [\d,]+ tokens/.test(t))).toBe(true);
    },
  );
});
