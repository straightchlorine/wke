import { describe, expect, it } from "vitest";
import type { ReactElement } from "react";
import { render } from "@testing-library/react";
import { HaloText } from "./HaloText";

function text(element: ReactElement) {
  const { container } = render(<svg>{element}</svg>);
  return container.querySelector("text")!;
}

describe("HaloText", () => {
  it("draws regular text in the second ink colour with an outline behind it", () => {
    const el = text(<HaloText>Name</HaloText>);
    expect(el.getAttribute("font-weight")).toBe("400");
    expect(el.getAttribute("fill")).toBe("var(--wke-ink-2)");
    expect(el.getAttribute("paint-order")).toBe("stroke");
    expect(el.getAttribute("stroke")).toBe("var(--wke-sheet)");
    expect(el.textContent).toBe("Name");
  });

  it("draws emphasised text heavier and in the full ink colour", () => {
    const el = text(<HaloText emphasised>Name</HaloText>);
    expect(el.getAttribute("font-weight")).toBe("500");
    expect(el.getAttribute("fill")).toBe("var(--wke-ink)");
  });

  it("passes other props to the text, and lets them replace the style", () => {
    const el = text(
      <HaloText x={12} data-plate-name="" fill="red" fontWeight={700}>
        n
      </HaloText>,
    );
    expect(el.getAttribute("x")).toBe("12");
    expect(el.hasAttribute("data-plate-name")).toBe(true);
    expect(el.getAttribute("fill")).toBe("red");
    expect(el.getAttribute("font-weight")).toBe("700");
  });
});
