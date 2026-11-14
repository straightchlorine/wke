import { useLayoutEffect, useState, type RefObject } from "react";
import type { DossierView } from "../../api/dossier";
import type { SectionRow } from "../dossierSections";
import { measureSections, NO_MEASURES, type SectionMeasures } from "../sectionMeasures";
import { SECTION_HEADING_SELECTOR } from "../sectionDepth";

/**
 * Measures where each section heading sits, so each ruler tick and margin note lines up with its
 * section. It measures again when the dossier, the article's size, the window or the web fonts
 * change, because a font that loads late can shift every heading by a few px without resizing the
 * article.
 */
export function useSectionMeasures(
  dossier: DossierView | undefined,
  rows: readonly SectionRow[],
  articleRef: RefObject<HTMLElement | null>,
  railRef: RefObject<HTMLElement | null>,
): SectionMeasures {
  const [measures, setMeasures] = useState<SectionMeasures>(NO_MEASURES);

  useLayoutEffect(() => {
    if (!dossier) {
      return () => {};
    }
    const usedTokens = dossier.budget.used_est_tokens;
    function measure() {
      const article = articleRef.current;
      if (!article || article.offsetHeight <= 0) {
        return;
      }
      const articleTop = article.getBoundingClientRect().top;
      const headingTops = new Map<string, number>();
      for (const row of rows) {
        const section = document.getElementById(row.id);
        const heading = section?.querySelector<HTMLElement>(SECTION_HEADING_SELECTOR) ?? section;
        if (heading) {
          headingTops.set(row.id, heading.getBoundingClientRect().top);
        }
      }
      setMeasures(
        measureSections({
          rows,
          usedTokens,
          headingTops,
          articleTop,
          articleHeight: article.offsetHeight,
          railTop: railRef.current?.getBoundingClientRect().top ?? articleTop,
        }),
      );
    }

    measure();
    const article = articleRef.current;
    let observer: ResizeObserver | undefined;
    if (article && typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(() => measure());
      observer.observe(article);
    }
    window.addEventListener("resize", measure);
    let cancelled = false;
    document.fonts?.ready
      ?.then(() => {
        if (!cancelled) {
          measure();
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      observer?.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [dossier, rows, articleRef, railRef]);

  return measures;
}
