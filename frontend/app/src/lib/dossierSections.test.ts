import { describe, expect, it } from "vitest";
import type { Section } from "../api/generated";
import { loadDossier } from "../test/fixtures";
import { packSection, type SectionPack } from "./dossierPack";
import {
  clusterInfoText,
  completenessNote,
  missingSummaryDetail,
  nextBudgetUp,
  rulerEntries,
  sectionRows,
  sectionTitle,
  sectionTotals,
  subsectionTokens,
  tokenOffsets,
  type SectionRow,
} from "./dossierSections";

const chunk = loadDossier().chunks[0]!;

function section(label: string, depth = 1, chunks = 1, extra: Partial<Section> = {}): Section {
  return {
    id: label,
    label,
    label_source: "heading",
    chunk_ids: Array.from({ length: chunks }, (_, i) => `${label}-${i}`),
    heading_path: Array.from({ length: depth }, (_, i) => `${label}${i}`),
    summary_state: "skipped",
    ...extra,
  };
}

function pack(state: SectionPack["state"], tokens: number, included = 1, held = 0): SectionPack {
  return {
    section: section("x"),
    includedChunks: Array.from({ length: included }, () => chunk),
    heldBackChunkIds: Array.from({ length: held }, (_, i) => `h${i}`),
    state,
    includedTokens: tokens,
    relevanceRange: null,
  };
}

function rowOf(s: Section, index: number, p: SectionPack): SectionRow {
  return { section: s, index, id: `s${index + 1}`, pack: p };
}

describe("sectionRows", () => {
  it("gives every section its position, its element id and its pack", () => {
    const dossier = loadDossier("dossier_1095706_2000.json");
    const rows = sectionRows(dossier);
    expect(rows).toHaveLength(dossier.sections.length);
    rows.forEach((row, index) => {
      expect(row.index).toBe(index);
      expect(row.id).toBe(`s${index + 1}`);
      expect(row.section).toBe(dossier.sections[index]);
      expect(row.pack).toEqual(packSection(dossier, row.section));
    });
  });
});

describe("subsectionTokens", () => {
  const rows = [
    rowOf(section("A"), 0, pack("full", 0, 0)),
    rowOf(section("A1", 2), 1, pack("full", 30)),
    rowOf(section("A1a", 3), 2, pack("full", 12)),
    rowOf(section("B"), 3, pack("full", 100)),
  ];

  it.each([
    ["adds every nested section up to the next of the same depth", 0, 42],
    ["adds only the deeper sections of a nested parent", 1, 12],
    ["is 0 for a section with no subsections", 3, 0],
    ["is 0 for an index outside the list", 9, 0],
  ])("%s", (_name, index, expected) => {
    expect(subsectionTokens(rows, index)).toBe(expected);
  });
});

describe("sectionTotals", () => {
  it("counts the sections and passages the budget kept", () => {
    const rows = [
      rowOf(section("A", 1, 3), 0, pack("cut", 10, 2, 1)),
      rowOf(section("B", 1, 2), 1, pack("folded", 0, 0, 2)),
      rowOf(section("C", 1, 4), 2, pack("full", 20, 4)),
    ];
    expect(sectionTotals(rows)).toEqual({
      shown: 2,
      leftOut: 1,
      includedPassages: 6,
      totalPassages: 9,
    });
  });
});

describe("tokenOffsets", () => {
  it("is the running total of the tokens of the sections before each one", () => {
    const rows = [10, 0, 5, 7].map((tokens, i) => rowOf(section(`S${i}`), i, pack("full", tokens)));
    expect(tokenOffsets(rows)).toEqual([0, 10, 10, 15]);
  });
});

describe("rulerEntries", () => {
  const rows = [
    rowOf(section("Lead"), 0, pack("full", 10)),
    rowOf(section("Heading only", 1, 0), 1, pack("full", 0, 0)),
    rowOf(section("Left out"), 2, pack("folded", 0, 0, 1)),
    rowOf(section("End"), 3, pack("full", 5)),
  ];

  it("marks only the sections that hold tokens, at their offsets and measured positions", () => {
    const fractions = new Map([
      ["s1", 0.1],
      ["s4", 0.8],
    ]);
    expect(rulerEntries(rows, 15, fractions)).toEqual([
      { id: "s1", label: "1 Lead", offset: 0, fraction: 0.1 },
      { id: "s4", label: "4 End", offset: 10, fraction: 0.8 },
    ]);
  });

  it("adds an overhead mark after the sections when the budget counts more tokens than they hold", () => {
    const entries = rulerEntries(rows, 40, new Map());
    expect(entries.at(-1)).toEqual({
      id: "overhead",
      label: "header, headings and summaries",
      offset: 15,
    });
    expect(entries).toHaveLength(3);
  });
});

