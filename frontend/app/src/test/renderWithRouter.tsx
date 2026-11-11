import type { ReactNode } from "react";
import { render } from "@testing-library/react";
import {
  RouterProvider,
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
} from "@tanstack/react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

export interface RenderWithRouterOptions {
  /** Memory-history entry the router starts on. Defaults to "/". */
  initialPath?: string;
  /** Extra route paths mounted beside "/" with an empty body, so links to them resolve. */
  extraRoutes?: string[];
  /** Component the root route renders for unmatched paths. */
  notFoundComponent?: () => ReactNode;
}

/** Renders `ui` at "/" inside a memory router and a query client, and returns the router with the render result. */
export function renderWithRouter(ui: ReactNode, options: RenderWithRouterOptions = {}) {
  const { initialPath = "/", extraRoutes = [], notFoundComponent } = options;
  const rootRoute = createRootRoute(notFoundComponent ? { notFoundComponent } : {});
  const indexRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/",
    component: () => <>{ui}</>,
  });
  const others = extraRoutes.map((path) =>
    createRoute({ getParentRoute: () => rootRoute, path, component: () => null }),
  );
  const router = createRouter({
    routeTree: rootRoute.addChildren([indexRoute, ...others]),
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  });
  const result = render(
    <QueryClientProvider client={new QueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { router, ...result };
}
