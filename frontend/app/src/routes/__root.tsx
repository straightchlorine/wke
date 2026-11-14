import { useEffect, useRef, useState } from "react";
import { createRootRoute, Outlet, useRouterState } from "@tanstack/react-router";
import { NotFound } from "../components/NotFound";
import { Header } from "../components/Header";
import { Colophon, ColophonPresenceContext } from "../components/Colophon";
import { ThemeToggle } from "../components/ThemeToggle";
import { WEBSITE_JSON_LD } from "../lib/seo";
import { useScrollRestoration } from "../lib/hooks/useScrollRestoration";

export const Route = createRootRoute({
  component: RootLayout,
  notFoundComponent: NotFound,
});

// True until the app's first commit has run, so a route that mounts while it is true belongs to the
// initial page load and not to a client-side navigation. A route must read it during its first
// render and keep the value, because it flips to false after that commit.
export const rootNavState = { isInitialLoad: true };

// "/t/" and "/t" are the same page: the Dossiers filter navigates between
// them when it writes a search param, and that must not read as a route
// change.
function normalizePath(pathname: string): string {
  return pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
}

function RootLayout() {
  const pathname = normalizePath(useRouterState({ select: (state) => state.location.pathname }));
  const hash = useRouterState({ select: (state) => state.location.hash });
  // Whether the current route mounted its own Colophon, reported through ColophonPresenceContext.
  // The router cannot say, because a dossier that failed to load and one that loaded fine both
  // count as a successful route.
  const [hasOwnFooter, setHasOwnFooter] = useState(false);
  const [footerHost, setFooterHost] = useState<HTMLElement | null>(null);
  const colophonHost = { report: setHasOwnFooter, host: footerHost };
  // The pathname changes while the router is still "pending" a lazy route chunk, so main can still
  // hold the old page's h1. Focusing that heading would leave focus on nothing once it unmounts, so
  // the focus effect waits for status "idle".
  const routerStatus = useRouterState({ select: (state) => state.status });
  const mainRef = useRef<HTMLElement>(null);
  const isFirstRender = useRef(true);
  const focusedForPath = useRef<string | null>(null);

  useEffect(() => {
    // The WebSite JSON-LD describes the whole site, so it is injected once and not per route.
    let script = document.head.querySelector<HTMLScriptElement>("script#ld-site");
    if (!script) {
      script = document.createElement("script");
      script.type = "application/ld+json";
      script.id = "ld-site";
      document.head.appendChild(script);
    }
    script.textContent = JSON.stringify(WEBSITE_JSON_LD);
  }, []);

  useEffect(() => {
    rootNavState.isInitialLoad = false;
  }, []);

  useEffect(() => {
    // Wait until the navigation has settled. The effect re-runs when the status returns to "idle",
    // and that run moves focus.
    if (routerStatus !== "idle") {
      return;
    }
    // A route change moves focus to the new page's h1. The first page load is skipped, and so is a
    // pathname already focused, because "idle" can fire more than once per navigation.
    if (isFirstRender.current) {
      isFirstRender.current = false;
      focusedForPath.current = pathname;
      return;
    }
    if (!pathname || pathname === focusedForPath.current) {
      return;
    }
    focusedForPath.current = pathname;
    // useScrollRestoration scrolls a route change that lands on a hash to that section. Focusing
    // the h1 here would pull focus above the target.
    if (hash) {
      return;
    }
    const heading = mainRef.current?.querySelector<HTMLElement>("h1");
    // The router's scroll restoration has already run when this fires, and focus() without
    // preventScroll would scroll back to the heading and undo it.
    heading?.focus({ preventScroll: true });
  }, [pathname, hash, routerStatus]);

  useScrollRestoration(pathname, hash ? `#${hash}` : "", routerStatus === "idle");

  return (
    <ColophonPresenceContext value={colophonHost}>
      <a href="#main" className="sr-only focus:not-sr-only">
        Skip to content
      </a>
      {/* The polite live region that announceLive() in lib/liveRegion writes into. */}
      <output id="live-region" aria-live="polite" className="sr-only" />
      <Header currentPath={pathname} themeToggle={<ThemeToggle />} />
      {/* The page width and gutter are set here once, so every page's h1 lines up with the header's
          wordmark. Routes add no horizontal padding or max-width of their own. */}
      {/* The minimum height keeps the footer below the fold before a lazy route has mounted, so it
          does not jump down later. */}
      <main
        id="main"
        ref={mainRef}
        className="mx-auto min-h-[calc(100svh-var(--header-h))] w-full max-w-(--container-page) px-(--gutter)"
      >
        <Outlet />
      </main>
      {/* The page's one contentinfo landmark. A loaded dossier renders its own Colophon into the host
          div. The generic Colophon shows only while no route has mounted one, so a 404 or a dossier that
          is still opening or building still gets a footer. */}
      <footer className="mx-auto max-w-(--container-page) px-(--gutter) py-8 max-[599px]:pb-[calc(2rem+var(--hud-h,0px))]">
        {hasOwnFooter ? null : <Colophon announce={false} />}
        <div ref={setFooterHost} />
      </footer>
    </ColophonPresenceContext>
  );
}
