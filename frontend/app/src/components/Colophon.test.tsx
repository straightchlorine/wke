import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithRouter } from "../test/renderWithRouter";
import { Colophon, ColophonPresenceContext } from "./Colophon";

const options = { extraRoutes: ["/about"] };

describe("Colophon", () => {
  it("renders in place outside a provider", async () => {
    renderWithRouter(
      <main>
        <Colophon
          article={{ url: "https://en.wikipedia.org/wiki/Alan_Turing", label: "Alan Turing" }}
        />
      </main>,
      options,
    );
    expect((await screen.findByRole("main")).textContent).toContain("Alan Turing");
  });

  it("renders into the footer host, outside main, and reports itself", async () => {
    const host = document.createElement("div");
    document.body.append(host);
    const report = vi.fn();
    renderWithRouter(
      <ColophonPresenceContext value={{ report, host }}>
        <main>
          <Colophon
            article={{ url: "https://en.wikipedia.org/wiki/Alan_Turing", label: "Alan Turing" }}
          />
        </main>
      </ColophonPresenceContext>,
      options,
    );
    expect((await screen.findByRole("main")).textContent).not.toContain("Alan Turing");
    expect(host.textContent).toContain("Alan Turing");
    expect(report).toHaveBeenCalledWith(true);
    host.remove();
  });

  it("renders in place and never reports when announce is false", async () => {
    const host = document.createElement("div");
    document.body.append(host);
    const report = vi.fn();
    renderWithRouter(
      <ColophonPresenceContext value={{ report, host }}>
        <main>
          <Colophon announce={false} />
        </main>
      </ColophonPresenceContext>,
      options,
    );
    expect((await screen.findByRole("main")).textContent).toContain("Wikipedia Knowledge Explorer");
    expect(host.textContent).toBe("");
    expect(report).not.toHaveBeenCalled();
    host.remove();
  });

  it("reports false last when an announcing instance unmounts", async () => {
    const host = document.createElement("div");
    document.body.append(host);
    const report = vi.fn();
    const { unmount } = renderWithRouter(
      <ColophonPresenceContext value={{ report, host }}>
        <Colophon />
      </ColophonPresenceContext>,
      options,
    );
    await vi.waitFor(() => expect(report).toHaveBeenCalledWith(true));
    unmount();
    expect(report).toHaveBeenLastCalledWith(false);
    host.remove();
  });

  it("names the author with three links and links to About", async () => {
    renderWithRouter(<Colophon announce={false} />, options);
    const links = await screen.findAllByRole("link");
    const byName = (name: string) => links.find((a) => a.textContent === name);
    expect(byName("piotrkrzysztof.dev")?.getAttribute("href")).toBe("https://piotrkrzysztof.dev");
    expect(byName("GitHub")?.getAttribute("href")).toBe("https://github.com/straightchlorine");
    expect(byName("LinkedIn")?.getAttribute("href")).toBe(
      "https://www.linkedin.com/in/straightchlorine",
    );
    expect(byName("About")?.getAttribute("href")).toBe("/about");
    const builtBy = byName("GitHub")?.closest("p");
    expect(builtBy?.textContent).toBe(
      "Built by Piotr Krzysztof Lis: piotrkrzysztof.dev, GitHub, LinkedIn.",
    );
    const about = byName("About")?.closest("p");
    expect(about?.textContent).toBe("About");
    expect(builtBy?.nextElementSibling).toBe(about);
    expect(links.some((a) => a.getAttribute("href")?.includes("codeberg"))).toBe(false);
    for (const name of ["Jakub Kucharski", "Wiktor Jarosi\u0144ski", "Daniel Ka\u0142mucki"]) {
      expect(links.some((a) => a.textContent?.includes(name))).toBe(false);
    }
  });
});
