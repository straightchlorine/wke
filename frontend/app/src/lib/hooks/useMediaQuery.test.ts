import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useMediaQuery } from "./useMediaQuery";
import { useReducedMotion } from "./useReducedMotion";

type Listener = () => void;

/** Installs a matchMedia whose matches come from `matches`, and returns a function that fires a query's change event. */
function stubMatchMedia(matches: Record<string, boolean>) {
  const listeners = new Map<string, Set<Listener>>();
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      get matches() {
        return matches[query] ?? false;
      },
      addEventListener: (_type: string, listener: Listener) => {
        listeners.set(query, (listeners.get(query) ?? new Set()).add(listener));
      },
      removeEventListener: (_type: string, listener: Listener) => {
        listeners.get(query)?.delete(listener);
      },
    })),
  );
  return {
    change(query: string, value: boolean) {
      matches[query] = value;
      for (const listener of listeners.get(query) ?? []) {
        listener();
      }
    },
    listenerCount: (query: string) => listeners.get(query)?.size ?? 0,
  };
}

describe("useMediaQuery", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("starts with the current match and follows its change events", () => {
    const media = stubMatchMedia({ "(min-width: 1024px)": false });
    const { result } = renderHook(() => useMediaQuery("(min-width: 1024px)"));
    expect(result.current).toBe(false);
    act(() => media.change("(min-width: 1024px)", true));
    expect(result.current).toBe(true);
  });

  it("reads the new query at once when the query changes", () => {
    stubMatchMedia({ "(max-width: 600px)": true, "(min-width: 600px)": false });
    const { result, rerender } = renderHook(({ query }) => useMediaQuery(query), {
      initialProps: { query: "(max-width: 600px)" },
    });
    expect(result.current).toBe(true);
    rerender({ query: "(min-width: 600px)" });
    expect(result.current).toBe(false);
  });

  it("stops listening to a query it no longer follows and on unmount", () => {
    const media = stubMatchMedia({});
    const { rerender, unmount } = renderHook(({ query }) => useMediaQuery(query), {
      initialProps: { query: "(a)" },
    });
    rerender({ query: "(b)" });
    expect(media.listenerCount("(a)")).toBe(0);
    expect(media.listenerCount("(b)")).toBe(1);
    unmount();
    expect(media.listenerCount("(b)")).toBe(0);
  });

  it("is false where matchMedia does not exist", () => {
    vi.stubGlobal("matchMedia", undefined);
    const { result } = renderHook(() => useMediaQuery("(min-width: 1024px)"));
    expect(result.current).toBe(false);
  });
});

describe("useReducedMotion", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("follows the prefers-reduced-motion media query", () => {
    const query = "(prefers-reduced-motion: reduce)";
    const media = stubMatchMedia({ [query]: true });
    const { result } = renderHook(() => useReducedMotion());
    expect(result.current).toBe(true);
    act(() => media.change(query, false));
    expect(result.current).toBe(false);
  });
});
