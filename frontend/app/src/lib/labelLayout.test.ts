import { describe, expect, it } from "vitest";
import fixture from "../../e2e/fixtures/trending.json";
import { loadDossier } from "../test/fixtures";
import {
  computeLayout,
  type GraphEdge,
  type GraphNode,
  type Hull,
  type LaidOutNode,
} from "./graphLayout";
import {
  boxCircleDistance,
  boxCrossesOutline,
  boxTouchesHull,
  boxesOverlap,
  countLabelCollisions,
  segmentsCross,
  type LabelBox,
  type Rect,
} from "./labelGeometry";
import {
  ALWAYS_NAMED,
  breakIntoTwoLines,
  computeLabelPlacements,
  glyphsOf,
  isolatedIds,
  type LabelPlacementOptions,
} from "./labelLayout";
import { guaranteedNameIds, plateLayoutOptions, type PlateFrame } from "./plateLayoutOptions";

type Point = [number, number];

const nodes: GraphNode[] = fixture.topics.map((t) => ({
  id: t.page_id,
  title: t.title,
  views: t.views,
}));
const edges: GraphEdge[] = fixture.edges;

/**
 * The frames of the index graph: a phone viewport, a tablet viewport and two desktop-layout
 * viewports. `narrow` marks the viewports under the desktop layout.
 */
const FRAMES = [
  { width: 348, chipOverlaysFrame: false, underDesktop: true, narrow: true },
  { width: 531, chipOverlaysFrame: true, underDesktop: true, narrow: true },
  { width: 709, chipOverlaysFrame: true, underDesktop: false, narrow: false },
  { width: 1064, chipOverlaysFrame: true, underDesktop: false, narrow: false },
];
type Frame = (typeof FRAMES)[number];

/** Lays out the trending fixture and places its names with the options the page uses at this frame. */
function indexGraph(frame: Frame) {
  const options = plateLayoutOptions({
    variant: "index",
    width: frame.width,
    height: frame.width,
    chipOverlaysFrame: frame.chipOverlaysFrame,
    underDesktop: frame.underDesktop,
  });
  const layout = computeLayout(nodes, edges, options.layout);
  const placements = computeLabelPlacements(layout.nodes, layout.hulls, {
    ...options.labels,
    alwaysShowIds: guaranteedNameIds("index", nodes),
    edges,
  });
  return { layout, placements, labels: options.labels };
}

/** Lays out a related graph in a frame and places its names, the seed always named. */
function relatedGraph(
  graphNodes: GraphNode[],
  links: GraphEdge[],
  seedId: number,
  frame: Pick<PlateFrame, "width" | "height">,
  fontPx?: number,
) {
  const options = plateLayoutOptions({
    variant: "related",
    ...frame,
    compact: false,
    chipOverlaysFrame: true,
    underDesktop: true,
  });
  const layout = computeLayout(graphNodes, links, options.layout);
  const placements = computeLabelPlacements(layout.nodes, layout.hulls, {
    ...options.labels,
    alwaysShowIds: new Set([seedId]),
    edges: links,
    fontPx,
  });
  return { layout, placements, labels: options.labels };
}

/** A graph of `count` dots with long names, the first the seed, every other joined to it and a chain among the first few. */
function northernCoast(count: number) {
  const subjects = [
    "Granite",
    "Harbour",
    "Lantern",
    "Meadow",
    "Orchard",
    "Quarry",
    "Ribbon",
    "Saddle",
    "Thistle",
    "Umbrella",
    "Velvet",
    "Walnut",
    "Yarrow",
    "Zephyr",
    "Anchor",
    "Bramble",
  ];
  const related: GraphNode[] = Array.from({ length: count }, (_, i) => ({
    id: i,
    title: `${subjects[i]} of the northern coast`,
    views: i === 0 ? null : 0.9 - i * 0.04,
  }));
  const links: GraphEdge[] = related
    .slice(1)
    .map((n) => ({ source: 0, target: n.id, weight: 0.5 }));
  for (const n of related.slice(1, 8)) {
    links.push({ source: n.id, target: n.id + 1, weight: 0.4 });
  }
  return { related, links };
}

function dot(
  id: number,
  x: number,
  y: number,
  title: string,
  views: number | null = 1,
  radius = 5,
): LaidOutNode {
  return { id, title, views, x, y, radius, cluster: 0 };
}

