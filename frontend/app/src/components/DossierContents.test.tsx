import { describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import type { Budget } from "../lib/budget";
import { loadDossier } from "../test/fixtures";
import { sectionRows } from "../lib/dossierSections";
import { renderWithRouter } from "../test/renderWithRouter";
import { DossierContents } from "./DossierContents";

const dossier = loadDossier("dossier_1095706_2000.json");
const rows = sectionRows(dossier);
const folded = rows.filter((row) => row.pack.state === "folded");

function renderContents(
  currentId: string | null,
  leftOutCount = folded.length,
  budget: Budget = 2000,
  initialPath = "/",
) {
  return renderWithRouter(
    <DossierContents
      dossier={dossier}
      rows={rows}
      currentId={currentId}
      budget={budget}
      leftOutCount={leftOutCount}
    />,
    { initialPath },
  );
}

describe("DossierContents", () => {
  it("lists every section as a link to its anchor, numbered", async () => {
    renderContents(null);
    const list = within(await screen.findByRole("navigation", { name: "Contents" }));
    expect(list.getAllByRole("link")).toHaveLength(rows.length);
    expect(list.getAllByRole("link")[2]?.getAttribute("href")).toBe("#s3");
    expect(list.getByText(`3 ${rows[2]!.section.label}`)).toBeTruthy();
  });

  it("marks only the current section, as a location", async () => {
    renderContents("s2");
    const nav = await screen.findByRole("navigation", { name: "Contents" });
    const current = [...nav.querySelectorAll("a[aria-current]")];
    expect(current.map((a) => a.getAttribute("href"))).toEqual(["#s2"]);
    expect(current[0]?.getAttribute("aria-current")).toBe("location");
  });

  it("says what a section holds: its tokens, subsection tokens, no prose, or left out", async () => {
    renderContents(null);
    const nav = await screen.findByRole("navigation", { name: "Contents" });
    const detail = (index: number) =>
      nav.querySelectorAll("a")[index]?.lastElementChild?.textContent;
    const full = rows.findIndex(
      (row) => row.pack.state !== "folded" && row.section.chunk_ids.length > 0,
    );
    expect(detail(full)).toBe(rows[full]!.pack.includedTokens.toLocaleString("en-US"));
    expect(detail(rows.indexOf(folded[0]!))).toBe("left out");
    const depthOf = (i: number) => rows[i]!.section.heading_path?.length ?? 1;
    const parent = rows.findIndex(
      (row, i) =>
        row.section.chunk_ids.length === 0 && i + 1 < rows.length && depthOf(i + 1) > depthOf(i),
    );
    let subsections = 0;
    for (let i = parent + 1; i < rows.length && depthOf(i) > depthOf(parent); i++) {
      subsections += rows[i]!.pack.includedTokens;
    }
    expect(detail(parent)).toBe(subsections.toLocaleString("en-US"));
  });

  it("says a section with no passages and no subsections has no prose", async () => {
    const last = dossier.sections.length - 1;
    const bare = {
      ...dossier,
      sections: dossier.sections.map((s, i) => (i === last ? { ...s, chunk_ids: [] } : s)),
    };
    renderWithRouter(
      <DossierContents
        dossier={bare}
        rows={sectionRows(bare)}
        currentId={null}
        budget={2000}
        leftOutCount={0}
      />,
    );
    const nav = await screen.findByRole("navigation", { name: "Contents" });
    expect([...nav.querySelectorAll("a")].at(-1)?.lastElementChild?.textContent).toBe(
      "no prose passages kept",
    );
  });

  it("notes how many sections the budget left out, and that a larger budget may bring them back", async () => {
    renderContents(null);
    expect(
      await screen.findByText(
        `${folded.length} sections left out at 2k. They may return at a larger budget.`,
      ),
    ).toBeTruthy();
  });

  it.each([
    ["nothing is left out", 0, 2000],
    ["the budget is the largest", folded.length, 32000],
  ] as const)("has no note when %s", async (_name, leftOut, budget) => {
    renderContents(null, leftOut, budget);
    await screen.findByRole("navigation", { name: "Contents" });
    expect(screen.queryByText(/left out at/)).toBeNull();
  });

  it("keeps the current search when an entry is clicked", async () => {
    const { router } = renderContents(null, 0, 8000, "/?budget=8000");
    const nav = await screen.findByRole("navigation", { name: "Contents" });
    fireEvent.click(within(nav).getAllByRole("link")[2]!);
    await waitFor(() => expect(router.state.location.hash).toBe("s3"));
    expect(router.state.location.search).toEqual({ budget: 8000 });
  });
});
