import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { sectionRows, sectionTotals } from "../lib/dossierSections";
import type { DossierExports } from "../lib/hooks/useDossierExports";
import { loadDossier } from "../test/fixtures";
import { DossierToolbar } from "./DossierToolbar";

const dossier = loadDossier();
const totals = sectionTotals(sectionRows(dossier));

function renderToolbar() {
  const exports: DossierExports = {
    fetchAsContext: vi.fn().mockResolvedValue("# text"),
    copyMessage: "Copied as context",
    downloadMarkdown: vi.fn().mockResolvedValue(undefined),
    downloadJson: vi.fn(),
  };
  const props = { onBudgetChange: vi.fn(), onCopy: vi.fn() };
  render(
    <DossierToolbar
      dossier={dossier}
      budget={8000}
      totals={totals}
      sectionCount={totals.shown + 3}
      exports={exports}
      {...props}
    />,
  );
  return { exports, ...props };
}

describe("DossierToolbar", () => {
  it("shows the token budget with the picked budget checked, and changes it on a pick", () => {
    const { onBudgetChange } = renderToolbar();
    expect(screen.getByRole<HTMLInputElement>("radio", { name: "8k" }).checked).toBe(true);
    fireEvent.click(screen.getByRole("radio", { name: "32k" }));
    expect(onBudgetChange).toHaveBeenCalledWith(32000);
  });

  it("labels the meter with the tokens used and the sections shown of all of them", () => {
    renderToolbar();
    const used = dossier.budget.used_est_tokens.toLocaleString("en-US");
    const label = `${used} of ${dossier.budget.requested.toLocaleString("en-US")} tokens, ${totals.shown} of ${totals.shown + 3} sections`;
    expect(screen.getByRole("meter", { name: label })).toBeTruthy();
  });

  it("hands the downloads to the exports", () => {
    const { exports } = renderToolbar();
    fireEvent.click(screen.getByRole("button", { name: /Download/ }));
    fireEvent.click(screen.getByRole("button", { name: "JSON" }));
    expect(exports.downloadMarkdown).toHaveBeenCalledTimes(1);
    expect(exports.downloadJson).toHaveBeenCalledTimes(1);
  });

  it("opens and closes the MCP tool call of the dossier at the budget", () => {
    renderToolbar();
    const button = screen.getByRole("button", { name: "MCP" });
    expect(button.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(
      screen.getByText(
        `get_dossier({ "title": "${dossier.topic.title}", "budget": 8000, "format": "json" })`,
      ),
    ).toBeTruthy();
    fireEvent.click(button);
    expect(screen.queryByText(/get_dossier/)).toBeNull();
  });

  it("copies the dossier as context with the exports' message", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    const { onCopy } = renderToolbar();
    fireEvent.click(screen.getByRole("button", { name: /Copy as context/ }));
    await vi.waitFor(() => expect(onCopy).toHaveBeenCalledWith("Copied as context"));
    expect(writeText).toHaveBeenCalledWith("# text");
  });
});
