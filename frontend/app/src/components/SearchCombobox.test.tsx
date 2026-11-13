import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

vi.mock("../lib/hooks/useTopicSuggestions", () => ({
  useTopicSuggestions: () => ({
    term: "tur",
    suggestions: [{ page_id: 1, title: "Alan Turing", dossier_state: "none" }],
  }),
}));

const { SearchCombobox } = await import("./SearchCombobox");

describe("SearchCombobox", () => {
  it("leaves Enter to the input method while a composition is open", () => {
    const onPick = vi.fn();
    render(<SearchCombobox value="tur" onChange={() => {}} onPick={onPick} ariaLabel="Search" />);
    const input = screen.getByRole("combobox");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter", isComposing: true });
    expect(onPick).not.toHaveBeenCalled();
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onPick).toHaveBeenCalledWith("Alan Turing");
  });
});
