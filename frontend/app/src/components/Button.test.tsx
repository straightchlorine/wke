import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Button } from "./Button";

describe("Button", () => {
  it("is enabled and focusable by default", () => {
    render(<Button>Build</Button>);
    const button = screen.getByRole("button", { name: "Build" });
    expect(button.getAttribute("aria-disabled")).toBeNull();
    expect(button.hasAttribute("disabled")).toBe(false);
  });

  it("is a plain button that does not submit a form", () => {
    render(<Button>Build</Button>);
    expect(screen.getByRole("button").getAttribute("type")).toBe("button");
  });

  it("adds className to its own classes and passes other attributes through", () => {
    render(
      <Button className="w-full" data-testid="b" title="Build it">
        Build
      </Button>,
    );
    const button = screen.getByTestId("b");
    expect(button.className).toContain("w-full");
    expect(button.className).toContain("inline-flex");
    expect(button.title).toBe("Build it");
  });

  it("calls onClick when not waiting", () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Build</Button>);
    fireEvent.click(screen.getByRole("button", { name: "Build" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("while waiting: aria-disabled without the disabled attribute, still focusable, click ignored", () => {
    const onClick = vi.fn();
    render(
      <Button waiting onClick={onClick}>
        Retry in 38 s
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Retry in 38 s" });

    expect(button.getAttribute("aria-disabled")).toBe("true");
    expect(button.hasAttribute("disabled")).toBe(false);
    expect(button.tabIndex).toBe(0);
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();

    button.focus();
    expect(document.activeElement).toBe(button);
  });
});