/** `count` dots at pseudo-random spots of a square frame, with titles of one to three words. */
function scatter(seed: number, count: number, size: number): LaidOutNode[] {
  let state = seed;
  const next = () => {
    state = (state * 1664525 + 1013904223) % 4294967296;
    return state / 4294967296;
  };
  const words = [
    "Granite",
    "Harbour",
    "Lantern",
    "Meadow",
    "Orchard",
    "Quarry",
    "Ribbon",
    "Saddle",
  ];
  return Array.from({ length: count }, (_, id) => ({
    id,
    title: Array.from(
      { length: 1 + Math.floor(next() * 3) },
      () => words[Math.floor(next() * words.length)]!,
    ).join(" "),
    views: id === 0 ? null : next(),
    x: 30 + next() * (size - 60),
    y: 30 + next() * (size - 60),
    radius: 4 + next() * 6,
    cluster: 0,
  }));
}

function square(x0: number, y0: number, x1: number, y1: number): Hull["points"] {
  return [
    [x0, y0],
    [x1, y0],
    [x1, y1],
    [x0, y1],
  ];
}

function named(placements: Map<number, LabelBox | null>): LabelBox[] {
  return [...placements.values()].filter((b): b is LabelBox => b != null);
}

/** The part of a cut name ahead of its ellipsis. */
function visibleStart(text: string): string {
  return text.replace(/\.{3}$/, "").trimEnd();
}

/** The distance from the text of a placed name to its dot's edge. */
function gapOf(box: LabelBox, node: LaidOutNode): number {
  return boxCircleDistance(glyphsOf(box), node);
}

function leaderOf(box: LabelBox): [Point, Point] | null {
  return box.leader
    ? [
        [box.leader.x1, box.leader.y1],
        [box.leader.x2, box.leader.y2],
      ]
    : null;
}

/** True when the segment passes through the rect or ends inside it. */
function touchesRect(from: Point, to: Point, r: Rect): boolean {
  const inside = (p: Point) =>
    p[0] >= r.x && p[0] <= r.x + r.width && p[1] >= r.y && p[1] <= r.y + r.height;
  const corners: Point[] = [
    [r.x, r.y],
    [r.x + r.width, r.y],
    [r.x + r.width, r.y + r.height],
    [r.x, r.y + r.height],
  ];
  return (
    inside(from) ||
    inside(to) ||
    corners.some((corner, i) => segmentsCross(from, to, corner, corners[(i + 1) % 4]!))
  );
}

/** Places dots in a 300px frame unless the options say otherwise; `hulls` are the group outlines. */
function place(
  dots: LaidOutNode[],
  options: Partial<LabelPlacementOptions>,
  hulls: Hull[] = [],
): Map<number, LabelBox | null> {
  return computeLabelPlacements(dots, hulls, {
    variant: "index",
    width: 300,
    height: 300,
    ...options,
  });
}

interface Scene {
  dots: LaidOutNode[];
  placements: Map<number, LabelBox | null>;
  width: number;
  height: number;
  desktop: boolean;
}

function scatterScene(seed: number, variant: "index" | "related", desktop: boolean): Scene {
  const size = 320;
  const dots = scatter(seed, 18, size);
  const placements = place(dots, {
    variant,
    desktop,
    alwaysShowIds: new Set([0]),
    width: size,
    height: size,
  });
  return { dots, placements, width: size, height: size, desktop };
}

const SCENES: Array<{ name: string; build: () => Scene }> = [
  ...FRAMES.map((frame) => ({
    name: `the trending graph at ${frame.width}`,
    build: (): Scene => {
      const { layout, placements, labels } = indexGraph(frame);
      return {
        dots: layout.nodes,
        placements,
        width: frame.width,
        height: frame.width,
        desktop: labels.desktop ?? false,
      };
    },
  })),
  ...(
    [
      [340, 260],
      [420, 420],
      [640, 640],
    ] as Array<[number, number]>
  ).map(([width, height]) => ({
    name: `a related graph at ${width}x${height}`,
    build: (): Scene => {
      const { related, links } = northernCoast(12);
      const { layout, placements, labels } = relatedGraph(related, links, 0, { width, height });
      return { dots: layout.nodes, placements, width, height, desktop: labels.desktop ?? false };
    },
  })),
  ...[8, 10, 23, 32].flatMap((seed) =>
    (["index", "related"] as const).flatMap((variant) =>
      [false, true].map((desktop) => ({
        name: `scattered dots, seed ${seed}, ${variant}, desktop ${desktop}`,
        build: () => scatterScene(seed, variant, desktop),
      })),
    ),
  ),
];

