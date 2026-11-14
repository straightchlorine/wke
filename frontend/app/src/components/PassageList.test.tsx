import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import type { Chunk, Citation } from "../api/generated";
import { loadDossier } from "../test/fixtures";
import { PassageList } from "./PassageList";

const dossier = loadDossier();
const baseCitation = dossier.citations[0]!;
const baseChunk = dossier.chunks[0]!;
const citations: Citation[] = [
  { ...baseCitation, id: "c1", url: "https://wiki/s1" },
  { ...baseCitation, id: "c2", url: undefined },
];
const numbers = new Map([
  ["c1", 1],
  ["c2", 2],
]);
const chunks: Chunk[] = [
  { ...baseChunk, id: "a", citation_id: "c1", text: "First passage here." },
  { ...baseChunk, id: "b", citation_id: "c1", text: "Second passage." },
  { ...baseChunk, id: "c", citation_id: "c2", text: "Third" },
];

function paragraphs() {
  const { container } = render(
    <PassageList chunks={chunks} citations={citations} numbers={numbers} />,
  );
  return [...container.querySelectorAll("p")];
}

describe("PassageList", () => {
  it("renders one paragraph per passage, anchored by its id", () => {
    expect(paragraphs().map((p) => p.id)).toEqual(["chunk-a", "chunk-b", "chunk-c"]);
  });

  it("puts a numbered link to the citation after the first passage of that citation only", () => {
    const links = paragraphs().map((p) => p.querySelector("a"));
    expect(links[0]?.textContent).toBe("[1]");
    expect(links[0]?.getAttribute("href")).toBe("https://wiki/s1");
    expect(links[1]).toBeNull();
    expect(links[2]?.textContent).toBe("[2]");
    expect(links[2]?.getAttribute("href")).toBe(baseCitation.pin.permalink);
  });

  it("keeps the last word and the marker in one no-wrap span", () => {
    const [first] = paragraphs();
    expect(first?.querySelector("span.whitespace-nowrap")?.textContent).toBe("here.[1]");
    expect(first?.textContent).toBe("First passage here.[1]");
  });
});
