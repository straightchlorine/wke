import type { Job } from "../api/generated";
import { buildStatusText, buildSteps } from "../lib/buildProgress";
import { Button } from "./Button";
import { DossierHead } from "./DossierHead";
import { ErrorPanel } from "./ErrorPanel";
import { SectionSkeleton } from "./SectionSkeleton";
import { Steps } from "./Steps";

export interface DossierBuildingProps {
  title: string;
  job: Job | null;
  /** True while the finished dossier's text is being fetched. */
  loading: boolean;
  /** Set when the build finished but the text did not load. */
  loadFailed: boolean;
  onCancel: () => void;
  onRetryLoad: () => void;
}

/** The page for a dossier that is still being built: its stages, a cancel button and a notice when the text did not load. */
export function DossierBuilding({
  title,
  job,
  loading,
  loadFailed,
  onCancel,
  onRetryLoad,
}: DossierBuildingProps) {
  return (
    <div className="min-h-svh w-full py-8">
      <DossierHead
        title={title}
        lede="Building this dossier now. Text is usually ready in under a minute. Model summaries follow within a few minutes."
      />
      <Steps steps={buildSteps(job)} className="mt-6 max-w-(--container-prose)" />
      <output className="mt-5 block text-14 text-ink-2">{buildStatusText(job)}</output>
      <Button variant="secondary" className="mt-3" onClick={onCancel}>
        Cancel
      </Button>
      {job ? <p className="mt-3 text-12 text-ink-3">Job {job.id}</p> : null}
      {loading ? <p className="mt-3 text-12 text-ink-3">Loading dossier text...</p> : null}
      {loadFailed ? (
        <ErrorPanel
          className="mt-4"
          title="Could not load the dossier"
          detail="The build finished but the dossier text did not load."
          retry={
            <Button variant="small" onClick={onRetryLoad}>
              Retry
            </Button>
          }
        />
      ) : null}
      <SectionSkeleton className="mt-10" />
    </div>
  );
}
