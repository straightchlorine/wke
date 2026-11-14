import { Link } from "@tanstack/react-router";
import { useSeo } from "../lib/seo";
import { ErrorPanel } from "./ErrorPanel";
import { OpenTopicSearch } from "./OpenTopicSearch";

/**
 * The page the root route shows when no route matches the address.
 * The root layout supplies the footer here, because this page mounts no Colophon of its own (see ColophonPresenceContext).
 */
export function NotFound() {
  useSeo({
    title: "Page not found",
    description:
      "That page does not exist. Go back to the WKE home page or browse recent dossiers.",
    path: "/",
    robots: "noindex,follow",
  });
  return (
    <div className="py-8">
      <h1 tabIndex={-1} className="font-serif text-36 text-ink lg:text-44">
        Page not found
      </h1>
      <ErrorPanel
        tone="muted"
        className="mt-4 max-w-(--container-prose)"
        title="This address has no page. Search for a topic instead."
        retry={
          <div>
            <OpenTopicSearch />
            <p className="mt-1 flex gap-x-4 text-13 text-ink-2">
              <Link
                to="/t"
                className="hit-44 inline-flex min-h-11 items-center text-accent underline"
              >
                Dossiers
              </Link>
              <Link
                to="/"
                className="hit-44 inline-flex min-h-11 items-center text-accent underline"
              >
                Today's index
              </Link>
            </p>
          </div>
        }
      />
    </div>
  );
}
