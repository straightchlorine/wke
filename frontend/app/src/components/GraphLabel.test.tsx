import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { LABEL_LINE_HEIGHT, type LabelBox } from "../lib/labelGeometry";
import { GraphLabel, type GraphLabelProps } from "./GraphLabel";

const label: LabelBox = { id: 1, x: 100, y: 50, width: 90, height: 20, text: "Lizzie Borden" };

function draw(over: Partial<GraphLabelProps> = {}) {
  const { container } = render(
    <svg>
      <GraphLabel label={label} emphasised={false} hidden={false} {...over} />
    </svg>,
  );
  return {
    text: container.querySelector("text")!,
    line: container.querySelector("line"),
  };
}

describe("GraphLabel", () => {
  it("draws the name in a tspan of its own, at the label's text origin", () => {
    const { text, line } = draw();
    expect(text.querySelectorAll("tspan")).toHaveLength(1);
    expect(text.querySelector("tspan")?.textContent).toBe("Lizzie Borden");
    expect(text.getAttribute("x")).toBe("102");
    expect(text.getAttribute("y")).toBe("67");
    expect(text.getAttribute("text-anchor")).toBe("start");
    expect(text.getAttribute("data-plate-label")).toBe("");
    expect(text.querySelector("title")).toBeNull();
    expect(line).toBeNull();
  });

  it("draws an emphasised name heavier", () => {
    expect(draw({ emphasised: true }).text.getAttribute("font-weight")).toBe("500");
  });

  it("gives a cut name a title with the whole text, apart from the visible tspan", () => {
    const { text } = draw({ label: { ...label, text: "Lizzie...", fullText: "Lizzie Borden" } });
    expect(text.querySelector("title")?.textContent).toBe("Lizzie Borden");
    expect(text.querySelector("tspan")?.textContent).toBe("Lizzie...");
  });

  it("draws a name that stands away from its dot with a leader line", () => {
    const leader = { x1: 1, y1: 2, x2: 3, y2: 4 };
    const { text, line } = draw({ label: { ...label, leader } });
    expect(text.getAttribute("data-plate-label")).toBe("leader");
    expect(line?.getAttribute("x1")).toBe("1");
    expect(line?.getAttribute("y2")).toBe("4");
  });

  it("breaks a two-line name into two tspans on the same x and lifts it by a line", () => {
    const { text } = draw({
      label: {
        ...label,
        height: 20 + LABEL_LINE_HEIGHT,
        lines: ["Lizzie", "Borden"],
        textX: 150,
        textAnchor: "end",
      },
    });
    const [first, second] = [...text.querySelectorAll("tspan")];
    expect(first?.textContent).toBe("Lizzie");
    expect(second?.textContent).toBe("Borden");
    expect(first?.getAttribute("x")).toBe("150");
    expect(second?.getAttribute("x")).toBe("150");
    expect(second?.getAttribute("dy")).toBe(String(LABEL_LINE_HEIGHT));
    expect(text.getAttribute("text-anchor")).toBe("end");
    expect(text.getAttribute("y")).toBe("67");
  });

  it("hides the name and its leader line without removing them", () => {
    const { text, line } = draw({
      hidden: true,
      label: { ...label, leader: { x1: 1, y1: 2, x2: 3, y2: 4 } },
    });
    expect(text.getAttribute("visibility")).toBe("hidden");
    expect(line?.getAttribute("visibility")).toBe("hidden");
  });

  it("marks a name that was placed by relaxing a rule", () => {
    expect(draw({ label: { ...label, relaxed: 2 } }).text.getAttribute("data-label-relaxed")).toBe(
      "2",
    );
    expect(draw().text.hasAttribute("data-label-relaxed")).toBe(false);
  });
});
