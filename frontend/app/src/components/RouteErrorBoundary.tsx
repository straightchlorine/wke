import type { ErrorComponentProps } from "@tanstack/react-router";
import { ErrorPanel } from "./ErrorPanel";
import { Button } from "./Button";

/**
 * Fallback for uncaught render errors in any route, so the header and the root layout's footer stay mounted.
 * It renders no Colophon, so the root layout shows its generic footer here, including when a dossier page crashes.
 */
export function RouteErrorBoundary({ error, reset }: ErrorComponentProps) {
  const detail = error instanceof Error ? error.message : String(error);
  return (
    <div className="mx-auto max-w-(--container-page) px-(--gutter) py-8">
      <h1 tabIndex={-1} className="font-serif text-36 text-ink lg:text-44">
        Something went wrong
      </h1>
      <ErrorPanel
        detail={detail}
        retry={
          <Button variant="small" onClick={reset}>
            Retry
          </Button>
        }
      />
    </div>
  );
}
