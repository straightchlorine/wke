import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { GraphNodeMark, type GraphNodeMarkProps } from "./GraphNodeMark";

const base: GraphNodeMarkProps = {
  node: { x: 100, y: 80, radius: 8, cluster: 1 },
  pinged: false,
  seed: false,
  neutral: false,
  highlighted: false,
  selected: false,
  ringed: false,
  hitRadius: 13,
  ringIds: [],
  reducedMotion: false,
};

function draw(over: Partial<GraphNodeMarkProps> = {}) {
  const { container } = render(
    <svg>
      <GraphNodeMark {...base} {...over} />
    </svg>,
  );
  return container;
}

describe("GraphNodeMark", () => {
  it("draws a grouped node in its group's colour", () => {
    const dot = draw().querySelector("circle[data-plate-cluster]")!;
    expect(dot.getAttribute("data-plate-cluster")).toBe("1");
    expect(dot.getAttribute("stroke")).toBe("var(--wke-c2)");
    expect(dot.getAttribute("fill")).toBe("var(--wke-c2)");
    expect(dot.getAttribute("r")).toBe("8");
  });

  it("draws a node with no linked group neutral, with no group colour", () => {
    const c = draw({ neutral: true });
    expect(c.querySelector("circle[data-plate-neutral]")?.getAttribute("fill")).toBe(
      "var(--wke-paper)",
    );
    expect(c.querySelector("[data-plate-cluster]")).toBeNull();
  });

  it("draws the seed as a filled ink dot", () => {
    const dot = draw({ seed: true }).querySelector("circle")!;
    expect(dot.getAttribute("fill")).toBe("var(--wke-ink)");
    expect(dot.hasAttribute("data-plate-cluster")).toBe(false);
  });

  it("draws an edited node in the stamp colour, even when it is the seed", () => {
    const dot = draw({ pinged: true, seed: true }).querySelector("circle")!;
    expect(dot.getAttribute("stroke")).toBe("var(--wke-stamp)");
    expect(dot.getAttribute("fill")).toBe("var(--wke-stamp-wash)");
  });

  it.each([
    ["grouped", {}, "1.5", "3"],
    ["seed", { seed: true }, "1.5", "3"],
    ["edited", { pinged: true }, "2.5", "4"],
  ] as const)(
    "draws a %s node with a heavier stroke when highlighted",
    (_name, over, plain, heavy) => {
      expect(draw(over).querySelector("circle")?.getAttribute("stroke-width")).toBe(plain);
      expect(
        draw({ ...over, highlighted: true })
          .querySelector("circle")
          ?.getAttribute("stroke-width"),
      ).toBe(heavy);
    },
  );

  it("gives a small node a hit circle of the hit radius and a large node one of its own radius", () => {
    const small = draw({ hitRadius: 22 }).querySelector("circle[data-plate-hit]");
    expect(small?.getAttribute("r")).toBe("22");
    const large = draw({ node: { ...base.node, radius: 30 } }).querySelector(
      "circle[data-plate-hit]",
    );
    expect(large?.getAttribute("r")).toBe("30");
  });

  it("draws a selection box around a selected node and a ring around a hovered one", () => {
    const c = draw({ selected: true, ringed: true });
    const box = c.querySelector("rect[data-plate-ring]")!;
    expect(box.getAttribute("x")).toBe("88");
    expect(box.getAttribute("width")).toBe("24");
    expect(c.querySelector("circle[data-plate-hover-ring]")?.getAttribute("r")).toBe("11.75");
  });

  it("draws neither when the node is neither selected nor ringed", () => {
    const c = draw();
    expect(c.querySelector("[data-plate-ring]")).toBeNull();
    expect(c.querySelector("[data-plate-hover-ring]")).toBeNull();
  });

  it("draws two animated rings per ping, the second one delayed, only while the node is edited", () => {
    const rings = draw({ pinged: true, ringIds: ["1-1"] }).querySelectorAll<SVGCircleElement>(
      "circle[fill='none']",
    );
    expect(rings).toHaveLength(2);
    expect(rings[0]?.getAttribute("class")).toContain("animate-");
    expect(rings[0]?.style.animationDelay).toBe("");
    expect(rings[1]?.style.animationDelay).toBe("450ms");
    expect(draw({ ringIds: ["1-1"] }).querySelectorAll("circle[fill='none']")).toHaveLength(0);
    expect(
      draw({ pinged: true, ringIds: ["1-1", "1-2"] }).querySelectorAll("circle[fill='none']"),
    ).toHaveLength(4);
  });

  it("draws the rings still and enlarged under reduced motion", () => {
    const rings = draw({
      pinged: true,
      ringIds: ["1-1"],
      reducedMotion: true,
    }).querySelectorAll<SVGCircleElement>("circle[fill='none']");
    expect(rings).toHaveLength(2);
    for (const ring of rings) {
      expect(ring.getAttribute("class")).toBe("");
      expect(ring.style.transform).toBe("scale(1.8)");
      expect(ring.style.animationDelay).toBe("");
    }
  });
});
