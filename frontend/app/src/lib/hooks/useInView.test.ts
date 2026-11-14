import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useInView } from "./useInView";

class FakeObserver {
  static instances: FakeObserver[] = [];
  disconnected = false;
  observed: Element[] = [];

  constructor(
    private callback: (entries: Array<{ isIntersecting: boolean }>) => void,
    readonly options: IntersectionObserverInit,
  ) {
    FakeObserver.instances.push(this);
  }

  observe(node: Element) {
    this.observed.push(node);
  }

  disconnect() {
    this.disconnected = true;
  }

  emit(isIntersecting: boolean) {
    this.callback([{ isIntersecting }]);
  }
}

describe("useInView", () => {
  afterEach(() => {
    FakeObserver.instances = [];
    vi.unstubAllGlobals();
  });

  it("turns true once the element comes into view, stays true and stops observing", () => {
    vi.stubGlobal("IntersectionObserver", FakeObserver);
    const node = document.createElement("div");
    const { result } = renderHook(() => useInView("50px"));
    act(() => void result.current[0](node));
    const [observer] = FakeObserver.instances;
    expect(observer?.options.rootMargin).toBe("50px");
    expect(observer?.observed).toEqual([node]);
    expect(result.current[1]).toBe(false);

    act(() => observer?.emit(false));
    expect(result.current[1]).toBe(false);
    act(() => observer?.emit(true));
    expect(result.current[1]).toBe(true);
    expect(observer?.disconnected).toBe(true);
    act(() => observer?.emit(false));
    expect(result.current[1]).toBe(true);
  });

  it("stops observing when the element goes away", () => {
    vi.stubGlobal("IntersectionObserver", FakeObserver);
    const { result } = renderHook(() => useInView());
    let cleanup: (() => void) | undefined;
    act(() => {
      cleanup = result.current[0](document.createElement("div"));
    });
    cleanup?.();
    expect(FakeObserver.instances[0]?.disconnected).toBe(true);
  });

  it("is true at once where IntersectionObserver does not exist", () => {
    vi.stubGlobal("IntersectionObserver", undefined);
    const { result } = renderHook(() => useInView());
    act(() => void result.current[0](document.createElement("div")));
    expect(result.current[1]).toBe(true);
  });
});
