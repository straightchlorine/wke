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

  it("shows a table passage as a table, a list passage as a list and anything else as a paragraph", () => {
    const mixed: Chunk[] = [
      { ...baseChunk, id: "p", citation_id: "c1", kind: "prose", text: "Some prose." },
      {
        ...baseChunk,
        id: "t",
        citation_id: "c1",
        kind: "table",
        text: "Cap\n| A | B |\n| --- | --- |\n| 1 | 2 |",
      },
      { ...baseChunk, id: "l", citation_id: "c1", kind: "list", text: "- x\n  - y" },
    ];
    const { container } = render(
      <PassageList chunks={mixed} citations={citations} numbers={numbers} />,
    );
    expect([...container.querySelectorAll("[id^='chunk-']")].map((el) => el.id)).toEqual([
      "chunk-p",
      "chunk-t",
      "chunk-l",
    ]);
    expect(container.querySelector("p#chunk-p")).not.toBeNull();
    expect(container.querySelectorAll("table tbody tr")).toHaveLength(1);
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(container.querySelectorAll("a")).toHaveLength(1);
  });

  it("falls back to a paragraph for a table or list text that does not parse", () => {
    const odd: Chunk[] = [
      { ...baseChunk, id: "t", citation_id: "c2", kind: "table", text: "Not a table at all" },
      { ...baseChunk, id: "l", citation_id: "c2", kind: "list", text: "plain words\nmore words" },
    ];
    const { container } = render(
      <PassageList chunks={odd} citations={citations} numbers={numbers} />,
    );
    expect(container.querySelectorAll("table, ul")).toHaveLength(0);
    expect([...container.querySelectorAll("p")].map((p) => p.id)).toEqual(["chunk-t", "chunk-l"]);
  });
});
