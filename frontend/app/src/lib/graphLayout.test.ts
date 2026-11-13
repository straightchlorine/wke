import { describe, expect, it } from "vitest";
import fixture from "../../e2e/fixtures/trending.json";
import chipGroupFixture from "../../e2e/fixtures/trending-top-right-group.json";
import { computeComponents, computeLayout, type GraphEdge, type GraphNode } from "./graphLayout";

const trendingNodes: GraphNode[] = fixture.topics.map((t) => ({
  id: t.page_id,
  title: t.title,
  views: t.views,
}));
// Edge endpoints are page ids, the same ids as `topics[].page_id`.
const trendingEdges: GraphEdge[] = fixture.edges;

const SMALL_NODES: GraphNode[] = [
  { id: 1, title: "Alan Turing", views: 200000 },
  { id: 2, title: "Enigma machine", views: 90000 },
  { id: 3, title: "Bletchley Park", views: 40000 },
  { id: 4, title: "Nobel Prize", views: 300000 },
  { id: 5, title: "Isolated Topic", views: 5000 },
];
const SMALL_EDGES: GraphEdge[] = [
  { source: 1, target: 2, weight: 0.9 },
  { source: 2, target: 3, weight: 0.8 },
  { source: 1, target: 3, weight: 0.7 },
];

describe("computeComponents", () => {
  it("groups linked nodes and isolates the rest", () => {
    const components = computeComponents(SMALL_NODES, SMALL_EDGES);
    expect(components.get(1)).toBe(components.get(2));
    expect(components.get(2)).toBe(components.get(3));
    expect(components.get(4)).not.toBe(components.get(1));
    expect(components.get(5)).not.toBe(components.get(1));
  });
});

describe("computeComponents order", () => {
  it("numbers the largest component 0, and breaks a tie by the smaller member id", () => {
    const nodes = [9, 8, 7, 6, 5, 4, 3, 2, 1].map((id): GraphNode => ({
      id,
      title: `N${id}`,
      views: 1,
    }));
    const edges: GraphEdge[] = [
      { source: 9, target: 8, weight: 1 },
      { source: 8, target: 7, weight: 1 },
      { source: 6, target: 5, weight: 1 },
      { source: 4, target: 3, weight: 1 },
    ];
    const components = computeComponents(nodes, edges);
    // The component {7, 8, 9} is the largest; {3, 4} and {5, 6} tie on size; 1 and 2 stand alone.
    expect([9, 8, 7].map((id) => components.get(id))).toEqual([0, 0, 0]);
    expect([4, 3].map((id) => components.get(id))).toEqual([1, 1]);
    expect([6, 5].map((id) => components.get(id))).toEqual([2, 2]);
    expect([components.get(1), components.get(2)]).toEqual([3, 4]);
  });
});

describe("computeLayout determinism", () => {
  it.each([
    ["a small graph", SMALL_NODES, SMALL_EDGES],
    ["the full trending fixture", trendingNodes, trendingEdges],
  ])("gives identical positions for %s run twice", (_name, nodes, edges) => {
    const options = { width: 774, height: 710 };
    const first = computeLayout(nodes, edges, options);
    const second = computeLayout(nodes, edges, options);
    expect(second.nodes).toEqual(first.nodes);
    expect(second.hulls).toEqual(first.hulls);
  });
});

describe("computeLayout fills the drawing area", () => {
  it.each([
    { width: 774, height: 710 },
    { width: 531, height: 704 },
  ])("spreads the dots over most of a $width x $height frame", ({ width, height }) => {
    const result = computeLayout(trendingNodes, trendingEdges, { width, height });
    const xs = result.nodes.map((n) => n.x);
    const ys = result.nodes.map((n) => n.y);
    const spanX = Math.max(...xs) - Math.min(...xs);
    const spanY = Math.max(...ys) - Math.min(...ys);
    // One scale for both axes seats the cloud, so the axis with spare room may keep a little slack.
    expect(spanX).toBeGreaterThanOrEqual(width * 0.75);
    expect(spanY).toBeGreaterThanOrEqual(height * 0.75);
  });
});

