import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import type { DossierView } from "../../api/dossier";
import { loadDossier } from "../../test/fixtures";
import { packSection } from "../dossierPack";
import type { SectionRow } from "../dossierSections";
import { useSectionMeasures } from "./useSectionMeasures";

const base = loadDossier();
const rows: SectionRow[] = [10, 20].map((tokens, index) => {
  const section = base.sections[index]!;
  return {
    section,
    index,
    id: `s${index + 1}`,
    pack: { ...packSection(base, section), includedTokens: tokens },
  };
});
const dossier: DossierView = { ...base, budget: { ...base.budget, used_est_tokens: 35 } };

class FakeResizeObserver {
  observe() {}
  disconnect() {}
}

const at = (el: Element, top: number) => {
  el.getBoundingClientRect = () => new DOMRect(0, top, 0, 0);
};

function layOut(articleHeight: number) {
  document.body.innerHTML = `<article id="a"></article><div id="rail"></div>
    <section id="s1"><h2 data-section-heading></h2></section>
    <section id="s2"><h2 data-section-heading></h2></section>`;
  const article = document.getElementById("a")!;
  at(article, 100);
  Object.defineProperty(article, "offsetHeight", { value: articleHeight });
  at(document.getElementById("rail")!, 50);
  at(document.querySelector("#s1 h2")!, 200);
  at(document.querySelector("#s2 h2")!, 600);
  return { article, rail: document.getElementById("rail")! };
}

describe("useSectionMeasures", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("measures the headings against the article and the rail", () => {
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    const { article, rail } = layOut(500);
    const refs = [{ current: article }, { current: rail }] as const;
    const { result } = renderHook(() => useSectionMeasures(dossier, rows, ...refs));
    expect(result.current.tickFractions.get("s1")).toBeCloseTo(0.2);
    expect(result.current.tickFractions.get("s2")).toBeCloseTo(1);
    expect(result.current.offsetsPx.get("s1")).toBe(150);
    expect(result.current.railBottomPx).toBe(550);
    expect(result.current.breakpoints.at(-1)).toEqual({ token: 35, fraction: 1 });
  });

  it("measures nothing for an article that has no height yet, or without a dossier", () => {
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    const { article, rail } = layOut(0);
    const refs = [{ current: article }, { current: rail }] as const;
    const empty = renderHook(() => useSectionMeasures(dossier, rows, ...refs));
    expect(empty.result.current.breakpoints).toEqual([]);
    const none = renderHook(() => useSectionMeasures(undefined, rows, ...refs));
    expect(none.result.current.breakpoints).toEqual([]);
  });
});
