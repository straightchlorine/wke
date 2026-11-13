import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { readStoredBudget, useBudget } from "./useBudget";

describe("useBudget", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState(null, "", "/");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it.each([
    ["the search param over the stored budget", "2000", "32000", 2000],
    ["an alias in the search param", "8k", "2000", 8000],
    ["the stored budget without a search param", undefined, "32000", 32000],
    ["the default for an invalid search param", "junk", "32000", 8000],
    ["the default for an invalid stored budget", undefined, "junk", 8000],
    ["the default when nothing is set", undefined, null, 8000],
  ])("resolves %s", (_name, searchBudget, stored, expected) => {
    if (stored !== null) {
      window.localStorage.setItem("wke-budget", stored);
    }
    const { result } = renderHook(() => useBudget(searchBudget));
    expect(result.current[0]).toBe(expected);
  });

  it.each([
    [null, 8000],
    ["2000", 2000],
    ["junk", 8000],
  ])("reads the stored budget %j as %j", (stored, expected) => {
    if (stored !== null) {
      window.localStorage.setItem("wke-budget", stored);
    }
    expect(readStoredBudget()).toBe(expected);
  });

  it("hands a change to the route's setter and remembers it, without touching the URL itself", () => {
    const setSearchBudget = vi.fn();
    const { result } = renderHook(() => useBudget(8000, setSearchBudget));
    act(() => result.current[1](2000));
    expect(setSearchBudget).toHaveBeenCalledWith(2000);
    expect(window.localStorage.getItem("wke-budget")).toBe("2000");
    expect(window.location.search).toBe("");
  });

  it("follows the route's value when the route has one", () => {
    const setSearchBudget = vi.fn();
    const { result, rerender } = renderHook(({ budget }) => useBudget(budget, setSearchBudget), {
      initialProps: { budget: 8000 },
    });
    act(() => result.current[1](2000));
    expect(result.current[0]).toBe(8000);
    rerender({ budget: 2000 });
    expect(result.current[0]).toBe(2000);
  });

  it("without a route setter keeps the change locally and writes it to the URL", () => {
    const { result } = renderHook(() => useBudget());
    act(() => result.current[1](32000));
    expect(result.current[0]).toBe(32000);
    expect(window.location.search).toBe("?budget=32000");
    expect(window.localStorage.getItem("wke-budget")).toBe("32000");
  });

  it("still works when storage cannot be read or written", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const { result } = renderHook(() => useBudget());
    expect(result.current[0]).toBe(8000);
    act(() => result.current[1](2000));
    expect(result.current[0]).toBe(2000);
  });
});
