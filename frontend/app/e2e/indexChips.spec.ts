import { eachTheme, expect, only, test } from "./support";

eachTheme(() => {
  test(
    "Home most-read index: three columns per entry (title with its edits line, one-width Fits in badge, views), badge and views centred in the row",
    only("mobile-390", "desktop-1440"),
    async ({ page, open }, info) => {
      await open("/", { ready: page.getByRole("heading", { name: /^Most read/ }) });
      const rows = await page.evaluate(() =>
        [...document.querySelectorAll("ol > li")].map((li) => {
          const box = li.getBoundingClientRect();
          const badge = li.querySelector("[data-entry-chip]")?.firstElementChild ?? null;
          const views = li.querySelector("[data-entry-views]");
          const link = li.querySelector("a");
          const title = link?.firstElementChild ?? null;
          const meta = li.querySelector("[data-entry-meta]");
          const badgeBox = badge?.getBoundingClientRect();
          const viewsBox = views?.getBoundingClientRect();
          return {
            column: Math.round(box.left),
            rowCentre: box.top + box.height / 2,
            badgeCentre: badgeBox ? badgeBox.top + badgeBox.height / 2 : null,
            viewsCentre: viewsBox ? viewsBox.top + viewsBox.height / 2 : null,
            badgeLeft: badgeBox ? Math.round((badgeBox.left - box.left) * 10) / 10 : null,
            badgeWidth: badgeBox?.width ?? null,
            badgeAbsLeft: badgeBox?.left ?? 0,
            badgeText: badge?.textContent?.replace(/^Fits in /, "") ?? "",
            linkRight: link?.getBoundingClientRect().right ?? 0,
            viewsLeft: viewsBox?.left ?? 0,
            badgeRight: badgeBox?.right ?? 0,
            titleBottom: title?.getBoundingClientRect().bottom ?? 0,
            metaTop: meta?.getBoundingClientRect().top ?? 0,
            titleLeft: title?.getBoundingClientRect().left ?? 0,
            metaLeft: meta?.getBoundingClientRect().left ?? 0,
            overflow: li.scrollWidth > li.clientWidth + 1,
          };
        }),
      );
      expect(rows.length).toBeGreaterThan(10);
      const withBadge = rows.filter((r) => r.badgeLeft != null && /^\d+k$/.test(r.badgeText));
      expect(withBadge.length).toBeGreaterThan(5);
      expect(
        new Set(withBadge.map((r) => r.badgeText)).size,
        "2k, 8k and 32k are all in play",
      ).toBeGreaterThan(1);
      expect(
        new Set(withBadge.map((r) => r.badgeWidth)).size,
        "every budget badge has one width",
      ).toBe(1);
      for (const r of rows) {
        expect(r.overflow).toBe(false);
        expect(r.metaTop, "the edits line sits under the title").toBeGreaterThanOrEqual(
          r.titleBottom - 1,
        );
        expect(
          Math.abs(r.metaLeft - r.titleLeft),
          "edits line starts where the title does",
        ).toBeLessThanOrEqual(0.5);
        expect(r.linkRight, "the title column ends before the views column").toBeLessThanOrEqual(
          r.viewsLeft + 0.5,
        );
        expect(
          Math.abs(r.viewsCentre! - r.rowCentre),
          "views centred in the row",
        ).toBeLessThanOrEqual(1);
      }
      for (const r of withBadge) {
        expect(r.badgeLeft, `${r.badgeText} badge x`).toBe(withBadge[0]!.badgeLeft);
        expect(
          Math.abs(r.badgeCentre! - r.rowCentre),
          `${r.badgeText} badge centred in the row`,
        ).toBeLessThanOrEqual(1);
        expect(r.badgeRight, "the badge sits between the title and the views").toBeLessThanOrEqual(
          r.viewsLeft + 0.5,
        );
        expect(r.linkRight, "the title column ends before the badge").toBeLessThanOrEqual(
          r.badgeAbsLeft + 0.5,
        );
      }
      expect(new Set(rows.map((r) => r.column)).size).toBe(
        info.project.name === "mobile-390" ? 1 : 4,
      );
    },
  );

  test(
    "Dossiers index: the Fits in chips start on one x in every row",
    only("mobile-390", "desktop-1440"),
    async ({ page, open }) => {
      await open("/t", { ready: page.locator("tbody tr").first() });
      const lefts = await page.evaluate(() =>
        [...document.querySelectorAll("tbody tr")].map((tr) => {
          const chip = [...tr.querySelectorAll("td")]
            .map((td) => td.querySelector("span.rounded-1"))
            .find((el) => /\d+k$/.test((el?.textContent ?? "").trim()));
          return chip
            ? Math.round(
                (chip.getBoundingClientRect().left - tr.getBoundingClientRect().left) * 10,
              ) / 10
            : null;
        }),
      );
      const found = lefts.filter((x): x is number => x != null);
      expect(found.length).toBeGreaterThan(3);
      for (const x of found) {
        expect(x).toBe(found[0]);
      }
    },
  );
});
