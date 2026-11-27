import { createContext, useContext, useLayoutEffect } from "react";
import { createPortal } from "react-dom";
import { Link } from "@tanstack/react-router";
import { REPO_URL } from "../lib/links";
import { AUTHOR } from "../lib/people";

/**
 * What the root layout provides to Colophon. `report` tells the layout that a route has its own colophon, so the layout skips its generic footer.
 * `host` is the footer node the colophon renders into, so it becomes the page's contentinfo. Outside any provider the context is null and the Colophon renders in place.
 */
export interface ColophonHost {
  report: (present: boolean) => void;
  host: HTMLElement | null;
}

export const ColophonPresenceContext = createContext<ColophonHost | null>(null);

export interface ColophonProps {
  /**
   * The dossier's own article link and its label, e.g.
   * `{ url: "https://en.wikipedia.org/wiki/Alan_Turing", label: "Alan Turing" }`.
   * Defaults to the generic wikipedia.org link.
   */
  article?: { url: string; label: string };
  /**
   * Reports this instance's mounted state through ColophonPresenceContext.
   * Defaults to true for every route's own Colophon; the root layout's
   * fallback footer passes false so it does not report its own presence
   * back into the decision of whether to render itself.
   */
  announce?: boolean;
}

export function Colophon({ article, announce = true }: ColophonProps = {}) {
  const context = useContext(ColophonPresenceContext);
  const setPresent = context?.report ?? null;
  // Layout effect, not a plain effect: this must flush before the
  // browser paints so the root layout's footer never renders for one
  // frame and then disappears once a route's own Colophon reports in.
  useLayoutEffect(() => {
    if (!announce || !setPresent) {
      return () => {};
    }
    setPresent(true);
    return () => setPresent(false);
  }, [announce, setPresent]);
  const body = (
    <div className="border-t-(length:--hairline) border-rule-strong pt-4 text-12 text-ink-3 xl:grid xl:grid-cols-[minmax(0,var(--container-prose))_auto] xl:gap-x-12">
      <p className="max-w-(--container-prose) xl:col-start-1">
        Wikipedia Knowledge Explorer turns one Wikipedia article into a dossier: its sections
        grouped by topic, every passage cited to one exact revision, cut to a chosen token budget. A
        self-hosted portfolio project for people and for language models.
      </p>
      <p className="mt-2 max-w-(--container-prose) xl:col-start-1">
        Text from Wikipedia, licensed CC BY-SA 4.0. The model summaries and the section groups are
        made by WKE and are not part of the Wikipedia article.{" "}
        <a href={article?.url ?? "https://www.wikipedia.org/"} className="hit-44 text-accent">
          {article ? article.label : "wikipedia.org"}
        </a>
        ,{" "}
        <a href="https://creativecommons.org/licenses/by-sa/4.0/" className="hit-44 text-accent">
          licence
        </a>
        ,{" "}
        <a href={REPO_URL} className="hit-44 text-accent">
          repository
        </a>
        . WKE is not affiliated with or endorsed by the Wikimedia Foundation.
      </p>
      {/* On a touch screen the larger margins and line height keep the tap areas of the links in the lines above and below from overlapping. */}
      <div className="xl:col-start-2 xl:row-span-2 xl:row-start-1">
        <p className="mt-3 pointer-coarse:mt-7 pointer-coarse:leading-6 xl:mt-0 pointer-coarse:xl:mt-0">
          Built by {AUTHOR.name}:{" "}
          {AUTHOR.links
            .filter((link) => !link.aboutOnly)
            .map((link, index) => (
              <span key={link.href}>
                {index > 0 ? ", " : null}
                <a href={link.href} className="hit-44 text-accent">
                  {link.label}
                </a>
              </span>
            ))}
          .
        </p>
        <p className="mt-2 pointer-coarse:mt-7 pointer-coarse:leading-6">
          <Link to="/about" className="hit-44 text-accent">
            About
          </Link>
        </p>
      </div>
    </div>
  );
  if (announce && context) {
    return context.host ? createPortal(body, context.host) : null;
  }
  return body;
}
