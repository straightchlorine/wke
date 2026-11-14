import { useCallback, useEffect, useLayoutEffect, useRef } from "react";
import type { DossierView } from "../../api/dossier";
import type { Budget } from "../budget";
import { announceLive } from "../liveRegion";
import { captureSectionAnchor, restoreSectionAnchor, stickyOffsetPx } from "../sectionAnchor";
import type { SectionAnchor } from "../sectionAnchorMath";

/** How long after a budget change a scroll counts as the page's own, not the reader's. */
const SETTLE_MS = 2000;
/** The same, after the scroll that puts the reader back once the new layout has rendered. */
const RESTORE_SETTLE_MS = 400;

/**
 * Keeps the reader in place when the budget changes and the page reflows around them.
 * Returns the function that changes the budget. It restores the exact scroll position the reader
 * left that budget at, and otherwise scrolls the section they were in back to where it sat.
 */
export function useBudgetScroll(
  slug: string,
  budget: Budget,
  dossier: DossierView | undefined,
  setBudgetState: (next: Budget) => void,
): (next: Budget) => void {
  // The section the reader was in before a budget change. Sections above it grow or shrink, so the
  // layout effect below scrolls its heading back to where it sat.
  const anchor = useRef<SectionAnchor | null>(null);
  // Where the page was scrolled when each budget was left. Coming back to one of them restores that
  // spot. Any scroll by the reader drops them all, and the section anchor takes over.
  const spots = useRef<Map<string, number>>(new Map());
  const returnSpot = useRef<number | null>(null);
  // Scrolls the page makes itself while a budget settles are not the reader's.
  const ownScrollUntil = useRef(0);

  const setBudget = useCallback(
    (next: Budget) => {
      if (next !== budget) {
        spots.current.set(`${slug}:${budget}`, window.scrollY);
        returnSpot.current = spots.current.get(`${slug}:${next}`) ?? null;
        ownScrollUntil.current = Date.now() + SETTLE_MS;
        anchor.current = captureSectionAnchor(stickyOffsetPx());
      }
      setBudgetState(next);
    },
    [slug, budget, setBudgetState],
  );

  useEffect(() => {
    const remembered = spots.current;
    const forget = () => remembered.clear();
    // Keys 1 to 3 change the budget and modifier keys do not scroll, so they keep the spots.
    const onKeyDown = (event: KeyboardEvent) => {
      if (!["1", "2", "3", "Shift", "Control", "Alt", "Meta"].includes(event.key)) {
        remembered.clear();
      }
    };
    const onPointerDown = (event: PointerEvent) => {
      if (!(event.target instanceof Element && event.target.closest('[role="radiogroup"]'))) {
        remembered.clear();
      }
    };
    const onScroll = () => {
      if (Date.now() > ownScrollUntil.current) {
        remembered.clear();
      }
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("wheel", forget, { passive: true });
    window.addEventListener("touchmove", forget, { passive: true });
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("pointerdown", onPointerDown);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("wheel", forget);
      window.removeEventListener("touchmove", forget);
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("pointerdown", onPointerDown);
    };
  }, []);

  // The previous dossier stays up while the new budget's request is in flight. Only a dossier
  // built for the requested budget is the new layout.
  useLayoutEffect(() => {
    const recorded = anchor.current;
    if (!recorded || !dossier || dossier.budget.requested !== budget) {
      return;
    }
    anchor.current = null;
    const spot = returnSpot.current;
    returnSpot.current = null;
    ownScrollUntil.current = Date.now() + RESTORE_SETTLE_MS;
    if (spot != null) {
      window.scrollTo(0, spot);
      return;
    }
    const result = restoreSectionAnchor(recorded, stickyOffsetPx());
    if (result?.fellBack) {
      announceLive(
        `Section ${recorded.number} is not in this budget; showing section ${result.landed}`,
      );
    }
  }, [dossier, budget]);

  return setBudget;
}
