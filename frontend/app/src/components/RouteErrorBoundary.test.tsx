import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { RouteErrorBoundary } from "./RouteErrorBoundary";

function renderBoundary(error: Error, reset = vi.fn()) {
  render(<RouteErrorBoundary error={error} reset={reset} />);
  return reset;
}

describe("RouteErrorBoundary", () => {
  it("shows a thrown Error's message as the detail", () => {
    renderBoundary(new Error("render blew up"));

    expect(screen.getByRole("alert").textContent).toBe("render blew up");
    expect(screen.getAllByText("Something went wrong")).toHaveLength(1);
  });

  it("shows the string form of a thrown non-Error value", () => {
    const notAnError = { name: "", message: "", toString: () => "plain string" };
    renderBoundary(notAnError);

    expect(screen.getByRole("alert").textContent).toBe("plain string");
  });

  it("calls reset once when Retry is clicked", () => {
    const reset = renderBoundary(new Error("boom"));

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(reset).toHaveBeenCalledTimes(1);
  });
});
