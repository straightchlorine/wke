import { describe, expect, it } from "vitest";
import type { Section } from "../api/generated";
import { loadDossier } from "../test/fixtures";
import { splitNoProse, withoutNoProse } from "./proseSections";

const section = (label: string, depth: number, state: Section["summary_state"]): Section => ({
  id: label,
  label,
  label_source: "heading",
  heading_path: Array.from({ length: depth }, (_, i) => `h${i}`),
  summary_state: state,
  chunk_ids: state === "no_prose" ? [] : ["c"],
});

describe("splitNoProse", () => {
  it("keeps everything when every section has prose", () => {
    const sections = [section("A", 1, "done"), section("B", 1, "skipped")];
    expect(splitNoProse(sections)).toEqual({ shown: sections, leftOut: [] });
  });

  it("leaves out a childless section without prose", () => {
    const [a, b, c] = [
      section("A", 1, "done"),
      section("B", 1, "no_prose"),
      section("C", 1, "done"),
    ];
    expect(splitNoProse([a, b, c])).toEqual({ shown: [a, c], leftOut: [b] });
  });

  it("keeps a heading whose subsection has prose", () => {
    const [parent, child, sibling] = [
      section("P", 1, "no_prose"),
      section("P.1", 2, "skipped"),
      section("S", 1, "no_prose"),
    ];
    expect(splitNoProse([parent, child, sibling])).toEqual({
      shown: [parent, child],
      leftOut: [sibling],
    });
  });

  it("drops a parent whose subsections are all without prose, with them", () => {
    const sections = [
      section("A", 1, "done"),
      section("P", 1, "no_prose"),
      section("P.1", 2, "no_prose"),
      section("P.2", 2, "no_prose"),
    ];
    const split = splitNoProse(sections);
    expect(split.shown.map((s) => s.label)).toEqual(["A"]);
    expect(split.leftOut.map((s) => s.label)).toEqual(["P", "P.1", "P.2"]);
  });

  it("looks only at the section's own descendants, not at what follows them", () => {
    const sections = [section("P", 1, "no_prose"), section("N", 1, "done")];
    expect(splitNoProse(sections).leftOut.map((s) => s.label)).toEqual(["P"]);
  });

  it("keeps a deep chain whose leaf has prose", () => {
    const sections = [
      section("P", 1, "no_prose"),
      section("P.1", 2, "no_prose"),
      section("P.1.1", 3, "done"),
    ];
    expect(splitNoProse(sections).leftOut).toEqual([]);
  });
});

describe("withoutNoProse", () => {
  it("returns the same dossier when no section is left out", () => {
    const dossier = loadDossier();
    const prose = { ...dossier, sections: [section("A", 1, "done")] };
    expect(withoutNoProse(prose)).toBe(prose);
  });

  it("drops the no-prose sections and keeps the rest of the dossier", () => {
    const dossier = loadDossier();
    const kept = section("A", 1, "done");
    const result = withoutNoProse({ ...dossier, sections: [kept, section("B", 1, "no_prose")] });
    expect(result.sections).toEqual([kept]);
    expect(result.chunks).toBe(dossier.chunks);
  });
});
