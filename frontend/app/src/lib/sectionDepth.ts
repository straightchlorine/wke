import type { Section } from "../api/generated";

/** Returns the nesting depth of a section: the length of its `heading_path`, at least 1. */
export function sectionDepth(section: Section): number {
  return Math.max(1, section.heading_path?.length ?? 1);
}

/** Returns whether the section after `index` is nested deeper than the section at `index`. */
export function hasSubsections(sections: Section[], index: number): boolean {
  const next = sections[index + 1];
  return next != null && sectionDepth(next) > sectionDepth(sections[index]!);
}

const HEADING_TAGS = ["h2", "h3", "h4", "h5", "h6"] as const;

/**
 * Returns the heading tag for a section: h2 at depth 1, one level lower per level of depth, capped
 * at h6.
 */
export function sectionHeadingTag(section: Section): "h2" | "h3" | "h4" | "h5" | "h6" {
  return HEADING_TAGS[Math.min(sectionDepth(section), HEADING_TAGS.length) - 1] ?? "h6";
}

export const SECTION_HEADING_SELECTOR = "[data-section-heading]";
