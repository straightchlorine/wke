import type { MouseEvent, ReactNode } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { isPlainLeftClick } from "../lib/clicks";
import { MIRROR_URL, REPO_URL } from "../lib/links";

const NAV_ITEMS: Array<{ label: string; to: string }> = [
  { label: "Today's index", to: "/" },
  { label: "Dossiers", to: "/t" },
  { label: "For machines", to: "/machines" },
];

const ICON_LINK =
  "hit-44 inline-flex size-(--control-h) items-center justify-center text-ink-2 transition-colors duration-(--motion-fast) hover:text-ink";

export interface HeaderProps {
  /** The current route path, for aria-current on the matching nav item. */
  currentPath: string;
  /** The light/dark theme toggle, rendered at the right of the header before the two icon links. */
  themeToggle?: ReactNode;
}

/** Returns "page" when the nav item is the current page, "true" when the current page is a sub-route of it (a dossier under Dossiers), else undefined. */
function currentFor(itemPath: string, currentPath: string): "page" | "true" | undefined {
  const path = currentPath.length > 1 ? currentPath.replace(/\/+$/, "") : currentPath;
  if (path === itemPath) {
    return "page";
  }
  return itemPath !== "/" && path.startsWith(`${itemPath}/`) ? "true" : undefined;
}

export function Header({ currentPath, themeToggle }: HeaderProps) {
  const navigate = useNavigate();

  // A plain anchor, not <Link>. On Home, Link would mark the wordmark active and set aria-current="page" on it.
  // Only the matching primary-nav item should carry that.
  function handleWordmarkClick(event: MouseEvent<HTMLAnchorElement>) {
    if (!isPlainLeftClick(event)) {
      return;
    }
    event.preventDefault();
    void navigate({ to: "/" });
  }

  return (
    <header className="h-20 border-b-(length:--hairline) border-ink pointer-coarse:h-22 short:h-(--header-h) xl:h-(--header-h) xl:pointer-coarse:h-(--header-h)">
      {/* The header uses --container-page, the same width token as the page content column in __root.tsx.
          Two different max-widths cannot share an inner edge at every viewport, so the wordmark would drift from each page's h1. */}
      <div className="mx-auto flex h-full max-w-(--container-page) flex-wrap items-center content-start gap-x-6 px-(--gutter) short:flex-nowrap xl:flex-nowrap">
        <a
          href="/"
          onClick={handleWordmarkClick}
          aria-label="WKE, Wikipedia Knowledge Explorer, home"
          // min-h-11 gives the link a real touch-target height. A hit-44 pseudo-element would enlarge the clickable area but not the anchor's own box.
          // Flex centering keeps the visible mark where it is.
          className="relative z-10 flex min-h-11 items-center gap-x-2"
        >
          <svg className="size-5" viewBox="0 0 20 20" aria-hidden="true">
            <rect
              x="0.5"
              y="0.5"
              width="19"
              height="19"
              fill="var(--wke-sheet)"
              stroke="var(--wke-ink)"
            />
            <path d="M5 15 10 10 15 5" stroke="var(--wke-rule-strong)" fill="none" />
            <circle cx="5" cy="15" r="2" fill="var(--wke-ink)" />
            <circle cx="10" cy="10" r="2" fill="var(--wke-ink)" />
            <circle cx="15" cy="5" r="2" fill="var(--wke-stamp)" />
          </svg>
          <span className="hidden font-serif text-18 text-ink sm:inline">
            Wikipedia Knowledge Explorer
          </span>
          <span className="font-serif text-18 text-ink sm:hidden">WKE</span>
        </a>

        <nav
          aria-label="Primary"
          className="order-3 -mt-1 flex h-13 basis-full gap-x-6 overflow-x-auto pt-1 pb-3 text-13 short:order-none short:-my-3 short:h-auto short:basis-auto short:flex-1 short:py-3 xl:order-none xl:h-auto xl:basis-auto xl:flex-1 xl:py-3 xl:-my-3 pointer-coarse:mt-0 pointer-coarse:h-11 pointer-coarse:py-0 short:pointer-coarse:my-0 short:pointer-coarse:h-auto short:pointer-coarse:py-0 xl:pointer-coarse:my-0 xl:pointer-coarse:h-auto xl:pointer-coarse:py-0"
        >
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              // Link matches by path prefix, so "/t" would be active on every dossier route and Link would force aria-current="page" over the explicit prop below.
              // `exact: true` stops that.
              activeOptions={{ exact: true }}
              aria-current={currentFor(item.to, currentPath)}
              className="relative flex items-center whitespace-nowrap text-ink-2 underline decoration-transparent underline-offset-2 transition-colors duration-(--motion-fast) hover:text-ink hover:decoration-current aria-[current]:text-ink aria-[current]:shadow-[inset_0_-2px_0_var(--wke-ink)] h-9 short:h-auto short:py-1 xl:h-auto xl:py-1 after:absolute after:inset-x-0 after:top-0 after:-bottom-2 after:content-[''] short:after:-inset-y-3 short:after:hidden xl:after:-inset-y-3 xl:after:hidden pointer-coarse:h-11 pointer-coarse:py-0 pointer-coarse:after:hidden short:pointer-coarse:h-11 short:pointer-coarse:py-0 xl:pointer-coarse:h-11 xl:pointer-coarse:py-0 [@media(pointer:coarse)]:short:after:block [@media(pointer:coarse)]:xl:after:block"
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-x-1">
          {themeToggle}
          <a href={MIRROR_URL} aria-label="Mirror on Codeberg" className={ICON_LINK}>
            <svg viewBox="0 0 24 24" className="size-4" fill="currentColor" aria-hidden="true">
              <path d="M11.955.49A12 12 0 0 0 0 12.49a12 12 0 0 0 1.832 6.373L11.838 5.928a.187.14 0 0 1 .324 0l10.006 12.935A12 12 0 0 0 24 12.49a12 12 0 0 0-12-12 12 12 0 0 0-.045 0zm.375 6.467l4.416 16.553a12 12 0 0 0 5.137-4.213z" />
            </svg>
          </a>
          <a href={REPO_URL} aria-label="Source on GitHub" className={ICON_LINK}>
            <svg viewBox="0 0 16 16" className="size-4" fill="currentColor" aria-hidden="true">
              <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 2-.27c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
            </svg>
          </a>
        </div>
      </div>
    </header>
  );
}
