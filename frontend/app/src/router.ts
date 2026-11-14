import { createRouter } from "@tanstack/react-router";
import { RouteErrorBoundary } from "./components/RouteErrorBoundary";
import { PATH_LITERAL_CHARACTERS } from "./lib/slug";
import { routeTree } from "./routeTree.gen";

export const router = createRouter({
  routeTree,
  defaultPreload: "intent",
  defaultErrorComponent: RouteErrorBoundary,
  scrollRestoration: true,
  // Without this option the router would percent-encode these characters in /t/{slug}.
  pathParamsAllowedCharacters: PATH_LITERAL_CHARACTERS,
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
