import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Pause } from "./PauseButton";

describe("Pause", () => {
  it.each([
    [false, "Pause"],
    [true, "Resume"],
  ])("labels the button for paused=%s as %s", (paused, label) => {
    render(<Pause paused={paused} onToggle={() => {}} />);
    expect(screen.getByRole("button", { name: label }).getAttribute("aria-pressed")).toBeNull();
  });

  it("toggles on click and shows its title", () => {
    const onToggle = vi.fn();
    render(<Pause paused onToggle={onToggle} title="12 edits arrived while paused" />);
    const button = screen.getByRole("button", { name: "Resume" });
    fireEvent.click(button);
    expect(onToggle).toHaveBeenCalledTimes(1);
    expect(button.title).toBe("12 edits arrived while paused");
  });

  it("ignores clicks but stays focusable while disabled", () => {
    const onToggle = vi.fn();
    render(<Pause paused={false} onToggle={onToggle} disabled />);
    const button = screen.getByRole("button", { name: "Pause" });
    expect(button.getAttribute("aria-disabled")).toBe("true");
    expect(button.hasAttribute("disabled")).toBe(false);
    fireEvent.click(button);
    expect(onToggle).not.toHaveBeenCalled();
  });
});