/** Largest gap between adjacent node rows by y, including the band above the first row and below the last, as a fraction of height. */
function maxEmptyBandFraction(nodes: Array<{ y: number }>, height: number): number {
  const ys = nodes.map((n) => n.y).toSorted((a, b) => a - b);
  let maxGap = ys[0] ?? 0;
  for (let i = 1; i < ys.length; i += 1) {
    const gap = (ys[i] ?? 0) - (ys[i - 1] ?? 0);
    if (gap > maxGap) {
      maxGap = gap;
    }
  }
  maxGap = Math.max(maxGap, height - (ys[ys.length - 1] ?? height));
  return maxGap / height;
}

describe("computeLayout empty-band fraction at every frame size", () => {
  it.each([
    { width: 348, height: 348 },
    { width: 736, height: 736 },
    { width: 531, height: 704 },
    { width: 774, height: 710 },
  ])(
    "keeps the largest empty band under 0.25 of height in $width x $height",
    ({ width, height }) => {
      const result = computeLayout(trendingNodes, trendingEdges, { width, height });
      expect(maxEmptyBandFraction(result.nodes, height)).toBeLessThan(0.25);
    },
  );
});

describe("computeLayout on one seed linked to every other node", () => {
  it("spreads related nodes over the whole area instead of collapsing onto one grid cell", () => {
    // One seed linked to every other node, so the whole graph is a single component.
    // The nodes must spread over the whole area instead of collapsing and leaving the lower half empty.
    const seedNodes: GraphNode[] = Array.from({ length: 15 }, (_, i) => ({
      id: i,
      title: `Related ${i}`,
      views: i === 0 ? null : 0.9 - i * 0.05,
    }));
    const seedEdges: GraphEdge[] = seedNodes
      .slice(1)
      .map((n) => ({ source: 0, target: n.id, weight: 0.5 }));
    const width = 520;
    const height = 520; // The related graph's frame is square at every width.
    const result = computeLayout(seedNodes, seedEdges, { width, height });
    expect(maxEmptyBandFraction(result.nodes, height)).toBeLessThan(0.25);
    const xs = result.nodes.map((n) => n.x);
    const spanX = Math.max(...xs) - Math.min(...xs);
    expect(spanX).toBeGreaterThanOrEqual(width * 0.7);
  });
});

describe("computeLayout wall clamp", () => {
  const EPSILON = 0.01; // floating-point rounding from the simulation's own clamp
  it.each([
    { width: 348, height: 348, squareFrame: false, wallMargin: undefined, margin: 12 },
    { width: 531, height: 704, squareFrame: false, wallMargin: undefined, margin: 12 },
    { width: 774, height: 710, squareFrame: false, wallMargin: undefined, margin: 12 },
    { width: 348, height: 348, squareFrame: true, wallMargin: undefined, margin: 12 },
    { width: 348, height: 348, squareFrame: true, wallMargin: 14, margin: 14 },
    { width: 774, height: 710, squareFrame: false, wallMargin: 14, margin: 14 },
  ])(
    "keeps every dot's edge at least $margin px from the frame in $width x $height (squareFrame $squareFrame)",
    ({ width, height, squareFrame, wallMargin, margin }) => {
      const result = computeLayout(trendingNodes, trendingEdges, {
        width,
        height,
        squareFrame,
        wallMargin,
      });
      for (const n of result.nodes) {
        expect(n.x - n.radius).toBeGreaterThanOrEqual(margin - EPSILON);
        expect(n.y - n.radius).toBeGreaterThanOrEqual(margin - EPSILON);
        expect(width - n.x - n.radius).toBeGreaterThanOrEqual(margin - EPSILON);
        expect(height - n.y - n.radius).toBeGreaterThanOrEqual(margin - EPSILON);
      }
    },
  );
});

describe("computeLayout square frame", () => {
  it.each([{ size: 358 }, { size: 348 }])(
    "places the trending fixture with no circle overlap in a $size x $size frame",
    ({ size }) => {
      const result = computeLayout(trendingNodes, trendingEdges, {
        width: size,
        height: size,
        squareFrame: true,
      });
      const overlaps: string[] = [];
      for (let i = 0; i < result.nodes.length; i++) {
        for (let j = i + 1; j < result.nodes.length; j++) {
          const a = result.nodes[i]!;
          const b = result.nodes[j]!;
          if (Math.hypot(a.x - b.x, a.y - b.y) < a.radius + b.radius) {
            overlaps.push(`${a.title} / ${b.title}`);
          }
        }
      }
      expect(overlaps).toEqual([]);
    },
  );
});

