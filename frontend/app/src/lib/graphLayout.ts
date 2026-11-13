import {
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type Simulation,
} from "d3-force";
import { polygonCentroid, polygonHull } from "d3-polygon";
import { fitToFrame, type FitItem, type FrameFit } from "./frameFit";

/**
 * Pure layout and outline math for the ConceptGraph.
 *
 * The API sends no cluster id for trending topics or related nodes, only edges. Nodes are therefore
 * grouped into connected components of the edge graph, and each component counts as one cluster for
 * outlines and colours.
 */

export interface GraphNode {
  id: number;
  title: string;
  /** Null when the value that sizes the dot is not known, such as a related node with no direct edge to the seed. */
  views: number | null;
}

export interface GraphEdge {
  source: number;
  target: number;
  weight: number;
}

export interface LaidOutNode extends GraphNode {
  x: number;
  y: number;
  radius: number;
  /** Connected-component index. The colour and the grid cell are both taken from it modulo their counts. */
  cluster: number;
}

/** A group's outline. It carries no text label, because its members' titles would repeat the node labels under it. */
export interface Hull {
  cluster: number;
  /** The padded outline, for rendering. */
  points: Array<[number, number]>;
}

export interface LayoutResult {
  nodes: LaidOutNode[];
  edges: GraphEdge[];
  hulls: Hull[];
}

export interface LayoutOptions {
  width: number;
  height: number;
  /** Outline padding in px around a group's dots. */
  hullPad?: number;
  /** Smallest and largest dot radius in px. */
  radiusRange?: [number, number];
  /** Number of simulation ticks run before the layout is returned. */
  ticks?: number;
  /**
   * Rects drawn over the graph, such as the legend chip, that dots should not sit under, in the same
   * coordinates as width and height. Unlike `reservedBoxes` in `computeLabelPlacements`, which only
   * steers label text, these keep the dots themselves clear.
   */
  excludeBoxes?: ExcludeBox[];
  /**
   * Tunes the layout for a close-to-square frame, which holds more dots per unit area.
   * Cluster centres seed on a grid of SQUARE_GRID_ROWS rows instead of GRID_ROWS, and dots get a wider collision pad.
   * More rows in a short frame would seed the clusters so close together that repulsion pushes the whole cloud to the walls.
   */
  squareFrame?: boolean;
  /**
   * Least distance in px from the frame's edge to a group outline, the padded hull. The fit keeps
   * every outline whole inside the frame by at least this much.
   */
  hullInset?: number;
  /** Least clearance in px from a dot's edge to the frame. */
  wallMargin?: number;
}

const GRID_COLS = 2;
const GRID_ROWS = 3;
const SQUARE_GRID_ROWS = 2;
/** Smallest side, in px, at which a square frame is roomy enough to seed a middle row. */
const SPACIOUS_FRAME_PX = 500;
/** Height over width above which a non-square frame counts as portrait. */
const PORTRAIT_RATIO = 1.15;
/** Multiplier on a singleton's pull toward the centre in a portrait frame. */
const PORTRAIT_CENTER_PULL = 1.4;
/** Multiplier on a group's pull toward its grid cell in a portrait frame. */
const PORTRAIT_GROUP_PULL = 3;
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
/** Default least clearance in px from a dot's edge to the frame. */
const WALL_MARGIN_PX = 12;
/** Default least distance in px from a group outline to the frame's edge. */
const HULL_INSET_PX = 6;
const DEFAULT_HULL_PAD_PX = 18;
const DEFAULT_RADIUS_RANGE_PX: [number, number] = [5, 16];
const DEFAULT_TICKS = 300;
/**
 * Least vertical spread, in px, between the highest and lowest dot of a group of three or more.
 * A rect that dots keep off can make the clamp snap a whole group onto one row, which would
 * collapse its outline to a line.
 */
const MIN_GROUP_SPAN_PX = 40;

class UnionFind {
  private readonly parent = new Map<number, number>();

  find(x: number): number {
    if (!this.parent.has(x)) {
      this.parent.set(x, x);
    }
    let root = x;
    while (this.parent.get(root) !== root) {
      const next = this.parent.get(root);
      root = next ?? root;
    }
    let cur = x;
    while (cur !== root) {
      const next = this.parent.get(cur) ?? root;
      this.parent.set(cur, root);
      cur = next;
    }
    return root;
  }

  union(a: number, b: number): void {
    const ra = this.find(a);
    const rb = this.find(b);
    if (ra !== rb) {
      this.parent.set(ra, rb);
    }
  }
}

