import type { DossierView } from "../api/dossier";
import type { Job } from "../api/generated";
import { formatDuration, formatNumber } from "./format";

/** The build stages in the order they run, each with the words the page shows for it. */
const JOB_STAGE_LABELS: Record<string, string> = {
  resolve: "Resolving title",
  fetch: "Fetched revision",
  parse: "Split into passages",
  related: "Found related articles",
  embed: "Embedded sections",
  cluster: "Grouped into sections",
  summarize: "Summarising",
  persist: "Saving dossier",
};
const JOB_STAGES = Object.keys(JOB_STAGE_LABELS);

/** One build stage as the page lists it. */
export interface BuildStep {
  label: string;
  state: "done" | "running" | "waiting";
  /** How far the running stage is, such as "3 of 10 steps"; undefined for any other stage. */
  time?: string;
}

/** One duration shown in the build record. */
export interface DurationRow {
  label: string;
  value: string;
  size: "normal";
}

function stepState(stage: string, job: Job | null): BuildStep["state"] {
  if (!job) {
    return stage === "resolve" ? "running" : "waiting";
  }
  const current = JOB_STAGES.indexOf(job.stage);
  const index = JOB_STAGES.indexOf(stage);
  return index < current ? "done" : index === current ? "running" : "waiting";
}

/**
 * Returns one step per build stage. Without a job yet, the first stage is running, and the step
 * of the job's current stage says how many of its steps are done.
 */
export function buildSteps(job: Job | null): BuildStep[] {
  return JOB_STAGES.map((stage) => ({
    label: JOB_STAGE_LABELS[stage] ?? stage,
    state: stepState(stage, job),
    time:
      job && stage === job.stage && job.progress.total > 0
        ? `${formatNumber(job.progress.done)} of ${formatNumber(job.progress.total)} steps`
        : undefined,
  }));
}

/** Returns the one-line status of a build that has not finished. */
export function buildStatusText(job: Job | null): string {
  if (job?.partial_available) {
    return "Building, sections streaming in";
  }
  return job ? `Building, ${(JOB_STAGE_LABELS[job.stage] ?? job.stage).toLowerCase()}` : "Building";
}

/** Returns the record rows for how long the build and summarize stages took. */
export function stageDurationRows(
  stageSeconds: DossierView["build"]["stage_seconds"],
): DurationRow[] {
  if (!stageSeconds) {
    return [];
  }
  const rows: DurationRow[] = [];
  if (stageSeconds["build"] != null) {
    rows.push({
      label: "Building dossier text",
      value: formatDuration(stageSeconds["build"]),
      size: "normal",
    });
  }
  if (stageSeconds["summarize"] != null) {
    rows.push({
      label: JOB_STAGE_LABELS["summarize"] ?? "Summarising",
      value: formatDuration(stageSeconds["summarize"]),
      size: "normal",
    });
  }
  return rows;
}
