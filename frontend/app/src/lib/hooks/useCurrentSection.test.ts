import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import type { DossierView } from "../../api/dossier";
import { loadDossier } from "../../test/fixtures";
import { useCurrentSection } from "./useCurrentSection";

const base = loadDossier();
const dossier: DossierView = { ...base, sections: base.sections.slice(0, 3) };

/** Puts three section headings at the given tops. */
function layOut(tops: [number, number, number]) {
  document.body.innerHTML = `<article>${tops
    .map((_, i) => `<section id="s${i + 1}"><h2 data-section-heading></h2></section>`)
    .join("")}</article>`;
  document.querySelectorAll<HTMLElement>("[data-section-heading]").forEach((h2, i) => {
    h2.getBoundingClientRect = () => new DOMRect(0, tops[i], 0, 0);
  });
}

function scrollTo(y: number) {
  Object.defineProperty(window, "scrollY", { value: y, configurable: true, writable: true });
  window.dispatchEvent(new Event("scroll"));
  vi.advanceTimersByTime(20);
}

describe("useCurrentSection", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    Object.defineProperty(document.documentElement, "scrollHeight", {
      value: 5000,
      configurable: true,
    });
    Object.defineProperty(window, "scrollY", { value: 0, configurable: true, writable: true });
  });
  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = "";
  });

  it("is null without a dossier, and the first section before any heading has reached the line below the sticky bars", () => {
    layOut([200, 600, 900]);
    expect(renderHook(() => useCurrentSection(undefined)).result.current).toBeNull();
    expect(renderHook(() => useCurrentSection(dossier)).result.current).toBe("s1");
  });

  it("follows the last heading at or above the line below the sticky bars as the reader scrolls", () => {
    layOut([-300, 500, 900]);
    const { result } = renderHook(() => useCurrentSection(dossier));
    expect(result.current).toBe("s1");
    layOut([-800, 10, 400]);
    act(() => scrollTo(100));
    expect(result.current).toBe("s2");
  });

  it("is the last section as soon as the page is scrolled to its end, though its heading never reaches the line", () => {
    layOut([-800, -400, 700]);
    const { result } = renderHook(() => useCurrentSection(dossier));
    expect(result.current).toBe("s2");
    act(() => scrollTo(5000 - window.innerHeight));
    expect(result.current).toBe("s3");
  });
});