/**
 * Groups node ids into connected components over the edges whose ends are both in `nodes`.
 *
 * The result maps each id to a 0-based component index, largest component first and ties broken by
 * the smallest member id, so the order is the same for the same input.
 */
export function computeComponents(nodes: GraphNode[], edges: GraphEdge[]): Map<number, number> {
  const ids = new Set(nodes.map((n) => n.id));
  const uf = new UnionFind();
  for (const node of nodes) {
    uf.find(node.id);
  }
  for (const edge of edges) {
    if (ids.has(edge.source) && ids.has(edge.target)) {
      uf.union(edge.source, edge.target);
    }
  }
  const members = new Map<number, number[]>();
  for (const node of nodes) {
    const root = uf.find(node.id);
    const list = members.get(root);
    if (list) {
      list.push(node.id);
    } else {
      members.set(root, [node.id]);
    }
  }
  const ordered = [...members.values()].toSorted((a, b) => {
    if (a.length !== b.length) {
      return b.length - a.length;
    }
    return Math.min(...a) - Math.min(...b);
  });
  const indexById = new Map<number, number>();
  ordered.forEach((group, index) => {
    for (const id of group) {
      indexById.set(id, index);
    }
  });
  return indexById;
}

function gridCenters(
  width: number,
  height: number,
  rows: number,
  inset = 0,
): Array<{ x: number; y: number }> {
  const cellW = (width - inset * 2) / GRID_COLS;
  const cellH = (height - inset * 2) / rows;
  const centers: Array<{ x: number; y: number }> = [];
  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < GRID_COLS; col += 1) {
      centers.push({ x: inset + cellW * (col + 0.5), y: inset + cellH * (row + 0.5) });
    }
  }
  return centers;
}

interface Bounded {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  cluster: number;
}

/** A rect drawn over the graph that dots keep off. */
export interface ExcludeBox {
  x: number;
  y: number;
  width: number;
  height: number;
  /**
   * True for a rect that group outlines keep off as well, not only dots. Such
   * a rect is kept clear after the fit, where the dots land, and not while
   * they settle: pushing the simulation away from a corner reshuffles the
   * whole cloud, while the clamp moves only the dots near it.
   */
  hull?: boolean;
}

/**
 * How far a dot's mark reaches from its centre toward a rect: its radius plus the wall margin.
 * For a grouped dot next to a rect that outlines also keep off, the outline padding plus
 * HULL_REACH_SLACK_PX counts instead if it is larger.
 */
type ReachOf = (node: { radius: number; cluster: number }, box: ExcludeBox) => number;

/** Maps a dot to the nearest position where it fits the frame and clears the rects it must keep off. */
type Clamp = (node: { x: number; y: number; radius: number; cluster: number }) => {
  x: number;
  y: number;
};

/** Groups items by cluster, in the order the clusters first appear. */
function groupByCluster<T extends { cluster: number }>(items: T[]): Map<number, T[]> {
  const groups = new Map<number, T[]>();
  for (const item of items) {
    const list = groups.get(item.cluster);
    if (list) {
      list.push(item);
    } else {
      groups.set(item.cluster, [item]);
    }
  }
  return groups;
}

/** Largest extra offset in px added to a dot moved off a rect that outlines also keep off; it varies with the dot's x so moved dots do not line up. */
const LEGEND_SCATTER_PX = 6;
const GOLDEN_FRACTION = 0.6180339887;

/**
 * The outline's padding is drawn from the dots' centres; this much more keeps its stroke and a
 * little air off a rect.
 */
const HULL_REACH_SLACK_PX = 7;

/**
 * Returns the y a dot must take to clear a rect, or null when it is already clear.
 * The dot goes above a rect in the lower half of the area and below one in the upper half.
 */
function yClearOf(
  box: ExcludeBox,
  node: { x: number; y: number },
  reach: number,
  height: number,
): number | null {
  if (!(node.x + reach > box.x && node.x - reach < box.x + box.width)) {
    return null;
  }
  if (box.y + box.height / 2 > height / 2) {
    const top = box.y - reach;
    return node.y > top ? top : null;
  }
  const bottom = box.y + box.height + reach;
  return node.y < bottom ? bottom : null;
}

/**
 * A d3-force that pushes dots vertically clear of the rects that only dots, not outlines, must keep off.
 *
 * The rects are in fitted coordinates, so each dot is mapped through `fit`, the scale and offset the
 * cloud will be given afterwards, before it is compared. The frame's edges are not a force: the fit
 * seats the whole cloud afterwards, so repulsion has no wall to pile dots against.
 */
