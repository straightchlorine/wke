import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ErrorPanel } from "./ErrorPanel";

describe("ErrorPanel", () => {
  it.each([
    ["alert", "alert", true],
    ["muted", "muted", false],
  ] as const)("the %s tone %s role=alert on the text", (tone, _verb, hasRole) => {
    render(<ErrorPanel tone={tone} title="Rate limited" detail="Slow down." />);
    expect(screen.queryByRole("alert") != null).toBe(hasRole);
  });

  it("is an alert by default", () => {
    render(<ErrorPanel title="Rate limited" />);
    expect(screen.getByRole("alert").textContent).toBe("Rate limited");
  });

  it("shows the title, detail, countdown and retry control it is given", () => {
    render(
      <ErrorPanel
        title="Rate limited"
        detail="Slow down."
        countdown="Retry in 38 s"
        retry={<button type="button">Retry</button>}
      />,
    );
    expect(screen.getByText("Rate limited")).toBeTruthy();
    expect(screen.getByText("Slow down.")).toBeTruthy();
    expect(screen.getByText("Retry in 38 s")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });

  it("shows nothing it is not given", () => {
    const { container } = render(<ErrorPanel detail="Only a detail." />);
    expect(container.querySelectorAll("p")).toHaveLength(1);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("shows the request id as a reference under the detail", () => {
    render(<ErrorPanel title="Upstream down" detail="Try again later." requestId="req-123" />);
    expect(screen.getByText("Request ID:").textContent).toBe("Request ID: req-123");
    expect(screen.getByText("req-123").tagName).toBe("CODE");
  });

  it("shows no reference line without a request id", () => {
    render(<ErrorPanel title="Upstream down" detail="Try again later." />);
    expect(screen.queryByText(/Request ID:/)).toBeNull();
  });
});
