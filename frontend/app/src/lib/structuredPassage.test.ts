import { describe, expect, it } from "vitest";
import { loadDossier } from "../test/fixtures";
import { parseList, parseTable, pieces, textLinks, type Range } from "./structuredPassage";

const slice = (text: string, range: Range) => text.slice(range.start, range.end);

const TABLE = [
  "Other personnel",
  "| Name | Activities |",
  "| --- | --- |",
  "| Farouk El-Baz | Geologist |",
  "| Kurt Debus | Rocket scientist |",
].join("\n");

describe("parseTable", () => {
  it("reads the caption, the header and the rows", () => {
    const layout = parseTable(TABLE)!;
    expect(layout.caption).toBe("Other personnel");
    expect(layout.header.map((r) => slice(TABLE, r))).toEqual(["Name", "Activities"]);
    expect(layout.rows.map((row) => row.map((r) => slice(TABLE, r)))).toEqual([
      ["Farouk El-Baz", "Geologist"],
      ["Kurt Debus", "Rocket scientist"],
    ]);
    expect(layout.note).toBeNull();
  });

  it("reads a table with no caption line", () => {
    const text = TABLE.split("\n").slice(1).join("\n");
    expect(parseTable(text)?.caption).toBe("");
    expect(parseTable(text)?.rows).toHaveLength(2);
  });

  it("reads the line that says how many rows are shown", () => {
    const text = `${TABLE}\n(21 rows; 2 shown)`;
    const layout = parseTable(text)!;
    expect(layout.note).toEqual({ total: 21, shown: 2, noun: "rows" });
    expect(layout.rows).toHaveLength(2);
  });

  it("pads a short row, keeps an empty cell and drops a column with no header and no text", () => {
    const text = [
      "Crew",
      "| Position | Astronaut |  |",
      "| --- | --- | --- |",
      "| Commander | Neil Armstrong |  |",
      "| Pilot |",
      "| Spare |  |  |",
    ].join("\n");
    const layout = parseTable(text)!;
    expect(layout.header.map((r) => slice(text, r))).toEqual(["Position", "Astronaut"]);
    expect(layout.rows.map((row) => row.map((r) => slice(text, r)))).toEqual([
      ["Commander", "Neil Armstrong"],
      ["Pilot", ""],
      ["Spare", ""],
    ]);
  });

  it("keeps a column whose header is empty when a cell under it has text", () => {
    const text = "T\n| A |  |\n| --- | --- |\n| 1 | note |";
    expect(parseTable(text)?.header).toHaveLength(2);
  });

  it("does not split a cell at an escaped pipe", () => {
    const text = "T\n| A | B |\n| --- | --- |\n| x \\| y | z |";
    const layout = parseTable(text)!;
    expect(layout.rows[0]!.map((r) => slice(text, r))).toEqual(["x \\| y", "z"]);
    expect(pieces(text, layout.rows[0]![0]!, [], true)).toEqual([{ text: "x | y", title: null }]);
  });

  it.each([
    ["an empty text", ""],
    ["prose", "Just a sentence."],
    ["no separator row", "T\n| A | B |\n| 1 | 2 |"],
    ["a header and no rows", "T\n| A | B |\n| --- | --- |"],
    ["a stray line among the rows", "T\n| A |\n| --- |\n| 1 |\nnot a row\n| 2 |"],
    ["a count note that is not last", "T\n| A |\n| --- |\n| 1 |\n(5 rows; 1 shown)\n| 2 |"],
  ])("gives up on %s", (_name, text) => {
    expect(parseTable(text)).toBeNull();
  });

  it("reads every table of the Apollo 11 fixture", () => {
    const tables = loadDossier("dossier_662_8000.json").chunks.filter((c) => c.kind === "table");
    expect(tables).toHaveLength(3);
    expect(tables.map((c) => parseTable(c.text)?.rows.length)).toEqual([3, 3, 12]);
  });
});

describe("parseList", () => {
  it("reads items, nested items and the count note", () => {
    const text = "- one\n- two\n  - two a\n  - two b\n    - deep\n- three\n(9 items; 3 shown)";
    const layout = parseList(text)!;
    expect(layout.note).toEqual({ total: 9, shown: 3, noun: "items" });
    expect(layout.items.map((i) => slice(text, i))).toEqual(["one", "two", "three"]);
    const two = layout.items[1]!;
    expect(two.children.map((i) => slice(text, i))).toEqual(["two a", "two b"]);
    expect(slice(text, two.children[1]!.children[0]!)).toBe("deep");
  });

  it("keeps an item that is indented deeper than its parent allows one level down", () => {
    const text = "- one\n      - far";
    const layout = parseList(text)!;
    expect(layout.items).toHaveLength(1);
    expect(layout.items[0]!.children).toHaveLength(1);
  });

  it("gives up when a line is not an item", () => {
    expect(parseList("- one\ntwo")).toBeNull();
    expect(parseList("")).toBeNull();
    expect(parseList("(3 items; 1 shown)")).toBeNull();
  });

  it("reads the list of the Apollo 11 fixture", () => {
    const list = loadDossier("dossier_662_8000.json").chunks.find((c) => c.kind === "list")!;
    expect(parseList(list.text)?.items).toHaveLength(8);
  });
});

