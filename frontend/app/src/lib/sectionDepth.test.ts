import { describe, expect, it } from "vitest";
import type { Section } from "../api/generated";
import { hasSubsections, sectionDepth, sectionHeadingTag } from "./sectionDepth";

const at = (depth: number | null): Section => ({
  id: "s",
  label: "L",
  label_source: "heading",
  ...(depth === null ? {} : { heading_path: Array.from({ length: depth }, (_, i) => `h${i}`) }),
  summary_state: "done",
  chunk_ids: [],
});

describe("sectionDepth", () => {
  it.each([
    [null, 1],
    [0, 1],
    [1, 1],
    [3, 3],
  ])("reads depth %s as %s", (path, depth) => {
    expect(sectionDepth(at(path))).toBe(depth);
  });
});

describe("hasSubsections", () => {
  it("is true only when the next section is deeper", () => {
    const sections = [at(1), at(2), at(2), at(1)];
    expect(sections.map((_, i) => hasSubsections(sections, i))).toEqual([
      true,
      false,
      false,
      false,
    ]);
  });
});

describe("sectionHeadingTag", () => {
  it.each([
    [1, "h2"],
    [2, "h3"],
    [5, "h6"],
    [9, "h6"],
  ])("renders depth %s as %s", (depth, tag) => {
    expect(sectionHeadingTag(at(depth))).toBe(tag);
  });
});
