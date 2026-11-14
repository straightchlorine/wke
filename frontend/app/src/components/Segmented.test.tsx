import { describe, expect, it, vi } from "vitest";
import type { ComponentProps } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { Segmented } from "./Segmented";

const OPTIONS = [
  { value: "2000", label: "2k" },
  { value: "8000", label: "8k" },
  { value: "32000", label: "32k" },
];

function renderSegmented(overrides: Partial<ComponentProps<typeof Segmented>> = {}) {
  return render(
    <Segmented
      ariaLabel="Token budget"
      name="budget"
      options={OPTIONS}
      value="8000"
      onChange={() => {}}
      {...overrides}
    />,
  );
}

describe("Segmented", () => {
  it("renders a radiogroup with the selected option checked", () => {
    renderSegmented();

    expect(screen.getByRole("radiogroup", { name: "Token budget" })).toBeTruthy();
    expect(screen.getByRole<HTMLInputElement>("radio", { name: "8k" }).checked).toBe(true);
    expect(screen.getByRole<HTMLInputElement>("radio", { name: "2k" }).checked).toBe(false);
  });

  it("picks options 1/2/3 with the matching number key when shortcuts are enabled", () => {
    const onChange = vi.fn();
    renderSegmented({ onChange, numberShortcuts: true });

    fireEvent.keyDown(document, { key: "3" });
    expect(onChange).toHaveBeenCalledWith("32000");

    fireEvent.keyDown(document, { key: "1" });
    expect(onChange).toHaveBeenCalledWith("2000");
  });

  it("ignores number keys without the shortcuts prop", () => {
    const onChange = vi.fn();
    renderSegmented({ onChange });

    fireEvent.keyDown(document, { key: "1" });
    expect(onChange).not.toHaveBeenCalled();
  });

  it.each([
    ["text input", () => <input type="text" aria-label="Field" />],
    ["textarea", () => <textarea aria-label="Field" />],
    [
      "select",
      () => (
        <select aria-label="Field">
          <option>a</option>
        </select>
      ),
    ],
    [
      "editable element",
      () => <div contentEditable suppressContentEditableWarning aria-label="Field" />,
    ],
  ])("ignores number keys typed into a %s", (_name, field) => {
    const onChange = vi.fn();
    render(
      <div>
        {field()}
        <Segmented
          ariaLabel="Token budget"
          name="budget"
          options={OPTIONS}
          value="8000"
          onChange={onChange}
          numberShortcuts
        />
      </div>,
    );

    const target = screen.getByLabelText("Field");
    if (target.getAttribute("contenteditable") != null) {
      // jsdom does not implement isContentEditable.
      Object.defineProperty(target, "isContentEditable", { value: true });
    }
    fireEvent.keyDown(target, { key: "1" });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("still takes number keys while a radio of the group has focus", () => {
    const onChange = vi.fn();
    renderSegmented({ onChange, numberShortcuts: true });

    fireEvent.keyDown(screen.getByRole("radio", { name: "8k" }), { key: "3" });
    expect(onChange).toHaveBeenCalledWith("32000");
  });

  it.each([{ ctrlKey: true }, { metaKey: true }, { altKey: true }])(
    "ignores number keys held with %o",
    (modifier) => {
      const onChange = vi.fn();
      renderSegmented({ onChange, numberShortcuts: true });

      fireEvent.keyDown(document, { key: "1", ...modifier });
      expect(onChange).not.toHaveBeenCalled();
    },
  );

  it("ignores keys that name no option", () => {
    const onChange = vi.fn();
    renderSegmented({ onChange, numberShortcuts: true, options: OPTIONS.slice(0, 2) });

    fireEvent.keyDown(document, { key: "3" });
    fireEvent.keyDown(document, { key: "4" });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("moves focus to the radio a shortcut picked", () => {
    renderSegmented({ numberShortcuts: true });

    fireEvent.keyDown(document, { key: "3" });
    expect(document.activeElement).toBe(screen.getByRole("radio", { name: "32k" }));
  });

  it("answers the keys only when the group is visible", () => {
    const onChange = vi.fn();
    renderSegmented({ onChange, numberShortcuts: true });
    const group = screen.getByRole("radiogroup");
    Object.defineProperty(group, "checkVisibility", { value: () => false });

    fireEvent.keyDown(document, { key: "1" });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("reports a chosen radio and shares its name across the options", () => {
    const onChange = vi.fn();
    renderSegmented({ onChange });

    fireEvent.click(screen.getByRole("radio", { name: "2k" }));
    expect(onChange).toHaveBeenCalledWith("2000");
    for (const radio of screen.getAllByRole("radio")) {
      expect(radio.getAttribute("name")).toBe("budget");
    }
  });
});