describe("every name placed", () => {
  it.each(SCENES)(
    "keeps names off other dots, leaders off names, dots and leaders, and text off the frame's edge, in $name",
    ({ build }) => {
      const { dots, placements, width, height } = build();
      const boxes = named(placements);
      expect(boxes.length).toBeGreaterThan(3);
      expect(countLabelCollisions(boxes)).toBe(0);
      for (const box of boxes) {
        // A name keeps 7px between its text and the frame's edge.
        const glyphs = glyphsOf(box);
        expect(glyphs.x, box.text).toBeGreaterThanOrEqual(7);
        expect(glyphs.y, box.text).toBeGreaterThanOrEqual(7);
        expect(glyphs.x + glyphs.width, box.text).toBeLessThanOrEqual(width - 7);
        expect(glyphs.y + glyphs.height, box.text).toBeLessThanOrEqual(height - 7);
        // A name placed as a last resort (relaxed 3) is the only one that may stand over a dot.
        for (const other of dots.filter((d) => d.id !== box.id && (box.relaxed ?? 0) < 3)) {
          expect(
            boxCircleDistance(box, other),
            `${box.text} over ${other.title}`,
          ).toBeGreaterThanOrEqual(1);
        }
        const leader = leaderOf(box);
        if (!leader) {
          continue;
        }
        for (const other of boxes.filter((o) => o.id !== box.id)) {
          expect(
            touchesRect(...leader, glyphsOf(other)),
            `${box.text} leader through ${other.text}`,
          ).toBe(false);
          const crossing = leaderOf(other);
          expect(
            crossing != null && segmentsCross(...leader, ...crossing),
            `${box.text} leader crosses the leader of ${other.text}`,
          ).toBe(false);
        }
        for (const other of dots.filter((d) => d.id !== box.id)) {
          const [from, to] = leader;
          const dx = to[0] - from[0];
          const dy = to[1] - from[1];
          const t = Math.max(
            0,
            Math.min(
              1,
              ((other.x - from[0]) * dx + (other.y - from[1]) * dy) / (dx * dx + dy * dy || 1),
            ),
          );
          expect(
            Math.hypot(from[0] + t * dx - other.x, from[1] + t * dy - other.y),
            `${box.text} leader through ${other.title}`,
          ).toBeGreaterThanOrEqual(other.radius);
        }
      }
    },
  );

  it.each(SCENES)(
    "keeps every name within reach of its dot and joins the ones away from it with a leader, in $name",
    ({ build }) => {
      const { dots, placements, desktop } = build();
      // A name stands at most 29.5px off its dot's edge, or 36px under the desktop layout.
      const reach = desktop ? 36 : 29.5;
      for (const node of dots) {
        const box = placements.get(node.id);
        if (!box) {
          continue;
        }
        expect(gapOf(box, node), node.title).toBeLessThanOrEqual(reach);
        if (gapOf(box, node) > 6) {
          expect(box.leader, node.title).toBeDefined();
        }
      }
    },
  );
});

describe("what a name keeps off", () => {
  const alpha = dot(0, 150, 150, "Alpha name");

  it.each(["index", "related"] as const)(
    "keeps a name off the lines between dots on the %s graph",
    (variant) => {
      const beta = dot(1, 290, 250, "Beta name", 0.5);
      const box = place([alpha, beta], {
        variant,
        alwaysShowIds: new Set([0]),
        edges: [{ source: 0, target: 1, weight: 1 }],
      }).get(0)!;
      expect(touchesRect([150, 150], [290, 250], glyphsOf(box))).toBe(false);
    },
  );

  it("keeps a name off its own group's outline", () => {
    const outline: Hull = { cluster: 0, points: square(120, 130, 180, 170) };
    const box = place([alpha], {}, [outline]).get(0)!;
    expect(boxCrossesOutline(glyphsOf(box), outline)).toBe(false);
  });

  it("keeps a name off another group's outline and fill", () => {
    const outline: Hull = { cluster: 1, points: square(165, 140, 290, 160) };
    const box = place([alpha], {}, [outline]).get(0)!;
    expect(boxTouchesHull(glyphsOf(box), outline)).toBe(false);
  });

  it("keeps a name off a reserved box", () => {
    const reserved: LabelBox = { id: -1, x: 160, y: 130, width: 130, height: 40, text: "" };
    const box = place([alpha], { reservedBoxes: [reserved] }).get(0)!;
    expect(boxesOverlap(box, reserved)).toBe(false);
  });

  it("cuts a name that would run nearly edge to edge, though it fits the frame", () => {
    // jsdom measures 6.72px a character: this 40-character name is 279px wide in a 300px frame.
    const title = "abcdefghi jklmnopqr stuvwxyz abcdefgh ij";
    const box = place([dot(0, 150, 150, title)], {}).get(0);
    expect(box?.fullText).toBe(title);
  });
});

