import { useEffect, useMemo, useState } from "react";
import { computeLayout, type GraphEdge, type GraphNode } from "../graphLayout";
import type { ConceptGraphEdge, ConceptGraphNode, GraphVariant } from "../graphNodeInfo";
import { computeLabelPlacements } from "../labelLayout";
import type { LegendSize } from "../plateLegend";
import { guaranteedNameIds, plateLayoutOptions } from "../plateLayoutOptions";
import { useMediaQuery } from "./useMediaQuery";

/**
 * Lays out the graph's dots and group outlines and decides which dots get a permanent name.
 *
 * The result depends on the viewport as well as the frame: whether the stats chip floats over the
 * frame, and whether the desktop layout applies. Names are measured with the real font, so they
 * are placed again once it has loaded.
 */
export function useGraphLayout(input: {
  nodes: ConceptGraphNode[];
  edges: ConceptGraphEdge[];
  variant: GraphVariant;
  /** The drawing area's size in CSS px. */
  width: number;
  height: number;
  compact?: boolean;
  squareFrame?: boolean;
  /** The size of the legend chip drawn over the frame, or null when there is none. */
  legendSize: LegendSize | null;
}) {
  const { nodes, edges, variant, width, height, compact, squareFrame, legendSize } = input;
  const graphNodes: GraphNode[] = useMemo(
    () => nodes.map((n) => ({ id: n.id, title: n.title, views: n.views })),
    [nodes],
  );
  const graphEdges: GraphEdge[] = useMemo(
    () => edges.map((e) => ({ source: e.source, target: e.target, weight: e.weight })),
    [edges],
  );
  const chipOverlaysFrame = useMediaQuery("(min-width: 600px)");
  const underDesktop = useMediaQuery("(max-width: 1279px)");
  const plate = useMemo(
    () =>
      plateLayoutOptions({
        variant,
        width,
        height,
        compact,
        squareFrame,
        chipOverlaysFrame,
        underDesktop,
        legendSize,
      }),
    [variant, width, height, compact, squareFrame, chipOverlaysFrame, underDesktop, legendSize],
  );
  const layout = useMemo(
    () => computeLayout(graphNodes, graphEdges, plate.layout),
    [graphNodes, graphEdges, plate.layout],
  );
  const [fontsReady, setFontsReady] = useState(
    () => typeof document === "undefined" || document.fonts?.status !== "loading",
  );
  useEffect(() => {
    if (!fontsReady) {
      void document.fonts.ready.then(() => setFontsReady(true));
    }
  }, [fontsReady]);
  // The permanent names never depend on hover, focus, selection or a recent edit: those only
  // restyle a name that is already there, or name one more dot beside its own.
  const labelPlacements = useMemo(
    () =>
      computeLabelPlacements(layout.nodes, layout.hulls, {
        ...plate.labels,
        alwaysShowIds: guaranteedNameIds(variant, nodes),
        edges: graphEdges,
        fontsReady,
      }),
    [layout, plate.labels, variant, nodes, graphEdges, fontsReady],
  );

  return {
    layout,
    labelPlacements,
    /** The boxes names keep clear of, such as the stats chip and the legend chip. */
    reservedBoxes: plate.labels.reservedBoxes,
    /** The longest name, in characters, of a dot that has no permanent label. */
    nameChars: plate.nameChars,
    graphEdges,
  };
}
