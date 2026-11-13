import { describe, expect, it } from "vitest";
import type { Chunk, Citation } from "../api/generated";
import { loadDossier } from "../test/fixtures";
import { passageMarkers, splitLastWord } from "./passageMarkers";

const dossier = loadDossier();
const baseCitation = dossier.citations[0]!;
const baseChunk = dossier.chunks[0]!;
const permalink = baseCitation.pin.permalink;

function citation(id: string, url?: string): Citation {
  return { ...baseCitation, id, url };
}

const chunk = (id: string, citationId: string): Chunk => ({
  ...baseChunk,
  id,
  citation_id: citationId,
});

describe("passageMarkers", () => {
  const citations = [citation("c1", "https://wiki/s1"), citation("c2")];
  const numbers = new Map([
    ["c1", 1],
    ["c2", 2],
  ]);

  it("marks only the first passage of each citation, linking to the citation's address", () => {
    const chunks = [chunk("a", "c1"), chunk("b", "c1"), chunk("c", "c2"), chunk("d", "c1")];
    expect(passageMarkers(chunks, citations, numbers)).toEqual([
      { n: 1, href: "https://wiki/s1" },
      null,
      { n: 2, href: permalink },
      null,
    ]);
  });

  it("marks nothing for a passage whose citation is unknown or has no number", () => {
    const chunks = [chunk("a", "missing"), chunk("b", "c2")];
    expect(passageMarkers(chunks, citations, new Map())).toEqual([null, null]);
    expect(passageMarkers(chunks, citations, numbers)).toEqual([null, { n: 2, href: permalink }]);
  });
});

describe("splitLastWord", () => {
  it.each([
    ["the text up to its last space and the word after it", "one two three", "one two ", "three"],
    ["no head for a single word", "alone", "", "alone"],
    ["trailing whitespace dropped", "one two \n", "one ", "two"],
  ])("gives %s", (_name, text, head, lastWord) => {
    expect(splitLastWord(text)).toEqual({ head, lastWord });
  });
});