describe("computeLayout edges", () => {
  it("returns every edge whose ends are both in the graph", () => {
    const result = computeLayout(SMALL_NODES, SMALL_EDGES, { width: 400, height: 400 });
    expect(result.edges).toEqual(SMALL_EDGES);
  });

  it("drops an edge whose end is not a node", () => {
    const dangling: GraphEdge = { source: 1, target: 999, weight: 0.5 };
    const result = computeLayout(SMALL_NODES, [...SMALL_EDGES, dangling], {
      width: 400,
      height: 400,
    });
    expect(result.edges).toEqual(SMALL_EDGES);
  });
});

describe("computeLayout hulls", () => {
  it("covers every member node inside its padded hull", () => {
    const result = computeLayout(trendingNodes, trendingEdges, { width: 774, height: 710 });
    const byCluster = new Map<number, typeof result.nodes>();
    for (const node of result.nodes) {
      const list = byCluster.get(node.cluster);
      if (list) {
        list.push(node);
      } else {
        byCluster.set(node.cluster, [node]);
      }
    }
    for (const hull of result.hulls) {
      const members = byCluster.get(hull.cluster) ?? [];
      for (const member of members) {
        // Each hull is padded outward, so a member lies inside it with margin instead of on its edge.
        expect(pointInPolygon([member.x, member.y], hull.points)).toBe(true);
      }
    }
  });
});

describe("computeLayout hullPad", () => {
  it.each([
    { hullPad: undefined, pad: 18 },
    { hullPad: 10, pad: 10 },
  ])("stands each polygon outline vertex $pad px off its dot", ({ hullPad, pad }) => {
    const { nodes, hulls } = computeLayout(trendingNodes, trendingEdges, {
      width: 774,
      height: 710,
      hullPad,
    });
    const polygons = hulls.filter(
      (hull) => nodes.filter((n) => n.cluster === hull.cluster).length > 2,
    );
    expect(polygons.length).toBeGreaterThan(0);
    for (const hull of polygons) {
      const members = nodes.filter((n) => n.cluster === hull.cluster);
      for (const [x, y] of hull.points) {
        const nearest = Math.min(...members.map((m) => Math.hypot(m.x - x, m.y - y)));
        expect(nearest).toBeCloseTo(pad, 5);
      }
    }
  });
});

describe("computeLayout dot radius", () => {
  const sized: GraphNode[] = [
    { id: 1, title: "Most", views: 400 },
    { id: 2, title: "A quarter", views: 100 },
    { id: 3, title: "None", views: 0 },
    { id: 4, title: "Unknown", views: null },
  ];
  it.each([
    { radiusRange: undefined, expected: [16, 10.5, 5, 10.5] },
    { radiusRange: [4, 11] as [number, number], expected: [11, 7.5, 4, 7.5] },
  ])(
    "scales the radius with the square root of the views over the range $radiusRange",
    ({ radiusRange, expected }) => {
      const { nodes } = computeLayout(sized, [], { width: 600, height: 600, radiusRange });
      expect(nodes.map((n) => n.radius)).toEqual(expected.map((r) => expect.closeTo(r, 5)));
    },
  );
});

describe("computeLayout ticks", () => {
  it("runs the default number of ticks unless told otherwise", () => {
    const options = { width: 774, height: 710 };
    const byDefault = computeLayout(trendingNodes, trendingEdges, options);
    expect(byDefault.nodes).toEqual(
      computeLayout(trendingNodes, trendingEdges, { ...options, ticks: 300 }).nodes,
    );
    expect(byDefault.nodes).not.toEqual(
      computeLayout(trendingNodes, trendingEdges, { ...options, ticks: 30 }).nodes,
    );
  });
});

describe("computeLayout a group under a wide rect", () => {
  // The rect pushes the group's row down; the wall margin is how far a dot's edge keeps from it.
  it.each([[undefined], [40]])(
    "gives a linked group of five dots a vertical spread instead of one row, at wall margin %s",
    (wallMargin) => {
      const group: GraphNode[] = [1, 2, 3, 4, 5].map((id) => ({
        id,
        title: `Group ${id}`,
        views: 100 * id,
      }));
      const singles: GraphNode[] = Array.from({ length: 8 }, (_, i) => ({
        id: 10 + i,
        title: `Single ${i}`,
        views: 50,
      }));
      const chain: GraphEdge[] = [1, 2, 3, 4].map((id) => ({
        source: id,
        target: id + 1,
        weight: 1,
      }));
      const { nodes } = computeLayout([...group, ...singles], chain, {
        width: 600,
        height: 600,
        excludeBoxes: [{ x: 0, y: 0, width: 600, height: 200 }],
        wallMargin,
      });
      const ys = nodes.filter((n) => n.id <= 5).map((n) => n.y);
      expect(Math.max(...ys) - Math.min(...ys)).toBeGreaterThanOrEqual(39);
    },
  );
});

