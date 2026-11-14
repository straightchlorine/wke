import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MachineCells } from "./MachineCells";

const writeText = vi.fn<(text: string) => Promise<void>>();

function lines(): string[] {
  return [...document.querySelectorAll("code")].map((el) => el.textContent ?? "");
}

describe("MachineCells", () => {
  beforeEach(() => {
    writeText.mockReset();
    writeText.mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
  });

  it("points the JSON and Markdown lines at the given dossier", () => {
    render(<MachineCells origin="https://wke.example" pageId={5} budget={2000} onCopy={vi.fn()} />);
    expect(lines()).toEqual([
      "GET https://wke.example/llms.txt",
      "GET https://wke.example/api/v1/dossiers/5?budget=2000",
      "GET https://wke.example/api/v1/dossiers/5.md?budget=2000",
      "https://wke.example/mcp",
    ]);
  });

  it("labels the buttons for what they copy", () => {
    render(<MachineCells origin="https://wke.example" pageId={5} budget={2000} onCopy={vi.fn()} />);
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Copy URL",
      "Copy URL",
      "Copy URL",
      "Copy config",
    ]);
  });

  it("gives each button its own accessible name", () => {
    render(<MachineCells origin="https://wke.example" pageId={5} budget={2000} onCopy={vi.fn()} />);
    expect(screen.getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual([
      "Copy URL: llms.txt",
      "Copy URL: JSON",
      "Copy URL: Markdown",
      "Copy config: MCP",
    ]);
  });

  it("shows URL patterns and disables the two dossier buttons while there is no dossier", () => {
    render(
      <MachineCells origin="https://wke.example" pageId={null} budget={8000} onCopy={vi.fn()} />,
    );
    expect(lines().slice(1, 3)).toEqual([
      "GET /api/v1/dossiers/{page_id}?budget=8000",
      "GET /api/v1/dossiers/{page_id}.md?budget=8000",
    ]);
    const disabled = screen.getAllByRole("button").map((b) => b.getAttribute("aria-disabled"));
    expect(disabled).toEqual([null, "true", "true", null]);
  });

  it.each([
    ["llms.txt", 0, "https://wke.example/llms.txt", "Copied URL"],
    ["JSON", 1, "https://wke.example/api/v1/dossiers/5?budget=8000", "Copied URL"],
    ["Markdown", 2, "https://wke.example/api/v1/dossiers/5.md?budget=8000", "Copied URL"],
    ["MCP", 3, '{"mcpServers":{"wke":{"url":"https://wke.example/mcp"}}}', "Copied MCP config"],
  ])("copies what the %s button stands for", async (_name, button, text, message) => {
    const onCopy = vi.fn();
    render(<MachineCells origin="https://wke.example" pageId={5} budget={8000} onCopy={onCopy} />);
    await act(async () => {
      fireEvent.click(screen.getAllByRole("button")[button]!);
    });
    expect(writeText).toHaveBeenCalledWith(text);
    expect(onCopy).toHaveBeenCalledWith(message);
  });
});