function excludeForce(excludeBoxes: ExcludeBox[], reachOf: ReachOf, height: number, fit: FrameFit) {
  let nodes: Bounded[] = [];
  const strength = 0.3;
  function force(alpha: number) {
    for (const node of nodes) {
      const placed = { x: node.x * fit.scale + fit.tx, y: node.y * fit.scale + fit.ty };
      for (const box of excludeBoxes) {
        const target = box.hull ? null : yClearOf(box, placed, reachOf(node, box), height);
        if (target !== null) {
          node.vy += ((target - placed.y) / fit.scale) * strength * alpha;
        }
      }
    }
  }
  force.initialize = (n: Bounded[]) => {
    nodes = n;
  };
  return force;
}

/**
 * Lists how far each dot must stay from the four frame edges, one item per dot in the same order.
 *
 * That is the dot's radius plus the wall margin. For a dot on a group outline's corner it is instead the
 * outline padding in the direction the corner is pushed plus the outline inset, when that is larger.
 */
function fitItemsFor(
  simNodes: Array<{ x: number; y: number; radius: number; cluster: number }>,
  hullPad: number,
  wallMargin: number,
  hullInset: number,
): FitItem[] {
  const items: FitItem[] = simNodes.map((n) => ({
    x: n.x,
    y: n.y,
    left: n.radius + wallMargin,
    right: n.radius + wallMargin,
    top: n.radius + wallMargin,
    bottom: n.radius + wallMargin,
  }));
  const byCluster = new Map<number, number[]>();
  simNodes.forEach((n, index) =>
    byCluster.set(n.cluster, [...(byCluster.get(n.cluster) ?? []), index]),
  );
  for (const members of byCluster.values()) {
    if (members.length < 3) {
      continue;
    }
    const raw = polygonHull(
      members.map((m): [number, number] => [simNodes[m]?.x ?? 0, simNodes[m]?.y ?? 0]),
    );
    if (raw === null || raw.length < 3) {
      continue;
    }
    const [cx, cy] = polygonCenter(raw);
    for (const [vx, vy] of raw) {
      const index = members.find((m) => simNodes[m]?.x === vx && simNodes[m]?.y === vy);
      const item = index === undefined ? undefined : items[index];
      if (!item) {
        continue;
      }
      const len = Math.hypot(vx - cx, vy - cy) || 1;
      const ux = (vx - cx) / len;
      const uy = (vy - cy) / len;
      item.left = Math.max(item.left, -ux * hullPad + hullInset);
      item.right = Math.max(item.right, ux * hullPad + hullInset);
      item.top = Math.max(item.top, -uy * hullPad + hullInset);
      item.bottom = Math.max(item.bottom, uy * hullPad + hullInset);
    }
  }
  return items;
}

/** Extra gap kept between two dots by the passes that separate overlapping dots. */
const RELAX_GAP_PX = 2;
const RELAX_PASSES = 400;

/**
 * Pushes overlapping dots apart after the wall clamp, in place.
 *
 * The clamp can drag a dot back into a neighbour it had cleared, which on a dense frame leaves true circle
 * overlaps. Each pass moves each dot of an overlapping pair half the shortfall and re-clamps, and the loop
 * stops once a pass moves nothing.
 */
function separateOverlaps(nodes: LaidOutNode[], clamp: Clamp): void {
  for (let pass = 0; pass < RELAX_PASSES; pass++) {
    let moved = false;
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      if (!a) continue;
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j];
        if (!b) continue;
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let dist = Math.hypot(dx, dy);
        const want = a.radius + b.radius + RELAX_GAP_PX;
        if (dist >= want) continue;
        if (dist < 1e-6) {
          dx = Math.cos(i + j);
          dy = Math.sin(i + j);
          dist = 1;
        }
        const push = (want - dist) / 2;
        const ux = dx / dist;
        const uy = dy / dist;
        a.x -= ux * push;
        a.y -= uy * push;
        b.x += ux * push;
        b.y += uy * push;
        moved = true;
      }
    }
    for (const node of nodes) {
      Object.assign(node, clamp(node));
    }
    if (!moved) return;
  }
}

/**
 * Last pass after the fit and every clamp: it pushes apart any two dots closer than their radii plus the gap.
 *
 * When a lone dot overlaps a grouped one, only the lone dot moves. The pass keeps the least-overlapping state it
 * has seen, so a clamp that undoes a push cannot leave the result worse than it began.
 */
