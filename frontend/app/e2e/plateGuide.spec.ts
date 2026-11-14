import { expect, lightOnly, only, test } from "./support";

// The caption says what the graph shows. The "How to read the plate" tooltip lists the encodings, one short row each.

// The pause flag stops the replayed edit rows, so nothing below the graph moves mid-test.
test.use({ paused: true });

const GUIDES = [
  {
    page: "Home",
    path: "/",
    lead: "Plate 1.",
    caption: /^Plate 1\. The \d+ most-read English Wikipedia articles( yesterday)?\.$/,
    rows: [
      ["Lines", "articles whose lead paragraphs are similar"],
      ["Hulls", "a group of articles joined by lines"],
      ["Colour", "which group an article is in"],
      ["Key", "point at a colour to outline its group"],
      ["Grey", "no line to any other article"],
      ["Size", "views (square root)"],
      ["Red ring", "edited in the last 60 s"],
      ["Method", "all-MiniLM-L6-v2 similarity, 0.35 or more"],
    ],
  },
  {
    page: "the dossier page",
    path: "/t/Lizzie_Borden",
    lead: "Plate 1.",
    caption:
      /^Plate 1\. \d+ articles Wikipedia search lists as similar\. Select a node to open its dossier\.$/,
    rows: [
      ["Size", "similarity to this article"],
      ["Lines", "each article's two most similar neighbours"],
      ["Hull", "the related set"],
      ["Method", "similarity 0.35 or more"],
    ],
  },
] as const;

lightOnly(() => {
  for (const guide of GUIDES) {
    test(
      `On ${guide.page}, the graph caption is one sentence and the (i) lists one line per encoding`,
      only("mobile-390", "desktop-1440"),
      async ({ page, open }, info) => {
        await open(guide.path, { ready: page.locator('svg[role="group"] a').first() });
        const figure = page.locator("figure", { hasText: guide.lead });
        const caption = figure.locator("figcaption");
        await expect(caption).toHaveText(guide.caption);
        await expect(figure).not.toContainText("square root).");
        const dot = figure.getByRole("button", { name: "How to read the plate" });
        await dot.scrollIntoViewIfNeeded();
        await dot.focus();
        const tip = figure.getByRole("tooltip").filter({ hasText: guide.rows[0][0] });
        await expect(tip).toBeVisible();
        const rows = tip.locator("dl > div");
        await expect(rows).toHaveCount(guide.rows.length);
        for (const [index, [label, value]] of guide.rows.entries()) {
          await expect(rows.nth(index).locator("dt")).toHaveText(label);
          await expect(rows.nth(index).locator("dd")).toHaveText(value);
          expect(value.split(" ").length, `${label} is at most 8 words`).toBeLessThanOrEqual(8);
        }
        const look = await tip.evaluate((el) => {
          const row = el.querySelector("dl > div")!;
          const rects = [...el.querySelectorAll("dl > div")].map((r) => r.getBoundingClientRect());
          return {
            width: el.getBoundingClientRect().width,
            font: getComputedStyle(row).fontSize,
            step: rects[1]!.top - rects[0]!.top,
            dtColor: getComputedStyle(row.querySelector("dt")!).color,
            ddColor: getComputedStyle(row.querySelector("dd")!).color,
            leader: getComputedStyle(row.querySelector("span")!).borderBottomStyle,
          };
        });
        expect(look.width).toBeLessThanOrEqual(info.project.name === "mobile-390" ? 358 : 320.5);
        expect(look.font).toBe("12px");
        expect(look.step).toBe(20);
        expect(look.leader).toBe("dotted");
        expect(look.dtColor).not.toBe(look.ddColor);
        await page.keyboard.press("Escape");
        await expect(tip).toBeHidden();
      },
    );
  }
});
