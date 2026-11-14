import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { citationNotes } from "../lib/dossierPack";
import { sectionRows, type SectionRow } from "../lib/dossierSections";
import { formatNumber } from "../lib/format";
import { loadDossier } from "../test/fixtures";
import { DossierSection, type DossierSectionProps } from "./DossierSection";

function view(name: string) {
  const dossier = loadDossier(name);
  return { dossier, rows: sectionRows(dossier), notes: citationNotes(dossier) };
}
const at2k = view("dossier_1095706_2000.json");
const at8k = view("dossier_1095706_8000.json");
const full32k = loadDossier("dossier_1095706_32000.json");

const first = ({ rows }: typeof at2k, state: "full" | "cut" | "folded") =>
  rows.find(
    (row) => row.pack.state === state && row.index > 0 && row.section.chunk_ids.length > 0,
  )!;

function renderSection(
  data: typeof at2k,
  row: SectionRow,
  props: Partial<DossierSectionProps> = {},
) {
  const handlers = { onShowAtBudget: vi.fn(), onReadHere: vi.fn() };
  const { container } = render(
    <DossierSection
      dossier={data.dossier}
      row={row}
      notes={data.notes}
      budget={data === at2k ? 2000 : 8000}
      tokenOffset={0}
      jobId={undefined}
      foldedText={undefined}
      {...handlers}
      {...props}
    />,
  );
  return { container, ...handlers };
}

describe("DossierSection", () => {
  it("is the anchor of its section, headed by its number and label", () => {
    const row = first(at8k, "full");
    const { container } = renderSection(at8k, row);
    expect(container.querySelector("section")?.id).toBe(row.id);
    const heading = container.querySelector("[data-section-heading]");
    expect(heading?.textContent).toBe(`${row.index + 1} ${row.section.label}`);
    expect(heading?.tagName).toBe(
      `H${Math.min(Math.max(1, row.section.heading_path?.length ?? 1), 5) + 1}`,
    );
  });

  it("says how many passages and tokens the budget kept", () => {
    const row = first(at8k, "full");
    renderSection(at8k, row);
    expect(
      screen.getByText(
        new RegExp(
          `Wikipedia section: ${row.section.label}, .*${formatNumber(row.pack.includedTokens)} tokens, ${row.pack.includedChunks.length} of ${row.section.chunk_ids.length} passages`,
        ),
      ),
    ).toBeTruthy();
  });

  it("renders the kept passages as the source text", () => {
    const row = first(at8k, "full");
    const { container } = renderSection(at8k, row);
    expect(container.querySelectorAll('[data-role="source-text"] p')).toHaveLength(
      row.pack.includedChunks.length,
    );
  });

  it("offers a cut section at the next budget", () => {
    const { onShowAtBudget } = renderSection(at2k, first(at2k, "cut"));
    fireEvent.click(screen.getByRole("button", { name: /^Show at 8k/ }));
    expect(onShowAtBudget).toHaveBeenCalledWith(8000);
  });

  it("replaces a left-out section's text with a row that offers it at the next budget or in place", () => {
    const { container, onShowAtBudget, onReadHere } = renderSection(at2k, first(at2k, "folded"));
    expect(container.querySelector('[data-role="source-text"]')).toBeNull();
    expect(screen.getByText(/not shown\. Left out entirely at this budget\./)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /^Show at 8k/ }));
    expect(onShowAtBudget).toHaveBeenCalledWith(8000);
    fireEvent.click(screen.getByRole("button", { name: /^Read here without changing the export/ }));
    expect(onReadHere).toHaveBeenCalledTimes(1);
  });

  it("says a left-out section does not fit when the budget is the largest, with no button to show it", () => {
    renderSection(at2k, first(at2k, "folded"), { budget: 32000 });
    expect(screen.getByText(/Does not fit even at 32k\./)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Show at/ })).toBeNull();
  });

  it("links a model summary to the passages the budget kept, numbered by their position among them", () => {
    const base = at2k.rows.find(
      (row) => row.pack.state === "cut" && row.pack.includedChunks.length > 1,
    )!;
    const kept = base.pack.includedChunks;
    const last = kept[kept.length - 1]!;
    const section: SectionRow["section"] = {
      ...base.section,
      summary_state: "done",
      summary: {
        kind: "machine_summary",
        text: "A summary.",
        model: "m",
        model_revision: "r",
        params: {},
        input_chunk_ids: [last.id, "not-included"],
        generated_at: "2026-01-01T00:00:00Z",
      },
    };
    const { container } = renderSection(at2k, { ...base, section });
    const links = container.querySelectorAll("[data-model-panel] a");
    expect(links).toHaveLength(1);
    expect(links[0]?.getAttribute("href")).toBe(`#chunk-${last.id}`);
    expect(links[0]?.textContent).toBe(String(kept.length));
    expect(base.section.chunk_ids.indexOf(last.id) + 1).not.toBe(kept.length);
  });

  it("shows a left-out section's passages once they are open", () => {
    const row = first(at2k, "folded");
    const chunk = full32k.chunks.find((c) => c.id === row.section.chunk_ids[0])!;
    const { container } = renderSection(at2k, row, { foldedText: [chunk] });
    expect(screen.getByRole("button", { name: /^Hide/ })).toBeTruthy();
    expect(container.querySelector(`[id="chunk-${chunk.id}"]`)).not.toBeNull();
  });

  it("shows a loading line while a left-out section's passages load", () => {
    renderSection(at2k, first(at2k, "folded"), { foldedText: "loading" });
    expect(screen.getByText("Loading...")).toBeTruthy();
  });

  it("says why a section has no model summary, naming the build job while it is pending", () => {
    const base = first(at8k, "full");
    const section = {
      ...base.section,
      summary_state: "pending" as const,
      label_source: "heading" as const,
    };
    renderSection(at8k, { ...base, section }, { jobId: "job-3" });
    expect(screen.getByText("Summary pending: summarise stage, job job-3.")).toBeTruthy();
  });

  it("says a section with no passages is heading only when subsections follow it", () => {
    const { rows, dossier } = at8k;
    const parent = rows.find(
      (row) =>
        row.section.chunk_ids.length === 0 &&
        (dossier.sections[row.index + 1]?.heading_path?.length ?? 0) >
          (row.section.heading_path?.length ?? 1),
    );
    expect(parent).toBeDefined();
    renderSection(at8k, parent!);
    expect(
      screen.getByText(/heading only, its text is in the subsections that follow/),
    ).toBeTruthy();
  });
});
