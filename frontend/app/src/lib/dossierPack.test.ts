import { describe, expect, it } from "vitest";
import { loadDossier } from "../test/fixtures";
import type { Chunk, Citation, RevisionPin } from "../api/generated";
import {
  citationFor,
  citationHref,
  citationNotes,
  humaniseAnchor,
  packSection,
  sectionChunks,
  sectionGroupSummary,
} from "./dossierPack";

const dossier8k = loadDossier();
const dossier2k = loadDossier("dossier_1095706_2000.json");

describe("sectionChunks", () => {
  it("resolves a section's chunk_ids to Chunk objects in order", () => {
    const section = dossier8k.sections[0];
    if (!section) throw new Error("fixture has no sections");
    const chunks = sectionChunks(dossier8k, section);
    expect(chunks.map((c) => c.id)).toEqual(section.chunk_ids);
  });

  it("skips chunk_ids the dossier's chunks array does not carry", () => {
    const section = { ...dossier8k.sections[0]!, chunk_ids: ["not-a-real-id"] };
    expect(sectionChunks(dossier8k, section)).toEqual([]);
  });
});

describe("packSection", () => {
  it("marks a section full when every listed chunk is in the budget", () => {
    const full = dossier8k.sections.find((s) => {
      const pack = packSection(dossier8k, s);
      return pack.state === "full" && s.chunk_ids.length > 0;
    });
    if (!full) throw new Error("expected at least one full section at 8k");
    const pack = packSection(dossier8k, full);
    expect(pack.heldBackChunkIds).toEqual([]);
    expect(pack.includedChunks.length).toBe(full.chunk_ids.length);
  });

  it("marks a section cut when some but not all chunk ids are held back", () => {
    const cut = dossier2k.sections.find((s) => packSection(dossier2k, s).state === "cut");
    if (!cut) throw new Error("expected at least one cut section at 2k");
    const pack = packSection(dossier2k, cut);
    expect(pack.includedChunks.length).toBeGreaterThan(0);
    expect(pack.heldBackChunkIds.length).toBeGreaterThan(0);
    expect(pack.includedChunks.length + pack.heldBackChunkIds.length).toBe(cut.chunk_ids.length);
  });

  it("marks a section folded when the 2k budget kept none of its chunk ids", () => {
    const folded = dossier2k.sections.find((s) => {
      const pack = packSection(dossier2k, s);
      return pack.state === "folded" && s.chunk_ids.length > 0;
    });
    if (!folded) throw new Error("expected at least one folded section at 2k");
    const pack = packSection(dossier2k, folded);
    expect(pack.includedChunks).toEqual([]);
    expect(pack.heldBackChunkIds.length).toBe(folded.chunk_ids.length);
  });

  it("computes the relevance range over the chunks the budget actually returned", () => {
    const section = dossier8k.sections.find((s) => s.chunk_ids.length > 1);
    if (!section) throw new Error("expected a section with more than one chunk");
    const pack = packSection(dossier8k, section);
    const relevances = pack.includedChunks.map((c) => c.relevance);
    expect(pack.relevanceRange).toEqual([Math.min(...relevances), Math.max(...relevances)]);
  });

  it("reports a null relevance range for a section with no chunks", () => {
    const empty = dossier8k.sections.find((s) => s.chunk_ids.length === 0);
    if (!empty) throw new Error("expected a section with no chunks in the fixture");
    expect(packSection(dossier8k, empty).relevanceRange).toBeNull();
  });
});

const PIN: RevisionPin = {
  page_id: 1,
  title: "Lizzie Borden",
  rev_id: 7,
  rev_timestamp: "2026-01-01T00:00:00Z",
  url: "https://x/",
  permalink: "https://x/?oldid=7",
  license: "CC BY-SA 4.0",
  retrieved_at: "2026-01-02T00:00:00Z",
};
const seed = (id: string, anchor?: string): Citation => ({
  id,
  role: "seed",
  pin: PIN,
  ...(anchor ? { anchor, url: `https://x/?oldid=7#${anchor}` } : {}),
});
const related = (id: string): Citation => ({ ...seed(id), role: "related" });
const makeChunk = (id: string, citation_id: string, heading_path: string[]): Chunk => ({
  id,
  citation_id,
  heading_path,
  order: 0,
  text: "t",
  est_tokens: 1,
  relevance: 0,
});

describe("citationNotes", () => {
  const dossier = {
    citations: [
      seed("c1"),
      related("c2"),
      related("c3"),
      seed("c4", "Early_life"),
      seed("c5", "Trial_and_acquittal"),
      seed("c6", "%22William_Borden%22"),
    ],
    chunks: [
      makeChunk("k1", "c1", []),
      makeChunk("k3", "c4", []),
      makeChunk("k4", "c4", ["Childhood"]),
      makeChunk("k6", "c6", ["Siblings", "William Borden"]),
    ],
  };

  it("numbers the cited seed citations first with no gaps, then the related ones", () => {
    const notes = citationNotes(dossier);
    expect(notes.cited.map((n) => [n.citation.id, n.n])).toEqual([
      ["c1", 1],
      ["c4", 2],
      ["c6", 3],
    ]);
    expect(notes.related.map((n) => [n.citation.id, n.n])).toEqual([
      ["c2", 4],
      ["c3", 5],
    ]);
  });

  it("leaves out a seed citation no passage points at", () => {
    expect(citationNotes(dossier).numbers.has("c5")).toBe(false);
  });

  it("names the section from the passage heading, else from the anchor, else none", () => {
    const [lead, early, third] = citationNotes(dossier).cited;
    expect(lead?.section).toBeNull();
    expect(early?.section).toBe("Childhood");
    expect(third?.section).toBe("William Borden");
  });
});

