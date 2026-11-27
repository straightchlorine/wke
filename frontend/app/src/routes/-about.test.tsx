import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { Route } from "./about";

function renderAbout() {
  const Page = Route.options.component;
  if (!Page) {
    throw new Error("the about route has no component");
  }
  return render(<Page />);
}

/** Returns the names in one credits group, in the order shown. */
function rowNames(group: string) {
  return Array.from(screen.getByRole("list", { name: group }).querySelectorAll("li")).map(
    (item) => item.firstElementChild?.textContent,
  );
}

afterEach(cleanup);

describe("About", () => {
  it("has one h1 and sets the title, description and canonical", () => {
    renderAbout();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("About");
    expect(document.title).toBe("About - WKE");
    expect(document.head.querySelector('meta[name="description"]')?.getAttribute("content")).toBe(
      "Who built WKE: a 2025 university project by four people, rewritten in 2026 by Piotr Krzysztof Lis. Licences and credits.",
    );
    expect(document.head.querySelector('link[rel="canonical"]')?.getAttribute("href")).toBe(
      "https://wke.piotrkrzysztof.dev/about",
    );
    expect(document.head.querySelector('meta[name="robots"]')?.getAttribute("content")).toBe(
      "index,follow",
    );
  });

  it("states the lede and the credits with the Polish letters", () => {
    renderAbout();
    const text = document.body.textContent ?? "";
    expect(text).not.toContain("WKE turns one Wikipedia article");
    expect(text).toContain(
      "Wikipedia Knowledge Explorer began in 2025 as a university project by Wiktor Jarosi\u0144ski, Daniel Ka\u0142mucki, Jakub Kucharski and Piotr Krzysztof Lis. The current version is a rewrite by Piotr Krzysztof Lis.",
    );
  });

  it("groups the credits as Current version and 2025 project", () => {
    renderAbout();
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual(["Current version", "2025 project", "Licence"]);
    expect(rowNames("Current version")).toEqual(["Piotr Krzysztof Lis"]);
    expect(rowNames("2025 project")).toEqual([
      "Wiktor Jarosi\u0144ski",
      "Daniel Ka\u0142mucki",
      "Jakub Kucharski",
      "Piotr Krzysztof Lis",
    ]);
  });

  it("links each person to their pages, the author with Codeberg", () => {
    renderAbout();
    const current = within(screen.getByRole("list", { name: "Current version" }));
    const project = within(screen.getByRole("list", { name: "2025 project" }));
    const links = (scope: typeof project, name: string) =>
      Array.from(scope.getByText(name).closest("li")?.querySelectorAll("a") ?? []).map((a) => [
        a.textContent,
        a.getAttribute("href"),
      ]);
    const author = [
      ["piotrkrzysztof.dev", "https://piotrkrzysztof.dev"],
      ["GitHub", "https://github.com/straightchlorine"],
      ["Codeberg", "https://codeberg.org/piotrkrzysztof"],
      ["LinkedIn", "https://www.linkedin.com/in/straightchlorine"],
    ];
    expect(links(current, "Piotr Krzysztof Lis")).toEqual(author);
    expect(links(project, "Piotr Krzysztof Lis")).toEqual(author);
    expect(links(project, "Jakub Kucharski")).toEqual([
      ["GitHub", "https://github.com/kubson2002k"],
      ["LinkedIn", "https://www.linkedin.com/in/jakub-kucharski-360811305/"],
    ]);
    expect(links(project, "Wiktor Jarosi\u0144ski")).toEqual([
      ["GitHub", "https://github.com/wiktorjarosinski"],
      ["LinkedIn", "https://www.linkedin.com/in/wiktor-jarosi%C5%84ski-719885244/"],
    ]);
    expect(links(project, "Daniel Ka\u0142mucki")).toEqual([
      ["GitHub", "https://github.com/Mastermod1"],
      ["LinkedIn", "https://www.linkedin.com/in/danielkalmucki/"],
    ]);
  });

  it("states the licences, linked, and never the closing verse", () => {
    renderAbout();
    const paragraphs = Array.from(document.querySelectorAll("p")).map((p) => p.textContent);
    expect(paragraphs).toContain("The code is MIT. Text from Wikipedia is CC BY-SA 4.0.");
    expect(document.body.textContent).not.toContain("Wikimedia Foundation");
    expect(screen.getByRole("link", { name: "wikipedia.org" }).getAttribute("href")).toBe(
      "https://www.wikipedia.org/",
    );
    expect(screen.getByRole("link", { name: "licence" }).getAttribute("href")).toBe(
      "https://creativecommons.org/licenses/by-sa/4.0/",
    );
    expect(screen.getByRole("link", { name: "repository" }).getAttribute("href")).toBe(
      "https://github.com/straightchlorine/wke",
    );
    expect(document.documentElement.outerHTML).not.toContain("honour and glory");
  });

  it("writes the AboutPage JSON-LD", () => {
    renderAbout();
    const ld: unknown = JSON.parse(document.getElementById("ld-page")?.textContent ?? "null");
    expect(ld).toMatchObject({ "@type": "AboutPage", url: "https://wke.piotrkrzysztof.dev/about" });
  });
});