function settleCollisions(
  nodes: LaidOutNode[],
  clamp: Clamp,
  isLone: (node: LaidOutNode) => boolean,
): void {
  const overlap = (): number => {
    let total = 0;
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i]!;
        const b = nodes[j]!;
        total += Math.max(0, a.radius + b.radius + RELAX_GAP_PX - Math.hypot(a.x - b.x, a.y - b.y));
      }
    }
    return total;
  };
  let best = overlap();
  let bestState = nodes.map((n) => ({ x: n.x, y: n.y }));
  for (let pass = 0; pass < RELAX_PASSES && best > 1e-6; pass++) {
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i]!;
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j]!;
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let dist = Math.hypot(dx, dy);
        const want = a.radius + b.radius + RELAX_GAP_PX;
        if (dist >= want) continue;
        if (dist < 1e-6) {
          dx = Math.cos(i + j);
          dy = Math.sin(i + j);
          dist = 1;
        }
        const push = want - dist;
        const ux = dx / dist;
        const uy = dy / dist;
        const aLone = isLone(a);
        const bLone = isLone(b);
        const shareA = aLone === bLone ? 0.5 : aLone ? 1 : 0;
        a.x -= ux * push * shareA;
        a.y -= uy * push * shareA;
        b.x += ux * push * (1 - shareA);
        b.y += uy * push * (1 - shareA);
      }
    }
    for (const node of nodes) {
      Object.assign(node, clamp(node));
    }
    const now = overlap();
    if (now < best) {
      best = now;
      bestState = nodes.map((n) => ({ x: n.x, y: n.y }));
    }
  }
  nodes.forEach((n, i) => Object.assign(n, bestState[i]));
}

/**
 * Returns a clamped square-root scale from `domain` onto `range`, like d3's
 * `scaleSqrt().domain(domain).range(range).clamp(true)` for a domain at or above zero.
 * It is written inline so this module does not import d3-scale for one function.
 */
function sqrtScale(domain: [number, number], range: [number, number]): (value: number) => number {
  const [d0, d1] = domain;
  const sd0 = Math.sqrt(Math.max(d0, 0));
  const sd1 = Math.sqrt(Math.max(d1, 0));
  const span = sd1 - sd0;
  return (value: number) => {
    const clamped = Math.min(Math.max(value, d0), d1);
    const t = span === 0 ? 0 : (Math.sqrt(Math.max(clamped, 0)) - sd0) / span;
    return range[0] + t * (range[1] - range[0]);
  };
}

/**
 * Gives every group of three or more dots a vertical spread of at least MIN_GROUP_SPAN_PX, in place, so
 * its outline keeps a 2D shape, and returns whether any group moved.
 *
 * The dots of a flat group alternate above and below the group's mean row. That row first moves clear of
 * any excluded rect the group sits under, so the clamp does not flatten the group again.
 */
function restoreFlatGroups(
  laidOut: LaidOutNode[],
  excludeBoxes: ExcludeBox[],
  height: number,
  reachOf: ReachOf,
  clamp: Clamp,
): boolean {
  const groups = groupByCluster(laidOut);
  let moved = false;
  for (const members of groups.values()) {
    if (members.length < 3) {
      continue;
    }
    const ys = members.map((m) => m.y);
    if (Math.max(...ys) - Math.min(...ys) >= MIN_GROUP_SPAN_PX) {
      continue;
    }
    let rowY = ys.reduce((sum, y) => sum + y, 0) / ys.length;
    for (const box of excludeBoxes) {
      const underBox = members.some(
        (m) => m.x + m.radius > box.x && m.x - m.radius < box.x + box.width,
      );
      if (!underBox) {
        continue;
      }
      if (box.y + box.height / 2 > height / 2) {
        const reach = Math.max(...members.map((m) => reachOf(m, box)));
        rowY = Math.min(rowY, box.y - reach - MIN_GROUP_SPAN_PX / 2);
      } else {
        const reach = Math.max(...members.map((m) => reachOf(m, box)));
        rowY = Math.max(rowY, box.y + box.height + reach + MIN_GROUP_SPAN_PX / 2);
      }
    }
    members
      .toSorted((a, b) => a.x - b.x)
      .forEach((member, index) => {
        const offset = index % 2 === 0 ? -MIN_GROUP_SPAN_PX / 2 : MIN_GROUP_SPAN_PX / 2;
        Object.assign(
          member,
          clamp({ x: member.x, y: rowY + offset, radius: member.radius, cluster: member.cluster }),
        );
      });
    moved = true;
  }
  return moved;
}

/**
 * Lifts every group of two or more dots, whole, until its lowest dot and outline clear a rect that
 * outlines must keep off, if the rect is in the lower half of the area.
 *
 * Lifting the whole group keeps its shape, which the clamp would squash. Lone dots are left to the clamp.
 */
