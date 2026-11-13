import { SECTION_HEADING_SELECTOR } from "./sectionDepth";

/**
 * Moves focus to a section's heading without scrolling, because the router has already scrolled it
 * into view.
 */
export function focusSectionHeading(id: string): void {
  document
    .getElementById(id)
    ?.querySelector<HTMLElement>(SECTION_HEADING_SELECTOR)
    ?.focus({ preventScroll: true });
}
