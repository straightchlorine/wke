import { afterEach, describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";
import { useHeadingRefocus } from "./useHeadingRefocus";

function setup() {
  document.body.innerHTML = '<main><h1 tabindex="-1">Title</h1></main><button>other</button>';
  return document.querySelector("h1");
}

describe("useHeadingRefocus", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("focuses the h1 when the phase changes after a client-side navigation", () => {
    const h1 = setup();
    const { rerender } = renderHook(({ key }) => useHeadingRefocus(key, true), {
      initialProps: { key: "building" },
    });
    expect(document.activeElement).toBe(document.body);
    rerender({ key: "loaded" });
    expect(document.activeElement).toBe(h1);
  });

  it("does not focus on a direct load", () => {
    const h1 = setup();
    const { rerender } = renderHook(({ key }) => useHeadingRefocus(key, false), {
      initialProps: { key: "building" },
    });
    rerender({ key: "loaded" });
    expect(document.activeElement).not.toBe(h1);
  });

  it("leaves focus where the reader put it", () => {
    setup();
    const button = document.querySelector("button")!;
    const { rerender } = renderHook(({ key }) => useHeadingRefocus(key, true), {
      initialProps: { key: "building" },
    });
    button.focus();
    rerender({ key: "loaded" });
    expect(document.activeElement).toBe(button);
  });

  it("does not focus while the phase stays the same", () => {
    const h1 = setup();
    const { rerender } = renderHook(({ key }) => useHeadingRefocus(key, true), {
      initialProps: { key: "loaded" },
    });
    rerender({ key: "loaded" });
    expect(document.activeElement).not.toBe(h1);
  });
});
