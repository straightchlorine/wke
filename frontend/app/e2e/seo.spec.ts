import type { Page } from "@playwright/test";
import { test, expect } from "./support";

async function themeColors(page: Page): Promise<string[]> {
  return page
    .locator('meta[name="theme-color"]')
    .evaluateAll((tags) => tags.map((tag) => tag.getAttribute("content") ?? ""));
}

async function paper(page: Page): Promise<string> {
  return page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue("--wke-paper").trim(),
  );
}

/** Returns the value's own properties as a record, or an empty one when it is not an object. */
function record(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? Object.fromEntries(Object.entries(value))
    : {};
}

interface Head {
  title: string;
  description: string | null;
  canonical: string | null;
  robots: string | null;
  ogType: string | null;
  ogUrl: string | null;
  modified: string | null;
  ldTypes: string[];
}

/** Reads the current head tags and the JSON-LD @type values found in script#ld-page. */
async function readHead(page: Page): Promise<Head> {
  return page.evaluate(() => {
    const { head } = document;
    const meta = (attr: string, key: string) =>
      head.querySelector(`meta[${attr}="${key}"]`)?.getAttribute("content") ?? null;
    const types: string[] = [];
    const collect = (node: unknown) => {
      if (Array.isArray(node)) {
        node.forEach(collect);
      } else if (node && typeof node === "object") {
        const type: unknown = Reflect.get(node, "@type");
        if (typeof type === "string") {
          types.push(type);
        }
        collect(Reflect.get(node, "@graph"));
      }
    };
    document.head
      .querySelectorAll("script#ld-page")
      .forEach((el) => collect(JSON.parse(el.textContent ?? "null")));
    return {
      title: document.title,
      description: meta("name", "description"),
      canonical: document.head.querySelector('link[rel="canonical"]')?.getAttribute("href") ?? null,
      robots: meta("name", "robots"),
      ogType: meta("property", "og:type"),
      ogUrl: meta("property", "og:url"),
      modified: meta("property", "article:modified_time"),
      ldTypes: types,
    };
  });
}

