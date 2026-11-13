import type { DossierView } from "../api/dossier";
import type { Section } from "../api/generated";
import { sectionDepth } from "./sectionDepth";

export interface ProseSplit {
  /** Sections the page shows, in article order. */
  shown: Section[];
  /** Sections without prose that the page leaves out. */
  leftOut: Section[];
}

/**
 * Splits a dossier's sections into shown and left-out ones. A `no_prose` section is left out unless
 * a section nested under it has prose, in which case its heading stays as the parent.
 */
export function splitNoProse(sections: readonly Section[]): ProseSplit {
  const keep = sections.map((section) => section.summary_state !== "no_prose");
  sections.forEach((section, index) => {
    if (keep[index]) {
      return;
    }
    const depth = sectionDepth(section);
    for (
      let next = index + 1;
      next < sections.length && sectionDepth(sections[next]!) > depth;
      next += 1
    ) {
      if (sections[next]!.summary_state !== "no_prose") {
        keep[index] = true;
        return;
      }
    }
  });
  return {
    shown: sections.filter((_, index) => keep[index]),
    leftOut: sections.filter((_, index) => !keep[index]),
  };
}

/**
 * Returns the dossier with its no-prose sections removed, or the dossier itself when there are
 * none.
 */
export function withoutNoProse(dossier: DossierView): DossierView {
  const { shown, leftOut } = splitNoProse(dossier.sections);
  return leftOut.length === 0 ? dossier : { ...dossier, sections: shown };
}
