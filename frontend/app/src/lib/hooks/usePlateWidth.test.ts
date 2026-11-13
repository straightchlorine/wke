import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { usePlateWidth } from "./usePlateWidth";

let notify: (width: number) => void = () => {};

class FakeResizeObserver {
  constructor(callback: (entries: Array<{ contentRect: { width: number } }>) => void) {
    notify = (width) => callback([{ contentRect: { width } }]);
  }
  observe() {}
  disconnect() {}
}

/** Mounts the hook with a frame attached, so the first measurement can be sent. */
function mount() {
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  const hook = renderHook(() => usePlateWidth());
  act(() => hook.result.current[0](document.createElement("div")));
  return hook;
}

describe("usePlateWidth", () => {
  afterEach(() => {
    document.documentElement.style.removeProperty("--hairline");
  });

  it("starts at a default width until the frame has been measured", () => {
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    expect(renderHook(() => usePlateWidth()).result.current[1]).toBe(364);
  });

  it("takes the frame's borders and padding off the measured width", () => {
    const hook = mount();
    act(() => notify(500));
    expect(hook.result.current[1]).toBe(490);
  });

  it("takes off more where the hairline border is wider", () => {
    document.documentElement.style.setProperty("--hairline", "1.1429px");
    const hook = mount();
    act(() => notify(500));
    expect(hook.result.current[1]).toBe(489);
  });

  it("never draws the graph narrower than the minimum", () => {
    const hook = mount();
    act(() => notify(120));
    expect(hook.result.current[1]).toBe(200);
  });
});
