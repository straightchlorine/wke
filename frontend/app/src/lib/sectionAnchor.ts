import {
  LANDING_GAP_PX,
  pickAnchorIndex,
  restoredOffset,
  type SectionAnchor,
} from "./sectionAnchorMath";
import { SECTION_HEADING_SELECTOR } from "./sectionDepth";

export type { SectionAnchor };

/**
 * Selectors of the two bars that stick to the top of the dossier page: the toolbar and the
 * section-chip strip.
 */
export const STICKY_BAR_SELECTORS = '[data-dossier-toolbar], nav[aria-label="Sections"]';

// A recorded anchor older than this is ignored. It belongs to a budget change
// whose request failed, and must not move the page on a later refetch.
const ANCHOR_MAX_AGE_MS = 10_000;

/** Returns the rendered height of a sticky element, or 0 when it is absent or display:none. */
export function visibleHeight(el: HTMLElement | null): number {
  return el && getComputedStyle(el).display !== "none" ? el.getBoundingClientRect().height : 0;
}

/**
 * Returns the combined height of the toolbar and the section-chip strip, each counting 0 while it
 * is hidden.
 */
export function stickyOffsetPx(): number {
  let total = 0;
  for (const bar of document.querySelectorAll<HTMLElement>(STICKY_BAR_SELECTORS)) {
    total += visibleHeight(bar);
  }
  return total;
}

function sectionHeadings(): Array<{ id: string; number: number; h2: HTMLElement }> {
  const found: Array<{ id: string; number: number; h2: HTMLElement }> = [];
  for (const section of document.querySelectorAll<HTMLElement>("article section[id]")) {
    const match = /^s(\d+)$/.exec(section.id);
    const h2 = section.querySelector<HTMLElement>(SECTION_HEADING_SELECTOR);
    if (match && h2) {
      found.push({ id: section.id, number: Number(match[1]), h2 });
    }
  }
  return found;
}

/**
 * Returns the id of the last section whose heading is at or above the landing line, else the first
 * section, or null when there are no section headings. The landing line sits LANDING_GAP_PX below
 * the sticky bars, where a heading comes to rest after a jump.
 */
export function currentSectionIdAtLanding(sticky: number): string | null {
  const headings = sectionHeadings();
  const tops = headings.map((heading) => heading.h2.getBoundingClientRect().top);
  return headings[pickAnchorIndex(tops, sticky + LANDING_GAP_PX)]?.id ?? null;
}

/**
 * Records the section heading the reader is in and its offset before a budget change reflows the
 * page, or returns null without section headings.
 */
export function captureSectionAnchor(sticky: number): SectionAnchor | null {
  const headings = sectionHeadings();
  const tops = headings.map((heading) => heading.h2.getBoundingClientRect().top);
  const index = pickAnchorIndex(tops, sticky + LANDING_GAP_PX);
  const heading = headings[index];
  if (!heading) {
    return null;
  }
  return { id: heading.id, number: heading.number, offset: tops[index] ?? 0, at: Date.now() };
}

/**
 * Scrolls back to the recorded section, or to the nearest earlier one when it is gone, and returns
 * the section landed on or null when the anchor is stale or no section qualifies.
 */
export function restoreSectionAnchor(
  anchor: SectionAnchor,
  sticky: number,
): { landed: number; fellBack: boolean } | null {
  if (Date.now() - anchor.at > ANCHOR_MAX_AGE_MS) {
    return null;
  }
  const headings = sectionHeadings();
  const landing = sticky + LANDING_GAP_PX;
  const exact = headings.find((heading) => heading.number === anchor.number);
  const target = exact ?? headings.findLast((heading) => heading.number < anchor.number);
  if (!target) {
    return null;
  }
  const section = document.getElementById(target.id);
  const wanted = exact
    ? restoredOffset(anchor.offset, landing, section?.getBoundingClientRect().height ?? 0)
    : landing;
  const delta = target.h2.getBoundingClientRect().top - wanted;
  if (Math.abs(delta) >= 1) {
    window.scrollTo({ top: window.scrollY + delta, behavior: "instant" });
  }
  return { landed: target.number, fellBack: exact == null };
}
