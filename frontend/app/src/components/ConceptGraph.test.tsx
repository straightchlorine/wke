import { createRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { PlateSlotsContext } from "../lib/plateSlots";
import {
  ConceptGraph,
  type ConceptGraphHandle,
  type ConceptGraphNode,
  type ConceptGraphProps,
} from "./ConceptGraph";

const nodes: ConceptGraphNode[] = [1, 2, 3, 4, 5].map((id) => ({
  id,
  title: `Article ${id}`,
  slug: `Article_${id}`,
  views: 1000 * (6 - id),
  editsLastHour: id,
  state: "ready",
}));
// Articles 1 to 3 form one linked group; 4 and 5 stand alone.
const edges = [
  { source: 1, target: 2, weight: 0.8 },
  { source: 2, target: 3, weight: 0.5 },
];

function draw(over: Partial<ConceptGraphProps> = {}) {
  const onOpen = vi.fn();
  const ref = createRef<ConceptGraphHandle>();
  const view = render(
    <ConceptGraph
      ref={ref}
      nodes={nodes}
      edges={edges}
      variant="index"
      width={774}
      height={710}
      onOpen={onOpen}
      hrefSuffix="?budget=8000"
      {...over}
    />,
  );
  return { ...view, onOpen, ref };
}

const node = (n: number) => screen.getByRole("button", { name: new RegExp(`^Article ${n},`) });
const board = () => document.querySelector("[data-plate-board]");
const ringCount = (container: HTMLElement) =>
  container.querySelectorAll("circle[fill='none'][stroke='var(--wke-stamp)']").length;

/** The smallest hit-circle radius in a drawn graph. */
const smallestHit = (container: HTMLElement) =>
  Math.min(
    ...[...container.querySelectorAll("circle[data-plate-hit]")].map((c) =>
      Number(c.getAttribute("r")),
    ),
  );

const live = () => document.getElementById("live-region")?.textContent;

function stubMedia(...matching: string[]) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: matching.includes(query),
      addEventListener: () => {},
      removeEventListener: () => {},
    })),
  );
}

