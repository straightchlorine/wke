import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithRouter } from "../test/renderWithRouter";
import { NotFound } from "./NotFound";

function renderNotFound() {
  return renderWithRouter(<div>home</div>, {
    initialPath: "/does-not-exist",
    extraRoutes: ["/t"],
    notFoundComponent: NotFound,
  });
}

describe("NotFound", () => {
  it("offers a search box and links to Dossiers and Today's index", async () => {
    renderNotFound();

    expect(await screen.findByRole("combobox", { name: "Search for a topic" })).toBeTruthy();
    expect((await screen.findByRole("link", { name: "Dossiers" })).getAttribute("href")).toBe("/t");
    expect((await screen.findByRole("link", { name: "Today's index" })).getAttribute("href")).toBe(
      "/",
    );
  });

  it("renders a focusable h1 for the root's focus-on-navigate", async () => {
    renderNotFound();

    const heading = await screen.findByRole("heading", { level: 1, name: "Page not found" });
    expect(heading.getAttribute("tabindex")).toBe("-1");
  });
});
