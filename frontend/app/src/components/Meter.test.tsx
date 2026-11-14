import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Meter } from "./Meter";

describe("Meter", () => {
  it("names the native meter with the label and shows the label and info", () => {
    render(<Meter label="6 of 8 sections at 8k" fraction={0.75} info={<i>detail</i>} />);
    const meter = screen.getByRole("meter", { name: "6 of 8 sections at 8k" });
    expect(meter.getAttribute("value")).toBe("0.75");
    expect(screen.getByText("6 of 8 sections at 8k")).toBeTruthy();
    expect(screen.getByText("detail")).toBeTruthy();
  });

  it.each([
    [-0.5, "0", "0%"],
    [0.25, "0.25", "25%"],
    [3, "1", "100%"],
  ])("clamps a fraction of %f to the range 0 to 1", (fraction, value, width) => {
    const { container } = render(<Meter label="x" fraction={fraction} />);
    expect(screen.getByRole("meter").getAttribute("value")).toBe(value);
    expect(container.querySelector<HTMLElement>("[style]")?.style.width).toBe(width);
  });
});
