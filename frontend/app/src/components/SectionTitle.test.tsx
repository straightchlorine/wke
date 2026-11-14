import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { SectionTitle } from "./SectionTitle";

describe("SectionTitle", () => {
  it("is an h2 by default and an h3 at level 3", () => {
    const { rerender } = render(<SectionTitle>Contents</SectionTitle>);
    expect(screen.getByRole("heading", { level: 2, name: "Contents" })).toBeTruthy();

    rerender(<SectionTitle level={3}>Contents</SectionTitle>);
    expect(screen.getByRole("heading", { level: 3, name: "Contents" })).toBeTruthy();
  });

  it("shows the count and the sub line only when given", () => {
    const { container, rerender } = render(<SectionTitle>Contents</SectionTitle>);
    expect(container.textContent).toBe("Contents");

    rerender(
      <SectionTitle count="12" sub="Every section.">
        Contents
      </SectionTitle>,
    );
    expect(screen.getByText("12")).toBeTruthy();
    expect(screen.getByText("Every section.")).toBeTruthy();
    expect(screen.getByRole("heading").textContent).toBe("Contents");
  });
});