describe("index names", () => {
  it.each(FRAMES)("names most of the ALWAYS_NAMED most-viewed dots, at $width", (frame) => {
    const { layout, placements } = indexGraph(frame);
    const top = [...layout.nodes]
      .toSorted((a, b) => (b.views ?? 0) - (a.views ?? 0))
      .slice(0, ALWAYS_NAMED);
    // A name among them that finds no free spot is dropped, never printed over another name or a dot.
    expect(top.filter((n) => placements.get(n.id) != null).length).toBeGreaterThanOrEqual(
      frame.narrow ? 3 : 6,
    );
  });

  it.each(FRAMES.filter((f) => f.narrow))(
    "shows no cut name shorter than the frame's minimum or beside a name it is the start of, at $width",
    (frame) => {
      const { placements, labels } = indexGraph(frame);
      const boxes = named(placements);
      expect(boxes.length).toBeGreaterThan(5);
      for (const box of boxes.filter((b) => b.fullText)) {
        expect(visibleStart(box.text).length, box.text).toBeGreaterThanOrEqual(
          labels.minVisibleChars!,
        );
        for (const other of boxes.filter((o) => o.id !== box.id)) {
          expect(
            (other.fullText ?? other.text).startsWith(visibleStart(box.text)),
            `${box.text} beside ${other.fullText ?? other.text}`,
          ).toBe(false);
        }
      }
    },
  );

  it("drops a cut name that would read as the start of another shown name, or shows it whole", () => {
    const pair: GraphNode[] = [
      { id: 1, title: "2026 Asian Games", views: 900 },
      { id: 2, title: "2026 Asian Games medal table", views: 800 },
    ];
    const layout = computeLayout(pair, [], { width: 240, height: 240 });
    const placements = computeLabelPlacements(layout.nodes, layout.hulls, {
      variant: "index",
      minVisibleChars: 16,
      width: 240,
      height: 240,
    });
    const shown = named(placements);
    expect(shown.length).toBeGreaterThan(0);
    for (const box of shown.filter((b) => b.fullText)) {
      expect(
        shown.some(
          (o) => o.id !== box.id && (o.fullText ?? o.text).startsWith(visibleStart(box.text)),
        ),
        box.text,
      ).toBe(false);
    }
  });

  it("names isolated dots wherever a position fits, at 709", () => {
    const { layout, placements } = indexGraph(FRAMES[2]!);
    const alone = isolatedIds(layout.nodes, 90);
    expect(alone.size).toBeGreaterThan(0);
    const unnamed = [...alone].filter((id) => placements.get(id) == null);
    expect(unnamed.length).toBeLessThanOrEqual(1);
  });

  it("is the same on every run", () => {
    const a = indexGraph(FRAMES[2]!).placements;
    const b = indexGraph(FRAMES[2]!).placements;
    expect([...a.entries()]).toEqual([...b.entries()]);
  });

  it("never breaks a name over two lines", () => {
    expect(named(indexGraph(FRAMES[2]!).placements).every((b) => b.lines == null)).toBe(true);
  });

  it("cuts a single long word where the frame allows no more, since it has no space to cut at", () => {
    const word = "Pneumonoultramicroscopicsilicovolcanoconiosis";
    const box = place([dot(1, 150, 150, word)], { ellipsisChars: 20 }).get(1);
    expect(box?.text).toBe(`${word.slice(0, 17)}...`);
  });
});

