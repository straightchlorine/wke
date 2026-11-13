import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { loadDossier } from "../test/fixtures";
import { DossierDataRecords } from "./DossierDataRecords";

const dossier = loadDossier();

describe("DossierDataRecords", () => {
  const onCopy = vi.fn();
  beforeEach(() => {
    onCopy.mockReset();
    render(<DossierDataRecords dossier={dossier} budget={8000} onCopy={onCopy} />);
  });

  it("shows each address on its own line under its label", () => {
    expect(screen.getByText(`GET ${dossier.links.self}`)).toBeTruthy();
    expect(screen.getByText(`GET ${dossier.links.markdown}`)).toBeTruthy();
    const origin = new URL(dossier.links.self).origin;
    expect(screen.getByText(`GET ${origin}/llms.txt`)).toBeTruthy();
    expect(
      screen.getByText(
        `get_dossier({ "title": "${dossier.topic.title}", "budget": 8000, "format": "json" })`,
      ),
    ).toBeTruthy();
  });

  it.each([
    ["Copy JSON URL", "Copy URL", dossier.links.self, "Copied JSON URL"],
    ["Copy Markdown URL", "Copy URL", dossier.links.markdown, "Copied Markdown URL"],
    [
      "Copy llms.txt URL",
      "Copy URL",
      `${new URL(dossier.links.self).origin}/llms.txt`,
      "Copied llms.txt URL",
    ],
    [
      "Copy MCP tool call",
      "Copy",
      `get_dossier({ "title": "${dossier.topic.title}", "budget": 8000, "format": "json" })`,
      "Copied MCP tool call",
    ],
  ])("%s reads %s, copies the address and reports it", async (name, text, copied, message) => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    const button = screen.getByRole("button", { name });
    expect(button.textContent).toBe(text);
    fireEvent.click(button);
    await vi.waitFor(() => expect(onCopy).toHaveBeenCalledWith(message));
    expect(writeText).toHaveBeenCalledWith(copied);
  });

  it("says Partial, and that only the first 400 passages were parsed, for a truncated partial build", () => {
    const partial = {
      ...dossier,
      build: { ...dossier.build, state: "partial", truncated: true },
    } as const;
    const { container } = render(
      <DossierDataRecords dossier={partial} budget={8000} onCopy={onCopy} />,
    );
    const view = within(container);
    expect(view.getByText("Partial")).toBeTruthy();
    expect(view.getByText("first 400 passages only")).toBeTruthy();
  });

  it("describes how the dossier was built", () => {
    expect(screen.getByText("Analysis")).toBeTruthy();
    expect(
      screen.getByText(dossier.build.analysis === "ml" ? "k-means on MiniLM" : "headings only"),
    ).toBeTruthy();
  });
});
