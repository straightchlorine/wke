import { describe, expect, it, vi } from "vitest";
import { router } from "./router";

// A tree of one route keeps the real pages, which no test here needs, out of the module graph.
vi.mock("./routeTree.gen", async () => {
  const { createRootRoute, createRoute } = await import("@tanstack/react-router");
  const rootRoute = createRootRoute();
  const slugRoute = createRoute({ getParentRoute: () => rootRoute, path: "/t/$slug" });
  return { routeTree: rootRoute.addChildren([slugRoute]) };
});

function hrefOf(slug: string): string {
  return router.buildLocation({ to: "/t/$slug", params: { slug }, search: { budget: 8000 } })
    .pathname;
}

function slugOf(path: string): unknown {
  return router.matchRoutes(path).find((match) => match.routeId === "/t/$slug")?.params["slug"];
}

describe("the slug in a /t/{slug} URL", () => {
  it.each([
    ["Mary,_mother_of_Jesus", "/t/Mary,_mother_of_Jesus"],
    ["Star_Wars:_The_Last_Jedi", "/t/Star_Wars:_The_Last_Jedi"],
    ["Foo;bar@baz$", "/t/Foo;bar@baz$"],
  ])("keeps the characters Wikipedia keeps in %s", (slug, href) => {
    expect(hrefOf(slug)).toBe(href);
  });

  it.each([
    ["AC/DC", "/t/AC%2FDC"],
    ["Q&A", "/t/Q%26A"],
    ["100%", "/t/100%25"],
    ["Why?", "/t/Why%3F"],
  ])("still encodes what would change the URL, as in %s", (slug, href) => {
    expect(hrefOf(slug)).toBe(href);
  });

  it.each(["Mary,_mother_of_Jesus", "Star_Wars:_The_Last_Jedi", "AC/DC", "Why?"])(
    "reads %s back from its own URL",
    (slug) => {
      expect(slugOf(hrefOf(slug))).toBe(slug);
    },
  );
});
