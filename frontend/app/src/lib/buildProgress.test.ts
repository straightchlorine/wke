import { describe, expect, it } from "vitest";
import type { Job } from "../api/generated";
import { buildSteps, buildStatusText, stageDurationRows } from "./buildProgress";

function job(stage: Job["stage"], progress = { done: 0, total: 0 }, partial = false): Job {
  return {
    id: "j1",
    page_id: 1,
    status: "running",
    stage,
    progress,
    poll_after_ms: 1000,
    partial_available: partial,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

describe("buildSteps", () => {
  it("shows the first stage running and the rest waiting before a job exists", () => {
    const steps = buildSteps(null);
    expect(steps.map((s) => s.state)).toEqual([
      "running",
      "waiting",
      "waiting",
      "waiting",
      "waiting",
      "waiting",
      "waiting",
      "waiting",
    ]);
    expect(steps.every((s) => s.time === undefined)).toBe(true);
  });

  it("marks the stages before the job's stage done and the ones after it waiting", () => {
    const steps = buildSteps(job("embed"));
    expect(steps.map((s) => [s.label, s.state])).toEqual([
      ["Resolving title", "done"],
      ["Fetched revision", "done"],
      ["Split into passages", "done"],
      ["Found related articles", "done"],
      ["Embedded sections", "running"],
      ["Grouped into sections", "waiting"],
      ["Summarising", "waiting"],
      ["Saving dossier", "waiting"],
    ]);
  });

  it("says how far the running stage is, only while it has a total", () => {
    const withTotal = buildSteps(job("embed", { done: 1200, total: 3400 }));
    expect(withTotal.find((s) => s.state === "running")?.time).toBe("1,200 of 3,400 steps");
    expect(withTotal.filter((s) => s.time !== undefined)).toHaveLength(1);
    expect(buildSteps(job("embed")).find((s) => s.state === "running")?.time).toBeUndefined();
  });
});

describe("buildStatusText", () => {
  it.each([
    ["no job yet", null, "Building"],
    ["a job in a stage", job("embed"), "Building, embedded sections"],
    [
      "a job with sections to read",
      job("summarize", { done: 0, total: 0 }, true),
      "Building, sections streaming in",
    ],
  ])("is right for %s", (_name, j, expected) => {
    expect(buildStatusText(j)).toBe(expected);
  });
});

describe("stageDurationRows", () => {
  it("lists the build and summarize durations and ignores other stages", () => {
    expect(stageDurationRows({ build: 12.4, parse: 3, summarize: 90 })).toEqual([
      { label: "Building dossier text", value: "12 s", size: "normal" },
      { label: "Summarising", value: "90 s", size: "normal" },
    ]);
  });

  it.each([
    ["no stage times", undefined],
    ["none of the two stages", { parse: 3 }],
  ])("gives no rows for %s", (_name, stages) => {
    expect(stageDurationRows(stages)).toEqual([]);
  });

  it("keeps a stage that took 0 seconds", () => {
    expect(stageDurationRows({ build: 0 })).toHaveLength(1);
  });
});
