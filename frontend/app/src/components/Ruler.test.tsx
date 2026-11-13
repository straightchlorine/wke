import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { Ruler, type RulerProps } from "./Ruler";

const TRACK_PX = 400;
let trackPx = TRACK_PX;

beforeEach(() => {
  trackPx = TRACK_PX;
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    get: () => trackPx,
  });
});

afterEach(() => {
  Reflect.deleteProperty(HTMLElement.prototype, "offsetHeight");
});

function renderRuler(props: Partial<RulerProps> = {}) {
  return render(<Ruler total={4000} filled={1000} tickEvery={1000} labelEvery={2000} {...props} />);
}

function labels(container: HTMLElement) {
  return Array.from(container.querySelectorAll("[data-ruler-label]"), (el) => el.textContent);
}

function fill(container: HTMLElement) {
  return container.querySelector<HTMLElement>("div.bg-accent")?.style.height;
}

describe("Ruler", () => {
  it("says the filled and total tokens in text", () => {
    const { container } = renderRuler({ total: 4000, filled: 9000 });
    expect(container.querySelector(".sr-only")?.textContent).toBe("4,000 of 4,000 tokens");
  });

  it("draws a tick every tickEvery tokens, the last at the total", () => {
    const { container } = renderRuler();
    const tops = Array.from(
      container.querySelectorAll<HTMLElement>("span.bg-rule"),
      (el) => el.style.top,
    );
    expect(tops).toEqual(["0%", "25%", "50%", "75%", "100%"]);
  });

  it("numbers every labelEvery tokens except the total", () => {
    expect(labels(renderRuler().container)).toEqual(["0", "2,000"]);
  });

  it("keeps the last numbered tick when labels collide on a short ruler", () => {
    trackPx = 20;
    expect(labels(renderRuler().container)).toEqual(["2,000"]);
  });

  it("draws a numbered tick longer than the others", () => {
    const { container } = renderRuler();
    const ticks = Array.from(container.querySelectorAll<HTMLElement>("span.bg-rule"), (el) => ({
      left: el.style.left,
      width: el.style.width,
    }));
    const long = { left: "34px", width: "12px" };
    const short = { left: "36px", width: "8px" };
    expect(ticks).toEqual([long, short, long, short, short]);
  });

  it("labels a section at its offset, with a title naming the section", () => {
    const { container } = renderRuler({
      sectionOffsets: [{ id: "s1", label: "History", offset: 1000 }],
    });
    expect(labels(container)).toEqual(["0", "1,000", "2,000"]);
    expect(container.querySelector("[title]")?.getAttribute("title")).toBe(
      "History starts at token 1,000",
    );
  });

  it("grows the fill in proportion to the filled tokens", () => {
    expect(fill(renderRuler({ filled: 1000 }).container)).toBe("25%");
    expect(fill(renderRuler({ filled: -5 }).container)).toBe("0%");
  });

  it("follows the breakpoints for the fill and the ticks", () => {
    const { container } = renderRuler({
      filled: 2000,
      breakpoints: [
        { token: 0, fraction: 0 },
        { token: 2000, fraction: 0.8 },
        { token: 4000, fraction: 1 },
      ],
    });
    expect(fill(container)).toBe("80%");
    const tops = Array.from(
      container.querySelectorAll<HTMLElement>("span.bg-rule"),
      (el) => el.style.top,
    );
    expect(tops).toEqual(["0%", "40%", "80%", "90%", "100%"]);
  });

  it("places a section label at its measured fraction when one is given", () => {
    const { container } = renderRuler({
      sectionOffsets: [{ id: "s1", label: "History", offset: 1000, fraction: 0.6 }],
    });
    expect(container.querySelector<HTMLElement>("[title]")?.style.top).toBe(`${0.6 * TRACK_PX}px`);
  });

  it("draws an empty fill and no NaN position for a zero total", () => {
    const { container } = renderRuler({ total: 0, filled: 0 });
    expect(fill(container)).toBe("0%");
    expect(container.querySelector("span.bg-rule")?.getAttribute("style")).not.toContain("NaN");
  });
});