test.describe("Per-route metadata", () => {
  test("Home is a WebPage of the site, and the site node carries the SearchAction", async ({
    page,
    open,
  }) => {
    await open("/");
    await expect.poll(async () => (await readHead(page)).ldTypes).toEqual(["WebPage"]);
    const head = await readHead(page);
    expect(head.title).toBe("WKE: Wikipedia Knowledge Explorer");
    expect(head.canonical).toBe("https://wke.piotrkrzysztof.dev/");
    expect(head.robots).toBe("index,follow");
    expect(head.ogType).toBe("website");
    const site = await page.locator("script#ld-site").textContent();
    expect(site).toContain("https://wke.piotrkrzysztof.dev/?q={search_term_string}");
    expect(await page.locator("script#ld-site").count()).toBe(1);
  });

  test("Home prefills the search box from ?q", async ({ page, open }) => {
    await open("/?q=Jesus");
    await expect(page.getByRole("combobox")).toHaveValue("Jesus");
  });

  test("Home prefills the search box from an all-digit ?q", async ({ page, open }) => {
    await open("/?q=1984");
    await expect(page.getByRole("combobox")).toHaveValue("1984");
  });

  test("Dossiers has its own tags and no JSON-LD", async ({ page, open }) => {
    await open("/t/");
    await expect(page).toHaveTitle("Dossiers - WKE");
    const head = await readHead(page);
    expect(head.description).toContain("last seven days");
    expect(head.canonical).toBe("https://wke.piotrkrzysztof.dev/t/");
    expect(head.robots).toBe("index,follow");
    expect(head.ldTypes).toEqual([]);
  });

  test("Machines has its own tags and no JSON-LD", async ({ page, open }) => {
    await open("/machines");
    await expect(page).toHaveTitle("For machines - WKE");
    const head = await readHead(page);
    expect(head.canonical).toBe("https://wke.piotrkrzysztof.dev/machines");
    expect(head.robots).toBe("index,follow");
    expect(head.ldTypes).toEqual([]);
  });

  test("a loaded dossier is an indexable Article with a breadcrumb", async ({ page, open }) => {
    await open("/t/jesus");
    await expect(page).toHaveTitle("Jesus - WKE");
    await expect
      .poll(async () => (await readHead(page)).ldTypes)
      .toEqual(["Article", "BreadcrumbList"]);
    const head = await readHead(page);
    expect(head.canonical).toBe("https://wke.piotrkrzysztof.dev/t/Jesus");
    expect(head.ogUrl).toBe(head.canonical);
    expect(head.robots).toBe("index,follow");
    expect(head.ogType).toBe("article");
    expect(head.modified).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(head.description?.length).toBeGreaterThan(0);
    expect(head.description?.length).toBeLessThanOrEqual(155);
    expect(head.description).not.toContain("cited dossier");

    const ld = record(JSON.parse((await page.locator("script#ld-page").textContent()) ?? "null"));
    const graph = ld["@graph"];
    const article = Array.isArray(graph) ? record(graph[0]) : {};
    expect(article["datePublished"]).toBe(head.modified);
    expect(article["dateModified"]).toBe(head.modified);
    expect(article["isBasedOn"]).toMatch(
      /^https:\/\/en\.wikipedia\.org\/w\/index\.php\?oldid=\d+$/,
    );
    expect(article["license"]).toBe("https://creativecommons.org/licenses/by-sa/4.0/");
  });

  test("the dossier JSON-LD is removed when leaving the page", async ({ page, open }) => {
    await open("/t/Jesus");
    await expect(page.locator("script#ld-page")).toHaveCount(1);
    await page.getByRole("link", { name: /^WKE/ }).first().click();
    await expect(page).toHaveTitle("WKE: Wikipedia Knowledge Explorer");
    await expect.poll(async () => (await readHead(page)).ldTypes).toEqual(["WebPage"]);
  });

  test("an unbuilt dossier is noindex and has no canonical", async ({ page, open }) => {
    await open("/t/Nonexistent_Title");
    await expect(page.getByText("No article by that title")).toBeVisible();
    await expect.poll(async () => (await readHead(page)).robots).toBe("noindex,follow");
    const head = await readHead(page);
    expect(head.canonical).toBeNull();
    expect(head.ogUrl).toBeNull();
    expect(head.ldTypes).toEqual([]);
  });

  test("an unknown path is noindex, titled Page not found and has no canonical", async ({
    page,
    open,
  }) => {
    await open("/nope");
    await expect(page).toHaveTitle("Page not found - WKE");
    const head = await readHead(page);
    expect(head.robots).toBe("noindex,follow");
    expect(head.canonical).toBeNull();
    expect(head.ldTypes).toEqual([]);
  });

  test("noindex does not leak from a not-found page to the next route", async ({ page, open }) => {
    await open("/nope");
    await expect.poll(async () => (await readHead(page)).robots).toBe("noindex,follow");
    await page.getByRole("link", { name: "Today's index", exact: true }).last().click();
    await expect.poll(async () => (await readHead(page)).robots).toBe("index,follow");
    expect((await readHead(page)).canonical).toBe("https://wke.piotrkrzysztof.dev/");
  });
});

test.describe("Shell metadata", () => {
  test("the shell has no hard-coded canonical and links the SVG icon first", async ({
    request,
  }) => {
    const html = await (await request.get("/")).text();
    expect(html).not.toContain('rel="canonical"');
    expect(html).not.toContain('property="og:url"');
    expect(html.indexOf('href="/favicon.svg"')).toBeGreaterThan(0);
    expect(html.indexOf('href="/favicon.svg"')).toBeLessThan(html.indexOf('href="/favicon.ico"'));
    expect(html).toContain("<noscript>");
    expect(html).toContain('href="/llms.txt"');
  });

  test.describe("with the light theme stored", () => {
    test.use({ theme: "light" });

    test("the theme toggle moves both theme-color metas to the paper color", async ({
      page,
      open,
    }) => {
      await open("/machines");
      const light = await paper(page);
      expect(light).not.toBe("");
      await expect.poll(() => themeColors(page)).toEqual([light, light]);

      await page.getByRole("button", { name: "Switch to dark theme" }).click();
      const dark = await paper(page);
      expect(dark).not.toBe(light);
      await expect.poll(() => themeColors(page)).toEqual([dark, dark]);
    });
  });
});