describe("humaniseAnchor", () => {
  it("turns underscores into spaces and decodes percent escapes", () => {
    expect(humaniseAnchor("Trial_and_acquittal")).toBe("Trial and acquittal");
    expect(humaniseAnchor("%22William_Borden%22")).toBe("William Borden");
    expect(humaniseAnchor("_Early_life_")).toBe("Early life");
  });

  it("keeps an anchor with a malformed escape", () => {
    expect(humaniseAnchor("100%_sure")).toBe("100% sure");
  });
});

describe("citationHref", () => {
  it("prefers the section url over the revision permalink", () => {
    const base = seed("c");
    expect(citationHref(base)).toBe(PIN.permalink);
    expect(citationHref({ ...base, url: "https://x/?oldid=7#A" })).toBe("https://x/?oldid=7#A");
  });
});

describe("citationFor", () => {
  it("resolves a chunk's citation_id to its Citation", () => {
    const chunk = dossier8k.chunks[0];
    if (!chunk) throw new Error("fixture has no chunks");
    const citation = citationFor(dossier8k.citations, chunk);
    expect(citation?.id).toBe(chunk.citation_id);
  });

  it("every chunk in the fixture resolves to a real citation", () => {
    for (const chunk of dossier8k.chunks) {
      expect(citationFor(dossier8k.citations, chunk)).not.toBeNull();
    }
  });
});

describe("sectionGroupSummary", () => {
  it("names the group as N of M, counting the groups the dossier holds", () => {
    const section = dossier8k.sections.find((s) =>
      sectionChunks(dossier8k, s).some((c) => c.cluster_id != null),
    );
    if (!section) throw new Error("fixture has no grouped section");
    const ids = new Set(dossier8k.chunks.map((c) => c.cluster_id).filter((id) => id != null));
    const text = sectionGroupSummary(dossier8k, section);
    expect(text).toMatch(
      new RegExp(
        `^passages (in group \\d+|split across groups \\d+(, \\d+)*( and \\d+)?) of ${ids.size}$`,
      ),
    );
  });

  it("says the group and the total for a single-group section", () => {
    const chunk = {
      id: "c1",
      citation_id: "x",
      heading_path: ["A"],
      order: 0,
      text: "t",
      est_tokens: 1,
      relevance: 0.5,
    };
    const view = {
      ...dossier8k,
      build: { ...dossier8k.build, analysis: "ml" as const },
      chunks: [
        { ...chunk, id: "c1", cluster_id: 1 },
        { ...chunk, id: "c2", cluster_id: 0 },
        { ...chunk, id: "c3", cluster_id: 2 },
      ],
    };
    const section = {
      id: "s1",
      label: "A",
      label_source: "heading" as const,
      chunk_ids: ["c1"],
      summary_state: "skipped" as const,
    };
    expect(sectionGroupSummary(view, section)).toBe("passages in group 2 of 3");
    expect(sectionGroupSummary(view, { ...section, chunk_ids: ["c1", "c3"] })).toBe(
      "passages split across groups 2 and 3 of 3",
    );
  });

  it("counts a group no returned passage has when a higher group is present, and lists groups in order", () => {
    const chunk = {
      id: "c1",
      citation_id: "x",
      heading_path: ["A"],
      order: 0,
      text: "t",
      est_tokens: 1,
      relevance: 0.5,
    };
    const view = {
      ...dossier8k,
      build: { ...dossier8k.build, analysis: "ml" as const },
      chunks: [
        { ...chunk, id: "c1", cluster_id: 0 },
        { ...chunk, id: "c2", cluster_id: 3 },
      ],
    };
    const section = {
      id: "s1",
      label: "A",
      label_source: "heading" as const,
      chunk_ids: ["c1"],
      summary_state: "skipped" as const,
    };
    expect(sectionGroupSummary(view, section)).toBe("passages in group 1 of 4");
    expect(sectionGroupSummary(view, { ...section, chunk_ids: [] })).toBeNull();
    expect(sectionGroupSummary(view, { ...section, chunk_ids: ["c2", "c1"] })).toBe(
      "passages split across groups 1 and 4 of 4",
    );
  });

  it("returns null for a structural build", () => {
    const view = { ...dossier8k, build: { ...dossier8k.build, analysis: "structural" as const } };
    expect(sectionGroupSummary(view, view.sections[0]!)).toBeNull();
  });
});
