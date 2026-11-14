import { useEffect, useState } from "react";
import type { DossierView } from "../../api/dossier";
import { currentSectionIdAtLanding, stickyOffsetPx } from "../sectionAnchor";

/**
 * Returns the id of the section the reader is in: the last heading at or above the landing line,
 * where a heading comes to rest below the sticky bars after a jump. A budget change anchors the page
 * with the same rule, so the Contents mark and the restored position agree. At the end of the page
 * it is the last section.
 */
export function useCurrentSection(dossier: DossierView | undefined): string | null {
  const [currentId, setCurrentId] = useState<string | null>(null);

  useEffect(() => {
    if (!dossier) {
      return () => {};
    }
    // When the document ends first, the last heading never reaches the landing line.
    const lastSectionId = `s${dossier.sections.length}`;
    let frame = 0;
    function markCurrentSection() {
      frame = 0;
      const atBottom =
        window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2;
      const id = atBottom ? lastSectionId : currentSectionIdAtLanding(stickyOffsetPx());
      if (id) {
        setCurrentId(id);
      }
    }
    function scheduleMark() {
      if (frame === 0) {
        frame = requestAnimationFrame(markCurrentSection);
      }
    }
    markCurrentSection();
    window.addEventListener("scroll", scheduleMark, { passive: true });
    window.addEventListener("resize", scheduleMark);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", scheduleMark);
      window.removeEventListener("resize", scheduleMark);
    };
  }, [dossier]);

  return currentId;
}
