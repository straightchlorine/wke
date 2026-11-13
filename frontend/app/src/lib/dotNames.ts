import type { LaidOutNode } from "./graphLayout";
import type { GraphVariant } from "./graphNodeInfo";
import { placeDotName, type LabelBox } from "./labelGeometry";

/** A name drawn beside its dot. `backed` names get a backing in the frame colour. */
export interface DotName {
  box: LabelBox;
  backed: boolean;
}

/**
 * Returns the names to draw beside the dots in `ids`, the dots in play at the moment, such as the
 * selected, hovered, focused or just-edited ones.
 *
 * A dot that already has a permanent label gets no second name, except the selected dot of the
 * related graph, whose name moves beside the dot and gets a backing. A name avoids the permanent
 * labels and the reserved boxes, and never moves one.
 */
export function dotNamesFor(
  ids: Array<number | null>,
  context: {
    variant: GraphVariant;
    selectedId: number | null;
    nodes: LaidOutNode[];
    labelPlacements: Map<number, LabelBox | null>;
    reservedBoxes: LabelBox[];
    width: number;
    height: number;
    ellipsisChars: number;
  },
): Map<number, DotName> {
  const { variant, selectedId, nodes, labelPlacements, reservedBoxes } = context;
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const taken: LabelBox[] = [
    ...reservedBoxes,
    ...[...labelPlacements.values()].filter((box): box is LabelBox => box != null),
  ];
  const names = new Map<number, DotName>();
  for (const id of ids) {
    const node = id == null ? undefined : byId.get(id);
    if (id == null || node == null) {
      continue;
    }
    const backed = variant === "related" && id === selectedId;
    if (labelPlacements.get(id) != null && !backed) {
      continue;
    }
    names.set(id, {
      box: placeDotName(node, taken, nodes, {
        width: context.width,
        height: context.height,
        ellipsisChars: context.ellipsisChars,
      }),
      backed,
    });
  }
  return names;
}