describe("index names sharing a grid cell", () => {
  // Ten dots far apart, each always named, and an eleventh near the most viewed one at (10, 40).
  const far = Array.from({ length: 10 }, (_, i) =>
    dot(
      i,
      i === 0 ? 10 : 150 + (i % 5) * 300,
      i === 0 ? 40 : 100 + Math.floor(i / 5) * 300,
      `Far dot ${i}`,
      100 - i,
    ),
  );

  it.each([
    { name: "on a wide screen", dx: 40, phone: false, isNamed: false },
    { name: "on a phone", dx: 40, phone: true, isNamed: false },
    { name: "on a wide screen, where it is not isolated", dx: 60, phone: false, isNamed: false },
    { name: "on a phone, where it is isolated", dx: 60, phone: true, isNamed: true },
  ])(
    "names a less viewed dot dx px from a named one only if it is isolated: $name, $dx px",
    ({ dx, phone, isNamed }) => {
      const near = dot(10, 10 + dx, 40, "Near dot", 1);
      const placements = place([...far, near], { phone, width: 1500, height: 700 });
      expect(placements.get(0)).not.toBeNull();
      expect(placements.get(10) != null).toBe(isNamed);
    },
  );
});

describe("related names", () => {
  it("names the dots", () => {
    const { related, links } = northernCoast(16);
    const { layout, placements } = relatedGraph(related, links, 0, { width: 340, height: 260 });
    expect(placements.get(0), "the seed").not.toBeNull();
    // A crowded frame leaves out a name that has no free spot rather than print it over another name.
    expect(layout.nodes.filter((n) => placements.get(n.id) != null).length).toBeGreaterThanOrEqual(
      14,
    );
  });

  it.each([
    { dy: 24, leader: true },
    { dy: 28, leader: false },
  ])(
    "joins a name beside its dot to it by a leader when another dot is close: neighbour $dy px away",
    ({ dy, leader }) => {
      const dots = [
        dot(0, 150, 150, "Seed article", null),
        dot(1, 150, 150 + dy, "Neighbour", 0.5),
      ];
      const box = place(dots, {
        variant: "related",
        alwaysShowIds: new Set([0]),
        width: 400,
        height: 300,
      }).get(0)!;
      expect(box.leader != null).toBe(leader);
    },
  );
});

describe("a name too long for its frame", () => {
  const title = "Oak Grove Cemetery (Fall River, Massachusetts)";
  const lone: GraphNode[] = [
    { id: 0, title: "Seed", views: null },
    { id: 1, title, views: 0.5 },
  ];
  const links: GraphEdge[] = [{ source: 0, target: 1, weight: 0.5 }];

  it("stays whole where the frame has room and is cut only as far as the free width asks", () => {
    const roomy = relatedGraph(lone, links, 0, { width: 420, height: 420 }).placements;
    expect(roomy.get(1)?.text, "a frame with room names it whole").toBe(title);

    const cut = relatedGraph(lone, links, 0, { width: 150, height: 150 }).placements.get(1);
    expect(cut?.text.endsWith("...")).toBe(true);
    expect(cut?.text.length, "cut at a word, not to a fixed 26 characters").toBeLessThan(
      title.length,
    );
    expect(cut?.fullText).toBe(title);
  });

  it("goes on two lines before it is cut, and its box is one line taller", () => {
    const { placements } = relatedGraph(lone, links, 0, { width: 210, height: 210 });
    const box = placements.get(1);
    expect(box?.text, "whole, not cut").toBe(title);
    expect(box?.fullText).toBeUndefined();
    expect(box?.lines).toHaveLength(2);
    expect(box?.height).toBe(14 * 2 + 3 * 2);
    expect(countLabelCollisions(named(placements))).toBe(0);
  });

  it("slides a two-line name centred over a dot near the frame's edge inward, to stay inside", () => {
    const box = place([dot(0, 20, 150, title)], {
      variant: "related",
      alwaysShowIds: new Set([0]),
    }).get(0)!;
    expect(box.lines).toHaveLength(2);
    expect(box.textAnchor).toBe("middle");
    expect(glyphsOf(box).x).toBeGreaterThanOrEqual(7);
  });
});

