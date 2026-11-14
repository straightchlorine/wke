import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { usePings } from "./usePings";

const KNOWN = new Set([1, 2]);

/** The ring animation, the second ring's delay and a little slack. */
const RING_LIFETIME_MS = 1550;
const PING_WINDOW_MS = 60_000;

function stubReducedMotion() {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: query === "(prefers-reduced-motion: reduce)",
      addEventListener: () => {},
      removeEventListener: () => {},
    })),
  );
}

function setup() {
  return renderHook(() => usePings(KNOWN));
}

function advance(ms: number) {
  act(() => void vi.advanceTimersByTime(ms));
}

describe("usePings", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("marks a node that exists and draws one ring around it", () => {
    const { result } = setup();
    act(() => result.current.ping(1));
    expect(result.current.counts.get(1)).toBe(1);
    expect(result.current.ringIdsFor(1)).toHaveLength(1);
    expect(result.current.ringIdsFor(2)).toEqual([]);
  });

  it("ignores a node that does not exist", () => {
    const { result } = setup();
    act(() => result.current.ping(99));
    expect(result.current.counts.size).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("marks without a ring when asked for none", () => {
    const { result } = setup();
    act(() => result.current.ping(1, false));
    expect(result.current.counts.get(1)).toBe(1);
    expect(result.current.ringIdsFor(1)).toEqual([]);
  });

  it("counts a repeat ping without drawing a second ring", () => {
    const { result } = setup();
    act(() => {
      result.current.ping(1);
      result.current.ping(1);
    });
    expect(result.current.counts.get(1)).toBe(2);
    expect(result.current.ringIdsFor(1)).toHaveLength(1);
    act(() => result.current.ping(1));
    expect(result.current.counts.get(1)).toBe(3);
    expect(result.current.ringIdsFor(1)).toHaveLength(1);
  });

  it("removes the rings after their animation but keeps the mark", () => {
    const { result } = setup();
    act(() => result.current.ping(1));
    advance(RING_LIFETIME_MS - 1);
    expect(result.current.ringIdsFor(1)).toHaveLength(1);
    advance(1);
    expect(result.current.ringIdsFor(1)).toEqual([]);
    expect(result.current.counts.has(1)).toBe(true);
  });

  it("draws a ring again once the mark has expired, and not before", () => {
    const { result } = setup();
    act(() => result.current.ping(1));
    advance(RING_LIFETIME_MS);
    act(() => result.current.ping(1));
    expect(result.current.ringIdsFor(1)).toEqual([]);
    advance(PING_WINDOW_MS);
    expect(result.current.counts.has(1)).toBe(false);
    act(() => result.current.ping(1));
    expect(result.current.counts.get(1)).toBe(1);
    expect(result.current.ringIdsFor(1)).toHaveLength(1);
  });

  it("restarts the mark's minute on each ping", () => {
    const { result } = setup();
    act(() => result.current.ping(1));
    advance(PING_WINDOW_MS - 1);
    act(() => result.current.ping(1));
    advance(PING_WINDOW_MS - 1);
    expect(result.current.counts.get(1)).toBe(2);
    advance(1);
    expect(result.current.counts.has(1)).toBe(false);
  });

  it("keeps each node's mark apart", () => {
    const { result } = setup();
    act(() => result.current.ping(1));
    advance(30_000);
    act(() => result.current.ping(2));
    advance(30_000);
    expect(result.current.counts.has(1)).toBe(false);
    expect(result.current.counts.has(2)).toBe(true);
  });

  it("keeps the ring for the whole window under reduced motion", () => {
    stubReducedMotion();
    const { result } = setup();
    act(() => result.current.ping(1));
    advance(RING_LIFETIME_MS);
    expect(result.current.ringIdsFor(1)).toHaveLength(1);
    advance(PING_WINDOW_MS - RING_LIFETIME_MS);
    expect(result.current.ringIdsFor(1)).toEqual([]);
  });

  it("clears every pending timer when the component unmounts", () => {
    const { result, unmount } = setup();
    act(() => {
      result.current.ping(1);
      result.current.ping(2);
      result.current.ping(1);
    });
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