describe("computeLayout dots moved off a large legend", () => {
  it("keeps every dot clear of the legend and does not line the moved dots up on its top edge", () => {
    const singles: GraphNode[] = Array.from({ length: 24 }, (_, i) => ({
      id: i + 1,
      title: `Single ${i}`,
      views: 100 + i,
    }));
    const legend = { x: 3, y: 180, width: 300, height: 165, hull: true };
    const { nodes } = computeLayout(singles, [], {
      width: 348,
      height: 348,
      squareFrame: true,
      excludeBoxes: [legend],
    });
    for (const n of nodes) {
      expect(n.y + n.radius, `${n.title} against the legend`).toBeLessThan(legend.y);
    }
    const bottoms = nodes.map((n) => n.y + n.radius).toSorted((a, b) => a - b);
    const lastRow = bottoms.filter((bottom) => bottom > bottoms.at(-1)! - 1);
    expect(lastRow.length).toBeLessThan(3);
  });
});

describe("computeLayout dense frames", () => {
  it.each([
    { count: 54, width: 260, height: 260, squareFrame: true },
    { count: 54, width: 200, height: 400, squareFrame: false },
    { count: 60, width: 200, height: 400, squareFrame: false },
    { count: 60, width: 348, height: 348, squareFrame: true },
  ])(
    "leaves no two dots overlapping with $count dots in a $width x $height frame",
    ({ count, width, height, squareFrame }) => {
      const dots: GraphNode[] = Array.from({ length: count }, (_, i) => ({
        id: i + 1,
        title: `Dot ${i}`,
        views: 1000 - i * 5,
      }));
      // Each dot after the first links to one of six hubs, so there are six groups.
      const links: GraphEdge[] = dots
        .slice(1)
        .map((dot, i) => ({ source: (i % 6) + 1, target: dot.id, weight: 1 }));
      const { nodes } = computeLayout(dots, links, { width, height, squareFrame });
      const overlapping: string[] = [];
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i]!;
          const b = nodes[j]!;
          if (Math.hypot(a.x - b.x, a.y - b.y) < a.radius + b.radius) {
            overlapping.push(`${a.title} / ${b.title}`);
          }
        }
      }
      expect(overlapping).toEqual([]);
    },
  );
});

describe("computeLayout two-dot groups", () => {
  it("draws a capsule around both dots, every disc inside it", () => {
    const pair: GraphNode[] = [
      { id: 1, title: "A", views: 900 },
      { id: 2, title: "B", views: 400 },
      { id: 3, title: "C", views: 100 },
    ];
    const result = computeLayout(pair, [{ source: 1, target: 2, weight: 0.8 }], {
      width: 600,
      height: 600,
      hullPad: 18,
    });
    expect(result.hulls).toHaveLength(1);
    const hull = result.hulls[0]!;
    const members = result.nodes.filter((n) => n.cluster === hull.cluster);
    expect(members).toHaveLength(2);
    for (const m of members) {
      expect(pointInPolygon([m.x, m.y], hull.points)).toBe(true);
      expect(pointInPolygon([m.x + m.radius, m.y], hull.points)).toBe(true);
    }
    expect(result.nodes.find((n) => n.id === 3)).toBeDefined();
  });
});

function pointInPolygon(point: [number, number], polygon: Array<[number, number]>): boolean {
  const [px, py] = point;
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
    const a = polygon[i];
    const b = polygon[j];
    if (!a || !b) {
      continue;
    }
    const [xi, yi] = a;
    const [xj, yj] = b;
    const intersects = yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi;
    if (intersects) {
      inside = !inside;
    }
  }
  return inside;
}

