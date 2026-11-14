import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  captureSectionAnchor,
  currentSectionIdAtLanding,
  restoreSectionAnchor,
  stickyOffsetPx,
} from "./sectionAnchor";
import { LANDING_GAP_PX } from "./sectionAnchorMath";

const STICKY = 56;
const LANDING = STICKY + LANDING_GAP_PX;

/** Gives an element a fixed box, since jsdom does no layout. */
function place(el: Element, top: number, height = 0) {
  el.getBoundingClientRect = () => new DOMRect(0, top, 0, height);
}

/** Builds an article whose sections s1.. have heading tops and heights as given. */
function article(sections: Array<{ n: number; top: number; height: number }>) {
  document.body.innerHTML = `<article>${sections
    .map(({ n }) => `<section id="s${n}"><h2 data-section-heading>H${n}</h2></section>`)
    .join("")}</article>`;
  for (const { n, top, height } of sections) {
    const section = document.getElementById(`s${n}`)!;
    place(section, top, height);
    place(section.querySelector("h2")!, top);
  }
}

describe("section anchor in the DOM", () => {
  let scrollTo: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  });

  afterEach(() => {
    document.body.innerHTML = "";
    scrollTo.mockRestore();
  });

  it("captures the heading the reader is in and where it sits", () => {
    article([
      { n: 1, top: -900, height: 800 },
      { n: 2, top: -120, height: 900 },
      { n: 3, top: 500, height: 600 },
    ]);
    expect(currentSectionIdAtLanding(STICKY)).toBe("s2");
    expect(captureSectionAnchor(STICKY)).toMatchObject({ id: "s2", number: 2, offset: -120 });
  });

  it("returns null without section headings", () => {
    document.body.innerHTML = "<article></article>";
    expect(captureSectionAnchor(STICKY)).toBeNull();
    expect(currentSectionIdAtLanding(STICKY)).toBeNull();
  });

  it("scrolls the anchored heading back to its recorded offset", () => {
    article([
      { n: 1, top: -700, height: 800 },
      { n: 2, top: 40, height: 900 },
    ]);
    const anchor = { id: "s2", number: 2, offset: 300, at: Date.now() };
    expect(restoreSectionAnchor(anchor, STICKY)).toEqual({ landed: 2, fellBack: false });
    expect(scrollTo).toHaveBeenCalledWith({ top: window.scrollY - 260, behavior: "instant" });
  });

  it("lands the heading at the landing line when its section shrank below the saved depth", () => {
    article([{ n: 1, top: 300, height: 400 }]);
    const anchor = { id: "s1", number: 1, offset: -800, at: Date.now() };
    expect(restoreSectionAnchor(anchor, STICKY)).toEqual({ landed: 1, fellBack: false });
    expect(scrollTo).toHaveBeenCalledWith({
      top: window.scrollY + 300 - LANDING,
      behavior: "instant",
    });
  });

  it("lands the nearest earlier section at the landing line when the anchored one is gone", () => {
    article([
      { n: 1, top: 300, height: 400 },
      { n: 3, top: 900, height: 400 },
    ]);
    const anchor = { id: "s2", number: 2, offset: 100, at: Date.now() };
    expect(restoreSectionAnchor(anchor, STICKY)).toEqual({ landed: 1, fellBack: true });
    expect(scrollTo).toHaveBeenCalledWith({
      top: window.scrollY + 300 - LANDING,
      behavior: "instant",
    });
  });

  it("does not scroll when the heading is already where it was", () => {
    article([{ n: 1, top: 200, height: 400 }]);
    expect(
      restoreSectionAnchor({ id: "s1", number: 1, offset: 200, at: Date.now() }, STICKY),
    ).toEqual({
      landed: 1,
      fellBack: false,
    });
    expect(scrollTo).not.toHaveBeenCalled();
  });

  it("ignores an anchor that is too old, and one with no earlier section", () => {
    article([{ n: 2, top: 200, height: 400 }]);
    expect(
      restoreSectionAnchor({ id: "s2", number: 2, offset: 0, at: Date.now() - 60_000 }, STICKY),
    ).toBeNull();
    expect(
      restoreSectionAnchor({ id: "s1", number: 1, offset: 0, at: Date.now() }, STICKY),
    ).toBeNull();
    expect(scrollTo).not.toHaveBeenCalled();
  });
});

describe("stickyOffsetPx", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("adds the heights of the toolbar and the chip strip, and skips a hidden one", () => {
    document.body.innerHTML =
      '<div data-dossier-toolbar></div><nav aria-label="Sections" style="display:none"></nav>';
    place(document.querySelector("[data-dossier-toolbar]")!, 0, 48);
    place(document.querySelector("nav")!, 0, 40);
    expect(stickyOffsetPx()).toBe(48);
    document.querySelector<HTMLElement>("nav")!.style.display = "";
    expect(stickyOffsetPx()).toBe(88);
  });
});