function liftGroups(
  laidOut: LaidOutNode[],
  excludeBoxes: ExcludeBox[],
  height: number,
  reachOf: ReachOf,
  isGrouped: (node: LaidOutNode) => boolean,
): void {
  for (const box of excludeBoxes) {
    if (!box.hull || box.y + box.height / 2 <= height / 2) {
      continue;
    }
    for (const members of groupByCluster(laidOut.filter(isGrouped)).values()) {
      const lift = Math.max(
        0,
        ...members.map((m) => {
          const target = yClearOf(box, m, reachOf(m, box), height);
          return target === null ? 0 : m.y - target;
        }),
      );
      for (const m of members) {
        m.y -= lift;
      }
    }
  }
}

function polygonCenter(points: Array<[number, number]>): [number, number] {
  const centroid = polygonCentroid(points);
  if (Number.isFinite(centroid[0]) && Number.isFinite(centroid[1])) {
    return centroid;
  }
  let sx = 0;
  let sy = 0;
  for (const [x, y] of points) {
    sx += x;
    sy += y;
  }
  return [sx / points.length, sy / points.length];
}

function padHull(points: Array<[number, number]>, pad: number): Array<[number, number]> {
  const [cx, cy] = polygonCenter(points);
  return points.map(([x, y]) => {
    const dx = x - cx;
    const dy = y - cy;
    const len = Math.hypot(dx, dy) || 1;
    return [x + (dx / len) * pad, y + (dy / len) * pad];
  });
}

const CAPSULE_ARC_STEPS = 16;
/** A capsule stands at least this far off each dot's edge. */
const CAPSULE_MARGIN_PX = 5;

/**
 * Returns the outline of a two-dot group as a polygon: the convex hull of a circle sampled around each
 * dot, with a radius close to the padding the polygon hulls keep.
 */
function capsuleHull(pair: [LaidOutNode, LaidOutNode], pad: number): Array<[number, number]> {
  const samples: Array<[number, number]> = [];
  for (const node of pair) {
    const r = Math.max(node.radius + CAPSULE_MARGIN_PX, pad * 0.8);
    for (let i = 0; i < CAPSULE_ARC_STEPS; i += 1) {
      const angle = (2 * Math.PI * i) / CAPSULE_ARC_STEPS;
      samples.push([node.x + r * Math.cos(angle), node.y + r * Math.sin(angle)]);
    }
  }
  return polygonHull(samples) ?? samples;
}

/** A dot while the simulation runs. */
interface SimNode extends GraphNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  cluster: number;
  /** The dot's position by id order among all dots, for the horizontal spread when no cluster is separable. */
  seedIndex: number;
}

/** What one layout pass works out from its input before any dot moves. */
interface PassPlan extends Required<LayoutOptions> {
  /** The cluster index of each node id. */
  clusterOf: Map<number, number>;
  /** How many nodes each cluster holds. */
  clusterSizes: Map<number, number>;
  /**
   * False when the graph is one cluster or one cluster holds most of the nodes, as a seed and
   * everything it links to do. There are then no groups to place on a grid.
   */
  separable: boolean;
  /** The grid cell centres that clusters are seeded on and pulled toward. */
  centers: Array<{ x: number; y: number }>;
  /** True for a square frame with room to spare. */
  spacious: boolean;
  /** True for a tall, narrow frame. */
  portrait: boolean;
  reachOf: ReachOf;
  /** True for a cluster of two or more nodes. */
  isGrouped: (cluster: number) => boolean;
}

function planPass(nodes: GraphNode[], edges: GraphEdge[], options: LayoutOptions): PassPlan {
  const {
    width,
    height,
    hullPad = DEFAULT_HULL_PAD_PX,
    radiusRange = DEFAULT_RADIUS_RANGE_PX,
    ticks = DEFAULT_TICKS,
    excludeBoxes = [],
    squareFrame = false,
    hullInset = HULL_INSET_PX,
    wallMargin = WALL_MARGIN_PX,
  } = options;
  const clusterOf = computeComponents(nodes, edges);
  const clusterSizes = new Map<number, number>();
  for (const cluster of clusterOf.values()) {
    clusterSizes.set(cluster, (clusterSizes.get(cluster) ?? 0) + 1);
  }
  const isGrouped = (cluster: number) => (clusterSizes.get(cluster) ?? 1) > 1;
  const largestCluster = Math.max(0, ...clusterSizes.values());
  const gridRows = squareFrame ? SQUARE_GRID_ROWS : GRID_ROWS;
  return {
    width,
    height,
    hullPad,
    radiusRange,
    ticks,
    excludeBoxes,
    squareFrame,
    hullInset,
    wallMargin,
    clusterOf,
    clusterSizes,
    separable: clusterSizes.size > 1 && largestCluster <= nodes.length * 0.6,
    centers: gridCenters(width, height, gridRows, hullPad),
    // In a square frame with room to spare, grouped clusters keep their grid cells but single nodes
    // gather on the middle row. Otherwise the middle band of the frame stays empty.
    spacious: squareFrame && Math.min(width, height) >= SPACIOUS_FRAME_PX,
    // A tall, narrow frame gets stronger pulls toward the centre and the grid cells.
    // Without them it settles into two columns of groups against its side walls.
    portrait: !squareFrame && height > width * PORTRAIT_RATIO,
    reachOf: (node, box) => {
      const mark = node.radius + wallMargin;
      return box.hull && isGrouped(node.cluster)
        ? Math.max(mark, hullPad + HULL_REACH_SLACK_PX)
        : mark;
    },
    isGrouped,
  };
}