describe("computeLayout hull inset and excluded boxes", () => {
  const frame = { width: 531, height: 704 };

  it.each([
    { size: { width: 900, height: 300 }, hullInset: undefined, inset: 6 },
    { size: { width: 531, height: 704 }, hullInset: 12, inset: 12 },
  ])(
    "keeps every group outline whole inside a $size.width x $size.height frame, $inset px from each edge",
    ({ size, hullInset, inset }) => {
      const { hulls } = computeLayout(trendingNodes, trendingEdges, {
        ...size,
        hullPad: 18,
        hullInset,
      });
      expect(hulls.length).toBeGreaterThan(0);
      for (const hull of hulls) {
        for (const [x, y] of hull.points) {
          expect(x).toBeGreaterThanOrEqual(inset - 0.5);
          expect(x).toBeLessThanOrEqual(size.width - inset + 0.5);
          expect(y).toBeGreaterThanOrEqual(inset - 0.5);
          expect(y).toBeLessThanOrEqual(size.height - inset + 0.5);
        }
      }
    },
  );

  it("keeps node circles clear of an excluded chip box", () => {
    const chip = { x: frame.width - 204, y: 0, width: 204, height: 30 };
    const { nodes } = computeLayout(trendingNodes, trendingEdges, {
      ...frame,
      excludeBoxes: [chip],
    });
    const touching = nodes.filter(
      (n) =>
        n.x + n.radius > chip.x &&
        n.x - n.radius < chip.x + chip.width &&
        n.y - n.radius < chip.y + chip.height,
    );
    expect(touching).toEqual([]);
  });
});

describe("computeLayout around a legend chip in the bottom-left corner", () => {
  const frame = { width: 348, height: 348 };
  const legend = { x: 3, y: frame.height - 3 - 44, width: 266, height: 44, hull: true };
  const hullPad = 18;

  it("keeps every dot clear of the chip and every outline off it", () => {
    const { nodes, hulls } = computeLayout(trendingNodes, trendingEdges, {
      ...frame,
      hullPad,
      excludeBoxes: [legend],
    });
    for (const n of nodes) {
      const near = Math.max(
        legend.x - n.x,
        n.x - (legend.x + legend.width),
        legend.y - n.y,
        n.y - (legend.y + legend.height),
      );
      expect(near, `${n.title} against the chip`).toBeGreaterThan(n.radius);
    }
    for (const hull of hulls) {
      for (const [x, y] of hull.points) {
        const inside =
          x >= legend.x &&
          x <= legend.x + legend.width &&
          y >= legend.y &&
          y <= legend.y + legend.height;
        expect(inside, `outline ${hull.cluster} at ${x.toFixed(0)},${y.toFixed(0)}`).toBe(false);
      }
    }
  });

  it("does not stand the dots it moves on one line along the chip's top edge", () => {
    const { nodes } = computeLayout(trendingNodes, trendingEdges, {
      ...frame,
      hullPad,
      excludeBoxes: [legend],
    });
    const bottoms = nodes
      .filter((n) => n.x < legend.x + legend.width && n.y > legend.y - 60)
      .map((n) => n.y + n.radius)
      .toSorted((a, b) => a - b);
    let widest = 0;
    for (let i = 0; i < bottoms.length; i += 1) {
      let j = i;
      while (j + 1 < bottoms.length && bottoms[j + 1]! - bottoms[i]! <= 1) {
        j += 1;
      }
      widest = Math.max(widest, j - i + 1);
    }
    expect(widest).toBeLessThan(3);
  });
});

const chip = (width: number) => ({ x: width - 204, y: 0, width: 204, height: 30 });

describe("computeLayout flat groups under a rect at the top right", () => {
  const nodes: GraphNode[] = chipGroupFixture.topics.map((t) => ({
    id: t.page_id,
    title: t.title,
    views: t.views,
  }));

  it.each([531, 643, 699, 760])(
    "keeps every group of three or more at least 24 px tall at width %i",
    (width) => {
      const laid = computeLayout(nodes, chipGroupFixture.edges, {
        width,
        height: 792,
        hullPad: 18,
        excludeBoxes: [chip(width)],
      });
      const groups = new Map<number, number[]>();
      for (const n of laid.nodes) {
        groups.set(n.cluster, [...(groups.get(n.cluster) ?? []), n.y]);
      }
      const sized = [...groups.values()].filter((g) => g.length >= 3);
      expect(sized.length).toBeGreaterThan(0);
      for (const ys of sized) {
        expect(Math.max(...ys) - Math.min(...ys)).toBeGreaterThanOrEqual(24);
      }
      const pairs = [...groups.values()].filter((g) => g.length === 2);
      expect(laid.hulls.length).toBe(sized.length + pairs.length);
    },
  );
});
