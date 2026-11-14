import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { usePausedFeed } from "./usePausedFeed";

const KEY = "wke-paused";

describe("usePausedFeed", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it.each([
    [null, false],
    ["0", false],
    ["1", true],
  ])("starts from the stored value %j as paused=%j", (stored, expected) => {
    if (stored !== null) {
      window.localStorage.setItem(KEY, stored);
    }
    const { result } = renderHook(() => usePausedFeed());
    expect(result.current.paused).toBe(expected);
    expect(result.current.pausedSince).toBeNull();
    expect(result.current.resumedAt).toBeNull();
  });

  it("stamps the time and stores the choice on each toggle", () => {
    const { result } = renderHook(() => usePausedFeed());
    act(() => result.current.toggle());
    expect(result.current.paused).toBe(true);
    expect(result.current.pausedSince).toBeInstanceOf(Date);
    expect(result.current.resumedAt).toBeNull();
    expect(window.localStorage.getItem(KEY)).toBe("1");

    act(() => result.current.toggle());
    expect(result.current.paused).toBe(false);
    expect(result.current.pausedSince).toBeNull();
    expect(result.current.resumedAt).toBeInstanceOf(Date);
    expect(window.localStorage.getItem(KEY)).toBe("0");
  });

  it("works when storage throws on read and on write", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const { result } = renderHook(() => usePausedFeed());
    expect(result.current.paused).toBe(false);
    act(() => result.current.toggle());
    expect(result.current.paused).toBe(true);
  });
});