/** Returns the centre of the grid cell a cluster is seeded on and pulled toward. */
function cellCenter(plan: PassPlan, cluster: number): { x: number; y: number } {
  return plan.centers[cluster % plan.centers.length] ?? { x: plan.width / 2, y: plan.height / 2 };
}

/**
 * Gives every node a start position and a radius, in id order.
 *
 * A dot starts near its cluster's grid cell and fans out by its order within the cluster or slot.
 * In a spacious frame a singleton starts instead on a staggered middle row.
 */
function seedNodes(nodes: GraphNode[], plan: PassPlan): SimNode[] {
  const { width, height, radiusRange, spacious } = plan;
  const knownViews = nodes.map((n) => n.views).filter((v): v is number => v != null);
  const radiusScale = sqrtScale(
    [Math.min(...knownViews, 0), Math.max(...knownViews, 1)],
    radiusRange,
  );
  // A node whose value is not known gets the midpoint of the radius range, so it neither claims a
  // value nor skews the sizes of nodes that do.
  const neutralRadius = (radiusRange[0] + radiusRange[1]) / 2;
  const clusterCounts = new Map<number, number>();
  // Singletons that map to the same grid slot fan out by their order within the slot. Seeded on one
  // point, they would start with identical positions, and the positional pulls would then hold
  // them closer together than their radii.
  const singletonSlotCounts = new Map<number, number>();
  const singletonTotal = [...plan.clusterSizes.values()].filter((size) => size === 1).length;
  let singletonSeen = 0;
  return [...nodes]
    .toSorted((a, b) => a.id - b.id)
    .map((node, seedIndex) => {
      const cluster = plan.clusterOf.get(node.id) ?? 0;
      const slot = cluster % plan.centers.length;
      const center = cellCenter(plan, cluster);
      const isSingleton = !plan.isGrouped(cluster);
      let localIndex: number;
      if (isSingleton) {
        localIndex = singletonSlotCounts.get(slot) ?? 0;
        singletonSlotCounts.set(slot, localIndex + 1);
      } else {
        localIndex = clusterCounts.get(cluster) ?? 0;
        clusterCounts.set(cluster, localIndex + 1);
      }
      const angle = localIndex * GOLDEN_ANGLE;
      const spread = Math.sqrt(localIndex) * 6;
      let seedX = center.x + spread * Math.cos(angle);
      let seedY = center.y + spread * Math.sin(angle);
      if (spacious && isSingleton) {
        // Spread across the width on the middle row, staggered so neighbours do not start on one line.
        seedX = (width * (singletonSeen + 0.5)) / singletonTotal;
        seedY = height / 2 + ((singletonSeen % 3) - 1) * 36;
        singletonSeen += 1;
      }
      return {
        ...node,
        cluster,
        seedIndex,
        radius: node.views == null ? neutralRadius : radiusScale(node.views),
        x: seedX,
        y: seedY,
        vx: 0,
        vy: 0,
      };
    });
}

/**
 * Builds the stopped d3-force simulation: link, charge and collision forces, the pulls toward grid
 * cells and the centre, and the push off the rects that only dots keep clear of.
 * `hint` is the scale and offset that those rects are mapped through while the dots settle.
 */
