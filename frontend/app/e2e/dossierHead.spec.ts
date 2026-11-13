import type { Page } from "@playwright/test";
import { readFixtureJson } from "./buildFixture";
import { eachTheme, expect, only, test } from "./support";

// The dossier head is the breadcrumb, the h1 and the lede, and nothing else:
// the revision, its date and the freshness live in the source record. On a
// desktop the breadcrumb sits above the left column only and the record starts
// level with the h1.

const VIEWPORTS = [
  [1920, 1080],
  [1440, 900],
  [1200, 900],
  [1024, 768],
  [390, 844],
] as const;

const firstSectionHeading = (page: Page) =>
  page.locator('section[id^="s"] [data-section-heading]').first();

test.describe("dossier head", only("desktop-1440"), () => {
  eachTheme(() => {
    for (const [width, height] of VIEWPORTS) {
      test(`at ${width}: no revision line, no chip, no pinned line under the lede; Freshness is a source record row; no dead band`, async ({
        page,
        open,
      }) => {
        await open("/t/Jesus", { viewport: { width, height } });
        await expect(page.locator("#source-record-h").first()).toBeAttached();
        const main = page.locator("main");
        await expect(main).not.toContainText(/From the lead, revision/);
        await expect(main).not.toContainText(/Pinned to revision/);

        const head = await page.evaluate(() => {
          const h1 = document.querySelector("main h1")!;
          const block = h1.parentElement!;
          const lede = h1.nextElementSibling!;
          const crumb = document.querySelector("main nav[aria-label=Breadcrumb]")!;
          const title = document.getElementById("source-record-h")!;
          // oxlint-disable-next-line unicorn/consistent-function-scoping -- the callback runs in the page, so its helpers cannot live outside it
          const visible = (el: Element) => el.getBoundingClientRect().width > 0;
          const chipsInBlock = [...block.querySelectorAll(".rounded-1, button")].filter(
            visible,
          ).length;
          const cs = getComputedStyle(lede);
          return {
            ledeText: lede.textContent ?? "",
            ledeIsLast: lede.nextElementSibling == null,
            chipsInBlock,
            // The block's own height, when the grid does not stretch it to the taller source record.
            blockBottom: (() => {
              block.style.alignSelf = "start";
              const bottom = block.getBoundingClientRect().bottom;
              block.style.alignSelf = "";
              return bottom;
            })(),
            ledeBottom: lede.getBoundingClientRect().bottom,
            recordBottom: title.closest("aside")!.getBoundingClientRect().bottom,
            clamp: cs.getPropertyValue("-webkit-line-clamp"),
            overflow: cs.overflow,
            ledeClipped: lede.scrollHeight > lede.clientHeight + 1,
            crumbTop: crumb.getBoundingClientRect().top,
            crumbBottom: crumb.getBoundingClientRect().bottom,
            h1Top: h1.getBoundingClientRect().top,
            ledeTop: lede.getBoundingClientRect().top,
            recordTop: title.closest("aside")!.getBoundingClientRect().top,
            titleTop: (title.closest("h2") ?? title).getBoundingClientRect().top,
            desktop: window.innerWidth >= 1024,
          };
        });
        expect(head.ledeText.length).toBeGreaterThan(20);
        expect(head.ledeIsLast, "the lede is the last thing in the head").toBe(true);
        expect(head.chipsInBlock, "no chip or control in the head").toBe(0);
        expect(
          head.blockBottom - head.ledeBottom,
          "nothing reserved under the lede",
        ).toBeLessThanOrEqual(1);
        expect(head.crumbBottom, "the breadcrumb sits above the title").toBeLessThanOrEqual(
          head.h1Top,
        );
        if (width >= 1440) {
          expect(
            Math.max(0, head.recordBottom - head.ledeBottom),
            "the record never runs past the lede by a band",
          ).toBeLessThan(24);
        } else if (width >= 1200) {
          expect(
            head.recordBottom - head.ledeBottom,
            "beside the head, the record ends within a few lines of the lede",
          ).toBeLessThanOrEqual(60);
        } else if (width >= 1024) {
          expect(
            head.recordBottom - head.ledeBottom,
            "the single-column record ends close to the lede",
          ).toBeLessThanOrEqual(85);
        }
        expect(head.clamp === "none" || head.clamp === "").toBe(true);
        expect(head.overflow).toBe("visible");
        expect(head.ledeClipped, "the lede is never cut").toBe(false);
        if (head.desktop) {
          expect(
            Math.abs(head.h1Top - head.titleTop),
            "the source record heading starts level with the h1",
          ).toBeLessThanOrEqual(1);
          expect(
            Math.abs(head.h1Top - head.recordTop),
            "the source record box starts level with the h1",
          ).toBeLessThanOrEqual(1);
          expect(
            head.recordTop,
            "the record starts below the breadcrumb, not at it",
          ).toBeGreaterThan(head.crumbBottom - 1);
        } else {
          expect(head.crumbTop).toBeLessThan(head.h1Top);
          expect(head.h1Top).toBeLessThan(head.ledeTop);
          expect(head.ledeTop, "stacked: breadcrumb, h1, lede, then the record").toBeLessThan(
            head.recordTop,
          );
        }

        if (width < 600) {
          await page.getByText("Full source record").click();
        }
        const rows = page.locator("[data-record-row]").filter({ visible: true });
        await expect(rows.filter({ hasText: /^Revision/ })).toHaveCount(1);
        await expect(rows.filter({ hasText: /^Revised/ })).toHaveCount(1);
        const freshness = rows.filter({ hasText: /^Freshness/ });
        await expect(freshness).toHaveCount(1);
        await expect(freshness.getByText(/^(Up to date|Not checked|Out of date)/)).toBeVisible();
        const leader = await freshness.evaluate((row) => {
          const probe = document.createElement("span");
          probe.style.cssText = "display:inline-block;width:0;height:0;vertical-align:baseline";
          row.firstElementChild!.append(probe);
          const baseline = probe.getBoundingClientRect().bottom;
          probe.remove();
          const dots = row.querySelector(":scope > span[aria-hidden]")!;
          return {
            baseline,
            leaderBottom: dots.getBoundingClientRect().bottom,
            style: getComputedStyle(dots).borderBottomStyle,
          };
        });
        expect(leader.style).toBe("dotted");
        expect(
          Math.abs(leader.leaderBottom - leader.baseline),
          "the Freshness leader sits on the baseline",
        ).toBeLessThanOrEqual(1);
      });
    }
  });

  // The id can only break after its colon, so a narrow column never leaves half a hash on each line.
  eachTheme(() => {
    for (const [width, height] of [
      [1440, 900],
      [1024, 768],
    ] as const) {
      test(`at ${width}: the dossier id takes at most two lines and breaks only after the colon`, async ({
        page,
        open,
      }) => {
        await open("/t/Jesus", { viewport: { width, height } });
        const id = page
          .locator("[data-record-row]")
          .filter({ hasText: "Dossier id" })
          .locator("span.font-mono:visible")
          .first();
        await expect(id).toBeVisible();
        const lines = await id.evaluate((el) => {
          const rows: Array<{ top: number; text: string }> = [];
          const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
          for (let node = walker.nextNode(); node; node = walker.nextNode()) {
            const text = node.textContent ?? "";
            for (let i = 0; i < text.length; i += 1) {
              const range = document.createRange();
              range.setStart(node, i);
              range.setEnd(node, i + 1);
              const top = Math.round(range.getBoundingClientRect().top);
              const last = rows[rows.length - 1];
              if (last && Math.abs(last.top - top) < 4) {
                last.text += text[i];
              } else {
                rows.push({ top, text: text[i] ?? "" });
              }
            }
          }
          return rows.map((r) => r.text);
        });
        expect(lines.length, lines.join(" / ")).toBeLessThanOrEqual(2);
        if (lines.length === 2) {
          expect(lines[0], "the first line ends at the colon").toMatch(/:$/);
        }
        expect(lines.join("")).toMatch(/^\d+@\d+:[0-9a-f]+$/);
      });
    }
  });

  test("a dossier without a short description shows its lead sentence, verbatim and unlabelled", async ({
    page,
    open,
  }) => {
    await open("/t/Jesus", { ready: firstSectionHeading(page) });
    const fixture = readFixtureJson<{
      topic: { description: string | null };
      sections: Array<{ chunk_ids: string[] }>;
      chunks: Array<{ id: string; text: string }>;
      citations: Array<{ pin: { rev_id: number } }>;
    }>("dossier_1095706_8000.json");
    expect(fixture.topic.description).toBeNull();
    const lead = fixture.chunks.find((c) => c.id === fixture.sections[0]?.chunk_ids[0])?.text ?? "";
    await expect(
      page.getByText(`From the lead, revision ${fixture.citations[0]?.pin.rev_id}`),
    ).toHaveCount(0);
    const lede = (await page.locator("main h1 + p").textContent()) ?? "";
    expect(lede.length).toBeGreaterThan(20);
    expect(lead.startsWith(lede)).toBe(true);
  });

  test("the dossier id is 12 px, never split mid-hash, and fits its row", async ({
    page,
    open,
  }) => {
    await open("/t/Lizzie_Borden", { ready: firstSectionHeading(page) });
    await page
      .locator("details")
      .evaluateAll((els) =>
        els.forEach((el) => el instanceof HTMLDetailsElement && (el.open = true)),
      );
    const id = page
      .locator("[data-record-row]")
      .filter({ hasText: "Dossier id" })
      .locator("span.font-mono:visible")
      .first();
    await expect(id).toBeVisible();
    expect(await id.evaluate((el) => getComputedStyle(el).fontSize)).toBe("12px");
    expect(await id.evaluate((el) => getComputedStyle(el).wordBreak)).toBe("normal");
    expect(
      await id.evaluate(
        (el) => (el.parentElement?.scrollWidth ?? 0) <= (el.parentElement?.clientWidth ?? 0) + 1,
      ),
    ).toBe(true);
  });

  test("Retrieved reads in the record date format", async ({ page, open }) => {
    await open("/t/Lizzie_Borden", { ready: firstSectionHeading(page) });
    const retrieved = await page
      .locator("[data-record-row]")
      .filter({ hasText: "Retrieved" })
      .first()
      .innerText();
    expect(retrieved).toMatch(/\d{4}-\d\d-\d\d, \d\d:\d\d UTC/);
  });
});