describe("links", () => {
  it("keeps a link span inside the cell it lies in", () => {
    const text = "T\n| A | B |\n| --- | --- |\n| Moon landing | Buzz Aldrin |";
    const layout = parseTable(text)!;
    const start = text.indexOf("Buzz");
    const links = textLinks(text, [{ start, end: start + 4, title: "Buzz Aldrin" }]);
    expect(pieces(text, layout.rows[0]![1]!, links, true)).toEqual([
      { text: "Buzz", title: "Buzz Aldrin" },
      { text: " Aldrin", title: null },
    ]);
    expect(pieces(text, layout.rows[0]![0]!, links, true)).toEqual([
      { text: "Moon landing", title: null },
    ]);
  });

  it("keeps a link span in a list item, after an item that holds a pipe", () => {
    const text = "- a | b\n  - see Moon here";
    const start = text.indexOf("Moon");
    const layout = parseList(text)!;
    const links = textLinks(text, [{ start, end: start + 4, title: "Moon" }]);
    expect(pieces(text, layout.items[0]!, links, false)).toEqual([{ text: "a | b", title: null }]);
    expect(pieces(text, layout.items[0]!.children[0]!, links, false)).toEqual([
      { text: "see ", title: null },
      { text: "Moon", title: "Moon" },
      { text: " here", title: null },
    ]);
  });

  it("leaves out a span that crosses the edge of the cell", () => {
    const text = "T\n| A | B |\n| --- | --- |\n| one | two |";
    const layout = parseTable(text)!;
    const start = text.indexOf("one");
    const links = textLinks(text, [{ start, end: start + 8, title: "X" }]);
    expect(pieces(text, layout.rows[0]![0]!, links, true)).toEqual([{ text: "one", title: null }]);
  });

  it("turns code-point offsets into UTF-16 offsets after an astral character", () => {
    const text = "- \u{1d7d8} Moon";
    const links = textLinks(text, [{ start: 4, end: 8, title: "Moon" }]);
    expect(text.slice(links[0]!.start, links[0]!.end)).toBe("Moon");
    expect(links[0]!.start).toBe(5);
    expect(textLinks("plain", [{ start: 1, end: 3, title: "T" }])).toEqual([
      { start: 1, end: 3, title: "T" },
    ]);
    expect(textLinks("plain", undefined)).toEqual([]);
  });
});

describe("text shapes the backend can write", () => {
  it("reads a table and a list with Windows line ends", () => {
    const table = "Cap\r\n| A | B |\r\n| --- | --- |\r\n| 1 | 2 |\r\n(5 rows; 1 shown)\r\n";
    const layout = parseTable(table)!;
    expect(layout.caption).toBe("Cap");
    expect(layout.rows.map((row) => row.map((r) => slice(table, r)))).toEqual([["1", "2"]]);
    expect(layout.note).toEqual({ total: 5, shown: 1, noun: "rows" });
    const list = "- a\r\n  - b\r\n(4 items; 2 shown)";
    const items = parseList(list)!;
    expect(slice(list, items.items[0]!)).toBe("a");
    expect(slice(list, items.items[0]!.children[0]!)).toBe("b");
    expect(items.note).toEqual({ total: 4, shown: 2, noun: "items" });
  });

  it("gives a row with more cells than the header a column of its own", () => {
    const text = "Cap\n| A |\n| --- |\n| 1 | 2 | 3 |";
    const layout = parseTable(text)!;
    expect(layout.header.map((r) => slice(text, r))).toEqual(["A", "", ""]);
    expect(layout.rows[0]!.map((r) => slice(text, r))).toEqual(["1", "2", "3"]);
  });

  it("keeps a total row that follows the cut rows as a body row", () => {
    const text = "Cap\n| A | B |\n| --- | --- |\n| 1 | 2 |\n| Total | 9 |\n(30 rows; 4 shown)";
    const layout = parseTable(text)!;
    expect(layout.rows).toHaveLength(2);
    expect(layout.note?.total).toBe(30);
  });

  it("leaves a span with offsets outside the text out instead of throwing", () => {
    const text = "- a\u{1d7d8}b";
    const layout = parseList(text)!;
    const links = textLinks(text, [
      { start: 9, end: 12, title: "far" },
      { start: -1, end: 2, title: "negative" },
    ]);
    expect(pieces(text, layout.items[0]!, links, false)).toEqual([
      { text: "a\u{1d7d8}b", title: null },
    ]);
  });
});