function createSimulation(
  simNodes: SimNode[],
  validEdges: GraphEdge[],
  plan: PassPlan,
  hint: FrameFit,
): Simulation<SimNode, undefined> {
  const { width, height, squareFrame, separable, spacious, portrait, isGrouped } = plan;
  const linkEdges = validEdges.map((e) => ({ source: e.source, target: e.target }));
  // A graph with one dominant component, such as a seed linked to everything else, settles into a tight
  // ring at the link distance whatever the frame size. The link distance therefore grows with the
  // frame's shorter side.
  const linkDistance = separable ? 42 : Math.max(42, Math.min(width, height) / 3);
  // With separable clusters, a square frame holds more nodes per unit area, so it uses a weaker repulsion.
  // At the landscape strength the repulsion overpowers the weak positional pulls below and settles the
  // cloud into a shell at the wall.
  const chargeStrength = separable ? (squareFrame ? -55 : -120) : -170;
  return (
    forceSimulation(simNodes)
      .force(
        "link",
        forceLink<SimNode, { source: number; target: number }>(linkEdges)
          .id((d) => d.id)
          .distance(linkDistance)
          .strength(separable ? 0.25 : 0.12),
      )
      .force("charge", forceManyBody().strength(chargeStrength))
      // A square frame is denser, so its dots get a wider collision pad.
      .force(
        "collide",
        forceCollide<SimNode>((d) => d.radius + (squareFrame ? 4 : 3)),
      )
      // Groups are pulled toward their grid cell so they fill the gaps between cells. Singletons get this
      // pull only in a square frame, and no dot gets it when no cluster is separable. Pulling many
      // repelling singletons to one shared centre would leave them in a hollow shell, so the grid cells
      // give them several centres to fill.
      .force(
        "x",
        forceX<SimNode>((d) => cellCenter(plan, d.cluster).x).strength((d) => {
          if (!separable) {
            return 0;
          }
          if (isGrouped(d.cluster)) {
            return portrait ? 0.035 * PORTRAIT_GROUP_PULL : 0.02;
          }
          return squareFrame ? 0.018 : 0;
        }),
      )
      .force(
        "y",
        forceY<SimNode>((d) =>
          spacious && !isGrouped(d.cluster) ? height / 2 : cellCenter(plan, d.cluster).y,
        ).strength((d) => {
          if (!separable) {
            return 0;
          }
          if (isGrouped(d.cluster)) {
            return portrait ? 0.02 * PORTRAIT_GROUP_PULL : 0.02;
          }
          return squareFrame ? 0.018 : 0;
        }),
      )
      // Centring force. For a group it only keeps the cloud from drifting, but a singleton outside a
      // square frame has no grid pull, so this is its main pull. When no cluster is separable, each dot's
      // x target is spread across the width by id order, because one component pulled to a single point
      // settles into a clump.
      .force(
        "centerX",
        forceX<SimNode>((d) =>
          separable ? width / 2 : (width * (d.seedIndex + 0.5)) / simNodes.length,
        ).strength((d) => {
          if (!separable) {
            return 0.3;
          }
          if (isGrouped(d.cluster)) {
            return 0.01;
          }
          return squareFrame ? 0.01 : portrait ? 0.03 * PORTRAIT_CENTER_PULL : 0.03;
        }),
      )
      .force(
        "centerY",
        forceY<SimNode>(height / 2).strength((d) => {
          if (!separable) {
            return 0.015;
          }
          if (isGrouped(d.cluster)) {
            return 0.01;
          }
          return squareFrame ? 0.01 : portrait ? 0.03 * PORTRAIT_CENTER_PULL : 0.03;
        }),
      )
      .force("exclude", excludeForce(plan.excludeBoxes, plan.reachOf, height, hint))
      .stop()
  );
}

/**
 * Runs the simulation, then moves the settled dots by one uniform scale and offset that seat the
 * cloud inside the frame, and returns that fit.
 * No dot is pulled to an edge on its own, so the groups keep their shape.
 */
function runSimulation(
  simulation: Simulation<SimNode, undefined>,
  simNodes: SimNode[],
  plan: PassPlan,
): FrameFit {
  simulation.tick(plan.ticks);
  const items = fitItemsFor(simNodes, plan.hullPad, plan.wallMargin, plan.hullInset);
  const fit = fitToFrame(items, plan.width, plan.height);
  for (const node of simNodes) {
    node.x = node.x * fit.scale + fit.tx;
    node.y = node.y * fit.scale + fit.ty;
  }
  return fit;
}

