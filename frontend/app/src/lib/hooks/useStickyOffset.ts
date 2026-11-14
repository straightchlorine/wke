import { useLayoutEffect } from "react";
import type { DossierView } from "../../api/dossier";
import { STICKY_BAR_SELECTORS, stickyOffsetPx } from "../sectionAnchor";

/**
 * While a dossier is shown, publishes the height of the sticky bars as the `--dossier-stick`
 * property on the page root, for the scroll margin of the sections. The height varies because the
 * chip strip is taller on a coarse pointer and the toolbar wraps, so it is measured.
 */
export function useStickyOffset(dossier: DossierView | undefined): void {
  useLayoutEffect(() => {
    if (!dossier) {
      return () => {};
    }
    const root = document.documentElement;
    const update = () => root.style.setProperty("--dossier-stick", `${stickyOffsetPx()}px`);
    update();
    const observer = new ResizeObserver(update);
    for (const bar of document.querySelectorAll(STICKY_BAR_SELECTORS)) {
      observer.observe(bar);
    }
    window.addEventListener("resize", update);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", update);
      root.style.removeProperty("--dossier-stick");
    };
  }, [dossier]);
}
