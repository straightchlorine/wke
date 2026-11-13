import { describe, expect, it } from "vitest";
import { loadDossier } from "../test/fixtures";
import { relatedGraphNodes, storedStateOf } from "./relatedGraph";

describe("storedStateOf", () => {
  it("says ready for a listed topic, whether or not the list is complete", () => {
    expect(storedStateOf({ items: [{ page_id: 1 }], next_cursor: null })(1)).toBe("ready");
    expect(storedStateOf({ items: [{ page_id: 1 }], next_cursor: "c" })(1)).toBe("ready");
  });

  it("says none for an unlisted topic only when the list is complete", () => {
    expect(storedStateOf({ items: [{ page_id: 1 }], next_cursor: null })(2)).toBe("none");
    expect(storedStateOf({ items: [{ page_id: 1 }], next_cursor: "c" })(2)).toBeUndefined();
  });

  it("does not know any topic's state before the list has loaded", () => {
    expect(storedStateOf(undefined)(1)).toBeUndefined();
  });
});

describe("relatedGraphNodes", () => {
  const dossier = loadDossier();
  const nodes = relatedGraphNodes(dossier, (id) => (id === 12490 ? "ready" : undefined));
  const seed = dossier.graph.nodes.find((n) => n.role === "seed")!;

  it("makes a node of every graph node, with the title's slug and the state asked for", () => {
    expect(nodes).toHaveLength(dossier.graph.nodes.length);
    const mark = nodes.find((n) => n.id === 12490)!;
    expect(mark).toMatchObject({ title: "Gospel of Mark", slug: "Gospel_of_Mark", state: "ready" });
  });

  it("sizes the seed by 1 and carries the topic's description on it alone", () => {
    const described = relatedGraphNodes(
      { ...dossier, topic: { ...dossier.topic, description: "A carpenter" } },
      () => undefined,
    );
    const node = described.find((n) => n.id === seed.id)!;
    expect(node.views).toBe(1);
    expect(node.description).toBe("A carpenter");
    expect(described.filter((n) => n.description !== undefined).map((n) => n.id)).toEqual([
      seed.id,
    ]);
  });

  it("sizes a related node by the weight of its edge to the seed, in either direction", () => {
    const edge = dossier.graph.edges.find((e) => e.source === seed.id || e.target === seed.id)!;
    const otherId = edge.source === seed.id ? edge.target : edge.source;
    expect(nodes.find((n) => n.id === otherId)!.views).toBe(edge.weight);
  });

  it("finds the edge to the seed whichever end the seed is on", () => {
    const edges = [
      { source: 2, target: 1, weight: 0.4 },
      { source: 1, target: 3, weight: 0.6 },
    ];
    const graph = {
      nodes: [
        { id: 1, title: "Seed", role: "seed" as const },
        { id: 2, title: "A", role: "related" as const },
        { id: 3, title: "B", role: "related" as const },
      ],
      edges,
    };
    const result = relatedGraphNodes({ ...dossier, graph }, () => undefined);
    expect(result.map((n) => n.views)).toEqual([1, 0.4, 0.6]);
  });

  it("leaves the similarity of a related node with no edge to the seed unknown, not 0", () => {
    const linked = new Set(
      dossier.graph.edges
        .filter((e) => e.source === seed.id || e.target === seed.id)
        .flatMap((e) => [e.source, e.target]),
    );
    const unlinked = nodes.filter((n) => n.role === "related" && !linked.has(n.id));
    expect(unlinked.length).toBeGreaterThan(0);
    expect(unlinked.every((n) => n.views === null)).toBe(true);
  });
});