describe("cut names on the Lizzie Borden related graph", () => {
  const dossier = loadDossier("dossier_214796_8000.json");
  const seed = dossier.graph.nodes.find((n) => n.role === "seed")!;
  const lizzie: GraphNode[] = dossier.graph.nodes.map((n) => ({
    id: n.id,
    title: n.title,
    views:
      n.role === "seed"
        ? 1
        : (dossier.graph.edges.find(
            (e) =>
              (e.source === seed.id && e.target === n.id) ||
              (e.target === seed.id && e.source === n.id),
          )?.weight ?? null),
  }));
  const oak = lizzie.find((n) => n.title.startsWith("Oak Grove"))!;

  // jsdom measures a name wider than the page's font does, so a smaller font size stands in for
  // the 284px frame of a landscape phone.
  it.each([
    { width: 284, fontPx: 10 },
    { width: 284, fontPx: 9 },
    { width: 280, fontPx: 12 },
    { width: 280, fontPx: 10 },
  ])("ends the cut Oak Grove name at a word, in a $width frame at $fontPx px", (size) => {
    const { placements } = relatedGraph(
      lizzie,
      dossier.graph.edges,
      seed.id,
      { width: size.width, height: size.width },
      size.fontPx,
    );
    const box = placements.get(oak.id);
    expect(box?.fullText, "the name is shown, and cut").toBe(oak.title);
    for (const cut of named(placements).filter((b) => b.fullText)) {
      expect(cut.fullText!.charAt(visibleStart(cut.text).length), cut.text).toBe(" ");
    }
  });
});

describe("breakIntoTwoLines", () => {
  it.each([
    [
      "Oak Grove Cemetery (Fall River, Massachusetts)",
      ["Oak Grove Cemetery (Fall", "River, Massachusetts)"],
    ],
    ["Monster: The Lizzie Borden Story", ["Monster: The", "Lizzie Borden Story"]],
    ["abcdefghijklmnopqrstuvwxyz tail", ["abcdefghijklmnopqrstuvwxyz", "tail"]],
    ["aaaaa b ccccc", ["aaaaa", "b ccccc"]],
  ])("breaks %s at a space into the most even lines the words allow", (title, lines) => {
    expect(breakIntoTwoLines(title)).toEqual(lines);
  });

  it.each([
    "Supercalifragilisticexpialidocious",
    "A very long title with far too many words to ever fit on two lines",
    "abcdefghijklmnopqrstuvwxyz0 tail",
  ])("has no break for %s, whose words cannot make two lines of 26", (title) => {
    expect(breakIntoTwoLines(title)).toBeNull();
  });
});

describe("isolatedIds", () => {
  it.each([
    {
      name: "two dots farther apart than the radius",
      dots: [dot(1, 0, 0, ""), dot(2, 100, 0, "")],
      ids: [1, 2],
    },
    {
      name: "two dots exactly the radius apart",
      dots: [dot(1, 0, 0, ""), dot(2, 60, 80, "")],
      ids: [1, 2],
    },
    {
      name: "two dots nearer than the radius",
      dots: [dot(1, 0, 0, ""), dot(2, 99, 0, "")],
      ids: [],
    },
    {
      name: "a lone dot beside a close pair",
      dots: [dot(1, 0, 0, ""), dot(2, 10, 0, ""), dot(3, 300, 300, "")],
      ids: [3],
    },
    { name: "a single dot", dots: [dot(1, 0, 0, "")], ids: [1] },
  ])("finds the isolated dots of $name", ({ dots, ids }) => {
    expect([...isolatedIds(dots, 100)]).toEqual(ids);
  });
});

describe("glyphsOf", () => {
  const box = { x: 10, y: 20, width: 60, height: 20 };

  it.each([
    { name: "left-aligned text", textAnchor: "start" as const, x: 12 },
    { name: "right-aligned text", textAnchor: "end" as const, x: 12 },
    { name: "centred text", textAnchor: "middle" as const, x: 15 },
    { name: "text without an anchor", textAnchor: undefined, x: 12 },
  ])("covers the glyphs of $name inside the padding of the box", ({ textAnchor, x }) => {
    expect(glyphsOf({ ...box, textAnchor })).toEqual({ x, y: 26, width: 50, height: 13 });
  });

  it("ends one pixel above the bottom of a taller two-line box", () => {
    expect(glyphsOf({ ...box, height: 34 })).toEqual({ x: 12, y: 26, width: 50, height: 27 });
  });
});
