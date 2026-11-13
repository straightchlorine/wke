import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import type { ApiError } from "../../api/generated";
import { getDossierView } from "../../api/dossier";
import { loadDossier } from "../../test/fixtures";
import { useFoldedReading } from "./useFoldedReading";

vi.mock("../../api/dossier", () => ({ getDossierView: vi.fn() }));
const getView = vi.mocked(getDossierView);
type ViewResult = Awaited<ReturnType<typeof getDossierView>>;

const dossier = loadDossier();
const [chunkA, chunkB] = dossier.chunks;
// The section lists its passages as b, a and one the dossier does not carry.
const section = { ...dossier.sections[0]!, id: "7", chunk_ids: [chunkB!.id, "gone", chunkA!.id] };
const apiError: ApiError = {
  type: "about:blank",
  title: "Problem",
  status: 500,
  code: "internal",
  request_id: "req-1",
};
const onToast = vi.fn();

describe("useFoldedReading", () => {
  beforeEach(() => {
    getView.mockReset();
    onToast.mockReset();
  });

  it("fetches the dossier at the largest budget and keeps the section's passages in its own order", async () => {
    getView.mockResolvedValue({ data: { ...dossier, chunks: [chunkA!, chunkB!] } });
    const { result } = renderHook(() => useFoldedReading(42, onToast));
    await act(() => result.current.toggle(section));
    expect(getView).toHaveBeenCalledWith({ path: { page_id: 42 }, query: { budget: 32000 } });
    expect(result.current.texts["7"]).toEqual([chunkB, chunkA]);
  });

  it("shows a loading state until the passages arrive", async () => {
    let release: ((value: ViewResult) => void) | undefined;
    getView.mockReturnValue(new Promise<ViewResult>((resolve) => (release = resolve)));
    const { result } = renderHook(() => useFoldedReading(42, onToast));
    let pending: Promise<void> = Promise.resolve();
    act(() => {
      pending = result.current.toggle(section);
    });
    expect(result.current.texts["7"]).toBe("loading");
    await act(async () => {
      release?.({ data: { ...dossier, chunks: [] } });
      await pending;
    });
    expect(result.current.texts["7"]).toEqual([]);
  });

  it("closes an open section on the next call without fetching again", async () => {
    getView.mockResolvedValue({ data: dossier });
    const { result } = renderHook(() => useFoldedReading(42, onToast));
    await act(() => result.current.toggle(section));
    await act(() => result.current.toggle(section));
    expect(result.current.texts).toEqual({});
    expect(getView).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["an API error", { error: apiError }],
    ["an empty answer", {}],
  ])("drops the loading state and tells the reader after %s", async (_name, answer) => {
    getView.mockResolvedValue(answer);
    const { result } = renderHook(() => useFoldedReading(42, onToast));
    await act(() => result.current.toggle(section));
    expect(result.current.texts).toEqual({});
    expect(onToast).toHaveBeenCalledWith("Could not load the full section");
  });

  it("does nothing before the page id is known", async () => {
    const { result } = renderHook(() => useFoldedReading(null, onToast));
    await act(() => result.current.toggle(section));
    expect(getView).not.toHaveBeenCalled();
    expect(result.current.texts).toEqual({});
  });

  it("drops the opened passages when the page id changes", async () => {
    getView.mockResolvedValue({ data: dossier });
    const { result, rerender } = renderHook(({ id }) => useFoldedReading(id, onToast), {
      initialProps: { id: 42 },
    });
    await act(() => result.current.toggle(section));
    expect(result.current.texts["7"]).toBeDefined();
    rerender({ id: 43 });
    expect(result.current.texts).toEqual({});
  });

  it("ignores a response that arrives after the page id changed", async () => {
    let releaseOld: ((value: ViewResult) => void) | undefined;
    let releaseNew: ((value: ViewResult) => void) | undefined;
    getView
      .mockReturnValueOnce(new Promise<ViewResult>((resolve) => (releaseOld = resolve)))
      .mockReturnValueOnce(new Promise<ViewResult>((resolve) => (releaseNew = resolve)));
    const { result, rerender } = renderHook(({ id }) => useFoldedReading(id, onToast), {
      initialProps: { id: 42 },
    });
    let pendingOld: Promise<void> = Promise.resolve();
    act(() => {
      pendingOld = result.current.toggle(section);
    });
    rerender({ id: 43 });
    let pendingNew: Promise<void> = Promise.resolve();
    act(() => {
      pendingNew = result.current.toggle(section);
    });
    await act(async () => {
      releaseOld?.({ data: { ...dossier, chunks: [chunkA!] } });
      await pendingOld;
    });
    await act(async () => {
      releaseNew?.({ data: { ...dossier, chunks: [chunkB!] } });
      await pendingNew;
    });
    expect(result.current.texts["7"]).toEqual([chunkB]);
  });

  it("keeps a section closed when it is closed again while its passages load", async () => {
    let release: ((value: ViewResult) => void) | undefined;
    getView.mockReturnValue(new Promise<ViewResult>((resolve) => (release = resolve)));
    const { result } = renderHook(() => useFoldedReading(42, onToast));
    let pending: Promise<void> = Promise.resolve();
    act(() => {
      pending = result.current.toggle(section);
    });
    await act(() => result.current.toggle(section));
    await act(async () => {
      release?.({ data: dossier });
      await pending;
    });
    expect(result.current.texts).toEqual({});
  });
});