/** Returns the clamp that keeps a dot's edge `wallMargin` inside the frame and clear of the rects it must keep off. */
function makeClamp(plan: PassPlan): Clamp {
  const { width, height, wallMargin, excludeBoxes, reachOf, isGrouped } = plan;
  return (node) => {
    const pad = node.radius + wallMargin;
    const x = Math.min(Math.max(node.x, pad), Math.max(width - pad, pad));
    let y = Math.min(Math.max(node.y, pad), Math.max(height - pad, pad));
    for (const box of excludeBoxes) {
      if (box.hull && isGrouped(node.cluster)) {
        // A group was lifted whole off the rect; moving a dot on its own would squash the group.
        continue;
      }
      const target = yClearOf(box, { x, y }, reachOf(node, box), height);
      if (target !== null) {
        // A dot goes to the clear edge of the rect. For a rect that outlines also keep off, it goes further by
        // half the depth it had entered plus a small amount that varies along the edge, so the moved dots do
        // not end on one line.
        const away = box.y + box.height / 2 > height / 2 ? -1 : 1;
        const scatter = LEGEND_SCATTER_PX * ((x * GOLDEN_FRACTION) % 1);
        const settled = box.hull ? target + away * (Math.abs(y - target) / 2 + scatter) : target;
        y = Math.min(Math.max(settled, pad), Math.max(height - pad, pad));
      }
    }
    return { x, y };
  };
}

/** Restores group shape and spacing after the fit, in place: flat groups, lifted groups, overlapping dots. */
function separateDots(laidOut: LaidOutNode[], plan: PassPlan): void {
  const { height, excludeBoxes, reachOf, isGrouped } = plan;
  const clamp = makeClamp(plan);
  restoreFlatGroups(laidOut, excludeBoxes, height, reachOf, clamp);
  liftGroups(laidOut, excludeBoxes, height, reachOf, (n) => isGrouped(n.cluster));
  separateOverlaps(laidOut, clamp);
  // Keeping dots off a rect that outlines keep off can flatten a group again, so restore the groups once more.
  if (
    excludeBoxes.some((box) => box.hull) &&
    restoreFlatGroups(laidOut, excludeBoxes, height, reachOf, clamp)
  ) {
    separateOverlaps(laidOut, clamp);
  }
  settleCollisions(laidOut, clamp, (n) => !isGrouped(n.cluster));
}

/** Builds the outline of every group of two or more dots, ordered by cluster. */
function buildHulls(laidOut: LaidOutNode[], hullPad: number): Hull[] {
  const hulls: Hull[] = [];
  for (const [cluster, members] of [...groupByCluster(laidOut).entries()].toSorted(
    (a, b) => a[0] - b[0],
  )) {
    if (members.length === 2) {
      hulls.push({ cluster, points: capsuleHull([members[0]!, members[1]!], hullPad) });
      continue;
    }
    if (members.length < 3) {
      continue;
    }
    const raw = polygonHull(members.map((m): [number, number] => [m.x, m.y]));
    if (raw === null || raw.length < 3) {
      continue;
    }
    hulls.push({ cluster, points: padHull(raw, hullPad) });
  }
  return hulls;
}

/**
 * One run of the layout: the simulation, the fit, and the passes that restore group shape and separate dots.
 * `hint` is the scale and offset that the reserved rects are mapped through while the dots settle.
 */
function layoutPass(
  nodes: GraphNode[],
  edges: GraphEdge[],
  options: LayoutOptions,
  hint: FrameFit,
): { layout: LayoutResult; fit: FrameFit } {
  const plan = planPass(nodes, edges, options);
  const simNodes = seedNodes(nodes, plan);
  const nodeIds = new Set(simNodes.map((n) => n.id));
  const validEdges = edges.filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target));
  const simulation = createSimulation(simNodes, validEdges, plan, hint);
  const fit = runSimulation(simulation, simNodes, plan);
  const laidOut: LaidOutNode[] = simNodes.map((node) => ({
    id: node.id,
    title: node.title,
    views: node.views,
    radius: node.radius,
    cluster: node.cluster,
    x: node.x,
    y: node.y,
  }));
  separateDots(laidOut, plan);
  return {
    layout: { nodes: laidOut, edges: validEdges, hulls: buildHulls(laidOut, plan.hullPad) },
    fit,
  };
}

/**
 * Runs the seeded force layout and returns the dots, the edges whose ends both exist, and an outline for
 * each group of two or more dots.
 *
 * A pair gets a capsule, and three or more get a padded convex hull unless it is degenerate. d3-force seeds
 * its random generator with a fixed value, so the same input always gives the same positions.
 */
export function computeLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  options: LayoutOptions,
): LayoutResult {
  const first = layoutPass(nodes, edges, options, { scale: 1, tx: 0, ty: 0 });
  if (!options.excludeBoxes?.some((box) => box.hull)) {
    return first.layout;
  }
  // The simulation settles before its fit is known, so it cannot place dots against the rects in fitted
  // coordinates. When a legend corner is reserved, run a second pass that maps the rects through the fit
  // the first pass found.
  return layoutPass(nodes, edges, options, first.fit).layout;
}
