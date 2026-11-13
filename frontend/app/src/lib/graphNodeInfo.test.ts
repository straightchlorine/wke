import { describe, expect, it } from "vitest";
import {
  boardNodeFor,
  groupedClusters,
  neighbourTitles,
  nodeAriaLabel,
  nodeFigure,
  type ConceptGraphNode,
} from "./graphNodeInfo";

const lizzie: ConceptGraphNode = {
  id: 1,
  title: "Lizzie Borden",
  slug: "Lizzie_Borden",
  views: 806988,
  editsLastHour: 5,
  state: "ready",
  description: "American woman tried for murder in 1892",
};

describe("nodeFigure", () => {
  it.each([
    ["index views", { views: 806988 }, "index", { label: "Views", value: "806,988" }],
    ["index views of zero", { views: 0 }, "index", { label: "Views", value: "0" }],
    [
      "related similarity to two places",
      { views: 0.7234 },
      "related",
      { label: "Similarity", value: "0.72" },
    ],
    ["unknown views on the index", { views: null }, "index", undefined],
    ["unknown similarity", { views: null }, "related", undefined],
    ["the seed of the related graph", { views: 1, role: "seed" }, "related", undefined],
    [
      "a seed role on the index",
      { views: 5, role: "seed" },
      "index",
      { label: "Views", value: "5" },
    ],
  ] as const)("gives %s", (_name, node, variant, expected) => {
    expect(nodeFigure(node, variant)).toEqual(expected);
  });
});

describe("nodeAriaLabel", () => {
  const idle = { pinged: false, selected: false };

  it.each([
    [
      "index node with views and a dossier",
      lizzie,
      "index",
      idle,
      "Lizzie Borden, 806,988 views, dossier ready, press Enter to select",
    ],
    [
      "related node with similarity and no dossier text",
      { ...lizzie, views: 0.5 },
      "related",
      idle,
      "Lizzie Borden, similarity 0.50, press Enter to select",
    ],
    [
      "node with no figure and no state",
      { ...lizzie, views: null, state: undefined },
      "index",
      idle,
      "Lizzie Borden, press Enter to select",
    ],
    [
      "edited node",
      lizzie,
      "index",
      { pinged: true, selected: false },
      "Lizzie Borden, 806,988 views, dossier ready, edited in the last minute, press Enter to select",
    ],
    [
      "selected node",
      { ...lizzie, state: "none" },
      "index",
      { pinged: false, selected: true },
      "Lizzie Borden, 806,988 views, no dossier yet, selected, press Enter to open the dossier",
    ],
  ] as const)("names a %s", (_name, node, variant, flags, expected) => {
    expect(nodeAriaLabel(node, variant, flags)).toBe(expected);
  });

  it.each([
    ["ready", "dossier ready"],
    ["partial", "dossier partial"],
    ["building", "dossier in progress"],
    ["none", "no dossier yet"],
  ] as const)("says %s as %s on the index", (state, text) => {
    expect(nodeAriaLabel({ ...lizzie, state }, "index", idle)).toContain(`, ${text},`);
  });
});

describe("neighbourTitles", () => {
  const nodes: ConceptGraphNode[] = [
    { id: 1, title: "A", slug: "A", views: 1 },
    { id: 2, title: "B", slug: "B", views: 1 },
    { id: 3, title: "C", slug: "C", views: 1 },
    { id: 4, title: "D", slug: "D", views: 1 },
  ];

  it("lists each node's neighbours from both ends of an edge, strongest first", () => {
    const found = neighbourTitles(nodes, [
      { source: 1, target: 2, weight: 0.2 },
      { source: 3, target: 1, weight: 0.9 },
      { source: 1, target: 4, weight: 0.5 },
    ]);
    expect(found.get(1)).toEqual(["C", "D", "B"]);
    expect(found.get(2)).toEqual(["A"]);
    expect(found.get(3)).toEqual(["A"]);
  });

  it("skips an edge with an end outside the nodes, and leaves unlinked nodes out", () => {
    const found = neighbourTitles(nodes, [{ source: 1, target: 99, weight: 1 }]);
    expect(found.size).toBe(0);
  });
});

describe("boardNodeFor", () => {
  const neighbours = new Map([[1, ["Fall River", "Andrew Borden"]]]);

  it("shows views, edits and the neighbours on the index", () => {
    expect(
      boardNodeFor(lizzie, {
        variant: "index",
        editsUnavailable: false,
        neighbours,
        hrefSuffix: "?budget=8000",
      }),
    ).toEqual({
      title: "Lizzie Borden",
      description: "American woman tried for murder in 1892",
      figure: { label: "Views", value: "806,988" },
      figureLabel: "Views",
      editsLastHour: 5,
      editsMissing: undefined,
      editsUnavailable: false,
      linkedTo: ["Fall River", "Andrew Borden"],
      state: "ready",
      href: "/t/Lizzie_Borden?budget=8000",
    });
  });

  it("passes the feed being down on the index but not on the related graph", () => {
    const options = { editsUnavailable: true, neighbours, hrefSuffix: "" };
    expect(boardNodeFor(lizzie, { ...options, variant: "index" }).editsUnavailable).toBe(true);
    expect(boardNodeFor(lizzie, { ...options, variant: "related" }).editsUnavailable).toBe(false);
  });

  it("shows similarity and says edits are not tracked on the related graph", () => {
    const board = boardNodeFor(
      { ...lizzie, views: 0.5 },
      { variant: "related", editsUnavailable: false, neighbours, hrefSuffix: "" },
    );
    expect(board.figure).toEqual({ label: "Similarity", value: "0.50" });
    expect(board.figureLabel).toBe("Similarity");
    expect(board.editsLastHour).toBeUndefined();
    expect(board.editsMissing).toBe("not tracked");
  });

  it("has no neighbours for a node outside the map", () => {
    const board = boardNodeFor(
      { ...lizzie, id: 7 },
      { variant: "index", editsUnavailable: false, neighbours, hrefSuffix: "" },
    );
    expect(board.linkedTo).toEqual([]);
  });
});

describe("groupedClusters", () => {
  it("keeps the clusters with two or more nodes", () => {
    const nodes = [
      { cluster: 0 },
      { cluster: 1 },
      { cluster: 0 },
      { cluster: 2 },
      { cluster: 2 },
      { cluster: 2 },
    ];
    expect(groupedClusters(nodes)).toEqual(new Set([0, 2]));
  });

  it("is empty when every node stands alone", () => {
    expect(groupedClusters([{ cluster: 0 }, { cluster: 1 }]).size).toBe(0);
    expect(groupedClusters([]).size).toBe(0);
  });
});
