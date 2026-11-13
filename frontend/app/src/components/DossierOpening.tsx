import { DossierHead } from "./DossierHead";
import { SectionSkeleton } from "./SectionSkeleton";

/**
 * The page while the API has not yet said whether the dossier is stored or must be built, so a
 * stored dossier does not flash the build panel.
 * It is at least one viewport tall, which keeps the footer below the fold and still when the article replaces it.
 */
export function DossierOpening({ title }: { title: string }) {
  return (
    <div className="min-h-svh w-full py-8" aria-busy="true">
      <DossierHead title={title} />
      <p className="mt-3 text-13 text-ink-2">Opening this dossier...</p>
      <div aria-hidden="true" className="mt-6 max-w-(--container-prose) space-y-3">
        {[90, 75, 82].map((width) => (
          <span
            key={width}
            style={{ width: `${width}%` }}
            className="block h-4 animate-pulse rounded-1 bg-sunken motion-reduce:animate-none"
          />
        ))}
        <span className="mt-6 block h-2 w-full animate-pulse rounded-1 bg-sunken motion-reduce:animate-none" />
      </div>
      <SectionSkeleton className="mt-10" />
    </div>
  );
}
