import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ThemeToggle } from "./ThemeToggle";

function stubSystemDark(dark: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: dark && query === "(prefers-color-scheme: dark)",
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

function theme(): string | null {
  return document.documentElement.getAttribute("data-theme");
}

describe("ThemeToggle", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it.each([
    ["dark", false, "dark"],
    ["light", true, "light"],
  ])(
    "starts from the stored %s theme over the system preference",
    (stored, systemDark, expected) => {
      localStorage.setItem("wke-theme", stored);
      stubSystemDark(systemDark);
      render(<ThemeToggle />);
      expect(theme()).toBe(expected);
    },
  );

  it.each([
    [true, "dark"],
    [false, "light"],
  ])("follows the system preference when nothing valid is stored (dark: %s)", (dark, expected) => {
    localStorage.setItem("wke-theme", "sepia");
    stubSystemDark(dark);
    render(<ThemeToggle />);
    expect(theme()).toBe(expected);
  });

  it("switches the theme, labels the button with the destination and saves the choice", () => {
    stubSystemDark(false);
    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: "Switch to dark theme" }).textContent).toBe("Dark");
    expect(screen.getByRole("button").hasAttribute("aria-pressed")).toBe(false);

    fireEvent.click(screen.getByRole("button"));
    expect(theme()).toBe("dark");
    expect(localStorage.getItem("wke-theme")).toBe("dark");
    expect(screen.getByRole("button", { name: "Switch to light theme" }).textContent).toBe("Light");
  });

  it("still renders and toggles when storage is blocked", () => {
    stubSystemDark(true);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    render(<ThemeToggle />);
    expect(theme()).toBe("dark");

    fireEvent.click(screen.getByRole("button"));
    expect(theme()).toBe("light");
  });
});
