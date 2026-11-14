import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { Section } from "../api/generated";
import { packSection, type SectionPack } from "../lib/dossierPack";
import { loadDossier } from "../test/fixtures";
import { Record } from "./Record";
import { sectionNoteRows } from "./sectionNoteRows";

const dossier = loadDossier();
const baseSection = dossier.sections[1]!;
const chunk = dossier.chunks[0]!;
const section = (chunks: number): Section => ({
  ...baseSection,
  chunk_ids: Array.from({ length: chunks }, (_, i) => `c${i}`),
});
const pack = (included: number, range: [number, number] | null): SectionPack => ({
  ...packSection(dossier, baseSection),
  includedChunks: Array.from({ length: included }, () => chunk),
  relevanceRange: range,
});

describe("sectionNoteRows", () => {
  it("says how many passages the budget kept", () => {
    const rows = sectionNoteRows("ml", section(4), pack(3, null), 0);
    expect(rows).toEqual([{ label: "Passages", value: "3 of 4", size: "normal" }]);
  });

  it("has no passage row for a section with no passages", () => {
    expect(sectionNoteRows("ml", section(0), pack(0, null), 0)).toEqual([]);
  });

  it("shows the range of similarity to the lead for an ML build that kept a passage", () => {
    const rows = sectionNoteRows("ml", section(2), pack(2, [0.3, 0.8]), 1);
    expect(rows.map((r) => r.value)).toEqual(["2 of 2", "0.30 to 0.80"]);
    render(<Record rows={rows} />);
    expect(screen.getByText("Similarity to lead")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: `About similarity to lead: ${baseSection.label}` }),
    ).toBeTruthy();
  });

  it.each([
    [0, "1.00"],
    [1, "0.50"],
    [3, "0.25"],
  ])("shows the position weight of section %i as %s for a structural build", (order, weight) => {
    const rows = sectionNoteRows("structural", section(1), pack(1, [0.3, 0.8]), order);
    expect(rows.map((r) => r.value)).toEqual(["1 of 1", weight]);
    render(<Record rows={rows} />);
    expect(screen.getByText("Position weight")).toBeTruthy();
  });
});
