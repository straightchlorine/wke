import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Record } from "./Record";

describe("Record", () => {
  it("is a named group only when given a label", () => {
    const { rerender } = render(<Record rows={[{ label: "Model", value: "MiniLM" }]} />);
    expect(screen.queryByRole("group")).toBeNull();

    rerender(<Record label="Build facts" rows={[{ label: "Model", value: "MiniLM" }]} />);
    expect(screen.getByRole("group", { name: "Build facts" })).toBeTruthy();
  });

  it("renders each row's label, value and second fact, then the footer", () => {
    render(
      <Record
        rows={[
          { label: "Model", value: "MiniLM", size: "normal" },
          { label: "Built", value: "12", sub: "today" },
        ]}
        footer={<a href="/x">More</a>}
      />,
    );
    expect(screen.getAllByText(/Model|Built/).map((el) => el.textContent)).toEqual([
      "Model",
      "Built",
    ]);
    expect(screen.getByText("MiniLM")).toBeTruthy();
    expect(screen.getByText("today")).toBeTruthy();
    expect(screen.getByRole("link", { name: "More" })).toBeTruthy();
  });

  it("shows a string value as its own title unless a title is given", () => {
    render(
      <Record
        rows={[
          { label: "A", value: "plain", size: "normal" },
          { label: "B", value: <b>node</b>, size: "normal" },
          { label: "C", value: "short", title: "the full value", size: "normal" },
        ]}
      />,
    );
    expect(screen.getByText("plain").title).toBe("plain");
    expect(screen.getByText("node").parentElement?.title).toBe("");
    expect(screen.getByText("short").title).toBe("the full value");
  });

  it("draws the dotted leader unless leader is false", () => {
    const { container } = render(
      <Record
        rows={[
          { label: "A", value: "1" },
          { label: "B", value: "2", leader: false },
        ]}
      />,
    );
    const rows = container.querySelectorAll("[data-record-row]");
    expect(rows[0]?.querySelector("[aria-hidden='true']")).not.toBeNull();
    expect(rows[1]?.querySelector("[aria-hidden='true']")).toBeNull();
  });

  it("lines mode keeps the second fact under the value and shows `below` after it", () => {
    const { container } = render(
      <Record
        lines
        rows={[
          { label: "Built", value: "12", sub: "today", below: <button type="button">Open</button> },
        ]}
      />,
    );
    const sub = container.querySelector("[data-record-sub]");
    expect(sub?.textContent).toBe("today");
    expect(sub?.nextElementSibling?.textContent).toBe("Open");
    expect(container.querySelector("[data-record-row]")?.textContent).not.toContain("today");
  });

  it("puts the second fact on its own line with subBlock", () => {
    render(<Record rows={[{ label: "URL", value: "x", sub: "copy", subBlock: true }]} />);
    expect(screen.getByText("copy").className).toContain("basis-full");
  });
});
