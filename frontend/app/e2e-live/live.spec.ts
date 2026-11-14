import type { APIResponse, Locator, Page } from "@playwright/test";
import { nearestHeading, stickyBottom, waitForBudget } from "../e2e/readingSection";
import { expect, only, settle, settleScroll, test } from "../e2e/support";

// Live checks against the real API through the preview proxy. Nothing is
// mocked, so every assertion has to hold for whatever the snapshot holds.
test.use({ mocked: false });

/** The dossier the Machines examples quote. */
const EXAMPLE_PAGE_ID = 1095706;
const SECTION_H2 = 'section[id^="s"] h2';
const APP_URL = /https?:\/\/[a-zA-Z0-9.-]+(?::\d+)?(?:\/(?:api|mcp|llms\.txt)[^\s'")]*)/g;

/** The first section heading, which shows once the dossier's text has loaded. */
const sectionsReady = (page: Page) => page.locator(SECTION_H2).first();

const PAGES: { name: string; path: string; ready: (page: Page) => Locator; copies: boolean }[] = [
  {
    name: "home",
    path: "/",
    ready: (page) => page.locator("svg[role='group']").first(),
    copies: true,
  },
  { name: "dossier", path: "/t/Lizzie_Borden", ready: sectionsReady, copies: true },
  {
    name: "dossiers",
    path: "/t",
    ready: (page) => page.locator("table tbody tr").first(),
    copies: false,
  },
  {
    name: "machines",
    path: "/machines",
    ready: (page) => page.getByRole("heading", { level: 1 }).first(),
    copies: true,
  },
];

/** Reads a JSON response as the shape the caller names; the caller owns that shape. */
// oxlint-disable-next-line typescript/no-unnecessary-type-parameters -- JSON has no checkable shape; the type parameter is the caller's claim about the response
function jsonOf<T>(response: APIResponse): Promise<T> {
  return response.json();
}

/** The text colour a span with the given class gets. */
function colourOf(page: Page, cls: string): Promise<string> {
  return page.evaluate((name) => {
    const el = document.createElement("span");
    el.className = name;
    document.body.appendChild(el);
    const colour = getComputedStyle(el).color;
    el.remove();
    return colour;
  }, cls);
}

/** The jump list that is on screen: the Contents rail from 1340px up, the section chips below. */
const jumpList = (page: Page) =>
  page.viewportSize()!.width >= 1340 ? 'nav[aria-label="Contents"]' : 'nav[aria-label="Sections"]';

/** The distance between the left edges of the wordmark and the first h1. */
async function wordmarkGap(page: Page): Promise<number> {
  const wordmarkX = await page
    .locator('a[aria-label^="WKE"]')
    .first()
    .evaluate((el) => el.getBoundingClientRect().x);
  const h1X = await page
    .locator("h1")
    .first()
    .evaluate((el) => el.getBoundingClientRect().x);
  return Math.abs(wordmarkX - h1X);
}

/** The distinct texts of the visible buttons that start with "Copy". */
function visibleCopyLabels(page: Page): Promise<string[]> {
  return page.evaluate(() =>
    Array.from(document.querySelectorAll("button"))
      .filter((b) => b.offsetParent !== null)
      .map((b) => b.innerText.trim().replace(/\s+/g, " "))
      .filter((t) => /^copy/i.test(t)),
  );
}

test.describe("anchor scrolling", () => {
  test(
    "a chip tap at 390 lands its section heading",
    only("mobile-390"),
    async ({ page, open }) => {
      await open("/t/Alan_Turing", { ready: sectionsReady(page) });
      const chip = page.locator('nav[aria-label="Sections"] a').nth(5);
      const id = (await chip.getAttribute("href"))?.split("#")[1];
      await chip.click();
      const heading = page.locator(`section#${id} [data-section-heading]`);
      await expect(heading).toBeInViewport();
      await settleScroll(page);
      const top = await heading.evaluate((el) => el.getBoundingClientRect().top);
      expect(Math.abs(top)).toBeLessThanOrEqual(200);
    },
  );

  test(
    "a Contents click at 1440 lands its section heading",
    only("desktop-1440"),
    async ({ page, open }) => {
      await open("/t/Alan_Turing", { ready: sectionsReady(page) });
      const link = page.locator('nav[aria-label="Contents"] a').nth(10);
      const id = (await link.getAttribute("href"))?.split("#")[1];
      await link.click();
      const heading = page.locator(`section#${id} [data-section-heading]`);
      await expect(heading).toBeInViewport();
      await settleScroll(page);
      const top = await heading.evaluate((el) => el.getBoundingClientRect().top);
      expect(top).toBeGreaterThanOrEqual(64);
      expect(top).toBeLessThanOrEqual(200);
    },
  );

  test("a Contents or chip jump lands the heading 16 px under the sticky bars", async ({
    page,
    open,
  }) => {
    await open("/t/Lizzie_Borden", { ready: sectionsReady(page) });
    await page.locator(`${jumpList(page)} a[href$="#s8"]`).click();
    await expect(page).toHaveURL(/#s8$/);
    await settleScroll(page);
    const top = await page
      .locator("section#s8 [data-section-heading]")
      .evaluate((el) => el.getBoundingClientRect().top);
    expect(Math.abs(top - ((await stickyBottom(page)) + 16))).toBeLessThanOrEqual(2);
  });

  test("a budget key keeps the section being read, before and after a jump", async ({
    page,
    open,
  }) => {
    await open("/t/Lizzie_Borden?budget=8000", { ready: sectionsReady(page) });
    const readOn = async (id: string) => {
      await page.evaluate(
        (i) =>
          window.scrollTo(
            0,
            document.getElementById(i)!.getBoundingClientRect().top + window.scrollY + 300,
          ),
        id,
      );
      await settleScroll(page);
    };
    await readOn("s5");
    const five = await nearestHeading(page);
    expect(five.n).toBe(5);
    await page.keyboard.press("1");
    await expect(page).toHaveURL(/budget=2000/);
    await waitForBudget(page, 2000);
    const afterKey = await nearestHeading(page);
    expect(afterKey.n).toBe(5);

    await page.keyboard.press("2");
    await waitForBudget(page, 8000);
    await page.locator(`${jumpList(page)} a[href$="#s8"]`).click();
    await expect(page).toHaveURL(/#s8$/);
    await settleScroll(page);
    const eight = await nearestHeading(page);
    expect(eight.n).toBe(8);
    await page.keyboard.press("1");
    await waitForBudget(page, 2000);
    const afterJump = await nearestHeading(page);
    expect(afterJump.n).toBe(8);
    expect(Math.abs(afterJump.top - eight.top)).toBeLessThanOrEqual(8);
  });

  test("the dossier has one contentinfo landmark and no Contents entry for a section without prose", async ({
    page,
    open,
  }) => {
    await open("/t/Lizzie_Borden", { ready: sectionsReady(page) });
    await expect(page.getByRole("contentinfo")).toHaveCount(1);
    await expect(page.getByRole("contentinfo")).toContainText("Lizzie Borden");
    await expect(
      page.locator('nav[aria-label="Contents"], nav[aria-label="Sections"]').first(),
    ).not.toContainText("no prose passages kept");
  });

  test("a section with no prose is left out of the page and the source record says so", async ({
    page,
    open,
  }) => {
    const idResponse = page.waitForResponse(
      (r) => /\/api\/v1\/dossiers\/\d+\?/.test(r.url()) && r.ok(),
    );
    await open("/t/Lord", { ready: sectionsReady(page) });
    const pageId = /\/dossiers\/(\d+)/.exec((await idResponse).url())![1];
    const api = await page.request.get(
      `/api/v1/dossiers/${pageId}?budget=8000&parts=dossier,metadata,sources`,
    );
    expect(api.ok()).toBe(true);
    type ApiSection = {
      label: string;
      summary_state: string;
      chunk_ids: string[];
      heading_path: string[];
    };
    const sections = (await jsonOf<{ dossier: { sections: ApiSection[] } }>(api)).dossier.sections;
    const noProse = (s: ApiSection) => s.summary_state === "no_prose" && s.chunk_ids.length === 0;
    // A parent with prose below it stays on the page, so only count a section whose whole subtree has none.
    const leftOut = sections.filter((s, i) => {
      if (!noProse(s)) {
        return false;
      }
      for (
        let j = i + 1;
        j < sections.length && sections[j]!.heading_path.length > s.heading_path.length;
        j += 1
      ) {
        if (!noProse(sections[j]!)) {
          return false;
        }
      }
      return true;
    });
    test.skip(
      leftOut.length === 0,
      `the /t/Lord dossier (page ${pageId}) has no section without prose right now`,
    );

    for (const section of leftOut) {
      const kept = sections.filter((s) => s.label === section.label && !leftOut.includes(s)).length;
      const rendered = page.locator("[data-section-heading]").filter({
        hasText: new RegExp(`^${section.label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`),
      });
      await expect(rendered, `"${section.label}" has no prose and is not a heading`).toHaveCount(
        kept,
      );
    }
    await expect(page.locator("article")).not.toContainText("No prose passages kept");
    const record = page.locator('[aria-labelledby="source-record-h"]');
    for (const summary of await record.locator("summary").all()) {
      if (await summary.isVisible()) {
        await summary.click();
      }
    }
    const line = record.locator("[data-record-row]:visible").filter({ hasText: /^Left out/ });
    const shown = Number(/(\d+) sections?$/.exec((await line.innerText()).trim())?.[1]);
    expect(shown).toBeGreaterThanOrEqual(leftOut.length);
    await record
      .getByRole("button", { name: "About the sections left out" })
      .locator("visible=true")
      .focus();
    await expect(page.getByRole("tooltip")).toContainText(
      /No prose, so left out \(lists and tables are not extracted\): /,
    );
    for (const section of leftOut) {
      await expect(page.getByRole("tooltip")).toContainText(section.label);
    }
  });

  test("a URL loaded with #s11 scrolls there after the content mounts", async ({ page, open }) => {
    await open("/t/Alan_Turing#s11", { ready: sectionsReady(page) });
    await expect(page.locator("section#s11 [data-section-heading]")).toBeInViewport();
  });

  test(
    "Back after a hash jump restores a smaller scroll position",
    only("desktop-1440"),
    async ({ page, open }) => {
      await open("/t/Alan_Turing", { ready: sectionsReady(page) });
      await page.locator('nav[aria-label="Contents"] a').nth(10).click();
      await expect(page.locator("section#s11 [data-section-heading]")).toBeInViewport();
      await settleScroll(page);
      const scrolledY = await page.evaluate(() => window.scrollY);
      expect(scrolledY).toBeGreaterThan(0);
      await page.goBack();
      await expect(page).not.toHaveURL(/#s11$/);
      await settleScroll(page);
      expect(await page.evaluate(() => window.scrollY)).toBeLessThan(scrolledY);
    },
  );

  test("a route change without a hash starts at the top with the h1 focused", async ({
    page,
    open,
  }) => {
    await open("/t/Alan_Turing", { ready: sectionsReady(page) });
    await page.evaluate(() => window.scrollTo(0, 2000));
    await settleScroll(page);
    await page
      .getByRole("navigation", { name: "Primary" })
      .getByRole("link", { name: "Dossiers" })
      .click();
    await expect(page).toHaveURL(/\/t\/?$/);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
    await expect(page.locator("main h1")).toBeFocused();
  });
});

test.describe("navigation and layout", () => {
  test("exactly one aria-current=page on Home, none on a dossier", async ({ page, open }) => {
    await open("/");
    await expect(page.locator('[aria-current="page"]')).toHaveCount(1);
    await open("/t/Alan_Turing", { ready: sectionsReady(page) });
    await expect(page.locator('[aria-current="page"]')).toHaveCount(0);
  });

  for (const p of PAGES) {
    test(`the h1 shares the wordmark's left edge on ${p.name}`, async ({ page, open }) => {
      await open(p.path);
      expect(await wordmarkGap(page)).toBeLessThan(0.5);
    });
  }

  test(
    "the h1 shares the wordmark's left edge at 768",
    only("desktop-1440"),
    async ({ page, open }) => {
      for (const p of PAGES) {
        await open(p.path, { viewport: { width: 768, height: 1024 } });
        expect(await wordmarkGap(page), p.name).toBeLessThan(0.5);
      }
    },
  );

  test(
    "Contents marks the current section after scrolling",
    only("desktop-1440"),
    async ({ page, open }) => {
      await open("/t/Lizzie_Borden", { ready: sectionsReady(page) });
      await page.mouse.wheel(0, 4000);
      await settleScroll(page);
      await expect(
        page.locator('nav[aria-label="Contents"] a[aria-current="location"]'),
      ).toHaveCount(1);
    },
  );

  test(
    "the Contents rail fits the window and scrolls itself",
    only("desktop-1440"),
    async ({ page, open }) => {
      await open("/t/Lizzie_Borden", { ready: sectionsReady(page) });
      const rail = await page.locator('nav[aria-label="Contents"]').evaluate((el) => ({
        overflowY: getComputedStyle(el).overflowY,
        height: el.getBoundingClientRect().height,
        windowHeight: window.innerHeight,
      }));
      expect(rail.overflowY).toBe("auto");
      expect(rail.height).toBeLessThanOrEqual(rail.windowHeight - 88 + 1);
    },
  );

  test("the not-found heading uses the ink colour, not the error colour", async ({
    page,
    open,
  }) => {
    await open("/t/No_Such_Article_Xyz", {
      ready: page.getByRole("heading", { level: 1, name: "No article by that title" }),
    });
    const h1 = await page
      .locator("h1")
      .first()
      .evaluate((el) => getComputedStyle(el).color);
    expect(h1).toBe(await colourOf(page, "text-ink"));
    expect(h1).not.toBe(await colourOf(page, "text-stamp"));
  });

  test(
    "the dossier head leaves a dead band under 24px at 1440",
    only("desktop-1440"),
    async ({ page, open }) => {
      await open("/t/Lizzie_Borden", {
        ready: page.locator('[aria-labelledby="source-record-h"]'),
      });
      const band = await settle(page, () =>
        page.evaluate(() => {
          const h1 = document.querySelector("h1");
          const rec = document.querySelector('[aria-labelledby="source-record-h"]');
          if (!h1 || !rec) return null;
          const head = h1.closest("div");
          const last = head ? head.children[head.children.length - 1] : null;
          const bottom = last
            ? last.getBoundingClientRect().bottom
            : h1.getBoundingClientRect().bottom;
          return Math.max(0, rec.getBoundingClientRect().bottom - bottom);
        }),
      );
      expect(band).not.toBeNull();
      expect(band ?? 999).toBeLessThan(24);
    },
  );
});

test.describe("sizes and labels", () => {
  test.describe("on a touch screen at 390", only("mobile-390"), () => {
    test.use({ hasTouch: true, isMobile: true });

    test("every visible button and nav link is 44px tall", async ({ page, open }) => {
      for (const p of PAGES) {
        await open(p.path, { ready: p.ready(page) });
        const short = await page.evaluate(() =>
          Array.from(document.querySelectorAll("button, nav[aria-label='Primary'] a"))
            .filter((el) => el instanceof HTMLElement && el.offsetParent !== null)
            .map((el) => {
              const r = el.getBoundingClientRect();
              // A small button reaches 44px through a generated hit area.
              const reach = Math.max(
                parseFloat(getComputedStyle(el, "::before").height) || 0,
                parseFloat(getComputedStyle(el, "::after").height) || 0,
              );
              return {
                text: (el.textContent ?? "").trim().slice(0, 30),
                h: Math.max(r.height, reach),
                w: r.width,
              };
            })
            // The (i) glyph is a 14px mark with a 44px generated hit area.
            .filter((r) => r.h < 44 && r.w > 0 && !(r.text === "i" && r.w <= 14)),
        );
        expect(short, p.name).toEqual([]);
      }
    });
  });

  test(
    "Copy labels come from one scheme on every page",
    only("desktop-1440"),
    async ({ page, open }) => {
      const allowed = ["Copy", "Copy URL", "Copy config", "Copy as context"];
      for (const p of PAGES) {
        await open(p.path, { ready: p.ready(page) });
        if (p.copies) {
          await expect.poll(() => visibleCopyLabels(page), { message: p.name }).not.toEqual([]);
        }
        for (const label of await visibleCopyLabels(page)) {
          expect(allowed, `${p.name}: ${label}`).toContain(label);
        }
      }
    },
  );

  test(
    "Machines and the data panel quote one API origin",
    only("desktop-1440"),
    async ({ page, open }) => {
      const origins = new Set<string>();
      for (const path of ["/", "/t/Lizzie_Borden", "/machines"]) {
        await open(path);
        if (path === "/machines") {
          // The origin comes from the JSON example's links.self, which is
          // fetched when its section nears the viewport.
          await page.locator("section#json").scrollIntoViewIfNeeded();
          await expect(page.locator("section#json pre").last()).toContainText("HTTP/1.1 200 OK");
        }
        const text = await settle(page, () => page.evaluate(() => document.body.innerText));
        for (const m of text.matchAll(APP_URL)) origins.add(new URL(m[0]).origin);
      }
      expect(origins.size).toBeLessThanOrEqual(1);
    },
  );

  test(
    "Machines quotes one origin in the Base URL row and every code block before any scroll",
    only("desktop-1440"),
    async ({ page, request, open }) => {
      const dossier = await jsonOf<{ metadata: { links: { self: string } } }>(
        await request.get("/api/v1/dossiers/1208?budget=8000&parts=dossier,metadata,sources"),
      );
      const apiOrigin = new URL(dossier.metadata.links.self).origin;
      await open("/machines");
      const baseRow = page.locator("code", { hasText: /^https?:\/\// }).first();
      await expect(baseRow).toHaveText(apiOrigin);
      const blocks = await settle(page, () => page.locator("pre").allInnerTexts());
      const origins = new Set<string>([(await baseRow.innerText()).trim()]);
      for (const text of blocks) {
        for (const m of text.matchAll(APP_URL)) origins.add(new URL(m[0]).origin);
      }
      expect([...origins]).toEqual([apiOrigin]);
    },
  );

  test(
    "the Dossiers freshness segments end at the search input's right edge at 390",
    only("mobile-390"),
    async ({ page, open }) => {
      await open("/t", { ready: page.locator("table tbody tr").first() });
      const edges = await page.evaluate(() => {
        const input = document.querySelector("#dossier-filter")?.getBoundingClientRect();
        const group = document.querySelector("[role=radiogroup][aria-label=Freshness]");
        const labels = [...(group?.querySelectorAll("label") ?? [])].map(
          (l) => l.getBoundingClientRect().right,
        );
        return {
          input: input?.right ?? 0,
          group: group?.getBoundingClientRect().right ?? 0,
          lastLabel: Math.max(...labels),
        };
      });
      expect(Math.abs(edges.group - edges.input)).toBeLessThanOrEqual(1);
      expect(edges.lastLabel).toBeLessThanOrEqual(edges.group);
    },
  );

  test(
    "the Home graph has a node centre in each of 8 horizontal bands at 1440",
    only("desktop-1440"),
    async ({ page, open }) => {
      await open("/", {
        ready: page.locator("svg[role='group'] a > circle:first-of-type").first(),
      });
      const { height, centres } = await settle(page, () =>
        page.evaluate(() => {
          const svg = document.querySelector("svg[role='group']")!;
          const f = svg.getBoundingClientRect();
          return {
            height: f.height,
            centres: [...svg.querySelectorAll("a > circle:first-of-type")].map((c) => {
              const b = c.getBoundingClientRect();
              return b.top + b.height / 2 - f.top;
            }),
          };
        }),
      );
      const counts = Array.from({ length: 8 }, () => 0);
      for (const y of centres) {
        const band = Math.min(7, Math.max(0, Math.floor((y / height) * 8)));
        counts[band] = (counts[band] ?? 0) + 1;
      }
      expect(
        counts.every((n) => n > 0),
        `bands ${counts.join(",")}`,
      ).toBe(true);
    },
  );

  test(
    "the Machines examples carry the snapshot's trending date and the API's own values",
    only("desktop-1440"),
    async ({ page, request, open }) => {
      const res = await request.get("/api/v1/trending");
      expect(res.ok()).toBe(true);
      const date = (await jsonOf<{ date: string }>(res)).date;
      const dossier = await jsonOf<{ metadata: { id: string; build: { built_at: string } } }>(
        await request.get(
          `/api/v1/dossiers/${EXAMPLE_PAGE_ID}?budget=8000&parts=dossier,metadata,sources`,
        ),
      );
      await open("/machines");
      for (const id of ["llms", "json", "markdown"]) {
        await page.locator(`section#${id}`).scrollIntoViewIfNeeded();
      }
      const main = page.locator("main");
      await expect(main).toContainText(`snapshot ${date}`);
      // The llms.txt excerpt is the head of the file the API serves, so it opens with that file's own lines.
      const llms = (await (await request.get("/llms.txt")).text()).split("\n");
      await expect(page.locator("section#llms pre").last()).toContainText(llms[2]!);
      await expect(main).toContainText(`"id": "${dossier.metadata.id}"`);
      await expect(main).toContainText(`"built_at": "${dossier.metadata.build.built_at}"`);
      await expect(main).not.toContainText("captured");
    },
  );
});

test.describe("Home", () => {
  test("a short prefix offers the stored dossier first, Ready", async ({ page, open }) => {
    await open("/");
    const box = page.getByRole("combobox").first();
    await box.fill("Lizzie");
    const options = page.getByRole("option");
    await expect(options.first()).toBeVisible();
    await expect(options.first()).toContainText("Lizzie Borden");
    await expect(options.first()).toContainText("Ready");
    expect(await options.count()).toBeLessThanOrEqual(5);
    await expect(page.locator("#live-region")).toHaveText(/^\d suggestions?$/);
  });

  test(
    "the 390 graph has no overlapping nodes and a 12px inset",
    only("mobile-390"),
    async ({ page, open }) => {
      await open("/", { ready: page.locator("svg[role='group']").first() });
      const m = await settle(page, () =>
        page.evaluate(() => {
          const svg = document.querySelector("svg[role='group']");
          if (!svg) return null;
          const [, , w, h] = (svg.getAttribute("viewBox") ?? "0 0 0 0").split(" ").map(Number);
          const circles = Array.from(
            svg.querySelectorAll('circle:not([fill="none"]):not([data-plate-hit])'),
          )
            .map((c) => ({
              cx: Number(c.getAttribute("cx")),
              cy: Number(c.getAttribute("cy")),
              r: Number(c.getAttribute("r")),
            }))
            .filter((c) => c.r > 0);
          let inset = Infinity;
          let overlaps = 0;
          for (const c of circles)
            inset = Math.min(
              inset,
              c.cx - c.r,
              (w ?? 0) - c.cx - c.r,
              c.cy - c.r,
              (h ?? 0) - c.cy - c.r,
            );
          for (let i = 0; i < circles.length; i++) {
            for (let j = i + 1; j < circles.length; j++) {
              const a = circles[i]!;
              const b = circles[j]!;
              if (Math.hypot(a.cx - b.cx, a.cy - b.cy) < a.r + b.r - 0.5) overlaps++;
            }
          }
          return { count: circles.length, inset, overlaps };
        }),
      );
      expect(m).not.toBeNull();
      expect(m?.count).toBeGreaterThan(0);
      expect(m?.overlaps).toBe(0);
      expect(m?.inset ?? 0).toBeGreaterThanOrEqual(11.5);
    },
  );

  test('the Dossiers filter narrows the table and lists suggestions for "Liz"', async ({
    page,
    open,
  }) => {
    await open("/t", { ready: page.locator("table tbody tr").first() });
    const filter = page.getByRole("combobox", { name: "Filter dossiers by title" });
    const before = await page.locator("table tbody tr").count();
    await filter.fill("Liz");
    const list = page.getByRole("listbox", { name: "Suggested titles" });
    await expect(list.getByRole("option").first()).toBeVisible();
    expect(await list.getByRole("option").count()).toBeLessThanOrEqual(5);
    const rows = await page.locator("table tbody tr").allTextContents();
    expect(rows.length).toBeLessThanOrEqual(before);
    for (const row of rows) {
      expect(row.toLowerCase()).toContain("liz");
    }
    // Stored titles come first: any "Ready" row precedes every "not built yet" row.
    const texts = await list.getByRole("option").allTextContents();
    const firstUnbuilt = texts.findIndex((t) => t.includes("not built yet"));
    if (firstUnbuilt >= 0) {
      expect(texts.slice(firstUnbuilt).some((t) => t.includes("Ready"))).toBe(false);
    }
    await filter.press("Enter");
    await expect(page).toHaveURL(/\/t\?q=Liz/);
  });

  test("a graph node selects on the first Enter and opens its dossier on the second", async ({
    page,
    open,
  }) => {
    await open("/", { ready: page.locator("svg[role='group']").first() });
    const node = page.locator("svg[role='group'] a[tabindex='0']");
    const title = (await node.getAttribute("aria-label"))!.split(/, [\d,]+ views/)[0]!;
    const board = page.locator("[data-plate-board]");
    const idleHeight = (await board.boundingBox())!.height;
    // Keyboard focus previews the node on the board, with no label.
    await node.focus();
    await expect(board).toHaveAttribute("data-plate-board", "preview");
    await expect(page.locator("[data-plate-tag]")).toHaveCount(0);
    await page.keyboard.press("Enter");
    await expect(page.locator("[data-plate-ring]")).toHaveCount(1);
    await expect(board).toHaveAttribute("data-plate-board", "selected");
    await expect(board.locator("p").first()).toHaveText(title);
    expect((await board.boundingBox())!.height).toBe(idleHeight);
    await expect(page).toHaveURL(/\/$/);
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/t\/[^/?]+\?budget=\d+$/);
  });

  test(
    "the live edit table lists newest first and carries its marker row",
    only("desktop-1440"),
    async ({ page, open }) => {
      await open("/");
      // A first poll the server refuses (parallel specs share its rate limit) shows one paused line instead of the table.
      const panel = page.locator("[data-ledger-panel]");
      await expect(panel).toContainText(
        /listening since|no live edits|Live edits paused, retrying/,
      );
      const times = await page.evaluate(() =>
        Array.from(document.querySelectorAll("table tbody tr"))
          .filter((r) => r.querySelectorAll("td").length >= 3)
          .map((r) => (r.querySelector("td")?.textContent ?? "").trim()),
      );
      expect(times).toEqual(times.toSorted().toReversed());
    },
  );
});
