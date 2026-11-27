import { readFileSync } from "node:fs";
import { AxeBuilder } from "@axe-core/playwright";
import { test, expect, eachTheme, only } from "./support";
import { trackErrors, assertNoErrors, expectShellRendered } from "./errorTracking";

const WIKTOR = "Wiktor Jarosi\u0144ski";
const DANIEL = "Daniel Ka\u0142mucki";

eachTheme(() => {
  test.describe("About", () => {
    test("the page content, credits and links", async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/about");
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("About");
      const main = page.locator("main");
      await expect(main).toContainText(
        `WKE began in 2025 as a university group project by Piotr Krzysztof Lis, Jakub Kucharski, ${WIKTOR} and ${DANIEL}. The current version is a rewrite by Piotr Krzysztof Lis.`,
      );
      await expect(main).toContainText(
        "The code is MIT. Text from Wikipedia is CC BY-SA 4.0. WKE is not affiliated with or endorsed by the Wikimedia Foundation.",
      );
      await expect(main.getByRole("heading", { level: 2 })).toHaveText([
        "Current version",
        "2025 project",
        "Licence",
      ]);
      const hrefsOf = async (group: string, name: string) =>
        main
          .getByRole("list", { name: group })
          .locator("li", { hasText: name })
          .locator("a")
          .evaluateAll((links) => links.map((a) => a.getAttribute("href")));
      const author = [
        "https://piotrkrzysztof.dev",
        "https://github.com/straightchlorine",
        "https://codeberg.org/piotrkrzysztof",
        "https://www.linkedin.com/in/straightchlorine",
      ];
      expect(await hrefsOf("Current version", "Piotr Krzysztof Lis")).toEqual(author);
      expect(await hrefsOf("2025 project", "Piotr Krzysztof Lis")).toEqual(author);
      expect(await hrefsOf("2025 project", "Jakub Kucharski")).toEqual([
        "https://github.com/kubson2002k",
        "https://www.linkedin.com/in/jakub-kucharski-360811305/",
      ]);
      expect(await hrefsOf("2025 project", WIKTOR)).toEqual([
        "https://www.linkedin.com/in/wiktor-jarosi%C5%84ski-719885244/",
      ]);
      expect(await hrefsOf("2025 project", DANIEL)).toEqual([
        "https://www.linkedin.com/in/danielkalmucki/",
      ]);
      await expect(page.getByRole("contentinfo")).toContainText(
        `The 2025 version was a group project with Jakub Kucharski, ${WIKTOR} and ${DANIEL}.`,
      );
      await expect(main.getByRole("link", { name: "wikipedia.org" })).toHaveAttribute(
        "href",
        "https://www.wikipedia.org/",
      );
      await expect(main.getByRole("link", { name: "licence" })).toHaveAttribute(
        "href",
        "https://creativecommons.org/licenses/by-sa/4.0/",
      );
      await expect(main.getByRole("link", { name: "repository" })).toHaveAttribute(
        "href",
        "https://github.com/straightchlorine/wke",
      );
      await expect(page.getByText("honour and glory")).toHaveCount(0);
      await expectShellRendered(page);
      assertNoErrors(errors);
    });

    test("has its own title, description, canonical, robots and structured data", async ({
      page,
      open,
    }) => {
      await open("/about");
      await expect(page).toHaveTitle("About - WKE");
      const head = await page.evaluate(() => ({
        description:
          document.head.querySelector('meta[name="description"]')?.getAttribute("content") ?? null,
        canonical:
          document.head.querySelector('link[rel="canonical"]')?.getAttribute("href") ?? null,
        robots: document.head.querySelector('meta[name="robots"]')?.getAttribute("content") ?? null,
        page: document.head.querySelector("script#ld-page")?.textContent ?? "null",
        site: document.head.querySelector("script#ld-site")?.textContent ?? "null",
      }));
      expect(head.description).toBe(
        "Who built WKE: a 2025 university group project by four people, rewritten in 2026 by Piotr Krzysztof Lis. Licences and credits.",
      );
      expect(head.canonical).toBe("https://wke.piotrkrzysztof.dev/about");
      expect(head.robots).toBe("index,follow");
      const ld: unknown = JSON.parse(head.page);
      expect(ld).toMatchObject({
        "@type": "AboutPage",
        author: { "@id": "https://piotrkrzysztof.dev/#piotr" },
        isPartOf: { "@id": "https://wke.piotrkrzysztof.dev/#website" },
        mentions: [
          { "@id": "https://piotrkrzysztof.dev/#jakub", name: "Jakub Kucharski" },
          { name: WIKTOR },
          { name: DANIEL },
        ],
      });
      const site: unknown = JSON.parse(head.site);
      expect(site).toMatchObject({
        "@type": "WebSite",
        author: { "@id": "https://piotrkrzysztof.dev/#piotr", name: "Piotr Krzysztof Lis" },
        publisher: { "@id": "https://piotrkrzysztof.dev/#piotr" },
      });
      expect(head.page + head.site).not.toContain("honour and glory");
    });

    test("no horizontal overflow", async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/about");
      const hasOverflow = await page.evaluate(
        () => document.documentElement.scrollWidth > window.innerWidth,
      );
      expect(hasOverflow).toBe(false);
      assertNoErrors(errors);
    });

    test("zero axe violations", async ({ page, open }) => {
      const errors = trackErrors(page);
      await open("/about");
      await page.waitForLoadState("networkidle");
      const results = await new AxeBuilder({ page }).analyze();
      expect(results.violations).toEqual([]);
      await expectShellRendered(page);
      assertNoErrors(errors);
    });

    test("the footer link opens it and the header has no About item", async ({ page, open }) => {
      await open("/machines");
      await expect(
        page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "About" }),
      ).toHaveCount(0);
      await expect(
        page.getByRole("contentinfo").getByRole("link", { name: "Codeberg" }),
      ).toHaveCount(0);
      await page.getByRole("contentinfo").getByRole("link", { name: "About" }).click();
      await expect(page).toHaveURL(/\/about$/);
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("About");
    });
  });
});

test.describe("About on the web server", only("desktop-1440"), () => {
  test("a direct load answers 200 with the app", async ({ request }) => {
    const response = await request.get("/about");
    expect(response.status()).toBe(200);
    expect(await response.text()).toContain('<div id="root">');
  });

  test("the web server config lists the path as an app page", () => {
    const conf = readFileSync(new URL("../nginx.conf", import.meta.url), "utf8");
    expect(conf).toContain("location ~ ^/(machines|about|t)(/.*)?$ {");
  });
});