describe("ConceptGraph", () => {
  beforeEach(() => {
    const region = document.createElement("div");
    region.id = "live-region";
    document.body.append(region);
  });

  afterEach(() => {
    document.getElementById("live-region")?.remove();
    vi.restoreAllMocks();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("draws a link to the dossier for each node, and names the graph for its variant", () => {
    draw();
    expect(screen.getAllByRole("button", { name: /^Article \d,/ })).toHaveLength(5);
    expect(node(2).getAttribute("href")).toBe("/t/Article_2?budget=8000");
    expect(screen.getByRole("group", { name: "Plate 1: concept graph" })).toBeTruthy();
  });

  it("uses the given accessible name and the related variant's default", () => {
    const { unmount } = draw({ ariaLabel: "Linked articles" });
    expect(screen.getByRole("group", { name: "Linked articles" })).toBeTruthy();
    unmount();
    draw({ variant: "related" });
    expect(screen.getByRole("group", { name: "Plate 2: concept graph" })).toBeTruthy();
  });

  it("colours only linked groups: a node with no partner is drawn neutral", () => {
    const { container } = draw();
    expect(container.querySelectorAll("circle[data-plate-cluster]")).toHaveLength(3);
    expect(container.querySelectorAll("circle[data-plate-neutral]")).toHaveLength(2);
    expect(container.querySelectorAll("path[data-plate-hull]")).toHaveLength(1);
  });

  it("selects a node on a click and opens its dossier on the second click", () => {
    const { onOpen } = draw();
    expect(board()?.getAttribute("data-plate-board")).toBe("idle");
    expect(fireEvent.click(node(2))).toBe(false);
    expect(node(2).getAttribute("aria-pressed")).toBe("true");
    expect(board()?.getAttribute("data-plate-board")).toBe("selected");
    expect(screen.getByText("Article 2", { selector: "p" })).toBeTruthy();
    expect(live()).toBe("Selected Article 2. Press Enter again to open.");
    expect(onOpen).not.toHaveBeenCalled();
    expect(fireEvent.click(node(2))).toBe(false);
    expect(onOpen).toHaveBeenCalledExactlyOnceWith(2);
    expect(node(2).getAttribute("aria-pressed")).toBe("true");
  });

  it("leaves a modified click to the browser", () => {
    const { onOpen } = draw();
    for (const modifier of [
      { ctrlKey: true },
      { metaKey: true },
      { shiftKey: true },
      { altKey: true },
      { button: 1 },
    ]) {
      expect(fireEvent.click(node(2), modifier)).toBe(true);
    }
    expect(node(2).getAttribute("aria-pressed")).toBe("false");
    expect(onOpen).not.toHaveBeenCalled();
  });

  it("selects on Space, then opens on the next Space, as a button does", () => {
    const { onOpen } = draw();
    expect(fireEvent.keyDown(node(3), { key: " " })).toBe(false);
    expect(node(3).getAttribute("aria-pressed")).toBe("true");
    expect(onOpen).not.toHaveBeenCalled();
    fireEvent.keyDown(node(3), { key: " " });
    expect(onOpen).toHaveBeenCalledExactlyOnceWith(3);
  });

  it("clears the selection on Escape and on a click that lands on no node", () => {
    const { container } = draw();
    fireEvent.click(node(1));
    fireEvent.keyDown(node(1), { key: "Escape" });
    expect(node(1).getAttribute("aria-pressed")).toBe("false");
    expect(live()).toBe("Selection cleared");
    fireEvent.click(node(1));
    fireEvent.click(container.querySelector("svg")!);
    expect(node(1).getAttribute("aria-pressed")).toBe("false");
  });

  it("says nothing for a click on the background when nothing is selected", () => {
    const { container } = draw();
    fireEvent.click(container.querySelector("svg")!);
    expect(live()).toBe("");
  });

  it("brings focus back from PlateBoard on Escape when it sits in a slot outside the graph", () => {
    const slot = document.createElement("div");
    document.body.append(slot);
    render(
      <PlateSlotsContext value={{ board: slot, legend: null }}>
        <ConceptGraph
          nodes={nodes}
          edges={edges}
          variant="index"
          width={774}
          height={710}
          onOpen={() => {}}
        />
      </PlateSlotsContext>,
    );
    fireEvent.click(node(1));
    const link = screen.getByRole("link", { name: /Open dossier/ });
    act(() => link.focus());
    fireEvent.keyDown(link, { key: "Escape" });
    expect(document.activeElement).toBe(node(1));
    expect(node(1).getAttribute("aria-pressed")).toBe("false");
    slot.remove();
  });

  it("moves focus along the nodes in the caller's order with the arrow keys and drops the selection", () => {
    draw();
    expect(node(1).tabIndex).toBe(0);
    expect(node(2).tabIndex).toBe(-1);
    fireEvent.click(node(1));
    act(() => node(1).focus());
    fireEvent.keyDown(node(1), { key: "ArrowRight" });
    expect(document.activeElement).toBe(node(2));
    expect(node(2).tabIndex).toBe(0);
    expect(node(1).getAttribute("aria-pressed")).toBe("false");
    fireEvent.keyDown(node(2), { key: "End" });
    expect(document.activeElement).toBe(node(5));
  });

  it("shows the node under the pointer in PlateBoard as a preview, and ignores a touch", () => {
    draw();
    fireEvent.pointerEnter(node(4), { pointerType: "mouse" });
    expect(board()?.getAttribute("data-plate-board")).toBe("preview");
    expect(document.querySelector("circle[data-plate-hover-ring]")).not.toBeNull();
    fireEvent.pointerLeave(node(4), { pointerType: "mouse" });
    expect(board()?.getAttribute("data-plate-board")).toBe("idle");
    fireEvent.pointerEnter(node(4), { pointerType: "touch" });
    expect(board()?.getAttribute("data-plate-board")).toBe("idle");
  });

  it("keeps the pointer on the node it is over when it leaves another one", () => {
    draw();
    fireEvent.pointerEnter(node(4), { pointerType: "mouse" });
    fireEvent.pointerEnter(node(5), { pointerType: "mouse" });
    fireEvent.pointerLeave(node(4), { pointerType: "mouse" });
    expect(screen.getByText("Article 5", { selector: "p" })).toBeTruthy();
  });

  it("shows the selected node in PlateBoard, not the one under the pointer, and gives it no hover ring", () => {
    draw();
    fireEvent.click(node(2));
    fireEvent.pointerEnter(node(4), { pointerType: "mouse" });
    expect(screen.getByText("Article 2", { selector: "p" })).toBeTruthy();
    expect(board()?.getAttribute("data-plate-board")).toBe("selected");
    expect(document.querySelectorAll("circle[data-plate-hover-ring]")).toHaveLength(1);
    fireEvent.pointerLeave(node(4), { pointerType: "mouse" });
    fireEvent.pointerEnter(node(2), { pointerType: "mouse" });
    expect(document.querySelector("circle[data-plate-hover-ring]")).toBeNull();
  });

  it("emphasises the name of the selected node, not of the one under the pointer", () => {
    const { container } = draw();
    const weight = (n: number) =>
      container
        .querySelector(`a[href='/t/Article_${n}?budget=8000'] text`)
        ?.getAttribute("font-weight");
    expect(weight(2)).toBe("400");
    fireEvent.pointerEnter(node(4), { pointerType: "mouse" });
    expect(weight(4)).toBe("500");
    fireEvent.click(node(2));
    expect(weight(2)).toBe("500");
    expect(weight(4)).toBe("400");
  });

  it("shows a ring for keyboard focus but not for focus that came from a pointer", () => {
    draw();
    act(() => node(1).focus());
    expect(document.querySelector("circle[data-plate-hover-ring]")).toBeNull();
    Object.defineProperty(node(2), "matches", {
      value: (selector: string) => selector === ":focus-visible",
    });
    act(() => node(2).focus());
    expect(document.querySelector("circle[data-plate-hover-ring]")).not.toBeNull();
    expect(board()?.getAttribute("data-plate-board")).toBe("preview");
  });

  it("drops the focus outline for a node a pointer pressed, until a key is pressed", () => {
    draw();
    expect(node(1).getAttribute("class")).not.toContain("outline-none");
    fireEvent.pointerDown(node(1));
    expect(node(1).getAttribute("class")).toContain("outline-none");
    fireEvent.keyDown(node(1), { key: "Tab" });
    expect(node(1).getAttribute("class")).not.toContain("outline-none");
  });

  it("names a node that has no permanent name while it is in play", () => {
    const many = Array.from({ length: 40 }, (_, i) => ({
      id: i + 1,
      title: `Many ${i + 1}`,
      slug: `M${i + 1}`,
      views: 1000 - i,
    }));
    const { container } = draw({ nodes: many, edges: [], width: 390, height: 390 });
    const unnamed = [...container.querySelectorAll("a")].find(
      (a) => a.querySelector("[data-plate-label]") == null,
    );
    expect(unnamed).toBeDefined();
    expect(container.querySelector("[data-plate-name]")).toBeNull();
    fireEvent.pointerEnter(unnamed!, { pointerType: "mouse" });
    expect(container.querySelectorAll("[data-plate-name]")).toHaveLength(1);
  });

  it("puts PlateBoard in the plate's slot when there is one", () => {
    const slot = document.createElement("div");
    render(
      <PlateSlotsContext value={{ board: slot, legend: null }}>
        <ConceptGraph
          nodes={nodes}
          edges={edges}
          variant="index"
          width={774}
          height={710}
          onOpen={() => {}}
        />
      </PlateSlotsContext>,
    );
    expect(slot.querySelector("[data-plate-board]")).not.toBeNull();
    expect(document.body.querySelector("section[data-plate-board]")).toBeNull();
  });

  it("draws the group a legend swatch points at stronger, with its dots on the heavier stroke", () => {
    const plain = draw({ activeGroup: null });
    const cluster = Number(
      plain.container.querySelector("path[data-plate-hull]")?.getAttribute("data-plate-hull"),
    );
    expect(plain.container.querySelector("path[data-plate-hull-active]")).toBeNull();
    const plainOpacity = Number(
      plain.container.querySelector("path[data-plate-hull]")?.getAttribute("fill-opacity"),
    );
    plain.unmount();

    const active = draw({ activeGroup: cluster });
    const hull = active.container.querySelector("path[data-plate-hull-active]")!;
    expect(hull.getAttribute("data-plate-hull")).toBe(String(cluster));
    expect(hull.getAttribute("stroke-width")).toBe("1.5");
    expect(Number(hull.getAttribute("fill-opacity"))).toBeGreaterThan(plainOpacity);
    for (const dot of active.container.querySelectorAll("circle[data-plate-cluster]")) {
      expect(dot.getAttribute("stroke-width")).toBe("3");
    }
    for (const dot of active.container.querySelectorAll("circle[data-plate-neutral]")) {
      expect(dot.getAttribute("stroke-width")).toBe("1.5");
    }
    active.unmount();

    const other = draw({ activeGroup: cluster + 1 });
    expect(other.container.querySelector("path[data-plate-hull-active]")).toBeNull();
  });

  it("draws the heavier stroke on a node the page highlights", () => {
    const { container, ref } = draw();
    const dot = () => container.querySelector("a[href='/t/Article_4?budget=8000'] circle")!;
    expect(dot().getAttribute("stroke-width")).toBe("1.5");
    act(() => ref.current?.highlight(4));
    expect(dot().getAttribute("stroke-width")).toBe("3");
    act(() => ref.current?.highlight(null));
    expect(dot().getAttribute("stroke-width")).toBe("1.5");
  });

  it("never highlights a node that has no linked group, whichever group is pointed at", () => {
    for (const activeGroup of [0, 1, 2, 3, 4]) {
      const { container, unmount } = draw({ activeGroup });
      for (const dot of container.querySelectorAll("circle[data-plate-neutral]")) {
        expect(dot.getAttribute("stroke-width")).toBe("1.5");
      }
      unmount();
    }
  });

  it("draws every node of the related graph in a group colour, and hides the selected name that moves beside its dot", () => {
    const { container } = draw({ variant: "related", edges: [] });
    expect(container.querySelector("circle[data-plate-neutral]")).toBeNull();
    const label = (n: number) =>
      container.querySelector(`a[href='/t/Article_${n}?budget=8000'] text`);
    expect(label(2)?.getAttribute("visibility")).toBeNull();
    expect(container.querySelector("[data-plate-name-backing]")).toBeNull();
    fireEvent.click(node(2));
    expect(label(2)?.getAttribute("visibility")).toBe("hidden");
    expect(label(3)?.getAttribute("visibility")).toBeNull();
    expect(container.querySelectorAll("[data-plate-name-backing]")).toHaveLength(1);
    expect(container.querySelector("[data-plate-name]")?.textContent).toBe("Article 2");
  });

  it("keeps the selected node's own name in place on the index graph", () => {
    const { container } = draw();
    fireEvent.click(node(2));
    expect(
      container
        .querySelector("a[href='/t/Article_2?budget=8000'] text")
        ?.getAttribute("visibility"),
    ).toBeNull();
    expect(container.querySelector("[data-plate-name-backing]")).toBeNull();
  });

  it("gives a node a larger hit circle under a coarse pointer", () => {
    const fine = draw();
    expect(smallestHit(fine.container)).toBe(13);
    fine.unmount();
    stubMedia("(pointer: coarse)");
    expect(smallestHit(draw().container)).toBe(22);
  });

  it("draws larger nodes first, so a small node's hit area wins an overlap", () => {
    const { container } = draw();
    const radii = [...container.querySelectorAll("a")].map((a) =>
      Number(a.querySelector("circle")?.getAttribute("r")),
    );
    expect(new Set(radii).size).toBeGreaterThan(1);
    expect(radii).toEqual(radii.toSorted((a, b) => b - a));
  });

  it("fades in after the first frame, and does not animate under reduced motion", async () => {
    const { container, unmount } = draw();
    const svg = () => container.querySelector("svg")!;
    expect(svg().style.opacity).toBe("0");
    expect(svg().style.transition).toContain("opacity");
    await waitFor(() => expect(svg().style.opacity).toBe("1"));
    unmount();
    stubMedia("(prefers-reduced-motion: reduce)");
    expect(draw().container.querySelector("svg")?.style.transition).toBe("none");
  });

  describe("pings", () => {
    it("marks an edited node, rings it once, and counts a repeat ping without a second ring", () => {
      vi.useFakeTimers();
      const { container, ref } = draw();
      act(() => ref.current?.ping(4));
      expect(node(4).getAttribute("aria-label")).toContain("edited in the last minute");
      expect(ringCount(container)).toBe(2);
      expect(container.textContent).not.toContain("+");
      act(() => ref.current?.ping(4));
      expect(container.textContent).toContain("+1");
      act(() => ref.current?.ping(4));
      expect(ringCount(container)).toBe(2);
      expect(container.textContent).toContain("+2");
    });

    it("ignores a node that is not in the graph", () => {
      vi.useFakeTimers();
      const { container, ref } = draw();
      act(() => ref.current?.ping(99));
      expect(ringCount(container)).toBe(0);
      expect(container.textContent).not.toContain("edited");
    });

    it("marks without rings when asked for none, and the mark ends after a minute", () => {
      vi.useFakeTimers();
      const { container, ref } = draw();
      act(() => ref.current?.ping(4, false));
      expect(ringCount(container)).toBe(0);
      expect(node(4).getAttribute("aria-label")).toContain("edited");
      act(() => void vi.advanceTimersByTime(60_000));
      expect(node(4).getAttribute("aria-label")).not.toContain("edited");
    });

    it("leaves no timer running after the graph unmounts", () => {
      vi.useFakeTimers();
      const { ref, unmount } = draw();
      const before = vi.getTimerCount();
      act(() => {
        ref.current?.ping(4);
        ref.current?.ping(5);
      });
      expect(vi.getTimerCount()).toBeGreaterThan(before);
      unmount();
      expect(vi.getTimerCount()).toBe(0);
    });
  });

  it("says no figure for the seed of the related graph", () => {
    draw({
      variant: "related",
      nodes: nodes.map((n) =>
        n.id === 1 ? { ...n, role: "seed" as const, views: 1 } : { ...n, views: 0.5 },
      ),
    });
    expect(screen.getByRole("button", { name: "Article 1, press Enter to select" })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Article 2, similarity 0.50, press Enter to select" }),
    ).toBeTruthy();
  });
});
