import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Colophon, ColophonPresenceContext } from "./Colophon";

describe("Colophon", () => {
  it("renders in place outside a provider", () => {
    render(
      <main>
        <Colophon
          article={{ url: "https://en.wikipedia.org/wiki/Alan_Turing", label: "Alan Turing" }}
        />
      </main>,
    );
    expect(screen.getByRole("main").textContent).toContain("Alan Turing");
  });

  it("renders into the footer host, outside main, and reports itself", () => {
    const host = document.createElement("div");
    document.body.append(host);
    const report = vi.fn();
    render(
      <ColophonPresenceContext value={{ report, host }}>
        <main>
          <Colophon
            article={{ url: "https://en.wikipedia.org/wiki/Alan_Turing", label: "Alan Turing" }}
          />
        </main>
      </ColophonPresenceContext>,
    );
    expect(screen.getByRole("main").textContent).not.toContain("Alan Turing");
    expect(host.textContent).toContain("Alan Turing");
    expect(report).toHaveBeenCalledWith(true);
    host.remove();
  });

  it("renders in place and never reports when announce is false", () => {
    const host = document.createElement("div");
    document.body.append(host);
    const report = vi.fn();
    render(
      <ColophonPresenceContext value={{ report, host }}>
        <main>
          <Colophon announce={false} />
        </main>
      </ColophonPresenceContext>,
    );
    expect(screen.getByRole("main").textContent).toContain("Wikipedia Knowledge Explorer");
    expect(host.textContent).toBe("");
    expect(report).not.toHaveBeenCalled();
    host.remove();
  });

  it("reports false last when an announcing instance unmounts", () => {
    const host = document.createElement("div");
    document.body.append(host);
    const report = vi.fn();
    const { unmount } = render(
      <ColophonPresenceContext value={{ report, host }}>
        <Colophon />
      </ColophonPresenceContext>,
    );
    unmount();
    expect(report).toHaveBeenLastCalledWith(false);
    host.remove();
  });
});
