import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import type { Job } from "../../api/generated";

const getJob = vi.fn();
vi.mock("../../api/generated", () => ({ getJob: (...args: unknown[]) => getJob(...args) }));

const { usePolledJob } = await import("./usePolledJob");

function job(status: Job["status"]): Job {
  return {
    id: "j1",
    page_id: 1,
    status,
    stage: "fetch",
    progress: { done: 0, total: 1 },
    partial_available: false,
    created_at: "2026-09-29T10:00:00Z",
    updated_at: "2026-09-29T10:00:00Z",
    poll_after_ms: 1000,
  };
}

const problem = {
  type: "about:blank",
  title: "Not found",
  status: 404,
  code: "not_found" as const,
  request_id: "r",
};

describe("usePolledJob", () => {
  let state: DocumentVisibilityState = "visible";

  function setVisibility(next: DocumentVisibilityState) {
    state = next;
    document.dispatchEvent(new Event("visibilitychange"));
  }

  beforeEach(() => {
    vi.useFakeTimers();
    state = "visible";
    vi.spyOn(document, "visibilityState", "get").mockImplementation(() => state);
    getJob.mockReset();
    getJob.mockResolvedValue({ data: job("running") });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("polls at the job's own cadence while the tab is visible", async () => {
    renderHook(() => usePolledJob("j1"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(getJob).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(getJob).toHaveBeenCalledTimes(2);
  });

  it("schedules no poll while hidden and polls at once when visible again", async () => {
    renderHook(() => usePolledJob("j1"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(getJob).toHaveBeenCalledTimes(1);

    act(() => setVisibility("hidden"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(getJob).toHaveBeenCalledTimes(1);

    await act(async () => {
      setVisibility("visible");
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(getJob).toHaveBeenCalledTimes(2);
  });

  it("does not schedule the next poll when a response lands in a hidden tab", async () => {
    const pending: Array<(value: unknown) => void> = [];
    getJob.mockReset();
    getJob.mockImplementationOnce(() => new Promise((r) => pending.push(r)));
    getJob.mockResolvedValue({ data: job("running") });
    renderHook(() => usePolledJob("j1"));
    act(() => setVisibility("hidden"));
    await act(async () => {
      pending[0]?.({ data: job("running") });
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(getJob).toHaveBeenCalledTimes(1);
    await act(async () => {
      setVisibility("visible");
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(getJob).toHaveBeenCalledTimes(2);
  });

  it.each(["done", "failed"] as const)("stops for good once the job is %s", async (status) => {
    getJob.mockResolvedValue({ data: job(status) });
    const { result } = renderHook(() => usePolledJob("j1"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(getJob).toHaveBeenCalledTimes(1);
    expect(result.current.polling).toBe(false);
  });

  it("polls once at mount even when the tab is hidden", async () => {
    state = "hidden";
    renderHook(() => usePolledJob("j1"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(getJob).toHaveBeenCalledTimes(1);
  });

  it("polls nothing without a job id", async () => {
    const { result } = renderHook(() => usePolledJob(null));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(getJob).not.toHaveBeenCalled();
    expect(result.current.polling).toBe(false);
  });

  it.each([
    ["an error answer", () => getJob.mockResolvedValue({ error: problem })],
    ["a failed request", () => getJob.mockRejectedValue(problem)],
  ])("stops and reports the problem after %s", async (_name, arrange) => {
    arrange();
    const { result } = renderHook(() => usePolledJob("j1"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(getJob).toHaveBeenCalledTimes(1);
    expect(result.current.error).toEqual(problem);
    expect(result.current.polling).toBe(false);
  });

  it("cancel stops polling and keeps the last job", async () => {
    const { result } = renderHook(() => usePolledJob("j1"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    act(() => result.current.cancel());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(getJob).toHaveBeenCalledTimes(1);
    expect(result.current.polling).toBe(false);
    expect(result.current.job?.status).toBe("running");
  });

  it("drops the old job at once and polls the new one when the id changes", async () => {
    const { result, rerender } = renderHook(({ id }) => usePolledJob(id), {
      initialProps: { id: "j1" },
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.job?.id).toBe("j1");

    getJob.mockReturnValue(new Promise(() => {}));
    rerender({ id: "j2" });
    expect(result.current.job).toBeNull();
    expect(getJob).toHaveBeenLastCalledWith({ path: { job_id: "j2" } });
  });

  it("makes no more requests after unmount, even for an answer still in flight", async () => {
    const pending: Array<(value: unknown) => void> = [];
    getJob.mockImplementation(() => new Promise((r) => pending.push(r)));
    const { unmount } = renderHook(() => usePolledJob("j1"));
    unmount();
    await act(async () => {
      pending[0]?.({ data: job("running") });
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(getJob).toHaveBeenCalledTimes(1);
  });
});