describe("nextBudgetUp", () => {
  it.each([
    [2000, 8000],
    [8000, 32000],
    [32000, null],
  ] as const)("goes from %i to %s", (budget, expected) => {
    expect(nextBudgetUp(budget)).toBe(expected);
  });
});

describe("sectionTitle", () => {
  it.each([
    ["the label for a top-level section", section("History", 1), "History"],
    ["the label for a section with no heading path", section("Lead", 0), "Lead"],
    [
      "the heading path, joined, for a nested section",
      section("Early life", 2),
      "Early life0 > Early life1",
    ],
  ])("is %s", (_name, s, expected) => {
    expect(sectionTitle(s)).toBe(expected);
  });
});

describe("completenessNote", () => {
  const full = pack("full", 5);
  it.each([
    [
      "a section with no passages says nothing",
      section("A", 1, 0, { dropped_non_prose: true }),
      full,
      false,
      null,
    ],
    [
      "a section that dropped lists says so",
      section("A", 1, 1, { dropped_non_prose: true }),
      full,
      false,
      "Lists and tables in this section are not included.",
    ],
    [
      "a complete section says its text is complete",
      section("A", 1, 1, { dropped_non_prose: false }),
      full,
      false,
      "The source text below is complete.",
    ],
    [
      "a cut section says nothing",
      section("A", 1, 1, { dropped_non_prose: false }),
      pack("cut", 5, 1, 1),
      false,
      null,
    ],
    [
      "a truncated build says nothing",
      section("A", 1, 1, { dropped_non_prose: false }),
      full,
      true,
      null,
    ],
    ["an unknown drop says nothing", section("A", 1, 1), full, false, null],
  ])("%s", (_name, s, p, truncated, expected) => {
    expect(completenessNote(s, p, truncated)).toBe(expected);
  });
});

describe("missingSummaryDetail", () => {
  it.each([
    ["pending", "j1", "Summary pending: summarise stage, job j1."],
    [
      "unavailable",
      undefined,
      "Summary unavailable: the build did not produce one for this section.",
    ],
    ["skipped", undefined, "Summary skipped: this section was not selected for summarising."],
  ] as const)("gives the reason for a %s summary", (state, jobId, expected) => {
    const s = section("A", 1, 1, { summary_state: state });
    expect(missingSummaryDetail(s, pack("full", 5), jobId)).toBe(expected);
  });

  it("names the job only when the build has one", () => {
    const s = section("A", 1, 1, { summary_state: "pending" });
    expect(missingSummaryDetail(s, pack("full", 5), undefined)).toBe(
      "Summary pending: summarise stage.",
    );
  });

  it("adds what the budget kept of a cut section, in the singular for one passage", () => {
    const s = section("A", 3, 1, { summary_state: "skipped" });
    expect(missingSummaryDetail(s, pack("cut", 5, 1, 2), undefined)).toBe(
      "Summary skipped: this section was not selected for summarising. 1 passage below. 2 left out at this budget.",
    );
    expect(missingSummaryDetail(s, pack("cut", 5, 2, 1), undefined)).toContain("2 passages below.");
  });

  it("says a left-out section is left out", () => {
    const s = section("A", 1, 1, { summary_state: "skipped" });
    expect(missingSummaryDetail(s, pack("folded", 0, 0, 1), undefined)).toBe(
      "Summary skipped: this section was not selected for summarising. This section is left out at this budget.",
    );
  });
});

describe("clusterInfoText", () => {
  it("says no grouping ran for a structural build", () => {
    expect(clusterInfoText("structural")).toBe(
      "This heading is Wikipedia's own. No grouping ran for this build.",
    );
  });

  it("names the model and says k and the silhouette score are not reported for an ML build", () => {
    const text = clusterInfoText("ml");
    expect(text).toContain("K-means on all-MiniLM-L6-v2");
    expect(text).toContain("does not report k or the silhouette score");
  });
});
