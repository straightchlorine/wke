import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { DossierStateChip, FreshnessChip, type DossierState } from "./Chip";

describe("DossierStateChip", () => {
  it.each<[DossierState, boolean, string | null]>([
    ["ready", false, "Ready"],
    ["partial", false, "Partial"],
    ["building", false, "Building"],
    ["none", false, null],
    ["none", true, "Not built"],
    ["ready", true, "Ready"],
  ])("renders %s (showNone %s) as %s", (state, showNone, text) => {
    const { container } = render(<DossierStateChip state={state} showNone={showNone} />);
    if (text === null) {
      expect(container.firstChild).toBeNull();
    } else {
      expect(screen.getByText(text)).toBeTruthy();
    }
  });

  it("passes className to the chip", () => {
    render(<DossierStateChip state="ready" className="w-19" />);
    expect(screen.getByText("Ready").className).toContain("w-19");
  });
});

describe("FreshnessChip", () => {
  it("shows the current label when fresh", () => {
    render(<FreshnessChip state="fresh" />);
    expect(screen.getByText("Up to date")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("sets the quiet Not checked chip in ink-3 with a hairline, and leaves the other states alone", () => {
    const { rerender } = render(<FreshnessChip state="unknown" showInfo={false} quiet />);
    expect(screen.getByText("Not checked").className).toMatch(/text-ink-3.*border-rule\b/);
    rerender(<FreshnessChip state="fresh" quiet />);
    expect(screen.getByText("Up to date").className).not.toMatch(/text-ink-3/);
  });

  it("sets the chip at control height only when asked", () => {
    const { rerender } = render(<FreshnessChip state="fresh" />);
    expect(screen.getByText("Up to date").className).not.toContain("h-(--control-h)");
    rerender(<FreshnessChip state="fresh" control />);
    expect(screen.getByText("Up to date").className).toContain("h-(--control-h)");
  });

  it("hides ' since built' on a narrow screen only when shortOnPhone is set", () => {
    const { container, rerender } = render(<FreshnessChip state="stale" editsSincePin={2} />);
    expect(screen.getByText("Out of date: 2 edits since built")).toBeTruthy();
    expect(container.querySelector(".max-md\\:hidden")).toBeNull();

    rerender(<FreshnessChip state="stale" editsSincePin={2} shortOnPhone />);
    expect(container.querySelector(".max-md\\:hidden")?.textContent).toBe(" since built");
    expect(container.textContent).toBe("Out of date: 2 edits since built");
  });

  it("keeps the whole label on a narrow screen when it has no ' since built' tail", () => {
    const { container } = render(<FreshnessChip state="stale" editsSincePin={null} shortOnPhone />);
    expect(screen.getByText("Out of date: newer revision")).toBeTruthy();
    expect(container.querySelector(".max-md\\:hidden")).toBeNull();
  });

  it("uses a custom current label when fresh", () => {
    render(<FreshnessChip state="fresh" currentLabel="Current" />);
    expect(screen.getByText("Current")).toBeTruthy();
  });

  it.each<[number | null, string]>([
    [null, "Out of date: newer revision"],
    [0, "Out of date: newer revision"],
    [1, "Out of date: 1 edit since built"],
    [2, "Out of date: 2 edits since built"],
    [1234, "Out of date: 1,234 edits since built"],
  ])("labels stale with %s edits since the pin", (edits, text) => {
    render(<FreshnessChip state="stale" editsSincePin={edits} />);
    expect(screen.getByText(text)).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("makes the whole Not checked chip the tooltip trigger, with the (i) inside it", () => {
    render(<FreshnessChip state="unknown" />);
    const chip = screen.getByRole("button", { name: "Not checked" });
    expect(chip.textContent).toBe("Not checkedi");
    expect(chip.querySelector("span[aria-hidden]")).not.toBeNull();
    expect(chip.parentElement?.querySelectorAll("button")).toHaveLength(1);
  });

  it("carries an explanation on any state when `info` is given", () => {
    render(<FreshnessChip state="fresh" info="Checked 30 Sep." />);
    expect(screen.getByRole("button", { name: "Up to date" })).toBeTruthy();
    expect(screen.getByRole("tooltip", { hidden: true }).textContent).toBe("Checked 30 Sep.");
  });

  it("omits the (i) when showInfo is false", () => {
    render(<FreshnessChip state="unknown" showInfo={false} />);
    expect(screen.getByText("Not checked")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("puts a custom unknownText in the tooltip", () => {
    render(<FreshnessChip state="unknown" unknownText="The edit feed is down." />);
    expect(screen.getByRole("tooltip", { hidden: true }).textContent).toBe(
      "The edit feed is down.",
    );
  });
});
