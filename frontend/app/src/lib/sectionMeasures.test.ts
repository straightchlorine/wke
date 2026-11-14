import { describe, expect, it } from "vitest";
import { loadDossier } from "../test/fixtures";
import { packSection } from "./dossierPack";
import type { SectionRow } from "./dossierSections";
import { measureSections } from "./sectionMeasures";

const dossier = loadDossier();

function row(index: number, tokens: number): SectionRow {
  const section = dossier.sections[index]!;
  return {
    section,
    index,
    id: `s${index + 1}`,
    pack: { ...packSection(dossier, section), includedTokens: tokens },
  };
}

const rows = [row(0, 10), row(1, 20), row(2, 5)];

describe("measureSections", () => {
  const measures = measureSections({
    rows,
    usedTokens: 40,
    headingTops: new Map([
      ["s1", 150],
      ["s2", 300],
      ["s3", 700],
    ]),
    articleTop: 100,
    articleHeight: 500,
    railTop: 250,
  });

  it("places each heading as a fraction of the article's height, and puts the last token at 1", () => {
    expect(measures.tickFractions.get("s1")).toBeCloseTo(0.1);
    expect(measures.tickFractions.get("s2")).toBeCloseTo(0.4);
    expect(measures.breakpoints).toEqual([
      { token: 0, fraction: 0.1 },
      { token: 10, fraction: 0.4 },
      { token: 30, fraction: 1 },
      { token: 40, fraction: 1 },
    ]);
  });

  it("clamps a heading above the article to 0 and below it to 1", () => {
    const clamped = measureSections({
      rows: rows.slice(0, 2),
      usedTokens: 30,
      headingTops: new Map([
        ["s1", 50],
        ["s2", 900],
      ]),
      articleTop: 100,
      articleHeight: 500,
      railTop: 0,
    });
    expect([...clamped.tickFractions.values()]).toEqual([0, 1]);
  });

  it("measures the notes' offsets from the rail's top, never above it", () => {
    expect(measures.offsetsPx.get("s1")).toBe(0);
    expect(measures.offsetsPx.get("s2")).toBe(50);
    expect(measures.offsetsPx.get("s3")).toBe(450);
  });

  it("measures the article's bottom from the rail's top", () => {
    expect(measures.railBottomPx).toBe(350);
    expect(
      measureSections({
        rows,
        usedTokens: 1,
        headingTops: new Map(),
        articleTop: 100,
        articleHeight: 100,
        railTop: 900,
      }).railBottomPx,
    ).toBe(0);
  });

  it("skips a section with no heading but still counts its tokens for the next one", () => {
    const skipped = measureSections({
      rows,
      usedTokens: 35,
      headingTops: new Map([
        ["s1", 100],
        ["s3", 600],
      ]),
      articleTop: 100,
      articleHeight: 500,
      railTop: 0,
    });
    expect([...skipped.tickFractions.keys()]).toEqual(["s1", "s3"]);
    expect(skipped.breakpoints).toEqual([
      { token: 0, fraction: 0 },
      { token: 30, fraction: 1 },
      { token: 35, fraction: 1 },
    ]);
  });
});
