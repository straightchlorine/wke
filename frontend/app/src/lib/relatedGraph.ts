import type { DossierView } from "../api/dossier";
import type { DossierListItem } from "../api/generated";
import type { DossierState } from "./dossierState";
import type { ConceptGraphNode } from "./graphNodeInfo";
import { slugify } from "./slug";

/** The part of a list of stored dossiers that says which topics have one. */
export interface StoredDossiers {
  items: readonly Pick<DossierListItem, "page_id">[];
  /** Null when the list holds every stored dossier. */
  next_cursor: string | null;
}

/**
 * Returns a function that says whether a topic has a stored dossier. A topic is "none" only when the
 * list is complete. Otherwise an unlisted topic's state is unknown, and undefined is returned.
 */
export function storedStateOf(
  list: StoredDossiers | undefined,
): (pageId: number) => DossierState | undefined {
  const stored = new Set((list?.items ?? []).map((item) => item.page_id));
  const complete = list != null && list.next_cursor == null;
  return (pageId) => (stored.has(pageId) ? "ready" : complete ? "none" : undefined);
}

/** Returns the dossier's related articles as graph nodes, sized by their similarity to the seed. */
export function relatedGraphNodes(
  dossier: DossierView,
  stateOf: (pageId: number) => DossierState | undefined,
): ConceptGraphNode[] {
  const { nodes, edges } = dossier.graph;
  const seedId = nodes.find((node) => node.role === "seed")?.id ?? null;
  return nodes.map((node) => {
    const seedEdge =
      seedId != null
        ? edges.find(
            (edge) =>
              (edge.source === seedId && edge.target === node.id) ||
              (edge.target === seedId && edge.source === node.id),
          )
        : undefined;
    return {
      id: node.id,
      title: node.title,
      slug: slugify(node.title),
      role: node.role,
      // A related node can have no edge to the seed, because the graph keeps only each node's most
      // similar neighbours. Its similarity is then unknown, so it is null rather than 0.
      views: node.role === "seed" ? 1 : (seedEdge?.weight ?? null),
      description: node.role === "seed" ? dossier.topic.description || undefined : undefined,
      state: stateOf(node.id),
    };
  });
}
