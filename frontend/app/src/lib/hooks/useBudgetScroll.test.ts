import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import type { DossierView } from "../../api/dossier";
import type { Budget } from "../budget";
import { loadDossier } from "../../test/fixtures";
import { useBudgetScroll } from "./useBudgetScroll";

const base = loadDossier();
const dossierAt = (requested: Budget): DossierView => ({
  ...base,
  budget: { ...base.budget, requested },
});

interface Props {
  budget: Budget;
  dossier: DossierView | undefined;
}

function setScrollY(y: number) {
  Object.defineProperty(window, "scrollY", { value: y, configurable: true, writable: true });
}

const setBudgetState = vi.fn();

function mountAt8k() {
  return renderHook(
    ({ budget, dossier }: Props) => useBudgetScroll("jesus", budget, dossier, setBudgetState),
    { initialProps: { budget: 8000, dossier: dossierAt(8000) } },
  );
}

describe("useBudgetScroll", () => {
  const scrollTo = vi.fn();

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00Z"));
    window.scrollTo = scrollTo;
    document.body.innerHTML =
      '<article><section id="s1"><h2 data-section-heading></h2></section></article>';
  });

  afterEach(() => {
    vi.useRealTimers();
    scrollTo.mockReset();
    setBudgetState.mockReset();
    document.body.innerHTML = "";
  });

  /** Mounts the hook at 8000, leaves for 2000 at scrollY 500, and lets the 2000 dossier arrive. */
  function leaveEightK() {
    setScrollY(500);
    const hook = mountAt8k();
    act(() => hook.result.current(2000));
    hook.rerender({ budget: 2000, dossier: dossierAt(2000) });
    scrollTo.mockClear();
    return hook;
  }

  it("hands the new budget to the setter", () => {
    const hook = renderHook(() => useBudgetScroll("jesus", 8000, dossierAt(8000), setBudgetState));
    act(() => hook.result.current(8000));
    expect(setBudgetState).toHaveBeenCalledWith(8000);
    act(() => hook.result.current(2000));
    expect(setBudgetState).toHaveBeenLastCalledWith(2000);
  });

  it("scrolls the section the reader was in back under the sticky bars once the new budget's dossier is shown", () => {
    setScrollY(500);
    const hook = mountAt8k();
    act(() => hook.result.current(2000));
    hook.rerender({ budget: 2000, dossier: dossierAt(8000) });
    expect(scrollTo).not.toHaveBeenCalled();
    hook.rerender({ budget: 2000, dossier: dossierAt(2000) });
    expect(scrollTo).toHaveBeenCalledTimes(1);
  });

  it("returns to the exact spot the reader left a budget at", () => {
    const hook = leaveEightK();
    setScrollY(120);
    act(() => hook.result.current(8000));
    hook.rerender({ budget: 8000, dossier: dossierAt(8000) });
    expect(scrollTo).toHaveBeenCalledWith(0, 500);
  });

  it("forgets the spots once the reader scrolls on their own", () => {
    const hook = leaveEightK();
    vi.advanceTimersByTime(3000);
    act(() => void window.dispatchEvent(new Event("scroll")));
    setScrollY(120);
    act(() => hook.result.current(8000));
    hook.rerender({ budget: 8000, dossier: dossierAt(8000) });
    expect(scrollTo).not.toHaveBeenCalledWith(0, 500);
  });

  it("does not count a scroll the page makes itself while the budget settles as the reader's", () => {
    const hook = leaveEightK();
    act(() => void window.dispatchEvent(new Event("scroll")));
    setScrollY(120);
    act(() => hook.result.current(8000));
    hook.rerender({ budget: 8000, dossier: dossierAt(8000) });
    expect(scrollTo).toHaveBeenCalledWith(0, 500);
  });

  it("keeps the spot of the budget just left when the page scrolls itself while the new one loads", () => {
    setScrollY(500);
    const hook = mountAt8k();
    act(() => hook.result.current(2000));
    act(() => void window.dispatchEvent(new Event("scroll")));
    hook.rerender({ budget: 2000, dossier: dossierAt(2000) });
    vi.advanceTimersByTime(3000);
    scrollTo.mockClear();
    setScrollY(120);
    act(() => hook.result.current(8000));
    hook.rerender({ budget: 8000, dossier: dossierAt(8000) });
    expect(scrollTo).toHaveBeenCalledWith(0, 500);
  });

  it("does not scroll when the budget it is given is the one already shown", () => {
    setScrollY(300);
    const hook = renderHook(
      ({ dossier }) => useBudgetScroll("jesus", 8000, dossier, setBudgetState),
      { initialProps: { dossier: dossierAt(8000) } },
    );
    act(() => hook.result.current(8000));
    hook.rerender({ dossier: dossierAt(8000) });
    expect(scrollTo).not.toHaveBeenCalled();
  });

  it.each([
    ["a wheel turn", () => window.dispatchEvent(new Event("wheel")), false],
    ["a touch move", () => window.dispatchEvent(new Event("touchmove")), false],
    [
      "a press elsewhere on the page",
      () => document.body.dispatchEvent(new Event("pointerdown", { bubbles: true })),
      false,
    ],
    ["a letter key", () => window.dispatchEvent(new KeyboardEvent("keydown", { key: "a" })), false],
    ["a budget key", () => window.dispatchEvent(new KeyboardEvent("keydown", { key: "2" })), true],
    [
      "a modifier key",
      () => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Shift" })),
      true,
    ],
  ])("%s: the spot is kept: %s", (_name, act_, kept) => {
    const hook = leaveEightK();
    act(() => void act_());
    setScrollY(120);
    act(() => hook.result.current(8000));
    hook.rerender({ budget: 8000, dossier: dossierAt(8000) });
    expect(scrollTo.mock.calls.some(([x, y]) => x === 0 && y === 500)).toBe(kept);
  });

  it("keeps the spots for a pointer press on the budget control", () => {
    const control = document.createElement("div");
    control.setAttribute("role", "radiogroup");
    document.body.append(control);
    const hook = leaveEightK();
    act(() => void control.dispatchEvent(new Event("pointerdown", { bubbles: true })));
    setScrollY(120);
    act(() => hook.result.current(8000));
    hook.rerender({ budget: 8000, dossier: dossierAt(8000) });
    expect(scrollTo).toHaveBeenCalledWith(0, 500);
  });
});
