import type { TrendingSnapshot } from "../api/generated";
import { computeComponents } from "./graphLayout";
import type { ConceptGraphEdge, ConceptGraphNode } from "./graphNodeInfo";
import { slugify } from "./slug";

/** Returns the graph nodes of a trending snapshot, one per topic. */
export function toGraphNodes(topics: TrendingSnapshot["topics"]): ConceptGraphNode[] {
  return topics.map((topic) => ({
    id: topic.page_id,
    title: topic.title,
    slug: slugify(topic.title),
    views: topic.views,
    description: topic.description,
    editsLastHour: topic.edits_last_hour,
    state: topic.dossier_state,
  }));
}

/** One linked group of the graph, labelled by its most-read member. */
export interface ColorKeyGroup {
  /** The group's colour index. */
  cluster: number;
  /** The most-read member's title. */
  name: string;
  state: ConceptGraphNode["state"];
}

/** Returns one entry per group of two or more linked articles, in the order the graph paints their colours. */
export function colorKeyGroups(
  nodes: ConceptGraphNode[],
  edges: ConceptGraphEdge[],
): ColorKeyGroup[] {
  const groupOf = computeComponents(nodes, edges);
  const top = new Map<number, ColorKeyGroup & { views: number; size: number }>();
  for (const node of nodes) {
    const cluster = groupOf.get(node.id);
    if (cluster == null) {
      continue;
    }
    const entry = top.get(cluster);
    const views = node.views ?? 0;
    if (entry == null) {
      top.set(cluster, { cluster, name: node.title, state: node.state, views, size: 1 });
    } else {
      entry.size += 1;
      if (views > entry.views) {
        entry.name = node.title;
        entry.state = node.state;
        entry.views = views;
      }
    }
  }
  return [...top.values()]
    .toSorted((a, b) => a.cluster - b.cluster)
    .filter((entry) => entry.size > 1)
    .map(({ cluster, name, state }) => ({ cluster, name, state }));
}
