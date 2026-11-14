import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import type { ConceptGraphEdge, ConceptGraphNode } from "../graphNodeInfo";
import { legendChipSize } from "../plateLegend";
import { useGraphLayout } from "./useGraphLayout";

const labelLayout = vi.hoisted(() => ({
  calls: [] as Array<{ fontsReady: boolean; edges: unknown }>,
}));
vi.mock("../labelLayout", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../labelLayout")>();
  return {
    ...actual,
    computeLabelPlacements: (...args: Parameters<typeof actual.computeLabelPlacements>) => {
      labelLayout.calls.push({ fontsReady: args[2].fontsReady === true, edges: args[2].edges });
      return actual.computeLabelPlacements(...args);
    },
  };
});

const nodes: ConceptGraphNode[] = [1, 2, 3, 4, 5].map((id) => ({
  id,
  title: `Article ${id}`,
  slug: `Article_${id}`,
  views: 1000 * (6 - id),
}));
const edges: ConceptGraphEdge[] = [
  { source: 1, target: 2, weight: 0.8 },
  { source: 2, target: 3, weight: 0.5 },
];

const frame = {
  nodes,
  edges,
  variant: "index",
  width: 774,
  height: 710,
  legendSize: null,
} as const;

describe("useGraphLayout", () => {
  afterEach(() => {
    labelLayout.calls.length = 0;
    vi.unstubAllGlobals();
    Reflect.deleteProperty(document, "fonts");
  });

  it("lays out every node and decides every node's name", () => {
    const { result } = renderHook(() => useGraphLayout(frame));
    expect(result.current.layout.nodes.map((n) => n.id).toSorted((a, b) => a - b)).toEqual([
      1, 2, 3, 4, 5,
    ]);
    expect([...result.current.labelPlacements.keys()].toSorted((a, b) => a - b)).toEqual([
      1, 2, 3, 4, 5,
    ]);
    expect(result.current.graphEdges).toEqual(edges);
    expect(result.current.layout.nodes.every((n) => n.x >= 0 && n.x <= 774)).toBe(true);
  });

  it("hands the drawn edges to the name placement, so a name keeps off them", () => {
    renderHook(() => useGraphLayout(frame));
    expect(labelLayout.calls.at(-1)?.edges).toEqual(edges);
  });

  it("keeps names off the legend chip when there is one", () => {
    const legendSize = legendChipSize(3, false);
    const withLegend = renderHook(() => useGraphLayout({ ...frame, legendSize })).result.current;
    const without = renderHook(() => useGraphLayout(frame)).result.current;
    expect(withLegend.reservedBoxes.length).toBe(without.reservedBoxes.length + 1);
  });

  it("reserves the stats chip and allows longer names once the viewport is wide enough for it", () => {
    const narrow = renderHook(() => useGraphLayout(frame)).result.current;
    vi.stubGlobal(
      "matchMedia",
      vi.fn((query: string) => ({
        matches: query === "(min-width: 600px)",
        addEventListener: () => {},
        removeEventListener: () => {},
      })),
    );
    const wide = renderHook(() => useGraphLayout(frame)).result.current;
    expect(narrow.reservedBoxes).toHaveLength(0);
    expect(wide.reservedBoxes).toHaveLength(1);
    expect(wide.nameChars).toBeGreaterThan(narrow.nameChars);
  });

  it("places names again once the page font has loaded", async () => {
    let loaded!: () => void;
    const ready = new Promise<void>((resolve) => {
      loaded = resolve;
    });
    Object.defineProperty(document, "fonts", {
      configurable: true,
      value: { status: "loading", ready },
    });
    renderHook(() => useGraphLayout(frame));
    expect(labelLayout.calls.at(-1)?.fontsReady).toBe(false);
    await act(async () => {
      loaded();
      await ready;
    });
    expect(labelLayout.calls.at(-1)?.fontsReady).toBe(true);
  });
});
