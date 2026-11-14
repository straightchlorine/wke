import type { DossierState } from "./dossierState";
import { formatNumber } from "./format";

/** Which graph: the index of trending topics on Home, or the related articles of one dossier. */
export type GraphVariant = "index" | "related";

export interface ConceptGraphNode {
  /** The Wikipedia page id; also the graph node id. */
  id: number;
  title: string;
  /** Used to build the dossier link, `/t/{slug}`. */
  slug: string;
  /** Views on the index variant, or similarity to the seed on the related variant. Null when unknown, for example a related node with no direct edge to the seed. */
  views: number | null;
  /** A "seed" draws as a filled dot in the ink colour. Only the related variant has one. */
  role?: "seed" | "related";
  /**
   * Edits in the last hour, shown by PlateBoard on the index variant. Null or undefined means the
   * figure was not measured, and PlateBoard says so instead of showing 0.
   */
  editsLastHour?: number | null;
  /** The topic's dossier state, for PlateBoard; omitted when the graph does not know it. */
  state?: DossierState;
  /** Wikipedia's short description of the article, verbatim, for PlateBoard. */
  description?: string;
}

export interface ConceptGraphEdge {
  source: number;
  target: number;
  weight: number;
}

/** What PlateBoard shows for one node. */
export interface PlateBoardNode {
  title: string;
  /** Wikipedia's short description of the article, verbatim; omitted when the source carries none. */
  description?: string;
  /** The first record row, e.g. "806,988" under "Views" or "0.72" under "Similarity"; "not measured" when omitted. */
  figure?: { label: "Views" | "Similarity"; value: string };
  /** Edits in the last hour; "not measured" when the source carries no such figure. */
  editsLastHour?: number | null;
  /** True while the edit feed is down: the edits row then says so instead of a count. */
  editsUnavailable?: boolean;
  /** The label of the first record row when `figure` is absent. Defaults to "Views". */
  figureLabel?: "Views" | "Similarity";
  /** The wording of the edits row when the source has no edit figures at all. */
  editsMissing?: string;
  /** The titles of the node's neighbours, strongest link first. */
  linkedTo: string[];
  /** The topic's dossier state; omitted when it is not known, and the badge then just says "Open". */
  state?: DossierState;
  /** The node's dossier link. */
  href: string;
}

const STATE_TEXT: Record<DossierState, string> = {
  ready: "dossier ready",
  partial: "dossier partial",
  building: "dossier in progress",
  none: "no dossier yet",
};

/** Returns the figure a node shows: its views on the index, its similarity on the related graph, or nothing when unknown or for the seed. */
export function nodeFigure(
  node: Pick<ConceptGraphNode, "views" | "role">,
  variant: GraphVariant,
): PlateBoardNode["figure"] {
  if (node.views == null || (variant === "related" && node.role === "seed")) {
    return undefined;
  }
  return variant === "related"
    ? { label: "Similarity", value: node.views.toFixed(2) }
    : { label: "Views", value: formatNumber(node.views) };
}

/** Returns the accessible name of a node's link: title, figure, dossier state, whether it was just edited, and what Enter does. */
export function nodeAriaLabel(
  node: ConceptGraphNode,
  variant: GraphVariant,
  flags: { pinged: boolean; selected: boolean },
): string {
  const figure = nodeFigure(node, variant);
  const figureText =
    figure == null
      ? ""
      : figure.label === "Similarity"
        ? `, similarity ${figure.value}`
        : `, ${figure.value} views`;
  const stateText = variant === "index" && node.state ? `, ${STATE_TEXT[node.state]}` : "";
  const pingedText = flags.pinged ? ", edited in the last minute" : "";
  const enterText = flags.selected
    ? ", selected, press Enter to open the dossier"
    : ", press Enter to select";
  return `${node.title}${figureText}${stateText}${pingedText}${enterText}`;
}

/** Returns each node's neighbours' titles by edge weight, strongest first. An edge with an end outside `nodes` is skipped. */
export function neighbourTitles(
  nodes: ConceptGraphNode[],
  edges: ConceptGraphEdge[],
): Map<number, string[]> {
  const titles = new Map(nodes.map((n) => [n.id, n.title]));
  const found = new Map<number, Array<{ title: string; weight: number }>>();
  for (const edge of edges) {
    const sourceTitle = titles.get(edge.source);
    const targetTitle = titles.get(edge.target);
    if (sourceTitle == null || targetTitle == null) {
      continue;
    }
    found.set(edge.source, [
      ...(found.get(edge.source) ?? []),
      { title: targetTitle, weight: edge.weight },
    ]);
    found.set(edge.target, [
      ...(found.get(edge.target) ?? []),
      { title: sourceTitle, weight: edge.weight },
    ]);
  }
  return new Map(
    [...found].map(([id, list]) => [
      id,
      list.toSorted((x, y) => y.weight - x.weight).map((item) => item.title),
    ]),
  );
}

/** Returns what PlateBoard shows for `node`. The related graph shows similarity and no edit figures; the index graph shows views and edits. */
export function boardNodeFor(
  node: ConceptGraphNode,
  options: {
    variant: GraphVariant;
    editsUnavailable: boolean;
    neighbours: Map<number, string[]>;
    hrefSuffix: string;
  },
): PlateBoardNode {
  const related = options.variant === "related";
  return {
    title: node.title,
    description: node.description,
    figure: nodeFigure(node, options.variant),
    figureLabel: related ? "Similarity" : "Views",
    editsLastHour: related ? undefined : node.editsLastHour,
    editsMissing: related ? "not tracked" : undefined,
    editsUnavailable: options.editsUnavailable && !related,
    linkedTo: options.neighbours.get(node.id) ?? [],
    state: node.state,
    href: `/t/${node.slug}${options.hrefSuffix}`,
  };
}

/** Returns the clusters with two or more nodes. On the index graph only these carry a colour. */
export function groupedClusters(nodes: Array<{ cluster: number }>): Set<number> {
  const counts = new Map<number, number>();
  for (const node of nodes) {
    counts.set(node.cluster, (counts.get(node.cluster) ?? 0) + 1);
  }
  return new Set([...counts].filter(([, n]) => n > 1).map(([cluster]) => cluster));
}
