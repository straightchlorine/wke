import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import type { Job } from "../api/generated";
import { renderWithRouter } from "../test/renderWithRouter";
import { DossierBuilding, type DossierBuildingProps } from "./DossierBuilding";

const job: Job = {
  id: "job-9",
  page_id: 1,
  status: "running",
  stage: "embed",
  progress: { done: 2, total: 5 },
  poll_after_ms: 1000,
  partial_available: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function renderBuilding(props: Partial<DossierBuildingProps> = {}) {
  const handlers = { onCancel: vi.fn(), onRetryLoad: vi.fn() };
  renderWithRouter(
    <DossierBuilding
      title="Jesus"
      job={null}
      loading={false}
      loadFailed={false}
      {...handlers}
      {...props}
    />,
  );
  return handlers;
}

describe("DossierBuilding", () => {
  it("shows the title, the stage the build is in and the job", async () => {
    renderBuilding({ job });
    expect(await screen.findByRole("heading", { level: 1, name: "Jesus" })).toBeTruthy();
    expect(screen.getByText("Building, embedded sections")).toBeTruthy();
    expect(screen.getByText("2 of 5 steps")).toBeTruthy();
    expect(screen.getByText("Job job-9")).toBeTruthy();
  });

  it("names no job before the API has returned one", async () => {
    renderBuilding();
    expect(await screen.findByText("Building")).toBeTruthy();
    expect(screen.queryByText(/^Job /)).toBeNull();
  });

  it("calls onCancel from the Cancel button", async () => {
    const { onCancel } = renderBuilding();
    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("says the text is loading, and offers a retry when it did not load", async () => {
    const { onRetryLoad } = renderBuilding({ loading: true, loadFailed: true });
    expect(await screen.findByText("Loading dossier text...")).toBeTruthy();
    expect(screen.getByText("The build finished but the dossier text did not load.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetryLoad).toHaveBeenCalledTimes(1);
  });

  it("shows neither notice while all is well", async () => {
    renderBuilding();
    await screen.findByText("Building");
    expect(screen.queryByText("Loading dossier text...")).toBeNull();
    expect(screen.queryByText("Could not load the dossier")).toBeNull();
  });
});
