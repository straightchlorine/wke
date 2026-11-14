import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { loadDossier } from "../../test/fixtures";
import { useStickyOffset } from "./useStickyOffset";

class FakeResizeObserver {
  static instances: FakeResizeObserver[] = [];
  observed: Element[] = [];
  disconnected = false;
  constructor(private callback: () => void) {
    FakeResizeObserver.instances.push(this);
  }
  observe(el: Element) {
    this.observed.push(el);
  }
  disconnect() {
    this.disconnected = true;
  }
  fire() {
    this.callback();
  }
}

function bar(attribute: string, value: string, height: number, tag = "div") {
  const el = document.createElement(tag);
  el.setAttribute(attribute, value);
  el.getBoundingClientRect = () => new DOMRect(0, 0, 0, height);
  document.body.append(el);
  return el;
}

/** Puts the toolbar and the chip strip in the page, and gives the hook a resize observer to use. */
function setup() {
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  bar("data-dossier-toolbar", "", 48);
  bar("aria-label", "Sections", 40, "nav");
}

const dossier = loadDossier();
const stick = () => document.documentElement.style.getPropertyValue("--dossier-stick");

describe("useStickyOffset", () => {
  afterEach(() => {
    document.body.innerHTML = "";
    FakeResizeObserver.instances = [];
  });

  it("publishes the height of the toolbar and the chip strip together, and removes it on unmount", () => {
    setup();
    const { unmount } = renderHook(() => useStickyOffset(dossier));
    expect(stick()).toBe("88px");
    unmount();
    expect(stick()).toBe("");
    expect(FakeResizeObserver.instances[0]?.disconnected).toBe(true);
  });

  it("measures again when a bar changes size", () => {
    setup();
    renderHook(() => useStickyOffset(dossier));
    const toolbar = document.querySelector<HTMLElement>("[data-dossier-toolbar]")!;
    toolbar.getBoundingClientRect = () => new DOMRect(0, 0, 0, 70);
    FakeResizeObserver.instances[0]?.fire();
    expect(stick()).toBe("110px");
    expect(FakeResizeObserver.instances[0]?.observed).toHaveLength(2);
  });

  it("publishes nothing without a dossier", () => {
    setup();
    renderHook(() => useStickyOffset(undefined));
    expect(stick()).toBe("");
  });
});
