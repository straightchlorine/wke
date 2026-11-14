import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { Section } from "../api/generated";
import { sectionRows } from "../lib/dossierSections";
import { loadDossier } from "../test/fixtures";
import { SourceRecord } from "./SourceRecord";

const at32k = loadDossier("dossier_1095706_32000.json");
const at8k = loadDossier();
const at2k = loadDossier("dossier_1095706_2000.json");
const freshness = { state: "fresh", info: undefined } as const;
const noProse: Section[] = at8k.sections
  .slice(0, 2)
  .map((section, i) => ({ ...section, label: ["See also", "References"][i]! }));

function renderRecord(
  dossier = at8k,
  noProseSections: Section[] = [],
  budget: 2000 | 8000 | 32000 = 8000,
) {
  return render(
    <SourceRecord
      dossier={dossier}
      rows={sectionRows(dossier)}
      noProseSections={noProseSections}
      budget={budget}
      freshness={freshness}
    />,
  );
}

describe("SourceRecord", () => {
  it("links the pinned revision, the licence and the article", () => {
    renderRecord();
    const pin = at8k.citations.find((c) => c.role === "seed")!.pin;
    expect(screen.getAllByRole("link", { name: String(pin.rev_id) })[0]?.getAttribute("href")).toBe(
      pin.permalink,
    );
    expect(screen.getAllByRole("link", { name: pin.license })[0]?.getAttribute("href")).toBe(
      "https://creativecommons.org/licenses/by-sa/4.0/",
    );
    expect(screen.getAllByRole("link", { name: at8k.topic.title })[0]?.getAttribute("href")).toBe(
      at8k.links.wikipedia,
    );
  });

  it("counts the sections the page leaves out of the article in the total", () => {
    renderRecord(at8k, noProse);
    expect(screen.getAllByText(String(at8k.sections.length + 2)).length).toBeGreaterThan(0);
  });

  it("has no Left out row when the budget keeps every section and none lacks prose", () => {
    expect(sectionRows(at32k).some((row) => row.pack.state === "folded")).toBe(false);
    renderRecord(at32k, [], 32000);
    expect(screen.queryByRole("button", { name: "About the sections left out" })).toBeNull();
  });

  it("adds a Left out row, with the count of both causes, when sections lack prose", () => {
    const folded = sectionRows(at2k).filter((row) => row.pack.state === "folded").length;
    renderRecord(at2k, noProse, 2000);
    expect(screen.getAllByText(`${folded + 2} sections`).length).toBeGreaterThan(0);
    expect(
      screen.getAllByRole("button", { name: "About the sections left out" }).length,
    ).toBeGreaterThan(0);
  });

  it("counts the sections the budget leaves out too", () => {
    const folded = sectionRows(at2k).filter((row) => row.pack.state === "folded").length;
    renderRecord(at2k, [], 2000);
    expect(screen.getAllByText(`${folded} sections`).length).toBeGreaterThan(0);
  });

  it("puts the dossier id in a title, so a clipped id can be read", () => {
    renderRecord();
    expect(document.querySelector(`[title="${at8k.id}"]`)).not.toBeNull();
  });
});
