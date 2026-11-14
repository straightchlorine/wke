import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";

export interface DossierHeadProps {
  title: string;
  /** The topic the breadcrumb names; defaults to `title`. */
  crumb?: string;
  /** The serif lede under the heading. */
  lede?: ReactNode;
  /** Content that renders under the lede next to the aside; it is ignored without an aside. */
  children?: ReactNode;
  /** A column beside the heading and lede (the source record), level with the h1 and below the breadcrumb. It stacks under them until `asideColumns` sets more than one grid column. */
  aside?: ReactNode;
  /** The grid column classes that size the aside, e.g. `lg:grid-cols-[1fr_360px]`. */
  asideColumns?: string;
}

/** The heading block shared by the dossier page's states: breadcrumb, serif h1 and serif lede, with an optional aside column. */
export function DossierHead({
  title,
  crumb,
  lede,
  children,
  aside,
  asideColumns = "",
}: DossierHeadProps) {
  const heading = (
    <>
      <h1
        tabIndex={-1}
        className={`${aside == null ? "mt-1 " : ""}font-serif text-36 text-ink lg:text-44`}
      >
        {title}
      </h1>
      {lede != null ? (
        <p className="mt-3 max-w-(--container-prose) font-serif text-16 text-ink-2 lg:text-18">
          {lede}
        </p>
      ) : null}
    </>
  );
  return (
    <>
      <nav aria-label="Breadcrumb" className="text-13 text-ink-3">
        {/* Exact matching: by prefix, "/t" would count as active on every dossier and Link would set aria-current="page" on it. */}
        <Link
          to="/t"
          activeOptions={{ exact: true }}
          className="hit-44 inline-block text-accent underline"
        >
          Dossiers
        </Link>{" "}
        / {crumb ?? title}
      </nav>
      {aside == null ? (
        heading
      ) : (
        <div className={`mt-1 grid grid-cols-1 gap-8 ${asideColumns}`}>
          <div>
            {heading}
            {children}
          </div>
          {aside}
        </div>
      )}
    </>
  );
}
