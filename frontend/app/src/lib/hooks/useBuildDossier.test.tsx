import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import type { ApiError } from "../../api/generated";

const requestDossierView = vi.fn();
vi.mock("../../api/dossier", () => ({
  requestDossierView: (...args: unknown[]) => requestDossierView(...args),
}));
const fetchDidYouMean = vi.fn();
vi.mock("./useDossier", () => ({
  fetchDidYouMean: (...args: unknown[]) => fetchDidYouMean(...args),
}));
const open = vi.fn();
vi.mock("./useOpenDossier", () => ({ useOpenDossier: () => open }));

const { useBuildDossier } = await import("./useBuildDossier");

function problem(code: ApiError["code"], status = 404): ApiError {
  return { type: "about:blank", title: "t", status, code, request_id: "r", detail: "d" };
}

describe("useBuildDossier", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it.each([
    [
      "a built dossier",
      { data: { schema_version: "1", topic: { title: "Mary Magdalene" } } },
      "Mary_Magdalene",
    ],
    ["a queued job that names its title", { data: { title: "Queued Title" } }, "Queued_Title"],
    ["a queued job without a title", { data: {} }, "typed_title"],
  ])("opens the route for %s", async (_name, result, slug) => {
    requestDossierView.mockResolvedValue(result);
    const { result: hook } = renderHook(() => useBuildDossier(8000));
    await act(() => hook.current.build("  typed title "));
    expect(requestDossierView).toHaveBeenCalledWith("typed title");
    expect(open).toHaveBeenCalledWith(slug);
    expect(hook.current.error).toBeNull();
    expect(hook.current.building).toBe(false);
  });

  it("ignores a second request while one is running", async () => {
    let release: (() => void) | undefined;
    requestDossierView.mockReturnValue(
      new Promise((resolve) => {
        release = () => resolve({ data: { title: "x" } });
      }),
    );
    const { result } = renderHook(() => useBuildDossier(8000));
    let first: Promise<void> = Promise.resolve();
    act(() => {
      first = result.current.build("x");
    });
    expect(result.current.building).toBe(true);
    await act(() => result.current.build("y"));
    expect(requestDossierView).toHaveBeenCalledTimes(1);
    await act(async () => {
      release?.();
      await first;
    });
    expect(result.current.building).toBe(false);
  });

  it("ignores an empty title", async () => {
    const { result } = renderHook(() => useBuildDossier(8000));
    await act(() => result.current.build("   "));
    expect(requestDossierView).not.toHaveBeenCalled();
  });

  it("keeps the problem of a failed build and does not search for matches", async () => {
    requestDossierView.mockResolvedValue({ error: problem("not_article", 422) });
    const { result } = renderHook(() => useBuildDossier(8000));
    await act(() => result.current.build("x"));
    expect(result.current.error).toEqual({ problem: problem("not_article", 422) });
    expect(fetchDidYouMean).not.toHaveBeenCalled();
    expect(open).not.toHaveBeenCalled();
  });

  it("adds the top matches and the suggestion to a not_found problem", async () => {
    const candidates = [{ title: "Mary" }];
    requestDossierView.mockResolvedValue({ error: problem("not_found") });
    fetchDidYouMean.mockResolvedValue({ candidates, suggestion: "Mary" });
    const { result } = renderHook(() => useBuildDossier(8000));
    await act(() => result.current.build("Mray"));
    expect(fetchDidYouMean).toHaveBeenCalledWith("Mray");
    expect(result.current.error).toEqual({
      problem: problem("not_found"),
      didYouMean: candidates,
      suggestion: "Mary",
    });
  });

  it("turns a thrown error into a problem", async () => {
    requestDossierView.mockRejectedValue(new TypeError("fetch failed"));
    const { result } = renderHook(() => useBuildDossier(8000));
    await act(() => result.current.build("x"));
    expect(result.current.error?.problem.code).toBe("internal");
    expect(result.current.building).toBe(false);
  });

  it("treats an answer with no body as a failure", async () => {
    requestDossierView.mockResolvedValue({});
    const { result } = renderHook(() => useBuildDossier(8000));
    await act(() => result.current.build("x"));
    expect(result.current.error).not.toBeNull();
    expect(open).not.toHaveBeenCalled();
  });

  it("clears the previous problem when a new build starts", async () => {
    requestDossierView.mockResolvedValueOnce({ error: problem("not_article", 422) });
    requestDossierView.mockResolvedValueOnce({ data: { title: "Ok" } });
    const { result } = renderHook(() => useBuildDossier(8000));
    await act(() => result.current.build("x"));
    expect(result.current.error).not.toBeNull();
    await act(() => result.current.build("y"));
    expect(result.current.error).toBeNull();
  });
});
